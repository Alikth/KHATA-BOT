from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu(is_admin: bool = False):
    """Player navigation only. Admin access is automatic in the configured admin group."""
    rows = [
        [InlineKeyboardButton(text="👑 پروفایل و دارایی‌ها", callback_data="menu:assets"),
         InlineKeyboardButton(text="🏗 ساختمان‌ها", callback_data="menu:buildings")],
        [InlineKeyboardButton(text="⚔️ کمپ‌ها", callback_data="menu:camps"),
         InlineKeyboardButton(text="🛡 ارتش و ادوات", callback_data="menu:army")],
        [InlineKeyboardButton(text="🤝 تجارت", callback_data="menu:trade"),
         InlineKeyboardButton(text="🚩 لشکرکشی", callback_data="menu:war")],
        [InlineKeyboardButton(text="ℹ️ راهنما", callback_data="menu:help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def section_back_menu(is_admin: bool = False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به منوی اصلی", callback_data="menu:back")]
    ])


def admin_menu():
    """Default owner control center shown by /start in the configured admin group."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸ توقف جهان", callback_data="admin:pause"),
         InlineKeyboardButton(text="▶️ شروع / ادامه بازی", callback_data="admin:resume")],
        [InlineKeyboardButton(text="📊 وضعیت جهان", callback_data="admin:status")],
        [InlineKeyboardButton(text="🏰 قلعه‌ها", callback_data="admin:castles"),
         InlineKeyboardButton(text="👑 لردها", callback_data="admin:lords")],
        [InlineKeyboardButton(text="⚔️ جنگ‌ها", callback_data="admin:wars"),
         InlineKeyboardButton(text="🤝 تجارت‌ها", callback_data="admin:trades")],
        [InlineKeyboardButton(text="📜 سناریوها", callback_data="admin:scenarios"),
         InlineKeyboardButton(text="🧾 گزارش‌ها", callback_data="admin:logs")],
        [InlineKeyboardButton(text="🛠 راهنمای مدیریت", callback_data="admin:commands")],
        [InlineKeyboardButton(text="📦 اعمال تولید هفتگی", callback_data="adminui:weekly")],
        [InlineKeyboardButton(text="🔒/🔓 قفل لشکرکشی", callback_data="adminui:toggle:expeditions"),
         InlineKeyboardButton(text="🔒/🔓 قفل تجارت", callback_data="adminui:toggle:trades")],
        [InlineKeyboardButton(text="🏰 قفل انتخاب قلعه", callback_data="adminui:toggle:castle")],
        [InlineKeyboardButton(text="⏱ تنظیم مهلت‌ها", callback_data="adminui:deadlines")],
        [InlineKeyboardButton(text="↩️ گزارش و بازگردانی تجارت", callback_data="adminui:trades")],
        [InlineKeyboardButton(text="⬆️ بازگشت به بالای پنل", callback_data="adminui:home")],
    ])


def trade_decision(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ پذیرش", callback_data=f"trade:accept:{offer_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"trade:reject:{offer_id}"),
    ]])
