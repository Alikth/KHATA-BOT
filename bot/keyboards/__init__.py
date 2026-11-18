from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👑 پروفایل"), KeyboardButton(text="📦 جمع‌آوری منابع")],
        [KeyboardButton(text="🤝 پیشنهادها"), KeyboardButton(text="📣 اعلان بازیکن")],
        [KeyboardButton(text="ℹ️ راهنما")],
    ], resize_keyboard=True)

def trade_decision(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ پذیرش", callback_data=f"trade:accept:{offer_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"trade:reject:{offer_id}"),
    ]])
