from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    """Persian inline menu; callback identifiers remain language-neutral."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 دارایی و پروفایل", callback_data="menu:assets"),
         InlineKeyboardButton(text="🏗 ساختمان‌ها", callback_data="menu:buildings")],
        [InlineKeyboardButton(text="⚔️ کمپ‌ها و نیروها", callback_data="menu:camps"),
         InlineKeyboardButton(text="🛡 ارتش و ادوات", callback_data="menu:army")],
        [InlineKeyboardButton(text="🤝 تجارت", callback_data="menu:trade"),
         InlineKeyboardButton(text="🚩 لشکرکشی", callback_data="menu:war")],
        [InlineKeyboardButton(text="📣 اعلان‌ها", callback_data="menu:announcements"),
         InlineKeyboardButton(text="ℹ️ راهنما", callback_data="menu:help")],
    ])

def trade_decision(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ پذیرش", callback_data=f"trade:accept:{offer_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"trade:reject:{offer_id}"),
    ]])
