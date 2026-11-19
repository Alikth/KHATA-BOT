from bot.keyboards import admin_menu, main_menu


def test_main_menu_uses_functional_persian_player_sections():
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
    assert all(not callback.startswith("admin:") and callback != "menu:admin" for callback in callbacks)


def test_player_menu_never_exposes_admin_entry_even_if_legacy_flag_is_true():
    callbacks = [b.callback_data for row in main_menu(is_admin=True).inline_keyboard for b in row]
    assert "menu:admin" not in callbacks
    assert not any(callback.startswith("admin:") for callback in callbacks)


def test_admin_panel_is_a_default_control_center_with_operational_sections():
    callbacks = [b.callback_data for row in admin_menu().inline_keyboard for b in row]
    assert {"admin:pause", "admin:resume", "admin:status", "admin:castles",
            "admin:lords", "admin:wars", "admin:trades", "admin:scenarios",
            "admin:logs", "admin:commands"} <= set(callbacks)
