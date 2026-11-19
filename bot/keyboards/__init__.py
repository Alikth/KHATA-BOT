from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu(is_admin: bool = False):
    """Single inline navigation; profile stays available and announcements are intentionally omitted."""
    rows = [
        [InlineKeyboardButton(text="👑 پروفایل و دارایی‌ها", callback_data="menu:assets"),
         InlineKeyboardButton(text="🏗 ساختمان‌ها", callback_data="menu:buildings")],
        [InlineKeyboardButton(text="⚔️ کمپ‌ها", callback_data="menu:camps"),
         InlineKeyboardButton(text="🛡 ارتش و ادوات", callback_data="menu:army")],
        [InlineKeyboardButton(text="🤝 تجارت", callback_data="menu:trade"),
         InlineKeyboardButton(text="🚩 لشکرکشی", callback_data="menu:war")],
        [InlineKeyboardButton(text="ℹ️ راهنما", callback_data="menu:help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🔐 پنل سوپرادمین", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def section_back_menu(is_admin: bool = False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به منوی اصلی", callback_data="menu:back")]
    ])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸ توقف جهان", callback_data="admin:pause"),
         InlineKeyboardButton(text="▶️ ادامه جهان", callback_data="admin:resume")],
        [InlineKeyboardButton(text="📊 وضعیت جهان", callback_data="admin:status")],
        [InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="menu:back")],
    ])


def trade_decision(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ پذیرش", callback_data=f"trade:accept:{offer_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"trade:reject:{offer_id}"),
    ]])
