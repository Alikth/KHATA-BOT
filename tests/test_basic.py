from bot.config import Settings

def test_world_starts_paused_by_default():
    assert Settings().world_start_paused is True

def test_settings_accept_numeric_owner_id():
    assert Settings(bot_owner_id=123456).bot_owner_id == 123456
