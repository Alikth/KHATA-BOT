import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import get_settings
from bot.database.session import make_engine, make_session_factory
from sqlalchemy import text
from bot import handlers
from bot.game.engine import weekly_settlement, advance_world_clock

async def main():
    cfg = get_settings()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.bot_token:
        raise RuntimeError("BOT_TOKEN is missing in .env")
    engine = make_engine()
    async with engine.connect() as conn:
        try:
            version = await conn.scalar(text("SELECT MAX(version) FROM schema_version"))
        except Exception as exc:
            raise RuntimeError("Database migrations are missing. Apply migrations 0001, 0002 and 0003 before starting the bot.") from exc
        if version is None or int(version) < 3:
            raise RuntimeError(f"Database schema is outdated (version={version}). Apply migrations 0001, 0002 and 0003 before starting the bot.")
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        from bot.database.models import GameState
        async with session.begin():
            state = await session.get(GameState, "world")
            if state is None:
                from datetime import datetime, timezone
                now=datetime.now(timezone.utc).isoformat()
                session.add(GameState(key="world", value={"paused": cfg.world_start_paused,"world_time":now,"last_real_tick":now}))
            else:
                # Deliberately discard offline wall-clock time: the world pauses while the host is off.
                await advance_world_clock(session, reset_real_tick=True)
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(handlers.router)
    dp["session_factory"] = session_factory
    async def war_arrival_worker():
        from sqlalchemy import select
        from bot.game.warfare import arrive_expeditions
        from bot.database.models import Castle, GroupRegistration
        while True:
            try:
                notices=[]
                async with session_factory() as session, session.begin():
                    rows=await arrive_expeditions(session)
                    for row in rows:
                        origin=await session.get(Castle,row.origin_castle_id)
                        target=await session.get(Castle,row.target_castle_id)
                        groups=(await session.scalars(select(GroupRegistration).where(GroupRegistration.castle_id.in_([row.origin_castle_id,row.target_castle_id]),GroupRegistration.enabled.is_(True)))).all()
                        text=f"⚔️ لشکرکشی #{row.id} به مقصد رسید\n{origin.name} → {target.name}\nمهاجم باید دستور بعدی را ثبت کند."
                        notices.extend((g.telegram_chat_id,text) for g in groups)
                for chat_id,notice in notices:
                    try: await bot.send_message(chat_id,notice)
                    except Exception: logging.exception("Could not publish war arrival to chat %s",chat_id)
            except Exception:
                logging.exception("War arrival worker failed")
            await asyncio.sleep(15)

    async def weekly_worker():
        while True:
            try:
                async with session_factory() as session, session.begin():
                    result = await weekly_settlement(session)
                    if result.get("processed"):
                        logging.info("Weekly settlement processed %s castles (%s)", result["processed"], result.get("week"))
            except Exception:
                logging.exception("Weekly settlement failed")
            await asyncio.sleep(1800)

    scheduler_task = asyncio.create_task(weekly_worker())
    war_task = asyncio.create_task(war_arrival_worker())
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, session_factory=session_factory)
    finally:
        scheduler_task.cancel(); war_task.cancel()
        for task in (scheduler_task,war_task):
            try: await task
            except asyncio.CancelledError: pass
        await bot.session.close()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
