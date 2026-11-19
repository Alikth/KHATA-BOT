from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Lord, ResourceBalance, TradeOffer, AdminAuditLog, GameState, Castle, GroupRegistration
from bot.game.engine import initialize_castle, STARTING_RESOURCES, CATALOG

# Resource names follow the source website's game-rules.js vocabulary.
RESOURCE_NAMES = {
    "peasants": "رعیت", "coins": "سکه", "wood": "چوب", "stone": "سنگ",
    "iron": "آهن", "meat": "گوشت", "fish": "ماهی", "grain": "غلات",
    "horses": "اسب", "dragon_glass": "شیشه اژدها", "wildfire": "وایلدفایر",
    "tar": "قیر", "grapes": "انگور",
}

async def get_lord(session: AsyncSession, telegram_id: int):
    return await session.scalar(select(Lord).where(Lord.telegram_user_id == telegram_id, Lord.status == "active"))

async def get_group(session: AsyncSession, chat_id: int):
    return await session.scalar(select(GroupRegistration).where(GroupRegistration.telegram_chat_id == chat_id, GroupRegistration.enabled.is_(True)))

def validate_castle_selection(castle_name: str, region: str, house: str) -> None:
    """Require an exact castle/region/house tuple from the canonical game catalog."""
    for region_entry in CATALOG.get("houses", []):
        if region_entry.get("region") != region:
            continue
        for castle_entry in region_entry.get("castles", []):
            if castle_entry.get("castle") == castle_name and castle_entry.get("house") == house:
                return
    raise ValueError("نام قلعه، منطقه یا خاندان با کاتالوگ رسمی بازی مطابقت ندارد.")


async def create_castle_group(session: AsyncSession, chat_id: int, title: str, castle_name: str, region: str, house: str, owner_id: int):
    validate_castle_selection(castle_name, region, house)
    if await get_group(session, chat_id):
        raise ValueError("این گروه قبلاً به یک قلعه متصل شده است.")
    castle = await session.scalar(select(Castle).where(Castle.name == castle_name))
    if castle:
        raise ValueError("این قلعه قبلاً به گروه دیگری اختصاص داده شده است.")
    castle = Castle(name=castle_name, region=region, house=house)
    session.add(castle)
    await session.flush()
    group = GroupRegistration(telegram_chat_id=chat_id, title=title[:255], chat_type="supergroup", castle_id=castle.id, registered_by_telegram_id=owner_id)
    session.add(group)
    await session.flush()
    return castle, group

async def create_lord(session: AsyncSession, telegram_id: int, display_name: str, username: str | None, creator_id: int, castle_id: int):
    from bot.game.controls import get_controls
    if not (await get_controls(session))["castle_selection_open"]:
        raise ValueError("انتخاب یا تخصیص قلعه در حال حاضر توسط مدیریت قفل شده است.")
    if await get_lord(session, telegram_id):
        raise ValueError("این حساب تلگرام قبلاً لرد دارد.")
    existing = await session.scalar(select(Lord).where(Lord.castle_id == castle_id, Lord.status == "active"))
    if existing:
        raise ValueError("این قلعه از قبل لرد فعال دارد.")
    lord = Lord(telegram_user_id=telegram_id, display_name=display_name[:120], username=username, created_by_telegram_id=creator_id, castle_id=castle_id)
    session.add(lord)
    await session.flush()
    # Starting balances mirror migrations/0002_castle_economy.sql from the uploaded site.
    for code, amount in STARTING_RESOURCES.items():
        session.add(ResourceBalance(lord_id=lord.id, resource_code=code, amount=amount))
    castle = await session.get(Castle, castle_id)
    await initialize_castle(session, castle)
    return lord

async def get_balances(session: AsyncSession, lord_id: int):
    rows = (await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id == lord_id).order_by(ResourceBalance.resource_code))).all()
    return {row.resource_code: row.amount for row in rows}

async def create_trade(session: AsyncSession, sender: Lord, recipient_id: int, offered_resource: str, offered_amount: int, requested_resource: str, requested_amount: int):
    from bot.game.engine import ensure_castle_not_under_siege
    from bot.game.controls import get_controls
    if offered_resource not in RESOURCE_NAMES or requested_resource not in RESOURCE_NAMES:
        raise ValueError("منبع نامعتبر است.")
    if offered_amount <= 0 or requested_amount <= 0:
        raise ValueError("مقدار باید مثبت باشد.")
    recipient = await get_lord(session, recipient_id)
    if not recipient or recipient.id == sender.id:
        raise ValueError("بازیکن مقصد معتبر نیست.")
    await ensure_castle_not_under_siege(session, sender.castle_id)
    await ensure_castle_not_under_siege(session, recipient.castle_id)
    if not (await get_controls(session))["trades_open"]:
        raise ValueError("ثبت پیشنهاد تجارت توسط مدیریت قفل شده است.")
    balances = (await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id.in_([sender.id, recipient.id])).order_by(ResourceBalance.lord_id, ResourceBalance.resource_code).with_for_update())).all()
    lookup = {(r.lord_id, r.resource_code): r.amount for r in balances}
    if lookup.get((sender.id, offered_resource), 0) < offered_amount:
        raise ValueError("منابع کافی برای پیشنهاد معامله نداری.")
    if lookup.get((recipient.id, requested_resource), 0) < requested_amount:
        raise ValueError("قلعه مقصد موجودی کافی برای پرداخت منبع درخواستی ندارد.")
    offer = TradeOffer(sender_lord_id=sender.id, recipient_lord_id=recipient.id, offered_resource=offered_resource, offered_amount=offered_amount, requested_resource=requested_resource, requested_amount=requested_amount, status="pending")
    session.add(offer)
    await session.flush()
    return offer

async def create_trade_bundle(session: AsyncSession, sender: Lord, recipient_id: int, offered: dict, requested: dict):
    from bot.game.engine import ensure_castle_not_under_siege
    from bot.game.controls import get_controls
    recipient=await get_lord(session,recipient_id)
    if not recipient or recipient.id==sender.id: raise ValueError("بازیکن مقصد معتبر نیست.")
    await ensure_castle_not_under_siege(session, sender.castle_id)
    await ensure_castle_not_under_siege(session, recipient.castle_id)
    if not (await get_controls(session))["trades_open"]:
        raise ValueError("ثبت پیشنهاد تجارت توسط مدیریت قفل شده است.")
    if not offered or not requested: raise ValueError("هر دو طرف معامله باید دارایی داشته باشند.")
    if len(offered)>20 or len(requested)>20: raise ValueError("حداکثر ۲۰ نوع دارایی در هر سمت مجاز است.")
    ids=sorted([sender.id,recipient.id])
    rows=(await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id.in_(ids)).order_by(ResourceBalance.lord_id,ResourceBalance.resource_code).with_for_update())).all()
    balance={(r.lord_id,r.resource_code):r.amount for r in rows}
    for code,raw in offered.items():
        amount=int(raw)
        if code not in RESOURCE_NAMES or code=="peasants" or amount<=0 or balance.get((sender.id,code),0)<amount: raise ValueError(f"دارایی پیشنهادی معتبر یا کافی نیست: {code}")
    for code,raw in requested.items():
        amount=int(raw)
        if code not in RESOURCE_NAMES or code=="peasants" or amount<=0 or balance.get((recipient.id,code),0)<amount: raise ValueError(f"موجودی قلعه مقصد برای پرداخت {code} کافی نیست.")
    first=next(iter(offered.items())); second=next(iter(requested.items()))
    offer=TradeOffer(sender_lord_id=sender.id,recipient_lord_id=recipient.id,
        offered_resource=first[0],offered_amount=int(first[1]),requested_resource=second[0],requested_amount=int(second[1]),
        offered_assets={k:int(v) for k,v in offered.items()},requested_assets={k:int(v) for k,v in requested.items()},status="pending")
    session.add(offer);await session.flush();return offer

async def cancel_trade(session: AsyncSession, offer_id: int, sender_telegram_id: int):
    """Allow only the offer's sender to cancel a still-pending trade."""
    offer = await session.scalar(
        select(TradeOffer).where(TradeOffer.id == offer_id).with_for_update()
    )
    if not offer or offer.status != "pending":
        raise ValueError("این پیشنهاد دیگر فعال نیست.")
    sender = await get_lord(session, sender_telegram_id)
    if not sender or sender.id != offer.sender_lord_id:
        raise ValueError("فقط فرستنده پیشنهاد می‌تواند آن را لغو کند.")
    offer.status = "cancelled"
    return offer


async def resolve_trade(session: AsyncSession, offer_id: int, recipient_telegram_id: int, accept: bool):
    offer = await session.scalar(select(TradeOffer).where(TradeOffer.id == offer_id).with_for_update())
    if not offer or offer.status != "pending":
        raise ValueError("این پیشنهاد دیگر فعال نیست.")
    recipient = await get_lord(session, recipient_telegram_id)
    if not recipient or recipient.id != offer.recipient_lord_id:
        raise ValueError("این پیشنهاد متعلق به تو نیست.")
    if not accept:
        offer.status = "rejected"
        return offer
    from bot.game.engine import ensure_castle_not_under_siege
    sender = await session.get(Lord, offer.sender_lord_id)
    if not sender:
        raise ValueError("فرستنده پیشنهاد دیگر لرد فعالی ندارد.")
    await ensure_castle_not_under_siege(session, sender.castle_id)
    await ensure_castle_not_under_siege(session, recipient.castle_id)
    if offer.offered_assets is not None or offer.requested_assets is not None:
        offered = offer.offered_assets or {}
        requested = offer.requested_assets or {}
        if not offered or not requested:
            raise ValueError("سبد هر دو طرف معامله باید حداقل یک دارایی داشته باشد.")
        ids = sorted([offer.sender_lord_id, offer.recipient_lord_id])
        rows = (await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id.in_(ids)).order_by(ResourceBalance.lord_id, ResourceBalance.resource_code).with_for_update())).all()
        lookup = {(r.lord_id, r.resource_code): r for r in rows}
        for code, amount in offered.items():
            amount=int(amount); row=lookup.get((offer.sender_lord_id,code))
            if amount<=0 or not row or row.amount<amount: raise ValueError(f"دارایی پیشنهادی فرستنده کافی نیست: {code}")
        for code, amount in requested.items():
            amount=int(amount); row=lookup.get((offer.recipient_lord_id,code))
            if amount<=0 or not row or row.amount<amount: raise ValueError(f"دارایی درخواستی گیرنده کافی نیست: {code}")
        for code,amount in offered.items():
            lookup[(offer.sender_lord_id,code)].amount-=int(amount)
            lookup[(offer.recipient_lord_id,code)].amount+=int(amount)
        for code,amount in requested.items():
            lookup[(offer.recipient_lord_id,code)].amount-=int(amount)
            lookup[(offer.sender_lord_id,code)].amount+=int(amount)
        offer.status="completed"
        return offer
    ids = sorted([offer.sender_lord_id, offer.recipient_lord_id])
    rows = (await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id.in_(ids)).order_by(ResourceBalance.lord_id, ResourceBalance.resource_code).with_for_update())).all()
    lookup = {(r.lord_id,r.resource_code):r for r in rows}
    so, rr = lookup.get((offer.sender_lord_id,offer.offered_resource)), lookup.get((offer.recipient_lord_id,offer.requested_resource))
    sr, ro = lookup.get((offer.sender_lord_id,offer.requested_resource)), lookup.get((offer.recipient_lord_id,offer.offered_resource))
    if not all((so,rr,sr,ro)) or so.amount < offer.offered_amount or rr.amount < offer.requested_amount:
        raise ValueError("منابع کافی برای انجام معامله وجود ندارد.")
    so.amount -= offer.offered_amount; ro.amount += offer.offered_amount
    rr.amount -= offer.requested_amount; sr.amount += offer.requested_amount
    offer.status = "completed"
    return offer

async def audit(session: AsyncSession, actor_id: int, action: str, target_id: str | None = None, details: str | None = None):
    session.add(AdminAuditLog(actor_telegram_id=actor_id, action=action, target_id=target_id, details=details))

async def is_world_paused(session: AsyncSession) -> bool:
    row = await session.get(GameState, "world")
    if row is None:
        row = GameState(key="world", value={"paused": True})
        session.add(row); await session.flush()
    return bool(row.value.get("paused", True))

async def set_world_paused(session: AsyncSession, paused: bool):
    from datetime import datetime, timezone
    from bot.game.engine import advance_world_clock
    row = await session.get(GameState, "world")
    if row is None:
        now=datetime.now(timezone.utc)
        row=GameState(key="world",value={"paused":True,"world_time":now.isoformat(),"last_real_tick":now.isoformat()})
        session.add(row); await session.flush()
    else:
        await advance_world_clock(session)
    value=dict(row.value or {})
    now=datetime.now(timezone.utc)
    value["paused"]=paused
    value["last_real_tick"]=now.isoformat()
    row.value=value
