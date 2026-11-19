"""Interactive Telegram UI for player economy, trade, warfare and admin controls."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, or_
from html import escape

from bot.config import get_settings
from bot.database.models import (
    Lord, Castle, GroupRegistration, ResourceBalance, TradeOffer, GameSetting,
    ProductionLevel, CampLevel, SpecialCampLevel, ArmyUnit, EquipmentItem,
    FleetShip, CastleEconomyState, WarExpedition, WarScenario, AdminAuditLog,
)
from bot.services import get_lord, get_group, get_balances, create_trade_bundle, audit, RESOURCE_NAMES
from bot.game.engine import (
    CATALOG, GENERAL_PRODUCTIONS, SPECIAL_PRODUCTIONS, GENERAL_CAMPS, SPECIAL_CAMPS,
    RESOURCE_LABELS, upgrade_workshop, build_equipment, upgrade_port, weekly_settlement,
)
from bot.game.warfare import launch_expedition, issue_war_command, set_arrival_choice, submit_scenario
from bot.game.controls import get_controls, update_controls
from bot.keyboards import main_menu, section_back_menu, admin_menu

router = Router()


class UIFlow(StatesGroup):
    trade_offer = State()
    trade_request = State()
    war_assets = State()
    war_duration = State()
    scenario_text = State()
    roll_text = State()
    admin_deadlines = State()


def _admin(user_id, chat, cfg):
    return bool(user_id and cfg.bot_owner_id and user_id == cfg.bot_owner_id and chat
                and chat.type in ("group", "supergroup") and cfg.admin_chat_id
                and chat.id == cfg.admin_chat_id)


async def _player(session, user_id, chat_id):
    group = await get_group(session, chat_id)
    lord = await get_lord(session, user_id)
    if not group:
        raise ValueError("این گروه به قلعه‌ای متصل نیست.")
    if not lord or lord.castle_id != group.castle_id:
        raise ValueError("در این گروه لرد این قلعه نیستی. دسترسی هر قلعه جداگانه با set lord تعیین می‌شود.")
    castle = await session.get(Castle, group.castle_id)
    if not castle or not castle.active:
        raise ValueError("قلعه فعال نیست.")
    return lord, castle


def _back():
    return section_back_menu()


ARMY_LABELS = {
    "archer": "🏹 کماندار", "cavalry": "🏇 سواره‌نظام",
    "spearman": "🔱 نیزه‌دار", "swordsman": "🗡 شمشیرزن",
    "ranger": "🥷 رنجر", "winter_soldier": "🐺 سرباز زمستان",
    "vale_knight": "⚔️ شوالیه ویل", "crossbowman": "🏹 کراسبو‌دار",
    "red_cloak": "🩸 ردا سرخ", "dragon_knight": "🐉 شوالیه اژدها",
    "axeman": "🪓 تبر‌دار", "flower_knight": "🏵 شوالیه گل",
    "hammer_wielder": "🔨 پتک‌دار", "dornish_spearman": "🔱 نیزه‌دار دورنیش",
}
EQUIPMENT_LABELS = {key: value["label"] for key, value in CATALOG["EQUIPMENT"].items()}
FLEET_LABELS = {"transport": "🚢 کشتی ترابری", "warship": "⚔️ کشتی جنگی"}


def _cost(definition):
    return "، ".join(f"{RESOURCE_LABELS.get(k,k)} {int(v):,}" for k,v in definition.get("cost",{}).items()) or "بدون هزینه"


def _parse_quantities(raw):
    result = {}
    for item in raw.replace("؛", ",").replace("،", ",").split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError("قالب هر مقدار باید resource=number باشد؛ نمونه: wood=100,grain=50")
        key = key.strip().lower()
        try:
            amount = int(value.strip())
        except ValueError:
            raise ValueError("مقدار باید عدد صحیح باشد.")
        if key not in RESOURCE_NAMES or key == "peasants" or amount <= 0 or amount > 100000000:
            raise ValueError(f"منبع یا مقدار نامعتبر است: {key}")
        result[key] = amount
    if not result:
        raise ValueError("حداقل یک منبع با مقدار مثبت وارد کن.")
    return result


async def render_player_section(call: CallbackQuery, session_factory, action: str):
    if not call.message or not call.from_user:
        return
    if call.message.chat.type not in ("group", "supergroup"):
        await call.answer("این بخش فقط در گروه اختصاصی قلعه قابل استفاده است.", show_alert=True)
        return
    async with session_factory() as session:
        try:
            lord, castle = await _player(session, call.from_user.id, call.message.chat.id)
        except ValueError as exc:
            await call.answer(str(exc), show_alert=True)
            return
        body = f"🏰 <b>مدیریت قلعه: {escape(castle.name)}</b>\n👑 {escape(lord.display_name)}\n\n"
        markup = _back()
        if action == "assets":
            balances = await get_balances(session, lord.id)
            army = (await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id))).all()
            gear = (await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id==castle.id))).all()
            fleet = (await session.scalars(select(FleetShip).where(FleetShip.castle_id==castle.id))).all()
            body += "📜 <b>لیست دارایی</b>\n📦 منابع\n"
            body += "\n".join(f"{RESOURCE_LABELS.get(k,k)}: <b>{int(v):,}</b>" for k,v in balances.items())
            body += "\n\n⚔️ <b>ارتش</b>\n" + ("\n".join(f"{ARMY_LABELS.get(r.unit_key,r.unit_key)}: {r.count:,}" for r in army) or "بدون نیرو")
            body += "\n\n🛠 <b>ادوات محاصره</b>\n" + ("\n".join(f"{EQUIPMENT_LABELS.get(r.item_key,r.item_key)}: {r.count:,}" for r in gear) or "بدون ادوات")
            body += "\n\n🚢 <b>ناوگان</b>\n" + ("\n".join(f"{FLEET_LABELS.get(r.ship_key,r.ship_key)}: {r.count:,}" for r in fleet) or "بدون کشتی")
            econ = await session.get(CastleEconomyState, castle.id)
            if econ:
                body += f"\n\n🏗 کارگاه: {econ.workshop_level}/5\n⚓ اسکله: {econ.port_level}/15"
        elif action in ("buildings", "camps"):
            if action == "buildings":
                rows = (await session.scalars(select(ProductionLevel).where(ProductionLevel.castle_id==castle.id))).all()
                body += "🏗 <b>ساختمان‌های تولید</b>\n"
                buttons = []
                for row in rows:
                    d = GENERAL_PRODUCTIONS.get(row.production_key)
                    if not d:
                        d0 = SPECIAL_PRODUCTIONS.get(castle.region, {})
                        d = d0 if d0.get("key") == row.production_key else None
                    if not d: continue
                    mult = int(CATALOG.get("REGION_MULTIPLIERS",{}).get(castle.region,{}).get(row.production_key,1))
                    body += f"\n{d['label']} — سطح {row.level}/{d['max']}\nتولید هفتگی: {row.level*int(d['yield'])*mult:,} {RESOURCE_LABELS.get(d['base'],d['base'])}\nهزینه ارتقای بعدی: {_cost(d)}\n"
                    if row.level < int(d["max"]):
                        buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {d['label']}", callback_data=f"upgrade:production:{row.production_key}")])
                buttons.append([InlineKeyboardButton(text="🛠 کارگاه و ادوات", callback_data="ui:workshop")])
                buttons.append([InlineKeyboardButton(text="⚓ اسکله", callback_data="ui:port")])
                buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")])
                markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            else:
                rows = (await session.scalars(select(CampLevel).where(CampLevel.castle_id==castle.id))).all()
                special = (await session.scalars(select(SpecialCampLevel).where(SpecialCampLevel.castle_id==castle.id))).all()
                body += "⚔️ <b>کمپ‌های نظامی</b>\n"
                buttons = []
                for row in rows:
                    d = GENERAL_CAMPS.get(row.camp_key)
                    if not d: continue
                    body += f"\n{d['label']} — سطح {row.level}/{d['max']}\nتولید هفتگی: {row.level*int(d['yield']):,} {d['unit']}\nهزینه: {_cost(d)}\n"
                    if row.level < int(d["max"]):
                        buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {d['label']}", callback_data=f"upgrade:camp:{row.camp_key}")])
                for row in special:
                    d = next((x for x in SPECIAL_CAMPS.get(castle.region,[]) if x["key"]==row.camp_key),None)
                    if not d: continue
                    body += f"\n{d['label']} — سطح {row.level}/{d['max']}\nتولید هفتگی: {row.level*int(d['yield']):,} {d['unit']}\nهزینه: {_cost(d)}\n"
                    if row.level < int(d["max"]):
                        buttons.append([InlineKeyboardButton(text=f"⬆️ ارتقا {d['label']}", callback_data=f"upgrade:special_camp:{row.camp_key}")])
                buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")])
                markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        elif action == "army":
            army = (await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id))).all()
            gear = (await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id==castle.id))).all()
            fleet = (await session.scalars(select(FleetShip).where(FleetShip.castle_id==castle.id))).all()
            body += "🛡 <b>ارتش و ادوات</b>\nنیروها:\n"
            body += "\n".join(f"{ARMY_LABELS.get(r.unit_key,r.unit_key)}: {r.count:,}" for r in army)
            body += "\n\nادوات محاصره:\n" + "\n".join(f"{EQUIPMENT_LABELS.get(r.item_key,r.item_key)}: {r.count:,}" for r in gear)
            body += "\n\nناوگان:\n" + "\n".join(f"{FLEET_LABELS.get(r.ship_key,r.ship_key)}: {r.count:,}" for r in fleet)
            econ = await session.get(CastleEconomyState, castle.id)
            body += f"\n\nکارگاه: {econ.workshop_level if econ else 0}/5\nاسکله: {econ.port_level if econ else 0}/15\n"
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 کارگاه محاصره", callback_data="ui:workshop"),
                 InlineKeyboardButton(text="⚓ اسکله", callback_data="ui:port")],
                [InlineKeyboardButton(text="🚩 لشکرکشی زمینی", callback_data="ui:war")],
                [InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")]])
        elif action == "workshop":
            econ = await session.get(CastleEconomyState, castle.id)
            level = econ.workshop_level if econ else 0
            body += f"🛠 <b>کارگاه محاصره</b>\nسطح: {level}/5\nهزینه ارتقای هر سطح: 💰 6,000\n"
            for key,d in CATALOG["EQUIPMENT"].items():
                item = await session.scalar(select(EquipmentItem).where(EquipmentItem.castle_id==castle.id,EquipmentItem.item_key==key))
                body += f"\n{d['label']}: {item.count if item else 0:,}\nهزینه ساخت: {_cost(d)} | نیاز کارگاه: {d['level']}\n"
            buttons = []
            if level < 5: buttons.append([InlineKeyboardButton(text="⬆️ ارتقای کارگاه", callback_data="ui:workshop:upgrade")])
            for key,d in CATALOG["EQUIPMENT"].items():
                buttons.append([InlineKeyboardButton(text=f"ساخت {d['label']}", callback_data=f"ui:equipment:{key}")])
            buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:army")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        elif action == "port":
            econ = await session.get(CastleEconomyState, castle.id)
            enabled = bool(econ and econ.port_enabled)
            body += f"⚓ <b>اسکله</b>\nوضعیت: {'فعال' if enabled else 'این قلعه بندر ندارد'}\nسطح: {econ.port_level if econ else 0}/15\nتولید هفتگی هر نوع کشتی: {econ.port_level if enabled and econ else 0}\nهزینه ارتقا: 💰 1,500 + 🪵 1,000"
            buttons = []
            if enabled and econ and econ.port_level < 15:
                buttons.append([InlineKeyboardButton(text="⬆️ ارتقای اسکله", callback_data="ui:port:upgrade")])
            buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:army")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        elif action == "trade":
            body += "🤝 <b>تجارت</b>\nپیشنهادهای دریافتی و ارسال پیشنهاد جدید:"
            offers = (await session.scalars(select(TradeOffer).where(TradeOffer.recipient_lord_id==lord.id,TradeOffer.status=="pending").order_by(TradeOffer.id.desc()).limit(8))).all()
            sent_offers = (await session.scalars(select(TradeOffer).where(TradeOffer.sender_lord_id==lord.id,TradeOffer.status=="pending").order_by(TradeOffer.id.desc()).limit(8))).all()
            buttons = []
            for offer in offers:
                buttons.append([
                    InlineKeyboardButton(text=f"✅ پذیرش #{offer.id}",callback_data=f"trade:accept:{offer.id}"),
                    InlineKeyboardButton(text="❌ رد",callback_data=f"trade:reject:{offer.id}"),
                ])
            for offer in sent_offers:
                buttons.append([InlineKeyboardButton(text=f"❌ لغو پیشنهاد ارسالی #{offer.id}",callback_data=f"ui:tradecancel:{offer.id}")])
            buttons.append([InlineKeyboardButton(text="➕ ایجاد پیشنهاد تجارت", callback_data="ui:trade:new")])
            buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        elif action == "war":
            body += "🚩 <b>لشکرکشی زمینی: THE WAR OF WESTEROS</b>\nزمان رسیدن برآوردی است و با توقف جهان ثابت می‌ماند."
            buttons = [[InlineKeyboardButton(text="⚔️ لشکرکشی زمینی", callback_data="ui:war:new")],
                       [InlineKeyboardButton(text="🎭 لشکرکشی نمایشی (هفته‌ای یک‌بار)", callback_data="ui:war:fake")]]
            econ = await session.get(CastleEconomyState, castle.id)
            if econ and econ.port_enabled:
                buttons.append([InlineKeyboardButton(text="🚢 لشکرکشی دریایی", callback_data="ui:war:sea")])
            rows = (await session.scalars(select(WarExpedition).where(
                or_(WarExpedition.attacker_lord_id==lord.id,WarExpedition.target_castle_id==castle.id)
            ).order_by(WarExpedition.id.desc()).limit(12))).all()
            submitted = set((await session.scalars(select(WarScenario.expedition_id).where(WarScenario.lord_id==lord.id))).all())
            for row in rows:
                body += f"\n\n#{row.id} → قلعه {row.target_castle_id} | {row.status} | رسیدن: {row.arrival_at:%Y-%m-%d %H:%M UTC}" if row.arrival_at else f"\n#{row.id} | {row.status}"
                if row.attacker_lord_id==lord.id and row.status == "arrived" and not row.command:
                    buttons.append([InlineKeyboardButton(text=f"دستور لشکر #{row.id}", callback_data=f"ui:arrival:{row.id}")])
                if row.command == "attack" and row.status == "resolving" and row.id not in submitted:
                    buttons.append([InlineKeyboardButton(text=f"📜 ارسال سناریو برای #{row.id}", callback_data=f"ui:scenario:{row.id}")])
            buttons.append([InlineKeyboardButton(text="🎲 ارسال رول", callback_data="ui:roll")])
            buttons.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data="menu:back")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        elif action == "help":
            body += "از دکمه‌ها برای دارایی، تولید، کمپ، تجارت و لشکرکشی استفاده کن. تعیین لرد و اتصال گروه قلعه فقط توسط مالک اصلی انجام می‌شود."
    try:
        await call.message.edit_text(body, reply_markup=markup)
    except Exception:
        await call.message.answer(body, reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("ui:") & ~F.data.startswith("ui:warfinal:"))
async def ui_callback(call: CallbackQuery, session_factory, state: FSMContext, bot):
    if not call.message or not call.from_user:
        await call.answer()
        return
    parts = (call.data or "").split(":")
    action = parts[1] if len(parts)>1 else ""
    try:
        if action in ("workshop","port") and len(parts)==2:
            await render_player_section(call, session_factory, action)
            return
        if action in ("assets","buildings","camps","army","trade","war","help") and len(parts)==2:
            await render_player_section(call, session_factory, action)
            return
        if action == "trade" and len(parts)>2 and parts[2]=="new":
            async with session_factory() as session:
                lord, castle = await _player(session,call.from_user.id,call.message.chat.id)
                rows=(await session.execute(select(Castle,Lord).join(Lord,Lord.castle_id==Castle.id).where(Castle.active.is_(True),Lord.status=="active",Lord.id!=lord.id).order_by(Castle.name))).all()
            if not rows: raise ValueError("قلعه دیگری با لرد فعال برای تجارت وجود ندارد.")
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🏰 {c.name}",callback_data=f"ui:trade:target:{l.id}")] for c,l in rows]+[[InlineKeyboardButton(text="لغو",callback_data="menu:trade")]])
            await call.message.edit_text("قلعه مقصد تجارت را انتخاب کن:",reply_markup=kb); await call.answer(); return
        if action=="tradecancel" and len(parts)==3:
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                offer=await session.scalar(select(TradeOffer).where(TradeOffer.id==int(parts[2])).with_for_update())
                if not offer or offer.sender_lord_id!=lord.id or offer.status!="pending": raise ValueError("فقط پیشنهاد معلق خودت را می‌توانی لغو کنی.")
                offer.status="cancelled"
                await audit(session,call.from_user.id,"trade_offer_cancelled",str(offer.id))
            await call.message.edit_text(f"پیشنهاد تجارت #{parts[2]} لغو شد.",reply_markup=_back());await call.answer();return
        if action=="trade" and len(parts)==4 and parts[2]=="target":
            async with session_factory() as session:
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                target=await session.get(Lord,int(parts[3]))
                if not target or target.id==lord.id: raise ValueError("لرد مقصد معتبر نیست.")
                balances=await get_balances(session,lord.id)
            await state.update_data(trade_target=target.telegram_user_id)
            await state.set_state(UIFlow.trade_offer)
            await call.message.edit_text("منابعی که می‌خواهی ارسال کنی را وارد کن. نمونه: wood=100,grain=50\nموجودی تو:\n"+", ".join(f"{k}={int(v)}" for k,v in balances.items()))
            await call.answer(); return
        if action=="war" and len(parts)==3 and parts[2] in ("new","fake","sea"):
            kind="sea" if parts[2]=="sea" else "land"
            async with session_factory() as session:
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                if kind=="sea":
                    econ=await session.get(CastleEconomyState,castle.id)
                    if not econ or not econ.port_enabled: raise ValueError("این قلعه بندر فعال ندارد.")
                targets=(await session.scalars(select(Castle).where(Castle.active.is_(True),Castle.id!=castle.id).order_by(Castle.name))).all()
            await state.update_data(war_type=kind,war_fake=parts[2]=="fake")
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🏰 {c.name}",callback_data=f"ui:war:target:{c.id}")] for c in targets]+[[InlineKeyboardButton(text="لغو",callback_data="menu:war")]])
            await call.message.edit_text("قلعه مقصد را انتخاب کن:",reply_markup=kb); await call.answer(); return
        if action=="war" and len(parts)==4 and parts[2]=="target":
            async with session_factory() as session:
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                target=await session.get(Castle,int(parts[3]))
                if not target or not target.active: raise ValueError("مقصد معتبر نیست.")
                army=(await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id))).all()
                gear=(await session.scalars(select(EquipmentItem).where(EquipmentItem.castle_id==castle.id))).all()
                fleet=(await session.scalars(select(FleetShip).where(FleetShip.castle_id==castle.id))).all()
                available={"army":{r.unit_key:r.count for r in army},"equipment":{r.item_key:r.count for r in gear},"fleet":{r.ship_key:r.count for r in fleet}}
            await state.update_data(war_target=target.name,war_available=available)
            await state.set_state(UIFlow.war_assets)
            await call.message.edit_text("نیرو و ادوات را وارد کن. نمونه: army:swordsman=100,archer=20;equipment:ladder=2\nموجودی قابل اعزام: "+str(available))
            await call.answer(); return
        if action=="arrival" and len(parts)==3:
            expedition_id=int(parts[2])
            async with session_factory() as session:
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                row=await session.get(WarExpedition,expedition_id)
                if not row or row.attacker_lord_id!=lord.id or row.status!="arrived": raise ValueError("این لشکر متعلق به تو نیست یا هنوز نرسیده است.")
            kb=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚔️ دستور حمله",callback_data=f"ui:command:{expedition_id}:attack"),
                 InlineKeyboardButton(text="🏰 دستور محاصره",callback_data=f"ui:command:{expedition_id}:siege")],
                [InlineKeyboardButton(text="🏕 اردوگاه",callback_data=f"ui:camp:{expedition_id}")]])
            await call.message.edit_text(f"لشکر #{expedition_id} به مقصد رسیده. دستور را انتخاب کن:",reply_markup=kb); await call.answer(); return
        if action=="command" and len(parts)==4:
            expedition_id=int(parts[2]); command=parts[3]
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                row=await issue_war_command(session,expedition_id,lord,command)
                await audit(session,call.from_user.id,"war_command_issued",str(row.id),command)
            kb=None
            if command=="attack":
                kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📜 ارسال سناریو",callback_data=f"ui:scenario:{expedition_id}")]])
                async with session_factory() as session:
                    target_group=await session.scalar(select(GroupRegistration).where(GroupRegistration.castle_id==row.target_castle_id,GroupRegistration.enabled.is_(True)))
                    target_castle=await session.get(Castle,row.target_castle_id)
                if target_group:
                    await bot.send_message(target_group.telegram_chat_id,
                        f"⚔️ دستور حمله برای لشکر #{expedition_id} به قلعه {target_castle.name} ثبت شد. مدافع می‌تواند سناریوی خود را ارسال کند.",
                        reply_markup=kb)
            await call.message.edit_text(f"دستور {command} برای لشکر #{expedition_id} ثبت شد.",reply_markup=kb); await call.answer(); return
        if action=="camp" and len(parts)==3:
            eid=int(parts[2])
            kb=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🤝 الحاق به نیروهای مقصد",callback_data=f"ui:campchoice:{eid}:join")],
                [InlineKeyboardButton(text="🛡 استقرار در قلعه",callback_data=f"ui:campchoice:{eid}:station")]])
            await call.message.edit_text("نوع اردوگاه را انتخاب کن:",reply_markup=kb); await call.answer(); return
        if action=="campchoice" and len(parts)==4:
            eid=int(parts[2]); choice="transfer" if parts[3]=="join" else "garrison"
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                row=await set_arrival_choice(session,eid,lord,choice)
                await audit(session,call.from_user.id,"war_camp_choice",str(row.id),choice)
            await call.message.edit_text(f"تصمیم اردوگاه برای لشکر #{eid} ثبت شد."); await call.answer(); return
        if action=="scenario" and len(parts)==3:
            eid=int(parts[2])
            async with session_factory() as session:
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                row=await session.get(WarExpedition,eid)
                if not row or row.command!="attack" or row.status!="resolving": raise ValueError("برای این لشکر ارسال سناریو فعال نیست.")
            await state.update_data(scenario_expedition=eid); await state.set_state(UIFlow.scenario_text)
            await call.message.answer("متن سناریوی نبرد را ارسال کن (حداکثر ۸۰۰۰ نویسه).")
            await call.answer(); return
        if action=="roll":
            await state.set_state(UIFlow.roll_text)
            await call.message.answer("متن رول را ارسال کن. محدودیت ارسال برای هر لرد طبق بازه زمانی تنظیم‌شده اعمال می‌شود.")
            await call.answer(); return
        if action=="equipment" and len(parts)==3:
            key=parts[2]
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                d,item=await build_equipment(session,lord,key)
                await audit(session,call.from_user.id,"equipment_built",str(castle.id),key)
            await call.message.edit_text(f"✅ {d['label']} ساخته شد. موجودی: {item:,}",reply_markup=_back()); await call.answer(); return
        if action=="workshop" and len(parts)==3 and parts[2]=="upgrade":
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                level=await upgrade_workshop(session,lord)
                await audit(session,call.from_user.id,"workshop_upgraded",str(castle.id),str(level))
            await call.message.edit_text(f"کارگاه به سطح {level}/5 ارتقا یافت.",reply_markup=_back()); await call.answer(); return
        if action=="port" and len(parts)==3 and parts[2]=="upgrade":
            async with session_factory() as session,session.begin():
                lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
                level=await upgrade_port(session,lord)
                await audit(session,call.from_user.id,"port_upgraded",str(castle.id),str(level))
            await call.message.edit_text(f"اسکله به سطح {level}/15 ارتقا یافت.",reply_markup=_back()); await call.answer(); return
        await call.answer("عملیات نامعتبر است.",show_alert=True)
    except (ValueError,TypeError) as exc:
        await call.answer(str(exc),show_alert=True)


@router.message(UIFlow.trade_offer)
async def trade_offer_input(message: Message,state:FSMContext,session_factory):
    try:
        offered=_parse_quantities(message.text or "")
        await state.update_data(trade_offered=offered)
        data=await state.get_data()
        async with session_factory() as session:
            lord,castle=await _player(session,message.from_user.id,message.chat.id)
            balances=await get_balances(session,lord.id)
            recipient=await get_lord(session,int(data["trade_target"]))
            target_balances=await get_balances(session,recipient.id) if recipient else {}
        await state.set_state(UIFlow.trade_request)
        await message.answer("اکنون منابعی را که در مقابل می‌خواهی دریافت کنی وارد کن. نمونه: iron=20,stone=50\nموجودی تو: "+", ".join(f"{k}={int(v)}" for k,v in balances.items())+"\nموجودی فعلی قلعه مقصد: "+", ".join(f"{k}={int(v)}" for k,v in target_balances.items()))
    except ValueError as exc: await message.answer(str(exc))


@router.message(UIFlow.trade_request)
async def trade_request_input(message:Message,state:FSMContext,session_factory,bot):
    try:
        requested=_parse_quantities(message.text or "")
        data=await state.get_data()
        async with session_factory() as session,session.begin():
            lord,castle=await _player(session,message.from_user.id,message.chat.id)
            offer=await create_trade_bundle(session,lord,int(data["trade_target"]),data["trade_offered"],requested)
            recipient=await get_lord(session,int(data["trade_target"]))
            await audit(session,message.from_user.id,"trade_bundle_created",str(offer.id))
        await state.clear()
        await message.answer(f"✅ پیشنهاد تجارت #{offer.id} برای {escape(recipient.display_name)} ثبت شد.")
        if get_settings().trade_log_chat_id:
            await bot.send_message(get_settings().trade_log_chat_id,f"پیشنهاد #{offer.id}: {data['trade_offered']} در برابر {requested}")
    except ValueError as exc: await message.answer(str(exc))


@router.message(UIFlow.war_assets)
async def war_assets_input(message:Message,state:FSMContext):
    try:
        raw=(message.text or "").strip()
        assets={"army":{},"equipment":{},"fleet":{}}
        for section in raw.split(";"):
            if not section.strip(): continue
            kind,sep,items=section.partition(":")
            if not sep or kind not in assets: raise ValueError("قالب: army:swordsman=10;equipment:ladder=1")
            parsed={}
            for item in items.split(","):
                key,eq,value=item.strip().partition("=")
                if not eq: raise ValueError("قالب هر دارایی باید key=count باشد.")
                try: count=int(value.strip())
                except ValueError: raise ValueError("تعداد دارایی باید عدد صحیح باشد.")
                if count<=0 or count>1000000: raise ValueError("تعداد باید بین ۱ تا ۱۰۰۰۰۰۰ باشد.")
                parsed[key.strip()]=count
            assets[kind]=parsed
        if not any(assets.values()): raise ValueError("حداقل یک نیرو یا ادوات وارد کن.")
        data=await state.get_data()
        available=data["war_available"]
        for kind,items in assets.items():
            for key,count in items.items():
                if count>int(available.get(kind,{}).get(key,0)): raise ValueError(f"موجودی {key} کافی نیست.")
        if data.get("war_type")=="land" and assets["fleet"]: raise ValueError("در لشکرکشی زمینی نمی‌توان کشتی انتخاب کرد.")
        await state.update_data(war_assets=assets)
        await state.set_state(UIFlow.war_duration)
        await message.answer("مدت سفر را به شکل ساعت:دقیقه وارد کن؛ نمونه 1:30. عدد دقیقه هم پذیرفته می‌شود.")
    except ValueError as exc: await message.answer(str(exc))


@router.message(UIFlow.war_duration)
async def war_duration_input(message:Message,state:FSMContext):
    try:
        raw=(message.text or "").strip()
        if ":" in raw:
            hours,minutes=(int(part) for part in raw.split(":",1))
            if hours<0 or not 0<=minutes<60: raise ValueError("قالب زمان باید ساعت:دقیقه باشد؛ نمونه 1:30")
            duration=hours*60+minutes
        else:
            duration=int(raw)
        if not 1<=duration<=10080: raise ValueError("مدت باید بین ۱ دقیقه تا ۱۶۸ ساعت باشد.")
        await state.update_data(war_duration=duration)
        data=await state.get_data()
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👑 لرد همراه باشد",callback_data="ui:warfinal:yes:no"),
             InlineKeyboardButton(text="بدون حضور لرد",callback_data="ui:warfinal:no:no")],
            [InlineKeyboardButton(text="👑 همراه + بازگشت خودکار",callback_data="ui:warfinal:yes:yes"),
             InlineKeyboardButton(text="بدون لرد + بازگشت خودکار",callback_data="ui:warfinal:no:yes")],
            [InlineKeyboardButton(text="لغو",callback_data="menu:war")]])
        await message.answer(f"مقصد: {data['war_target']}\nمدت: {duration//60} ساعت و {duration%60} دقیقه\nحضور لرد و بازگشت خودکار پس از رسیدن را انتخاب کن:",reply_markup=kb)
    except ValueError as exc: await message.answer(str(exc))

@router.callback_query(F.data.startswith("ui:warfinal:"))
async def war_final(call:CallbackQuery,state:FSMContext,session_factory,bot):
    if not call.from_user or not call.message: await call.answer();return
    data=await state.get_data()
    if not data.get("war_target"): await call.answer("فرایند منقضی شده است.",show_alert=True);return
    parts=(call.data or "").split(":")
    lord_present=len(parts)>2 and parts[2]=="yes"
    return_after=len(parts)>3 and parts[3]=="yes"
    try:
        async with session_factory() as session,session.begin():
            lord,castle=await _player(session,call.from_user.id,call.message.chat.id)
            fake=bool(data.get("war_fake"))
            row=await launch_expedition(session,lord,data["war_target"],data["war_type"],int(data["war_duration"]),data["war_assets"],lord_present=lord_present,fake=fake,return_after_arrival=return_after)
            await audit(session,call.from_user.id,"fake_expedition_created" if fake else "war_expedition_launched",str(row.id))
            target=await session.get(Castle,row.target_castle_id)
        await state.clear()
        await call.message.edit_text(f"🚩 لشکرکشی #{row.id} ثبت شد\n{castle.name} → {target.name}\nرسیدن برآوردی: {row.arrival_at:%Y-%m-%d %H:%M UTC}\n{'نمایشی؛ دارایی کسر نشد.' if fake else 'دارایی‌ها از موجودی مبدأ کسر شدند.'}")
        await call.answer("ثبت شد")
        if get_settings().war_log_chat_id: await bot.send_message(get_settings().war_log_chat_id,f"لشکرکشی #{row.id}: {castle.name} → {target.name}")
    except ValueError as exc: await call.answer(str(exc),show_alert=True)


@router.message(UIFlow.scenario_text)
async def scenario_input(message:Message,state:FSMContext,session_factory):
    data=await state.get_data()
    try:
        async with session_factory() as session,session.begin():
            lord,castle=await _player(session,message.from_user.id,message.chat.id)
            item=await submit_scenario(session,int(data["scenario_expedition"]),lord,message.text or "")
            await audit(session,message.from_user.id,"war_scenario_submitted",str(item.id))
        await state.clear(); await message.answer(f"📜 سناریو برای نبرد #{item.expedition_id} ثبت شد.")
    except ValueError as exc: await message.answer(str(exc))


@router.message(UIFlow.roll_text)
async def roll_input(message:Message,state:FSMContext,session_factory,bot):
    raw=(message.text or "").strip()
    if not raw or len(raw)>4000: await message.answer("متن رول باید بین ۱ تا ۴۰۰۰ نویسه باشد.");return
    try:
        async with session_factory() as session,session.begin():
            lord,castle=await _player(session,message.from_user.id,message.chat.id)
            controls=await get_controls(session)
            row=await session.get(GameSetting,"roll_submissions",with_for_update=True)
            values=dict(row.value or {}) if row else {}
            key=str(lord.id); now=datetime.now(timezone.utc)
            previous=values.get(key)
            interval=int(controls["roll_interval_hours"])
            if previous:
                last=datetime.fromisoformat(previous["created_at"])
                remaining=timedelta(hours=interval)-(now-last)
                if remaining.total_seconds()>0: raise ValueError(f"ارسال رول بعد از {int(remaining.total_seconds()//3600)} ساعت و {int((remaining.total_seconds()%3600)//60)} دقیقه مجاز است.")
            values[key]={"lord_name":lord.display_name,"text":raw,"created_at":now.isoformat(),"castle_id":castle.id}
            if row: row.value=values
            else: session.add(GameSetting(key="roll_submissions",value=values))
            await audit(session,message.from_user.id,"lord_roll_submitted",str(lord.id))
        await state.clear(); await message.answer("🎲 رول ثبت شد.")
        destination=get_settings().admin_audit_chat_id or get_settings().admin_chat_id
        if destination:
            await bot.send_message(destination,f"🎲 <b>رول جدید</b>\nلرد: {escape(lord.display_name)}\nقلعه: {escape(castle.name)}\nمتن: {escape(raw)}")
    except ValueError as exc: await message.answer(str(exc))


@router.callback_query(F.data.startswith("adminui:"))
async def admin_ui(call:CallbackQuery,session_factory,state:FSMContext,bot):
    cfg=get_settings()
    if not call.message or not _admin(call.from_user.id if call.from_user else None,call.message.chat,cfg):
        await call.answer("فقط مالک اصلی در گروه مدیریت مجاز است.",show_alert=True);return
    action=(call.data or "").split(":")[1:]
    try:
        if action[0]=="weekly":
            async with session_factory() as session,session.begin():
                result=await weekly_settlement(session,force=True)
                await audit(session,call.from_user.id,"admin_weekly_settlement","world",str(result))
            await call.message.edit_text(f"تولید هفتگی انجام شد. قلعه‌های پردازش‌شده: {result.get('processed',0)}",reply_markup=admin_menu());await call.answer();return
        if action[0]=="toggle" and len(action)==2:
            field=action[1]
            mapping={"expeditions":"expeditions_open","trades":"trades_open","castle":"castle_selection_open"}
            if field not in mapping: raise ValueError("تنظیم نامعتبر است.")
            async with session_factory() as session,session.begin():
                controls=await get_controls(session); value=not bool(controls[mapping[field]])
                await update_controls(session,**{mapping[field]:value})
                await audit(session,call.from_user.id,"admin_control_changed",field,str(value))
            await call.answer("وضعیت به‌روزرسانی شد.")
            await call.message.edit_text(await _admin_panel_text(session_factory),reply_markup=admin_menu());return
        if action[0]=="deadlines":
            await state.set_state(UIFlow.admin_deadlines)
            await call.message.answer("سه عدد را به ترتیب وارد کن: مهلت دستور لشکرکشی به دقیقه، مهلت سناریو به ساعت، فاصله رول به ساعت. نمونه: 90 24 48")
            await call.answer();return
        if action[0]=="rollback" and len(action)==2:
            offer_id=int(action[1])
            async with session_factory() as session:
                offer=await session.get(TradeOffer,offer_id)
                if not offer or offer.status!="completed": raise ValueError("فقط معامله تکمیل‌شده را می‌توان برگرداند.")
                sender=await session.get(Lord,offer.sender_lord_id)
                recipient=await session.get(Lord,offer.recipient_lord_id)
            kb=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ تأیید بازگردانی",callback_data=f"adminui:rollbackconfirm:{offer_id}")],
                [InlineKeyboardButton(text="انصراف",callback_data="adminui:trades")]])
            await call.message.edit_text(
                f"بازگردانی معامله #{offer_id}؟\\n{sender.display_name} ↔ {recipient.display_name}\\nاین کار موجودی دو طرف را معکوس می‌کند و فقط در صورت کافی بودن موجودی فعلی انجام می‌شود.",
                reply_markup=kb)
            await call.answer();return
        if action[0]=="rollbackconfirm" and len(action)==2:
            offer_id=int(action[1])
            async with session_factory() as session,session.begin():
                offer=await session.scalar(select(TradeOffer).where(TradeOffer.id==offer_id).with_for_update())
                if not offer or offer.status!="completed": raise ValueError("فقط معامله تکمیل‌شده را می‌توان برگرداند.")
                sender=await session.get(Lord,offer.sender_lord_id); recipient=await session.get(Lord,offer.recipient_lord_id)
                offered=offer.offered_assets or {offer.offered_resource:offer.offered_amount}
                requested=offer.requested_assets or {offer.requested_resource:offer.requested_amount}
                ids=sorted([sender.id,recipient.id])
                rows=(await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id.in_(ids)).order_by(ResourceBalance.lord_id,ResourceBalance.resource_code).with_for_update())).all()
                lookup={(r.lord_id,r.resource_code):r for r in rows}
                for code,amount in offered.items():
                    src=lookup.get((recipient.id,code)); dst=lookup.get((sender.id,code)); n=Decimal(str(amount))
                    if not src or not dst or src.amount<n: raise ValueError(f"بازگردانی ممکن نیست؛ موجودی {code} نزد گیرنده کافی نیست.")
                    src.amount-=n; dst.amount+=n
                for code,amount in requested.items():
                    src=lookup.get((sender.id,code)); dst=lookup.get((recipient.id,code)); n=Decimal(str(amount))
                    if not src or not dst or src.amount<n: raise ValueError(f"بازگردانی ممکن نیست؛ موجودی {code} نزد فرستنده کافی نیست.")
                    src.amount-=n; dst.amount+=n
                offer.status="cancelled"
                await audit(session,call.from_user.id,"trade_rolled_back",str(offer.id))
            await call.message.edit_text(f"معامله #{offer_id} برگردانده شد.",reply_markup=admin_menu());await call.answer();return
        if action[0]=="trades":
            async with session_factory() as session:
                castles=(await session.scalars(select(Castle).order_by(Castle.region,Castle.name))).all()
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🏰 {c.name}",callback_data=f"adminui:tradecastle:{c.id}")] for c in castles]+[[InlineKeyboardButton(text="↩️ پنل",callback_data="adminui:home")]])
            await call.message.edit_text("گزارش تجارت را برای کدام قلعه می‌خواهی؟",reply_markup=kb);await call.answer();return
        if action[0]=="tradecastle" and len(action)==2:
            castle_id=int(action[1])
            async with session_factory() as session:
                lord_ids=(await session.scalars(select(Lord.id).where(Lord.castle_id==castle_id))).all()
                rows=(await session.scalars(select(TradeOffer).where(
                    TradeOffer.status=="completed",
                    (TradeOffer.sender_lord_id.in_(lord_ids)) | (TradeOffer.recipient_lord_id.in_(lord_ids))
                ).order_by(TradeOffer.id.desc()).limit(20))).all()
                castle=await session.get(Castle,castle_id)
            lines=[f"گزارش معاملات قلعه {castle.name if castle else castle_id}:"]
            for item in rows:
                lines.append(f"#{item.id} | {item.sender_lord_id} → {item.recipient_lord_id} | {item.offered_assets or {item.offered_resource:item.offered_amount}} ↔ {item.requested_assets or {item.requested_resource:item.requested_amount}}")
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"↩️ بازگردانی معامله #{item.id}",callback_data=f"adminui:rollback:{item.id}")] for item in rows]+[[InlineKeyboardButton(text="⬅️ قلعه‌ها",callback_data="adminui:trades")]])
            await call.message.edit_text("\\n".join(lines) if rows else lines[0]+"\\nمعامله تکمیل‌شده‌ای وجود ندارد.",reply_markup=kb);await call.answer();return
        if action[0]=="home":
            await call.message.edit_text(await _admin_panel_text(session_factory),reply_markup=admin_menu());await call.answer();return
        await call.answer("عملیات نامعتبر است.",show_alert=True)
    except (ValueError,TypeError) as exc: await call.answer(str(exc),show_alert=True)


async def _admin_panel_text(session_factory):
    async with session_factory() as session:
        controls=await get_controls(session)
        from bot.services import is_world_paused
        paused=await is_world_paused(session)
    return ("🔐 <b>مرکز فرماندهی جهان</b>\n"
            f"وضعیت جهان: {'متوقف' if paused else 'در حال اجرا'}\n"
            f"لشکرکشی: {'باز' if controls['expeditions_open'] else 'قفل'} | تجارت: {'باز' if controls['trades_open'] else 'قفل'}\n"
            f"انتخاب قلعه: {'باز' if controls['castle_selection_open'] else 'قفل'}\n"
            f"مهلت دستور: {controls['expedition_order_minutes']} دقیقه | سناریو: {controls['scenario_deadline_hours']} ساعت | رول: {controls['roll_interval_hours']} ساعت")


@router.message(UIFlow.admin_deadlines)
async def admin_deadlines_input(message:Message,state:FSMContext,session_factory):
    cfg=get_settings()
    if not _admin(message.from_user.id if message.from_user else None,message.chat,cfg):
        await state.clear();return
    try:
        values=[int(x) for x in (message.text or "").split()]
        if len(values)!=3 or not (1<=values[0]<=10080 and 1<=values[1]<=168 and 1<=values[2]<=720):
            raise ValueError("مقادیر نامعتبر است. نمونه: 90 24 48")
        async with session_factory() as session,session.begin():
            await update_controls(session,expedition_order_minutes=values[0],scenario_deadline_hours=values[1],roll_interval_hours=values[2])
            await audit(session,message.from_user.id,"admin_deadlines_updated","world",str(values))
        await state.clear();await message.answer("مهلت‌ها ذخیره شدند.")
    except ValueError as exc: await message.answer(str(exc))
