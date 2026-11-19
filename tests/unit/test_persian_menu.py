from bot.keyboards import main_menu


def test_main_menu_uses_functional_persian_sections():
    menu = main_menu()
    labels = [button.text for row in menu.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in menu.inline_keyboard for button in row]
    assert "👑 پروفایل و دارایی‌ها" in labels
    assert "🏗 ساختمان‌ها" in labels
    assert "⚔️ کمپ‌ها" in labels
    assert "🛡 ارتش و ادوات" in labels
    assert "🤝 تجارت" in labels
    assert "🚩 لشکرکشی" in labels
    assert "📣 اعلان‌ها" not in labels
    assert "menu:assets" in callbacks
    assert "menu:army" in callbacks
    assert "menu:war" in callbacks


def test_superadmin_button_is_only_shown_for_owner_menu():
    normal = [b.callback_data for row in main_menu().inline_keyboard for b in row]
    owner = [b.callback_data for row in main_menu(is_admin=True).inline_keyboard for b in row]
    assert "menu:admin" not in normal
    assert "menu:admin" in owner
