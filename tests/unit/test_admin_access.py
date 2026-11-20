from types import SimpleNamespace

from bot.handlers import _is_admin_actor


OWNER_ID = 987654321
ADMIN_GROUP_ID = -1004475496519
CONFIG = SimpleNamespace(bot_owner_id=OWNER_ID, admin_chat_id=ADMIN_GROUP_ID)


def test_owner_is_superuser_in_admin_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_owner_is_superuser_in_player_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID - 1)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_owner_is_superuser_in_private_chat():
    chat = SimpleNamespace(type="private", id=OWNER_ID)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_other_user_is_never_superuser():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID + 1, chat, CONFIG) is False


def test_owner_id_must_be_configured():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    config = SimpleNamespace(bot_owner_id=0, admin_chat_id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID, chat, config) is False
