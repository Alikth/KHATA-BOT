from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from decimal import Decimal, InvalidOperation
from html import escape
from bot.config import get_settings
from bot.database.models import Lord, TradeOffer, Castle, ResourceBalance, AdminAuditLog
from bot.services import (get_lord, get_group, create_lord, create_castle_group, get_balances,
                          create_trade, resolve_trade, audit, is_world_paused, set_world_paused,
                          RESOURCE_NAMES)
from bot.keyboards import trade_decision, main_menu, section_back_menu, admin_menu
from bot.integrations.site_api import SiteApiError

router = Router()

def _is_admin_actor(user_id: int | None, chat, cfg) -> bool:
    # Superuser identity is the Telegram numeric user ID, not the current chat.
    # Group registration and castle ownership are checked independently.
    return bool(user_id and cfg.bot_owner_id and user_id == cfg.bot_owner_id)

async def _safe_edit_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise

async def publish_admin_audit(bot, actor_id: int, action: str, target: str = "", details: str = ""):
    """Send a concise audit notification to the configured admin/audit group."""
    cfg = get_settings()
    destination = cfg.admin_audit_chat_id or cfg.admin_chat_id
    if not destination:
        return
    body = (
        "🧾 <b>گزارش عملیات مدیریتی</b>\n"
        f"مدیر: <code>{actor_id}</code>\n"
        f"عملیات: <code>{escape(action)}</code>\n"
        f"هدف: <code>{escape(str(target or '-'))}</code>\n"
        f"جزئیات: {escape(str(details or '-'))}"
    )
    try:
        await bot.send_message(destination, body)
    except Exception:
        import logging
        logging.exception("Could not publish admin audit event")

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
    cfg = get_settings()
    if _is_admin_actor(message.from_user.id if message.from_user else None, message.chat, cfg):
        await message.answer(
            "🔐 <b>مرکز فرماندهی KHATA-GAMES</b>\n"
            "مالک اصلی شناسایی شد. مدیریت جهان از همین گروه و همین پنل انجام می‌شود.",
            reply_markup=admin_menu(),
        )
        return
    await message.answer(
        "به جهان KHATA-GAMES خوش آمدی. از منوی فارسی زیر بخش موردنظر را انتخاب کن. "
        "دستورات بازی در گروه اختصاصی قلعه اجرا می‌شوند.",
        reply_markup=main_menu(),
    )

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


@router.callback_query(F.data.startswith("menu:"))
async def persian_menu_callback(call: CallbackQuery, session_factory):
    """Render real player data from inline navigation; no command text is emitted."""
    action = call.data.split(":", 1)[1]
    await call.answer()
    if not call.from_user or not call.message:
        return

    cfg = get_settings()
    if action == "back":
        await _safe_edit_text(call.message, "به جهان KHATA-GAMES خوش آمدی. بخش موردنظر را انتخاب کن.", reply_markup=main_menu())
        return
    async with session_factory() as session, session.begin():
        lord = await get_lord(session, call.from_user.id)
        if action in ("assets", "buildings", "camps", "army", "trade", "war") and not lord:
            await _safe_edit_text(
                call.message,
                "برای این حساب هنوز لرد فعالی ثبت نشده است. پس از اتصال حساب به قلعه، اطلاعات بازی از همین منو نمایش داده می‌شود.",
                reply_markup=main_menu(),
            )
            return
        castle = await session.get(Castle, lord.castle_id) if lord else None
        reply_markup = section_back_menu()

        if action == "assets":
            from bot.database.models import ProductionLevel, CampLevel, SpecialCampLevel, ArmyUnit, EquipmentItem, FleetShip, CastleEconomyState
            from bot.integrations.site_api import configured, fetch_site_snapshot, sync_snapshot_to_postgres, SiteApiError
            if configured():
                try:
                    snapshot = await fetch_site_snapshot(call.from_user.id, castle.name)
                    await sync_snapshot_to_postgres(session, lord, snapshot)
                except SiteApiError as exc:
                    await _safe_edit_text(call.message, f"دریافت اطلاعات به‌روز سایت ناموفق بود: {escape(str(exc))}", reply_markup=section_back_menu())
                    return
            balances = await get_balances(session, lord.id)
            production = (await session.scalars(select(ProductionLevel).where(ProductionLevel.castle_id==lord.castle_id).order_by(ProductionLevel.production_key))).all()
            camps = (await session.scalars(select(CampLevel).where(CampLevel.castle_id==lord.castle_id).order_by(CampLevel.camp_key))).all()
            special_camps = (await session.scalars(select(SpecialCampLevel).where(SpecialCampLevel.castle_id==lord.castle_id).order_by(SpecialCampLevel.camp_key))).all()
            army = (await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==lord.castle_id).order_by(ArmyUnit.unit_key))).all()
            equipment = (await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id==lord.castle_id).order_by(EquipmentItem.item_key))).all()
            fleet = (await session.scalars(select(FleetShip).where(FleetShip.castle_id==lord.castle_id).order_by(FleetShip.ship_key))).all()
            economy = await session.get(CastleEconomyState, lord.castle_id)
            lines = [f"👑 پروفایل {escape(lord.display_name)}", f"🏰 {escape(castle.name) if castle else 'قلعه نامشخص'}", "", "📦 منابع"]
            lines.extend(f"{RESOURCE_NAMES.get(key, key)}: {value:,.0f}" for key, value in balances.items())
            lines.append("\n🏗 ساختمان‌های تولید")
            for row in production:
                definition = GENERAL_PRODUCTIONS.get(row.production_key) or (SPECIAL_PRODUCTIONS.get(castle.region) if castle and SPECIAL_PRODUCTIONS.get(castle.region,{}).get("key")==row.production_key else None)
                if definition: lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
            lines.append("\n🏕 کمپ‌ها")
            for row in camps:
                definition = GENERAL_CAMPS.get(row.camp_key)
                if definition: lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
            for row in special_camps:
                definition = next((x for x in SPECIAL_CAMPS.get(castle.region,[]) if x["key"]==row.camp_key),None) if castle else None
                if definition: lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
            lines.append("\n⚔️ ارتش")
            lines.extend(f"{row.unit_key}: {row.count:,}" for row in army)
            lines.append("\n🛠 تجهیزات")
            lines.extend(f"{row.item_key}: {row.count:,}" for row in equipment)
            lines.append("\n🚢 ناوگان")
            lines.extend(f"{row.ship_key}: {row.count:,}" for row in fleet)
            if economy and economy.food_debt:
                lines.append(f"\n⚠️ بدهی غذا: {economy.food_debt:,}")
                if economy.food_debt_due_at: lines.append(f"مهلت: {economy.food_debt_due_at:%Y-%m-%d %H:%M UTC}")
            if economy:
                lines.append(f"کارگاه: سطح {economy.workshop_level} | بندر: {'فعال' if economy.port_enabled else 'غیرفعال'} (سطح {economy.port_level})")
            body = "\n".join(lines)
        elif action in ("buildings", "camps"):
            from bot.database.models import ProductionLevel, CampLevel, SpecialCampLevel
            from bot.game.engine import GENERAL_PRODUCTIONS, SPECIAL_PRODUCTIONS, GENERAL_CAMPS, SPECIAL_CAMPS
            productions = (await session.scalars(select(ProductionLevel).where(ProductionLevel.castle_id == lord.castle_id).order_by(ProductionLevel.production_key))).all()
            camps = (await session.scalars(select(CampLevel).where(CampLevel.castle_id == lord.castle_id).order_by(CampLevel.camp_key))).all()
            special = (await session.scalars(select(SpecialCampLevel).where(SpecialCampLevel.castle_id == lord.castle_id).order_by(SpecialCampLevel.camp_key))).all()
            lines = [f"🏰 {escape(castle.name) if castle else 'قلعه'}"]
            if action == "buildings":
                lines.append("🏗 ساختمان‌های تولید")
                buttons = []
                for row in productions:
                    definition = GENERAL_PRODUCTIONS.get(row.production_key)
                    if not definition:
                        candidate = SPECIAL_PRODUCTIONS.get(castle.region, {}) if castle else {}
                        definition = candidate if candidate.get("key") == row.production_key else None
                    if definition:
                        lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
                        if row.level < int(definition["max"]):
                            buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {definition['label']}", callback_data=f"upgrade:production:{row.production_key}")])
                reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")]])
            if action == "camps":
                lines.append("⚔️ کمپ‌ها")
                buttons = []
                for row in camps:
                    definition = GENERAL_CAMPS.get(row.camp_key)
                    if definition:
                        lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
                        if row.level < int(definition["max"]):
                            buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {definition['label']}", callback_data=f"upgrade:camp:{row.camp_key}")])
                for row in special:
                    definitions = SPECIAL_CAMPS.get(castle.region, []) if castle else []
                    definition = next((item for item in definitions if item["key"] == row.camp_key), None)
                    if definition:
                        lines.append(f"{definition['label']}: سطح {row.level}/{definition['max']}")
                        if row.level < int(definition["max"]):
                            buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {definition['label']}", callback_data=f"upgrade:special_camp:{row.camp_key}")])
                reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons + [[InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")]])
            body = "\n".join(lines)
        elif action == "army":
            from bot.database.models import ArmyUnit, EquipmentItem, FleetShip
            army = (await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id == lord.castle_id).order_by(ArmyUnit.unit_key))).all()
            equipment = (await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id == lord.castle_id).order_by(EquipmentItem.item_key))).all()
            fleet = (await session.scalars(select(FleetShip).where(FleetShip.castle_id == lord.castle_id).order_by(FleetShip.ship_key))).all()
            lines = [f"🛡 ارتش {castle.name if castle else ''}", "نیروها:"]
            lines.extend(f"{row.unit_key}: {row.count:,}" for row in army)
            lines.append("ادوات:")
            lines.extend(f"{row.item_key}: {row.count:,}" for row in equipment)
            lines.append("ناوگان:")
            lines.extend(f"{row.ship_key}: {row.count:,}" for row in fleet)
            body = "\n".join(lines)
        elif action == "trade":
            rows = (await session.scalars(select(TradeOffer).where(
                (TradeOffer.recipient_lord_id == lord.id) & (TradeOffer.status == "pending")
            ).order_by(TradeOffer.id.desc()).limit(10))).all()
            body = "🤝 پیشنهادهای تجاری دریافتی"
            if not rows:
                body += "\nدر حال حاضر پیشنهاد معلقی نداری."
            else:
                for offer in rows:
                    offered = offer.offered_assets or {offer.offered_resource: offer.offered_amount}
                    requested = offer.requested_assets or {offer.requested_resource: offer.requested_amount}
                    await call.message.answer(
                        f"پیشنهاد #{offer.id}\nدریافت: {offered}\nپرداخت: {requested}",
                        reply_markup=trade_decision(offer.id)
                    )
                body = "پیشنهادهای فعال با دکمه پذیرش/رد در پیام‌های بالا نمایش داده شدند."
        elif action == "war":
            from bot.database.models import WarExpedition
            rows = (await session.scalars(select(WarExpedition).where(
                WarExpedition.attacker_lord_id == lord.id
            ).order_by(WarExpedition.id.desc()).limit(10))).all()
            body = "🚩 آخرین لشکرکشی‌ها"
            if rows:
                body += "\n" + "\n".join(
                    f"#{row.id} | مقصد قلعه {row.target_castle_id} | {row.status} | رسیدن: {row.arrival_at:%Y-%m-%d %H:%M}"
                    for row in rows
                )
            else:
                body += "\nهنوز لشکرکشی ثبت نشده است."
        elif action == "help":
            body = "ℹ️ راهنمای بازی\nاز دکمه‌های منو برای مشاهده پروفایل، ساختمان‌ها، کمپ‌ها، ارتش، تجارت و لشکرکشی استفاده کن. هر بخش اطلاعات واقعی قلعه و حساب متصل را نمایش می‌دهد."
        else:
            body = "بخش درخواستی در دسترس نیست."

    await _safe_edit_text(call.message, body, reply_markup=reply_markup)

@router.message(F.text.regexp(r"(?i)^set lord$"))
async def set_lord_reply(message: Message, session_factory):
    cfg = get_settings()
    from bot.integrations.site_api import configured
    if not configured():
        await message.answer("اتصال امن بات به سایت هنوز تنظیم نشده است؛ ابتدا SITE_API_URL و SITE_API_SECRET را تنظیم کن. هیچ موجودی محلی به‌عنوان موجودی واقعی ثبت نشد.")
        return
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
        site_assignment_created = False
        try:
            lord = await create_lord(session, target.id, target.full_name, target.username, cfg.bot_owner_id, group.castle_id)
            from bot.integrations.site_api import configured, assign_lord_on_site, sync_snapshot_to_postgres, SiteApiError
            if configured():
                snapshot = await assign_lord_on_site(target.id, (await session.get(Castle, group.castle_id)).name, cfg.bot_owner_id)
                site_assignment_created = True
                await sync_snapshot_to_postgres(session, lord, snapshot)
            await audit(session, cfg.bot_owner_id, "lord_assigned", str(lord.id), f"castle_id={group.castle_id}; chat_id={message.chat.id}")
            castle = await session.get(Castle, group.castle_id)
        except (ValueError, SiteApiError) as exc:
            await session.rollback()
            try:
                from bot.integrations.site_api import revoke_lord_on_site
                if site_assignment_created:
                    await revoke_lord_on_site(target.id)
            except SiteApiError:
                import logging
                logging.exception("Could not roll back website lord assignment")
            await message.answer(str(exc)); return
    await message.answer(f"✅ لرد با موفقیت انتخاب شد.\n🏰 قلعه: {castle.name}\n👑 لرد: {target.full_name}")

@router.message(Command("registercastle"))
async def register_castle(message: Message, session_factory):
    cfg = get_settings()
    if not message.from_user or message.from_user.id != cfg.bot_owner_id:
        await message.answer("فقط مالک اصلی می‌تواند گروه قلعه را ثبت کند."); return
    # /registercastle Castle Name | Region | House
    raw = (message.text or "").partition(" ")[2]
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 3 or not all(parts):
        await message.answer("فرمت: /registercastle نام قلعه | منطقه | خاندان"); return
    async with session_factory() as session, session.begin():
        try:
            castle, _ = await create_castle_group(session, message.chat.id, message.chat.title or "Castle Group", parts[0], parts[1], parts[2], cfg.bot_owner_id)
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

@router.callback_query(F.data.startswith("admin:"))
async def admin_menu_callback(call: CallbackQuery, session_factory):
    cfg = get_settings()
    if not call.message or not _is_admin_actor(call.from_user.id if call.from_user else None, call.message.chat, cfg):
        await call.answer("فقط مالک اصلی در گروه مدیریت اجازه این کار را دارد.", show_alert=True)
        return
    action = call.data.split(":", 1)[1]
    allowed = {"pause", "resume", "status", "castles", "lords", "wars", "trades", "scenarios", "logs", "commands"}
    if action not in allowed:
        await call.answer("عملیات نامعتبر است.", show_alert=True)
        return
    if action in {"pause", "resume"}:
        paused = action == "pause"
        async with session_factory() as session, session.begin():
            await set_world_paused(session, paused)
            await audit(session, call.from_user.id, "world_paused" if paused else "world_resumed")
        await publish_admin_audit(call.bot, call.from_user.id, "world_paused" if paused else "world_resumed", "world", "کنترل ساعت جهان از پنل")
        body = "⏸ ساعت جهان متوقف شد." if paused else "▶️ ساعت جهان ادامه یافت."
    else:
        async with session_factory() as session:
            if action == "status":
                paused = await is_world_paused(session)
                from bot.database.models import WarExpedition
                from sqlalchemy import func
                states = ("prepared", "travelling", "arrived", "resolving", "returning", "completed", "cancelled", "failed")
                counts = []
                for state in states:
                    count = await session.scalar(select(func.count()).select_from(WarExpedition).where(WarExpedition.status == state))
                    counts.append(f"{state}: {count or 0}")
                body = f"📊 <b>وضعیت جهان</b>\nساعت جهان: {'متوقف' if paused else 'فعال'}\n" + "\n".join(counts)
            elif action == "castles":
                rows = (await session.scalars(select(Castle).order_by(Castle.region, Castle.name).limit(80))).all()
                body = "🏰 <b>قلعه‌ها</b>\n" + ("\n".join(f"#{x.id} {escape(x.name)} | {escape(x.region)} | {escape(x.house)} | {'فعال' if x.active else 'غیرفعال'}" for x in rows) or "قلعه‌ای ثبت نشده است.")
            elif action == "lords":
                rows = (await session.scalars(select(Lord).order_by(Lord.id.desc()).limit(80))).all()
                body = "👑 <b>لردها</b>\n" + ("\n".join(f"#{x.id} {escape(x.display_name)} | تلگرام <code>{x.telegram_user_id}</code> | قلعه {x.castle_id} | {x.status}" for x in rows) or "لردی ثبت نشده است.")
            elif action == "wars":
                from bot.database.models import WarExpedition
                rows = (await session.scalars(select(WarExpedition).order_by(WarExpedition.id.desc()).limit(30))).all()
                body = "⚔️ <b>لشکرکشی‌ها</b>\n" + ("\n".join(f"#{x.id} | {x.origin_castle_id} → {x.target_castle_id} | {x.status} | {x.outcome or '-'}" for x in rows) or "لشکرکشی‌ای ثبت نشده است.")
            elif action == "trades":
                rows = (await session.scalars(select(TradeOffer).order_by(TradeOffer.id.desc()).limit(30))).all()
                body = "🤝 <b>معاملات</b>\n" + ("\n".join(f"#{x.id} | {x.sender_lord_id} → {x.recipient_lord_id} | {x.status}" for x in rows) or "معامله‌ای ثبت نشده است.")
            elif action == "scenarios":
                rows = (await session.scalars(select(WarScenario).where(WarScenario.reviewed.is_(False)).order_by(WarScenario.created_at).limit(20))).all()
                body = "📜 <b>سناریوهای بررسی‌نشده</b>\n" + ("\n".join(f"#{x.id} | نبرد #{x.expedition_id} | لرد #{x.lord_id}\n{escape(x.scenario_text[:450])}" for x in rows) or "سناریوی بررسی‌نشده‌ای وجود ندارد.")
            elif action == "logs":
                rows = (await session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(20))).all()
                body = "🧾 <b>گزارش عملیات</b>\n" + ("\n".join(f"#{x.id} | {x.actor_telegram_id} | {escape(x.action)} | {escape(x.target_id or '-')}" for x in rows) or "گزارشی ثبت نشده است.")
            else:
                body = ("🛠 <b>فرمان‌های مدیریتی</b>\n"
                    "/registercastle نام | منطقه | خاندان — ثبت گروه قلعه\n"
                    "Reply به پیام بازیکن + set lord — تعیین لرد\n"
                    "/setresource شناسه منبع مقدار — تغییر منابع\n"
                    "/setasset شناسه_قلعه نوع کلید مقدار — تغییر دارایی\n"
                    "/setlordcastle شناسه_تلگرام شناسه_قلعه — انتقال لرد\n"
                    "/setcastleinfo شناسه نام | منطقه | خاندان — ویرایش قلعه\n"
                    "/setlordstatus شناسه active|suspended|deleted — وضعیت لرد\n"
                    "/admincastles /adminwars /admintrades /adminscenarios /adminlogs\n"
                    "/warresolve شناسه attacker|defender JSON — نتیجه نبرد\n"
                    "/reviewscenario شناسه نتیجه — بررسی سناریو\n"
                    "/canceltrade شناسه — لغو معامله")
    await _safe_edit_text(call.message, body, reply_markup=admin_menu())
    await call.answer("انجام شد")


async def admin_action(message: Message, session_factory, bot, paused: bool | None):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        return False
    if paused is not None:
        async with session_factory() as session, session.begin():
            await set_world_paused(session, paused)
            await audit(session, message.from_user.id, "world_paused" if paused else "world_resumed")
        action = "world_paused" if paused else "world_resumed"
        await publish_admin_audit(bot, message.from_user.id, action, "world", "تغییر وضعیت ساعت جهان")
        await message.answer("ساعت جهان متوقف شد." if paused else "ساعت جهان ادامه یافت.")
    else:
        async with session_factory() as session:
            value = await is_world_paused(session)
        await message.answer(f"وضعیت ساعت جهان: {'متوقف' if value else 'فعال'}")
    return True

@router.message(Command("pause"))
async def pause_world(message: Message, session_factory, bot):
    if not await admin_action(message, session_factory, bot, True): await message.answer("این فرمان فقط برای مالک اصلی در گروه مدیریت فعال است.")

@router.message(Command("resume"))
async def resume_world(message: Message, session_factory, bot):
    if not await admin_action(message, session_factory, bot, False): await message.answer("ابتدا از گروه مدیریت و با کد معتبر وارد پنل شو.")

@router.message(Command("status"))
async def world_status(message: Message, session_factory, bot):
    if not await admin_action(message, session_factory, bot, None): await message.answer("دسترسی مجاز نیست.")

# Website-aligned economy commands. Definitions are loaded from the uploaded site's catalog.
from bot.game.engine import (CATALOG, upgrade as engine_upgrade, recruit as engine_recruit,
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

@router.callback_query(F.data.startswith("upgrade:"))
async def upgrade_prompt(call: CallbackQuery, session_factory):
    if not call.from_user or not call.message:
        await call.answer()
        return
    from bot.integrations.site_api import configured
    if not configured():
        await call.answer("اتصال امن به سایت تنظیم نشده است.", show_alert=True)
        return
    _, category, key = call.data.split(":", 2)
    async with session_factory() as session:
        lord = await get_lord(session, call.from_user.id)
        if not lord:
            await call.answer("برای این حساب لردی ثبت نشده است.", show_alert=True)
            return
        castle = await session.get(Castle, lord.castle_id)
        if category == "production":
            definition = GENERAL_PRODUCTIONS.get(key) or (SPECIAL_PRODUCTIONS.get(castle.region) if SPECIAL_PRODUCTIONS.get(castle.region, {}).get("key") == key else None)
            model, field = ProductionLevel, "production_key"
        elif category == "camp":
            definition = GENERAL_CAMPS.get(key)
            model, field = CampLevel, "camp_key"
        elif category == "special_camp":
            definition = next((x for x in SPECIAL_CAMPS.get(castle.region, []) if x["key"] == key), None)
            model, field = SpecialCampLevel, "camp_key"
        else:
            definition = None
            model, field = ProductionLevel, "production_key"
        if not definition:
            await call.answer("این ارتقا برای قلعه تعریف نشده است.", show_alert=True)
            return
        row = await session.scalar(select(model).where(model.castle_id == lord.castle_id, getattr(model, field) == key))
        level = int(row.level if row else 0)
        if level >= int(definition.get("max", 0)):
            await call.answer("این مورد به حداکثر سطح رسیده است.", show_alert=True)
            return
    cost = "، ".join(f"{RESOURCE_LABELS.get(k,k)} {v}" for k,v in definition.get("cost",{}).items()) or "بدون هزینه"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید ارتقا", callback_data=f"upgradeconfirm:{category}:{key}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="upgradecancel")],
    ])
    await _safe_edit_text(call.message, f"ارتقای {definition['label']}\nسطح فعلی: {level}\nسطح بعدی: {level+1}\nهزینه: {cost}\n\nآیا تأیید می‌کنی؟", reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data == "upgradecancel")
async def upgrade_cancel(call: CallbackQuery):
    if call.message:
        await _safe_edit_text(call.message, "عملیات ارتقا لغو شد.", reply_markup=section_back_menu())
    await call.answer("لغو شد")


@router.callback_query(F.data.startswith("upgradeconfirm:"))
async def upgrade_confirm(call: CallbackQuery, session_factory):
    if not call.from_user or not call.message:
        await call.answer()
        return
    from bot.integrations.site_api import configured, upgrade_on_site, sync_snapshot_to_postgres
    if not configured():
        await call.answer("اتصال امن به سایت تنظیم نشده است.", show_alert=True)
        return
    _, category, key = call.data.split(":", 2)
    try:
        async with session_factory() as session, session.begin():
            lord = await get_lord(session, call.from_user.id)
            if not lord:
                raise SiteApiError("برای این حساب لردی ثبت نشده است.")
            castle = await session.get(Castle, lord.castle_id)
            remote = await upgrade_on_site(call.from_user.id, castle.name, category, key)
            await sync_snapshot_to_postgres(session, lord, remote["snapshot"])
            await audit(session, call.from_user.id, "building_upgraded", str(lord.castle_id), f"{category}:{key}:{remote['result'].get('newLevel')}")
            level = int(remote["result"].get("newLevel", 0))
            definition = GENERAL_PRODUCTIONS.get(key) or (SPECIAL_PRODUCTIONS.get(castle.region) if SPECIAL_PRODUCTIONS.get(castle.region, {}).get("key") == key else None) or GENERAL_CAMPS.get(key) or next((x for x in SPECIAL_CAMPS.get(castle.region, []) if x["key"] == key), {})
        cost = "، ".join(f"{RESOURCE_LABELS.get(k,k)} {v}" for k,v in definition.get("cost",{}).items()) or "بدون هزینه"
        await _safe_edit_text(call.message, f"✅ {definition['label']} به سطح {level} ارتقا یافت.\nهزینه: {cost}", reply_markup=section_back_menu())
        await call.answer("ارتقا انجام شد")
    except (ValueError, SiteApiError) as exc:
        await call.answer(str(exc), show_alert=True)


@router.message(Command("upgrade"))
async def upgrade_cmd(message: Message, session_factory):
    from bot.integrations.site_api import configured
    if not configured():
        await message.answer("ارتقا تا زمان تنظیم اتصال امن به سایت غیرفعال است تا موجودی دو دیتابیس از هم جدا نشود.")
        return
    parts=(message.text or "").split()
    if len(parts)!=3 or parts[1] not in ("production","camp","special_camp"):
        await message.answer("فرمت: /upgrade production farm\nیا /upgrade camp swordsman\nیا /upgrade special_camp ranger"); return
    async with session_factory() as session, session.begin():
        group=await get_group(session,message.chat.id)
        if not group: await message.answer("این گروه به قلعه متصل نیست."); return
        lord=await get_lord(session,message.from_user.id)
        if not lord or lord.castle_id!=group.castle_id: await message.answer("در این گروه لرد نیستی."); return
        try:
            from bot.integrations.site_api import configured, upgrade_on_site, sync_snapshot_to_postgres
            if configured():
                castle = await session.get(Castle, lord.castle_id)
                remote = await upgrade_on_site(message.from_user.id, castle.name, parts[1], parts[2])
                await sync_snapshot_to_postgres(session, lord, remote["snapshot"])
                level = int(remote["result"].get("newLevel", 0))
                definition = (GENERAL_PRODUCTIONS.get(parts[2]) or (SPECIAL_PRODUCTIONS.get(castle.region) if SPECIAL_PRODUCTIONS.get(castle.region,{}).get("key")==parts[2] else None) or GENERAL_CAMPS.get(parts[2]) or next((x for x in SPECIAL_CAMPS.get(castle.region,[]) if x["key"]==parts[2]), {}))
            else:
                level,definition=await engine_upgrade(session,lord,parts[1],parts[2])
            await audit(session,message.from_user.id,"building_upgraded",str(lord.castle_id),f"{parts[1]}:{parts[2]}:{level}")
        except (ValueError, SiteApiError) as e: await message.answer(str(e)); return
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
    raw=(message.text or "").partition(" ")[2]
    bits=raw.split(maxsplit=3)
    if len(bits)<4:
        await message.answer("فرمت: /march نام_قلعه_مقصد land|sea مدت_دقیقه army:swordsman=100,archer=20;equipment:ladder=2;fleet:transport=1");return
    target,kind,minutes_s,assets_s=bits
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
    await message.answer("لشکرهای رسیده:\n"+"\n".join(f"#{x.id} → قلعه مقصد {x.target_castle_id} | انتخاب: /arrival {x.id} garrison|alliance|transfer|deploy" for x in rows))

@router.message(Command("arrival"))
async def arrival_choice_cmd(message: Message, session_factory):
    p=(message.text or "").split()
    if len(p)!=3: await message.answer("فرمت: /arrival شناسه garrison|alliance|transfer|deploy");return
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
async def war_resolve_admin_cmd(message: Message, session_factory, bot):
    cfg=get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
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
        await publish_admin_audit(bot, message.from_user.id, "war_battle_reviewed", str(row.id), str(row.result))
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
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    async with session_factory() as session:
        rows=(await session.scalars(select(WarScenario).where(WarScenario.reviewed.is_(False)).order_by(WarScenario.created_at).limit(30))).all()
    if not rows: await message.answer("سناریوی بررسی‌نشده‌ای وجود ندارد.");return
    for x in rows: await message.answer(f"سناریو #{x.id} | نبرد #{x.expedition_id} | لرد #{x.lord_id}\n{x.scenario_text[:3500]}\nبرای بررسی: /reviewscenario {x.id} متن_نتیجه")

@router.message(Command("reviewscenario"))
async def review_scenario_cmd(message: Message, session_factory, bot):
    cfg=get_settings();p=(message.text or "").split(maxsplit=2)
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی مدیریتی فعال نیست.");return
    if len(p)<3: await message.answer("فرمت: /reviewscenario شناسه نتیجه بررسی");return
    async with session_factory() as session,session.begin():
        item=await session.scalar(select(WarScenario).where(WarScenario.id==int(p[1])).with_for_update())
        if not item: await message.answer("سناریو پیدا نشد.");return
        item.reviewed=True;item.review_result=p[2];item.reviewed_at=datetime.now(timezone.utc)
        await audit(session,message.from_user.id,"war_scenario_reviewed",str(item.id),p[2][:500])
    await publish_admin_audit(bot, message.from_user.id, "war_scenario_reviewed", str(item.id), p[2][:500])
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
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
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
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
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
    p=(message.text or "").partition(" ")[2].split(maxsplit=4)
    if len(p)<5: await message.answer("فرمت: /marchgarrison sourceCastleId target land|sea minutes army:swordsman=10;equipment:ladder=1;fleet:transport=1");return
    try:
        source_id=int(p[0]);target=p[1];kind=p[2];minutes=int(p[3]);assets={"army":{},"equipment":{},"fleet":{}}
        for section in p[4].split(";"):
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
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
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


@router.message(Command("adminhelp"))
async def admin_help_cmd(message: Message):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("ابتدا با /admin و کد معتبر وارد پنل شو.")
        return
    await message.answer(
        "🔐 <b>راهنمای سوپرادمین</b>\n"
        "/status — وضعیت جهان\n/pause و /resume — کنترل ساعت جهان\n"
        "/admincastles — فهرست قلعه‌ها\n/adminwars — گزارش لشکرکشی‌ها\n/admintrades — گزارش تجارت‌ها\n"
        "/adminscenarios — سناریوهای بررسی‌نشده\n"
        "/setresource شناسه_تلگرام منبع مقدار — تغییر موجودی هر لرد\n"
        "/setasset شناسه_قلعه نوع کلید مقدار — ویرایش دارایی قلعه\n"
        "/setlordcastle شناسه_تلگرام شناسه_قلعه — جابه‌جایی لرد\n"
        "/setcastleinfo شناسه نام | منطقه | خاندان — ویرایش مشخصات قلعه\\n"
        "/setlordstatus شناسه active|suspended|deleted — مدیریت وضعیت لرد\\n"
        "/canceltrade شناسه — لغو معامله معلق\\n"
        "/adminlogs — آخرین گزارش‌های مدیریتی"
    )

@router.message(Command("setresource"))
async def admin_set_resource_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("فرمت: /setresource شناسه_تلگرام منبع مقدار")
        return
    try:
        telegram_id = int(parts[1])
        resource = parts[2].lower()
        amount = Decimal(parts[3])
        if resource not in RESOURCE_NAMES or not amount.is_finite() or amount < 0:
            raise ValueError("منبع یا مقدار نامعتبر است؛ مقدار باید عددی و نامنفی باشد.")
        async with session_factory() as session, session.begin():
            lord = await session.scalar(select(Lord).where(Lord.telegram_user_id == telegram_id).with_for_update())
            if not lord:
                raise ValueError("لرد موردنظر پیدا نشد.")
            balance = await session.scalar(select(ResourceBalance).where(ResourceBalance.lord_id == lord.id, ResourceBalance.resource_code == resource).with_for_update())
            before = str(balance.amount) if balance else "0"
            if balance:
                balance.amount = amount
            else:
                balance = ResourceBalance(lord_id=lord.id, resource_code=resource, amount=amount)
                session.add(balance)
            await audit(session, message.from_user.id, "superadmin_resource_changed", str(lord.id), f"{resource}: {before} -> {amount}")
            castle = await session.get(Castle, lord.castle_id)
        await publish_admin_audit(bot, message.from_user.id, "superadmin_resource_changed", f"{castle.name} / {lord.display_name}", f"{resource}: {before} -> {amount}")
        await message.answer(f"✅ موجودی {RESOURCE_NAMES[resource]} برای {lord.display_name} تغییر کرد: {before} ← {amount}")
    except (ValueError, InvalidOperation) as exc:
        await message.answer(str(exc))

@router.message(Command("adminlogs"))
async def admin_logs_cmd(message: Message, session_factory):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    async with session_factory() as session:
        rows = (await session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(15))).all()
    if not rows:
        await message.answer("هنوز گزارشی ثبت نشده است.")
        return
    lines = ["🧾 آخرین عملیات مدیریتی:"]
    for row in rows:
        lines.append(f"#{row.id} | مدیر {row.actor_telegram_id} | {row.action} | هدف {row.target_id or '-'} | {row.details or '-'}")
    await message.answer("\n".join(lines))



@router.message(Command("setasset"))
async def admin_set_asset_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    parts = (message.text or "").split()
    if len(parts) != 5:
        await message.answer("فرمت: /setasset شناسه_قلعه army|equipment|fleet|production|camp|special_camp کلید مقدار")
        return
    try:
        castle_id, kind, key, amount = int(parts[1]), parts[2].lower(), parts[3], int(parts[4])
        if amount < 0:
            raise ValueError("مقدار نمی‌تواند منفی باشد.")
        from bot.database.models import ArmyUnit, EquipmentItem, FleetShip, ProductionLevel, CampLevel, SpecialCampLevel
        mapping = {
            "army": (ArmyUnit, "unit_key", "count"),
            "equipment": (EquipmentItem, "item_key", "count"),
            "fleet": (FleetShip, "ship_key", "count"),
            "production": (ProductionLevel, "production_key", "level"),
            "camp": (CampLevel, "camp_key", "level"),
            "special_camp": (SpecialCampLevel, "camp_key", "level"),
        }
        if kind not in mapping:
            raise ValueError("نوع دارایی نامعتبر است.")
        model, key_field, value_field = mapping[kind]
        async with session_factory() as session, session.begin():
            castle = await session.get(Castle, castle_id)
            if not castle:
                raise ValueError("قلعه پیدا نشد.")
            condition = getattr(model, key_field) == key
            row = await session.scalar(select(model).where(model.castle_id == castle_id, condition).with_for_update())
            before = getattr(row, value_field) if row else 0
            if row:
                setattr(row, value_field, amount)
            else:
                row = model(castle_id=castle_id, **{key_field: key, value_field: amount})
                session.add(row)
            await audit(session, message.from_user.id, "superadmin_asset_changed", str(castle_id), f"{kind}/{key}: {before} -> {amount}")
        await publish_admin_audit(bot, message.from_user.id, "superadmin_asset_changed", castle.name, f"{kind}/{key}: {before} -> {amount}")
        await message.answer(f"✅ دارایی قلعه {castle.name} تغییر کرد: {kind}/{key}، {before} ← {amount}")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))

@router.message(Command("setlordcastle"))
async def admin_set_lord_castle_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("فرمت: /setlordcastle شناسه_تلگرام شناسه_قلعه")
        return
    try:
        telegram_id, castle_id = int(parts[1]), int(parts[2])
        async with session_factory() as session, session.begin():
            lord = await session.scalar(select(Lord).where(Lord.telegram_user_id == telegram_id).with_for_update())
            castle = await session.get(Castle, castle_id)
            if not lord or not castle:
                raise ValueError("لرد یا قلعه پیدا نشد.")
            other = await session.scalar(select(Lord).where(Lord.castle_id == castle_id, Lord.id != lord.id).with_for_update())
            if other:
                raise ValueError("این قلعه از قبل به لرد دیگری اختصاص دارد؛ ابتدا وضعیت مالک فعلی را تعیین تکلیف کن.")
            old_castle = await session.get(Castle, lord.castle_id)
            before = old_castle.name if old_castle else str(lord.castle_id)
            lord.castle_id = castle_id
            await audit(session, message.from_user.id, "superadmin_lord_castle_changed", str(lord.id), f"{before} -> {castle.name}")
        await publish_admin_audit(bot, message.from_user.id, "superadmin_lord_castle_changed", lord.display_name, f"{before} -> {castle.name}")
        await message.answer(f"✅ قلعه لرد {lord.display_name} از {before} به {castle.name} تغییر کرد.")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))


@router.message(Command("setcastleinfo"))
async def admin_set_castle_info_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    raw = (message.text or "").partition(" ")[2]
    castle_id_text, sep, values = raw.partition(" ")
    parts = [value.strip() for value in values.split("|")]
    if not sep or len(parts) != 3 or not all(parts):
        await message.answer("فرمت: /setcastleinfo شناسه_قلعه نام_قلعه | منطقه | خاندان")
        return
    try:
        castle_id = int(castle_id_text)
        name, region, house = parts
        if len(name) > 120 or len(region) > 80 or len(house) > 80:
            raise ValueError("طول نام قلعه، منطقه یا خاندان بیش از حد مجاز است.")
        async with session_factory() as session, session.begin():
            castle = await session.get(Castle, castle_id, with_for_update=True)
            if not castle:
                raise ValueError("قلعه پیدا نشد.")
            duplicate = await session.scalar(select(Castle.id).where(Castle.name == name, Castle.id != castle_id))
            if duplicate:
                raise ValueError("این نام قلعه قبلاً استفاده شده است.")
            before = f"{castle.name} | {castle.region} | {castle.house}"
            castle.name, castle.region, castle.house = name, region, house
            await audit(session, message.from_user.id, "superadmin_castle_info_changed", str(castle_id), f"{before} -> {name} | {region} | {house}")
        await publish_admin_audit(bot, message.from_user.id, "superadmin_castle_info_changed", str(castle_id), f"{before} -> {name} | {region} | {house}")
        await message.answer(f"✅ مشخصات قلعه #{castle_id} به‌روزرسانی شد.")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))

@router.message(Command("setlordstatus"))
async def admin_set_lord_status_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in ("active", "suspended", "deleted"):
        await message.answer("فرمت: /setlordstatus شناسه_تلگرام active|suspended|deleted")
        return
    try:
        telegram_id = int(parts[1])
        async with session_factory() as session, session.begin():
            lord = await session.scalar(select(Lord).where(Lord.telegram_user_id == telegram_id).with_for_update())
            if not lord:
                raise ValueError("لرد پیدا نشد.")
            before = lord.status
            lord.status = parts[2]
            await audit(session, message.from_user.id, "superadmin_lord_status_changed", str(lord.id), f"{before} -> {lord.status}")
        await publish_admin_audit(bot, message.from_user.id, "superadmin_lord_status_changed", lord.display_name, f"{before} -> {lord.status}")
        await message.answer(f"وضعیت لرد {lord.display_name}: {before} ← {lord.status}")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))

@router.message(Command("canceltrade"))
async def admin_cancel_trade_cmd(message: Message, session_factory, bot):
    cfg = get_settings()
    if not message.from_user or not _is_admin_actor(message.from_user.id, message.chat, cfg):
        await message.answer("دسترسی سوپرادمین فعال نیست.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("فرمت: /canceltrade شناسه_معامله")
        return
    try:
        offer_id = int(parts[1])
        async with session_factory() as session, session.begin():
            offer = await session.scalar(select(TradeOffer).where(TradeOffer.id == offer_id).with_for_update())
            if not offer or offer.status != "pending":
                raise ValueError("معامله پیدا نشد یا دیگر در انتظار نیست.")
            offer.status = "cancelled"
            await audit(session, message.from_user.id, "superadmin_trade_cancelled", str(offer.id))
        await publish_admin_audit(bot, message.from_user.id, "superadmin_trade_cancelled", str(offer_id), "معامله معلق لغو شد.")
        await message.answer(f"معامله #{offer_id} لغو شد.")
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc))
