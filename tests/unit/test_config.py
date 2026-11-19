from bot.config import Settings


def test_defaults_keep_world_paused():
    settings = Settings(bot_token="test-token", database_url="postgresql+asyncpg://u:p@localhost/db")
    assert settings.world_start_paused is True


def test_owner_id_is_numeric():
    settings = Settings(bot_owner_id=987654321)
    assert settings.bot_owner_id == 987654321



def test_empty_optional_chat_ids_are_ignored():
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        _env_file=None,
    )
    assert settings.admin_chat_id == 0
    assert settings.admin_audit_chat_id is None


def test_telegram_proxy_is_optional_and_configurable():
    settings = Settings(telegram_proxy="http://127.0.0.1:2080", _env_file=None)
    assert settings.telegram_proxy == "http://127.0.0.1:2080"
