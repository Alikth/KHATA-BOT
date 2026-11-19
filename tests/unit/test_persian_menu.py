from bot.keyboards import main_menu


def test_main_menu_uses_persian_inline_buttons():
    menu = main_menu()
    labels = [button.text for row in menu.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in menu.inline_keyboard for button in row]
    assert "👑 دارایی و پروفایل" in labels
    assert "⚔️ کمپ‌ها و نیروها" in labels
    assert "🤝 تجارت" in labels
    assert "🚩 لشکرکشی" in labels
    assert "menu:assets" in callbacks
    assert "menu:camps" in callbacks
