from bot.config import Settings


def test_defaults_keep_world_paused():
    settings = Settings(bot_token="test-token", database_url="postgresql+asyncpg://u:p@localhost/db")
    assert settings.world_start_paused is True


def test_owner_id_is_numeric():
    settings = Settings(bot_owner_id=987654321)
    assert settings.bot_owner_id == 987654321
