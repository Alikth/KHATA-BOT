import re
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from time import monotonic
from datetime import datetime, timedelta, timezone
from bot.config import get_settings
from bot.database.models import Lord, TradeOffer, Castle, AdminLoginAttempt
from bot.services import (get_lord, get_group, create_lord, create_castle_group, get_balances,
                          create_trade, resolve_trade, audit, is_world_paused, set_world_paused,
                          RESOURCE_NAMES)
from bot.keyboards import trade_decision

router = Router()
_admin_sessions: dict[int, float] = {}

async def require_registered_group(message: Message, session):
    if not message.chat or message.chat.type not in ("group", "supergroup"):
        await message.answer("دستورات بازی فقط داخل گروه اختصاصی قلعه اجرا می‌شوند.")
        return None
    group = await get_group(session, message.chat.id)
    if not group:
        await message.answer("این گروه هنوز به قلعه‌ای متصل نشده است. مالک اصلی باید آن را ثبت کند.")
        return None
    return group

@router.message(CommandStart())
async def start(message: Message):
    await message.answer("ربات مستقل KHATA-GAMES فعال است. دستورات بازی فقط در گروه قلعه ثبت‌شده اجرا می‌شوند. برای راهنما در گروه قلعه /help را بزنید.")

@router.message(Command("help"))
async def help_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group = await require_registered_group(message, session)
    if not group: return
    await message.answer(
        "دستورات گروه قلعه:\n/profile — وضعیت لرد و منابع\n"
        "/trade <telegram_id> <resource> <amount> <resource> <amount> — پیشنهاد تجارت\n"
        "/offers — پیشنهادهای دریافتی\n"
        "/economy — اقتصاد و بدهی غذا\n/buildings — ساختمان‌ها و کمپ‌ها\n/upgrade — ارتقای تولید یا کمپ\n/army — ارتش، ادوات و ناوگان\n/workshop — کارگاه\n/equipment — ساخت ادوات\n/port — ارتقای اسکله\n"
        "منابع: " + ", ".join(RESOURCE_NAMES.keys()) +
        "\nانتخاب لرد فقط با Reply و دستور set lord توسط مالک اصلی انجام می‌شود."
    )

@router.message(F.text.regexp(r"(?i)^set lord$"))
async def set_lord_reply(message: Message, session_factory):
    cfg = get_settings()
    if not message.from_user or message.from_user.id != cfg.bot_owner_id:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("برای انتخاب لرد، ابتدا روی پیام بازیکن Reply بزن و سپس set lord را ارسال کن.")
        return
    async with session_factory() as session, session.begin():
        group = await get_group(session, message.chat.id)
        if not group:
            await message.answer("این گروه هنوز به قلعه متصل نشده است."); return
        target = message.reply_to_message.from_user
        try:
            lord = await create_lord(session, target.id, target.full_name, target.username, cfg.bot_owner_id, group.castle_id)
            await audit(session, cfg.bot_owner_id, "lord_assigned", str(lord.id), f"castle_id={group.castle_id}; chat_id={message.chat.id}")
            castle = await session.get(Castle, group.castle_id)
        except ValueError as exc:
            await message.answer(str(exc)); return
    await message.answer(f"✅ لرد با موفقیت انتخاب شد.\n🏰 قلعه: {castle.name}\n👑 لرد: {target.full_name}")

@router.message(Command("registercastle"))
async def register_castle(message: Message, session_factory):
    cfg = get_settings()
    if not message.from_user or message.from_user.id != cfg.bot_owner_id:
        await message.answer("فقط مالک اصلی می‌تواند گروه قلعه را ثبت کند."); return
    if not message.chat or message.chat.type not in ("group", "supergroup"):
        await message.answer("ثبت قلعه باید داخل گروه تلگرام انجام شود."); return
    # /registercastle Castle Name | Region | House
    raw = (message.text or "").partition(" ")[2]
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 3 or not all(parts):
        await message.answer("فرمت: /registercastle نام قلعه | منطقه | خاندان"); return
    async with session_factory() as session, session.begin():
        try:
            castle, _ = await create_castle_group(session, message.chat.id, message.chat.title or "Castle Group", parts[0], parts[1], parts[2], cfg.bot_owner_id, message.chat.type)
            await audit(session, cfg.bot_owner_id, "castle_group_registered", str(castle.id), f"chat_id={message.chat.id}")
        except ValueError as exc:
            await message.answer(str(exc)); return
    await message.answer(f"✅ گروه به قلعه متصل شد.\n🏰 {castle.name}\n🗺 {castle.region}\n🏠 {castle.house}\nاکنون می‌توانی با Reply به بازیکن و دستور set lord، لرد را تعیین کنی.")

@router.message(Command("profile"))
async def profile(message: Message, session_factory):
    async with session_factory() as session:
        group = await require_registered_group(message, session)
        if not group: return
        lord = await get_lord(session, message.from_user.id)
        castle = await session.get(Castle, group.castle_id)
        if not lord or lord.castle_id != group.castle_id:
            await message.answer("در این گروه لرد نیستی."); return
        balances = await get_balances(session, lord.id)
    lines = [f"🏰 {castle.name}", f"👑 {lord.display_name}", "", "منابع:"]
    lines += [f"{RESOURCE_NAMES.get(k,k)}: {v}" for k,v in balances.items()]
    await message.answer("\n".join(lines))

@router.message(Command("trade"))
async def trade(message: Message, bot, session_factory):
    parts = (message.text or "").split()
    if len(parts) != 6:
        await message.answer("فرمت: /trade <telegram_id> <resource> <amount> <resource> <amount>"); return
    try:
        recipient_id, offered_amount, requested_amount = int(parts[1]), int(parts[3]), int(parts[5])
        offered_resource, requested_resource = parts[2].lower(), parts[4].lower()
        async with session_factory() as session, session.begin():
            group = await require_registered_group(message, session)
            if not group: return
            lord = await get_lord(session, message.from_user.id)
            if not lord or lord.castle_id != group.castle_id:
                raise ValueError("در این گروه لرد نیستی.")
            offer = await create_trade(session, lord, recipient_id, offered_resource, offered_amount, requested_resource, requested_amount)
            recipient = await get_lord(session, recipient_id)
            await audit(session, message.from_user.id, "trade_offer_created", str(offer.id))
        await message.answer(f"پیشنهاد معامله #{offer.id} برای لرد مقصد ثبت شد.")
        dest = get_settings().trade_log_chat_id
        if dest:
            await bot.send_message(dest, f"🤝 پیشنهاد معامله #{offer.id}\nفرستنده: {lord.display_name}\nگیرنده: {recipient.display_name}\nدریافت: {offered_amount} {offered_resource}\nپرداخت: {requested_amount} {requested_resource}\nوضعیت: در انتظار")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))

@router.message(Command("offers"))
async def offers(message: Message, session_factory):
    async with session_factory() as session:
        group = await require_registered_group(message, session)
        if not group: return
        lord = await get_lord(session, message.from_user.id)
        if not lord or lord.castle_id != group.castle_id:
            await message.answer("در این گروه لرد نیستی."); return
        rows = (await session.scalars(select(TradeOffer).where(TradeOffer.recipient_lord_id == lord.id, TradeOffer.status == "pending").order_by(TradeOffer.id.desc()).limit(20))).all()
    if not rows:
        await message.answer("پیشنهاد فعالی نداری."); return
    for offer in rows:
        offered=offer.offered_assets or {offer.offered_resource:offer.offered_amount}
        requested=offer.requested_assets or {offer.requested_resource:offer.requested_amount}
        await message.answer(f"پیشنهاد #{offer.id}: دریافت {offered}، پرداخت {requested}", reply_markup=trade_decision(offer.id))

@router.callback_query(F.data.startswith("trade:"))
async def trade_callback(call: CallbackQuery, bot, session_factory):
    _, action, offer_id = call.data.split(":")
    try:
        async with session_factory() as session, session.begin():
            recipient_before = await get_lord(session, call.from_user.id)
            group = await get_group(session, call.message.chat.id) if call.message and call.message.chat else None
            if not recipient_before or not group or recipient_before.castle_id != group.castle_id:
                raise ValueError("این پیشنهاد فقط در گروه قلعه مقصد قابل پاسخ‌گویی است.")
            offer = await resolve_trade(session, int(offer_id), call.from_user.id, action == "accept")
            await audit(session, call.from_user.id, f"trade_{offer.status}", str(offer.id))
            sender = await session.get(Lord, offer.sender_lord_id)
            recipient = await session.get(Lord, offer.recipient_lord_id)
        await call.message.edit_text(f"پیشنهاد #{offer.id}: {offer.status}")
        if offer.status == "completed" and get_settings().trade_log_chat_id:
            offered=offer.offered_assets or {offer.offered_resource:offer.offered_amount}
            requested=offer.requested_assets or {offer.requested_resource:offer.requested_amount}
            await bot.send_message(get_settings().trade_log_chat_id, f"✅ معامله #{offer.id} تکمیل شد\n{sender.display_name} ↔ {recipient.display_name}\n{offered} در برابر {requested}")
        await call.answer("انجام شد")
    except ValueError as exc:
        await call.answer(str(exc), show_alert=True)

@router.message(Command("admin"))
async def admin_panel(message: Message, session_factory):
    cfg = get_settings()
    if not message.from_user or message.from_user.id != cfg.bot_owner_id or message.chat.id != cfg.admin_chat_id:
        await message.answer("دسترسی مجاز نیست."); return

    code = (message.text or "").partition(" ")[2].strip()
    try: await message.delete()
    except Exception: pass

    now = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        attempt = await session.scalar(
            select(AdminLoginAttempt).where(
                AdminLoginAttempt.telegram_user_id == message.from_user.id
            ).with_for_update()
        )
        if attempt and attempt.locked_until and attempt.locked_until > now:
            remaining = max(1, int((attempt.locked_until - now).total_seconds() // 60) + 1)
            await message.answer(f"ورود موقتاً قفل شده است؛ {remaining} دقیقه دیگر تلاش کن.")
            return

    valid = False
    if code and cfg.admin_password_hash:
        try:
            PasswordHasher().verify(cfg.admin_password_hash, code)
            valid = True
        except Exception:
            valid = False

    async with session_factory() as session, session.begin():
        attempt = await session.scalar(
            select(AdminLoginAttempt).where(
                AdminLoginAttempt.telegram_user_id == message.from_user.id
            ).with_for_update()
        )
        if attempt is None:
            attempt = AdminLoginAttempt(telegram_user_id=message.from_user.id, failures=0)
            session.add(attempt)
            await session.flush()
        if valid:
            attempt.failures = 0
            attempt.locked_until = None
        else:
            attempt.failures = (attempt.failures or 0) + 1
            if attempt.failures >= 5:
                attempt.failures = 0
                attempt.locked_until = now + timedelta(minutes=15)

    if not valid:
        await message.answer("کد دسترسی نامعتبر است یا تنظیم نشده؛ پس از ۵ تلاش ناموفق، ورود ۱۵ دقیقه قفل می‌شود.")
        return

    _admin_sessions[message.from_user.id] = monotonic() + (cfg.admin_session_minutes * 60)
    async with session_factory() as session:
        paused = await is_world_paused(session)
    await message.answer("🔐 پنل مدیریت KHATA-GAMES\n" + f"ساعت جهان: {'متوقف' if paused else 'فعال'}\n\n/pause — توقف جهان\n/resume — ادامه جهان\n/status — وضعیت جهان")


async def admin_action(message: Message, session_factory, paused: bool | None):
    cfg = get_settings()
    if not message.from_user or message.from_user.id != cfg.bot_owner_id or message.chat.id != cfg.admin_chat_id or (_admin_sessions.get(message.from_user.id, 0) < monotonic()):
        return False
    if paused is not None:
        async with session_factory() as session, session.begin():
            await set_world_paused(session, paused)
            await audit(session, message.from_user.id, "world_paused" if paused else "world_resumed")
        await message.answer("ساعت جهان متوقف شد." if paused else "ساعت جهان ادامه یافت.")
    else:
        async with session_factory() as session:
            value = await is_world_paused(session)
        await message.answer(f"وضعیت ساعت جهان: {'متوقف' if value else 'فعال'}")
    return True

@router.message(Command("pause"))
async def pause_world(message: Message, session_factory):
    if not await admin_action(message, session_factory, True): await message.answer("ابتدا از گروه مدیریت و با کد معتبر وارد پنل شو.")

@router.message(Command("resume"))
async def resume_world(message: Message, session_factory):
    if not await admin_action(message, session_factory, False): await message.answer("ابتدا از گروه مدیریت و با کد معتبر وارد پنل شو.")

@router.message(Command("status"))
async def world_status(message: Message, session_factory):
    if not await admin_action(message, session_factory, None): await message.answer("دسترسی مجاز نیست.")

# Website-aligned economy commands. Definitions are loaded from the uploaded site's catalog.
from bot.game.engine import (CATALOG, EQUIPMENT, upgrade as engine_upgrade, recruit as engine_recruit,
    RESOURCE_LABELS, GENERAL_PRODUCTIONS, SPECIAL_PRODUCTIONS, GENERAL_CAMPS, SPECIAL_CAMPS)
from bot.database.models import ProductionLevel, CampLevel, SpecialCampLevel, ArmyUnit, EquipmentItem, FleetShip, CastleEconomyState

@router.message(Command("buildings"))
async def buildings_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group: return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        castle=await session.get(Castle,group.castle_id)
        rows=(await session.scalars(select(ProductionLevel).where(ProductionLevel.castle_id==castle.id).order_by(ProductionLevel.production_key))).all()
        camps=(await session.scalars(select(CampLevel).where(CampLevel.castle_id==castle.id))).all()
        scamps=(await session.scalars(select(SpecialCampLevel).where(SpecialCampLevel.castle_id==castle.id))).all()
    lines=[f"🏰 ساختمان‌ها و کمپ‌های {castle.name}","\nتولید:"]
    for r in rows:
        d=GENERAL_PRODUCTIONS.get(r.production_key) or (SPECIAL_PRODUCTIONS.get(castle.region) if SPECIAL_PRODUCTIONS.get(castle.region,{}).get("key")==r.production_key else None)
        if d: lines.append(f"{d['label']}: سطح {r.level}/{d['max']}")
    lines.append("\nکمپ‌ها:")
    for r in camps:
        d=GENERAL_CAMPS[r.camp_key]; lines.append(f"{d['label']}: سطح {r.level}/{d['max']}")
    for r in scamps:
        d=next(x for x in SPECIAL_CAMPS[castle.region] if x['key']==r.camp_key); lines.append(f"{d['label']}: سطح {r.level}/{d['max']}")
    lines.append("\nارتقا: /upgrade production farm یا /upgrade camp swordsman")
    await message.answer("\n".join(lines))

@router.message(Command("upgrade"))
async def upgrade_cmd(message: Message, session_factory):
    parts=(message.text or "").split()
    if len(parts)!=3 or parts[1] not in ("production","camp","special_camp"):
        await message.answer("فرمت: /upgrade production farm\nیا /upgrade camp swordsman\nیا /upgrade special_camp ranger"); return
    async with session_factory() as session, session.begin():
        group=await get_group(session,message.chat.id)
        if not group: await message.answer("این گروه به قلعه متصل نیست."); return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        try:
            level,definition=await engine_upgrade(session,lord,parts[1],parts[2])
            await audit(session,message.from_user.id,"building_upgraded",str(lord.castle_id),f"{parts[1]}:{parts[2]}:{level}")
        except ValueError as e: await message.answer(str(e)); return
    await message.answer(f"✅ {definition['label']} به سطح {level} ارتقا یافت.\nهزینه: " + "، ".join(f"{RESOURCE_LABELS.get(k,k)} {v}" for k,v in definition.get("cost",{}).items()))

@router.message(Command("army"))
async def army_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group: return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        rows=(await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==group.castle_id).order_by(ArmyUnit.unit_key))).all()
        equipment=(await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id==group.castle_id))).all()
        fleet=(await session.scalars(select(FleetShip).where(FleetShip.castle_id==group.castle_id))).all()
    lines=["⚔️ ارتش قلعه"]+[f"{r.unit_key}: {r.count:,}" for r in rows]+["\nادوات:"]+[f"{r.item_key}: {r.count}" for r in equipment]+["\nناوگان:"]+[f"{r.ship_key}: {r.count}" for r in fleet]
    await message.answer("\n".join(lines))

@router.message(Command("recruit"))
async def recruit_cmd(message: Message, session_factory):
    await message.answer("در نسخه سایتِ آپلودشده، نیروها به‌صورت تولید هفتگی کمپ اضافه می‌شوند و API سربازگیری مستقیم وجود ندارد. برای افزایش نیرو، کمپ مربوطه را با /upgrade camp ارتقا بده.")

@router.message(Command("economy"))
async def economy_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group: return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        balances=await get_balances(session,lord.id)
        state=await session.get(CastleEconomyState,group.castle_id)
    lines=["📊 اقتصاد قلعه"]+[f"{RESOURCE_LABELS.get(k,k)}: {v:,.0f}" for k,v in balances.items()]
    if state and state.food_debt: lines.append(f"⚠️ بدهی غذایی: {state.food_debt:,}")
    await message.answer("\n".join(lines))

from bot.game.engine import upgrade_workshop, build_equipment, upgrade_port

@router.message(Command("workshop"))
async def workshop_cmd(message: Message, session_factory):
    async with session_factory() as session, session.begin():
        group=await get_group(session,message.chat.id)
        if not group: await message.answer("این گروه به قلعه متصل نیست."); return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        state=await session.get(CastleEconomyState,group.castle_id)
        if (message.text or "").strip().lower()=="/workshop upgrade":
            try: level=await upgrade_workshop(session,lord)
            except ValueError as e: await message.answer(str(e)); return
            await message.answer(f"کارگاه به سطح {level} ارتقا یافت."); return
        await message.answer(f"🏗 سطح کارگاه: {state.workshop_level if state else 0}/5\nارتقا: /workshop upgrade\nساخت ادوات: /equipment ladder")

@router.message(Command("equipment"))
async def equipment_cmd(message: Message, session_factory):
    parts=(message.text or "").split()
    if len(parts)!=2:
        await message.answer("فرمت: /equipment ladder\nگزینه‌ها: "+", ".join(EQUIPMENT.keys())); return
    async with session_factory() as session, session.begin():
        group=await get_group(session,message.chat.id)
        if not group: await message.answer("این گروه به قلعه متصل نیست."); return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        try: definition,count=await build_equipment(session,lord,parts[1])
        except ValueError as e: await message.answer(str(e)); return
    await message.answer(f"✅ {definition['label']} ساخته شد. موجودی: {count}")

@router.message(Command("port"))
async def port_cmd(message: Message, session_factory):
    if (message.text or "").strip().lower()!="/port upgrade":
        await message.answer("برای ارتقای اسکله: /port upgrade"); return
    async with session_factory() as session, session.begin():
        group=await get_group(session,message.chat.id)
        if not group: await message.answer("این گروه به قلعه متصل نیست."); return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        try: level=await upgrade_port(session,lord)
        except ValueError as e: await message.answer(str(e)); return
    await message.answer(f"⚓ اسکله به سطح {level}/15 ارتقا یافت.")

# Warfare workflow ported from the uploaded site's war-expedition/scenario/alliance flow.
from datetime import datetime, timezone
from bot.database.models import WarExpedition, MilitaryAlliance, TroopTransferRequest, WarScenario
from bot.game.warfare import (launch_expedition, arrive_expeditions, set_arrival_choice,
    issue_war_command, submit_scenario, review_battle, answer_alliance, answer_transfer, cancel_expedition)

@router.message(Command("march"))
async def march_cmd(message: Message, session_factory, bot):
    """/march target-castle land|sea minutes army:swordsman=100,archer=20;equipment:ladder=2;fleet:transport=1"""
    raw=(message.text or "").partition(" ")[2].strip()
    match=re.match(r"^(.+?)\s+(land|sea)\s+(\d+)\s+(.+)$",raw,re.IGNORECASE)
    if not match:
        await message.answer("فرمت: /march نام کامل قلعه land|sea مدت_دقیقه army:swordsman=100;equipment:ladder=2;fleet:transport=1");return
    target,kind,minutes_s,assets_s=match.groups()
    kind=kind.lower()
    assets={"army":{},"equipment":{},"fleet":{}}
    try:
        for section in assets_s.split(";"):
            if not section.strip(): continue
            group,sep,items=section.partition(":")
            if not sep or group not in assets: raise ValueError("بخش دارایی باید army، equipment یا fleet باشد.")
            for item in items.split(","):
                key,eq,value=item.partition("=")
                if not eq: raise ValueError("هر دارایی باید به شکل key=count باشد.")
                assets[group][key.strip()]=int(value)
        async with session_factory() as session, session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            war=await launch_expedition(session,lord,target,kind,int(minutes_s),assets)
            await audit(session,message.from_user.id,"war_expedition_launched",str(war.id),f"target={target};type={kind}")
            origin=await session.get(Castle,war.origin_castle_id);dest=await session.get(Castle,war.target_castle_id)
        await message.answer(f"⚔️ لشکرکشی #{war.id} ثبت شد\n{origin.name} → {dest.name}\nنوع: {kind}\nزمان رسیدن: {war.arrival_at:%Y-%m-%d %H:%M UTC}")
        if get_settings().war_log_chat_id: await bot.send_message(get_settings().war_log_chat_id,f"⚔️ لشکرکشی #{war.id}\n{origin.name} → {dest.name}\nمهاجم: {lord.display_name}\nنوع: {kind}")
    except (ValueError,TypeError) as exc: await message.answer(str(exc))

@router.message(Command("arrivals"))
async def arrivals_cmd(message: Message, session_factory):
    async with session_factory() as session, session.begin():
        group=await require_registered_group(message,session)
        if not group:return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی.");return
        await arrive_expeditions(session)
        rows=(await session.scalars(select(WarExpedition).where(WarExpedition.attacker_lord_id==lord.id,WarExpedition.status=="arrived").order_by(WarExpedition.id.desc()))).all()
    if not rows: await message.answer("لشکر رسیده‌ای نداری.");return
    await message.answer("لشکرهای رسیده:\n"+"\n".join(f"#{x.id} → قلعه مقصد {x.target_castle_id} | ابتدا /warcommand {x.id} deploy و سپس /arrival {x.id} garrison|alliance|transfer" for x in rows))

@router.message(Command("arrival"))
async def arrival_choice_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=3: await message.answer("فرمت: /arrival شناسه garrison|alliance|transfer (پس از دستور /warcommand شناسه deploy)");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            await arrive_expeditions(session)
            row=await set_arrival_choice(session,int(p[1]),lord,p[2])
        await message.answer(f"انتخاب لشکر #{row.id} ثبت شد: {p[2]}")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("warcommand"))
async def war_command_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=3: await message.answer("فرمت: /warcommand شناسه attack|siege|deploy");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            row=await issue_war_command(session,int(p[1]),lord,p[2])
        await message.answer(f"دستور {p[2]} برای لشکر #{row.id} ثبت شد.")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("scenario"))
async def scenario_cmd(message: Message, session_factory):
    p=(message.text or "").split(maxsplit=2)
    if len(p)<3: await message.answer("فرمت: /scenario شناسه متن سناریو");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            item=await submit_scenario(session,int(p[1]),lord,p[2])
        await message.answer(f"سناریوی نبرد #{item.expedition_id} ثبت شد.")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("alliances"))
async def alliances_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group:return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی.");return
        rows=(await session.scalars(select(MilitaryAlliance).where(MilitaryAlliance.owner_b_lord_id==lord.id,MilitaryAlliance.status=="pending"))).all()
    if not rows: await message.answer("درخواست اتحاد معلقی نداری.");return
    await message.answer("درخواست‌ها:\n"+"\n".join(f"#{x.id}: /alliance {x.id} accept یا /alliance {x.id} reject" for x in rows))

@router.message(Command("alliance"))
async def alliance_response_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=3 or p[2] not in ("accept","reject"): await message.answer("فرمت: /alliance شناسه accept|reject");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            row=await answer_alliance(session,int(p[1]),lord,p[2]=="accept")
        await message.answer(f"درخواست اتحاد #{row.id}: {row.status}")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("transfers"))
async def transfers_cmd(message: Message, session_factory):
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group:return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی.");return
        rows=(await session.scalars(select(TroopTransferRequest).where(TroopTransferRequest.receiver_lord_id==lord.id,TroopTransferRequest.status=="pending"))).all()
    await message.answer("درخواست‌های انتقال:\n"+"\n".join(f"#{x.id}: /transfer {x.id} accept|reject" for x in rows) if rows else "درخواست انتقالی نداری.")

@router.message(Command("transfer"))
async def transfer_response_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=3 or p[2] not in ("accept","reject"): await message.answer("فرمت: /transfer شناسه accept|reject");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            row=await answer_transfer(session,int(p[1]),lord,p[2]=="accept")
        await message.answer(f"درخواست انتقال #{row.id}: {row.status}")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("warresolve"))
async def war_resolve_admin_cmd(message: Message, session_factory):
    cfg=get_settings()
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("این دستور فقط برای مالک اصلی با نشست مدیریتی فعال است.");return
    # /warresolve ID attacker|defender attacker:swordsman=10,archer=2 defender:spearman=5
    p=(message.text or "").split(maxsplit=3)
    if len(p)!=4: await message.answer('فرمت: /warresolve ID attacker|defender و سپس JSON تلفات مهاجم و مدافع');return
    try:
        if p[3].lstrip().startswith("{"):
            payload=json.loads(p[3]); attacker_losses=payload.get("attacker",{}); defender_losses=payload.get("defender",{}).get("army",payload.get("defender",{}))
        else:
            losses={"attacker":{},"defender":{}}
            for section in p[3].split():
                side,sep,items=section.partition(":")
                if not sep or side not in losses: raise ValueError("ساختار تلفات نامعتبر است.")
                for pair in items.split(","):
                    key,eq,n=pair.partition("=")
                    if not eq: raise ValueError("تلفات باید key=count باشد.")
                    losses[side][key]=int(n)
            attacker_losses=losses["attacker"]; defender_losses=losses["defender"]
        async with session_factory() as session,session.begin():
            row=await review_battle(session,int(p[1]),p[2],attacker_losses,defender_losses)
            await audit(session,message.from_user.id,"war_battle_reviewed",str(row.id),str(row.result))
        await message.answer(f"نبرد #{row.id} نهایی شد. نتیجه: {row.outcome}")
    except (ValueError,TypeError) as e: await message.answer(str(e))

import json
from bot.services import create_trade_bundle

@router.message(Command("tradepack"))
async def trade_pack_cmd(message: Message, bot, session_factory):
    # /tradepack TELEGRAM_ID {"offer":{"wood":100,"grain":50},"request":{"iron":20}}
    p=(message.text or "").split(maxsplit=2)
    if len(p)!=3: await message.answer('فرمت: /tradepack TELEGRAM_ID {"offer":{"wood":100},"request":{"iron":20}}');return
    try:
        recipient_id=int(p[1]); payload=json.loads(p[2]); offered=payload.get("offer",{});requested=payload.get("request",{})
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            offer=await create_trade_bundle(session,lord,recipient_id,offered,requested)
            recipient=await get_lord(session,recipient_id)
            await audit(session,message.from_user.id,"trade_bundle_created",str(offer.id))
        await message.answer(f"سبد معامله #{offer.id} برای {recipient.display_name} ثبت شد.")
        if get_settings().trade_log_chat_id:
            await bot.send_message(get_settings().trade_log_chat_id,f"🤝 معامله چنددارایی #{offer.id}\nفرستنده: {lord.display_name}\nگیرنده: {recipient.display_name}\nپیشنهاد: {offered}\nدرخواست: {requested}\nوضعیت: در انتظار")
    except (ValueError,TypeError,json.JSONDecodeError) as e: await message.answer(str(e))

@router.message(Command("adminscenarios"))
async def admin_scenarios_cmd(message: Message, session_factory):
    cfg=get_settings()
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    async with session_factory() as session:
        rows=(await session.scalars(select(WarScenario).where(WarScenario.reviewed.is_(False)).order_by(WarScenario.created_at).limit(30))).all()
    if not rows: await message.answer("سناریوی بررسی‌نشده‌ای وجود ندارد.");return
    for x in rows: await message.answer(f"سناریو #{x.id} | نبرد #{x.expedition_id} | لرد #{x.lord_id}\n{x.scenario_text[:3500]}\nبرای بررسی: /reviewscenario {x.id} متن_نتیجه")

@router.message(Command("reviewscenario"))
async def review_scenario_cmd(message: Message, session_factory):
    cfg=get_settings();p=(message.text or "").split(maxsplit=2)
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    if len(p)<3: await message.answer("فرمت: /reviewscenario شناسه نتیجه بررسی");return
    async with session_factory() as session,session.begin():
        item=await session.scalar(select(WarScenario).where(WarScenario.id==int(p[1])).with_for_update())
        if not item: await message.answer("سناریو پیدا نشد.");return
        item.reviewed=True;item.review_result=p[2];item.reviewed_at=datetime.now(timezone.utc)
        await audit(session,message.from_user.id,"war_scenario_reviewed",str(item.id),p[2][:500])
    await message.answer("نتیجه بررسی سناریو ثبت شد.")

@router.message(Command("cancelmarch"))
async def cancel_march_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=2: await message.answer("فرمت: /cancelmarch شناسه");return
    try:
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id: raise ValueError("در این گروه لرد نیستی.")
            row=await cancel_expedition(session,int(p[1]),lord)
            await audit(session,message.from_user.id,"war_expedition_cancelled",str(row.id))
        await message.answer(f"لشکرکشی #{row.id} لغو شد و دارایی‌ها به قلعه مبدأ برگشتند.")
    except (ValueError,TypeError) as e: await message.answer(str(e))

@router.message(Command("adminwars"))
async def admin_wars_cmd(message: Message, session_factory):
    cfg=get_settings()
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    async with session_factory() as session:
        rows=(await session.scalars(select(WarExpedition).order_by(WarExpedition.id.desc()).limit(30))).all()
        castles={x.id:x.name for x in (await session.scalars(select(Castle))).all()}
    if not rows: await message.answer("لشکرکشی ثبت‌شده‌ای نیست.");return
    for x in rows:
        await message.answer(f"#{x.id} {castles.get(x.origin_castle_id,x.origin_castle_id)} → {castles.get(x.target_castle_id,x.target_castle_id)} | وضعیت: {x.status} | دستور: {x.command or 'ندارد'} | نتیجه: {x.outcome or 'ثبت نشده'}")

@router.message(Command("admincastles"))
async def admin_castles_cmd(message: Message, session_factory):
    cfg=get_settings()
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    async with session_factory() as session:
        rows=(await session.scalars(select(Castle).order_by(Castle.region,Castle.name))).all()
    await message.answer("قلعه‌های ثبت‌شده:\n"+"\n".join(f"#{x.id} {x.name} | {x.region} | {x.house} | {'فعال' if x.active else 'غیرفعال'}" for x in rows) if rows else "قلعه‌ای ثبت نشده است.")

@router.message(Command("garrisons"))
async def garrisons_cmd(message: Message, session_factory):
    from bot.database.models import GarrisonAsset
    async with session_factory() as session:
        group=await require_registered_group(message,session)
        if not group:return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی.");return
        rows=(await session.scalars(select(GarrisonAsset).where(GarrisonAsset.owner_lord_id==lord.id,GarrisonAsset.count>0).order_by(GarrisonAsset.castle_id,GarrisonAsset.asset_kind,GarrisonAsset.asset_key))).all()
        castles={x.id:x.name for x in (await session.scalars(select(Castle))).all()}
    if not rows: await message.answer("پادگان متعلق به تو خالی است.");return
    lines=["🏰 پادگان‌های متعلق به تو:"]
    for x in rows: lines.append(f"قلعه #{x.castle_id} ({castles.get(x.castle_id,'?')}) | {x.asset_kind}/{x.asset_key}: {x.count}")
    lines.append("برای حرکت از پادگان: /marchgarrison شناسه_قلعه_مبدأ نام_مقصد land|sea دقیقه army:swordsman=10")
    await message.answer("\n".join(lines))

@router.message(Command("marchgarrison"))
async def march_garrison_cmd(message: Message, session_factory, bot):
    raw=(message.text or "").partition(" ")[2].strip()
    match=re.match(r"^(\d+)\s+(.+?)\s+(land|sea)\s+(\d+)\s+(.+)$",raw,re.IGNORECASE)
    if not match: await message.answer("فرمت: /marchgarrison sourceCastleId نام کامل مقصد land|sea minutes army:swordsman=10;equipment:ladder=1;fleet:transport=1");return
    try:
        source_s,target,kind,minutes_s,asset_text=match.groups()
        source_id=int(source_s);kind=kind.lower();minutes=int(minutes_s);assets={"army":{},"equipment":{},"fleet":{}}
        for section in asset_text.split(";"):
            if not section.strip():continue
            group,sep,items=section.partition(":")
            if not sep or group not in assets:raise ValueError("بخش دارایی نامعتبر است.")
            for pair in items.split(","):
                key,eq,n=pair.partition("=")
                if not eq:raise ValueError("فرمت دارایی key=count است.")
                assets[group][key.strip()]=int(n)
        async with session_factory() as session,session.begin():
            group=await require_registered_group(message,session)
            if not group:return
            lord=await get_lord(session,message.from_user.id)
            if not lord or lord.castle_id!=group.castle_id:raise ValueError("در این گروه لرد نیستی.")
            from bot.database.models import GarrisonAsset
            owns=await session.scalar(select(GarrisonAsset.id).where(GarrisonAsset.owner_lord_id==lord.id,GarrisonAsset.castle_id==source_id).limit(1))
            if not owns:raise ValueError("در این قلعه پادگان متعلق به تو پیدا نشد.")
            war=await launch_expedition(session,lord,target,kind,minutes,assets,use_garrison=True,source_castle_id=source_id)
            await audit(session,message.from_user.id,"garrison_expedition_launched",str(war.id))
            origin=await session.get(Castle,source_id);dest=await session.get(Castle,war.target_castle_id)
        await message.answer(f"⚔️ لشکرکشی از پادگان #{war.id} ثبت شد: {origin.name} → {dest.name}")
        if get_settings().war_log_chat_id:await bot.send_message(get_settings().war_log_chat_id,f"⚔️ لشکرکشی از پادگان #{war.id}: {origin.name} → {dest.name}")
    except (ValueError,TypeError) as e:await message.answer(str(e))

@router.message(Command("admintrades"))
async def admin_trades_cmd(message: Message, session_factory):
    cfg=get_settings()
    if not message.from_user or message.from_user.id!=cfg.bot_owner_id or message.chat.id!=cfg.admin_chat_id or _admin_sessions.get(message.from_user.id,0)<monotonic():
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    async with session_factory() as session:
        rows=(await session.scalars(select(TradeOffer).order_by(TradeOffer.id.desc()).limit(30))).all()
    if not rows: await message.answer("معامله‌ای ثبت نشده است.");return
    lines=[]
    for x in rows:
        offered=x.offered_assets or {x.offered_resource:x.offered_amount}
        requested=x.requested_assets or {x.requested_resource:x.requested_amount}
        lines.append(f"#{x.id} | لرد {x.sender_lord_id} → {x.recipient_lord_id} | {offered} در برابر {requested} | {x.status}")
    await message.answer("📋 آخرین معاملات:\n"+"\n".join(lines))
