from bot.config import Settings

def test_world_starts_paused_by_default():
    assert Settings().world_start_paused is True

def test_settings_accept_numeric_owner_id():
    assert Settings(bot_owner_id=123456).bot_owner_id == 123456


def test_application_modules_import_cleanly():
    import bot.main
    import bot.handlers
    import bot.game.assets
    import bot.game.combat
    import bot.game.expeditions
    import bot.game.production
    import bot.game.rules
