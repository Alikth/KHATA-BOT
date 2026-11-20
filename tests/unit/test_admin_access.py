from types import SimpleNamespace

from bot.handlers import _is_admin_actor, _is_admin_panel_chat


OWNER_ID = 987654321
ADMIN_GROUP_ID = -1004475496519
CONFIG = SimpleNamespace(bot_owner_id=OWNER_ID, admin_chat_id=ADMIN_GROUP_ID)


def test_owner_is_admin_in_configured_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_other_user_in_admin_group_is_not_admin():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID + 1, chat, CONFIG) is False


def test_owner_in_private_chat_is_admin():
    chat = SimpleNamespace(type="private", id=OWNER_ID)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_owner_in_player_group_is_admin():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID - 1)
    assert _is_admin_actor(OWNER_ID, chat, CONFIG) is True


def test_non_owner_is_never_admin_even_in_admin_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    assert _is_admin_actor(OWNER_ID + 1, chat, CONFIG) is False


def test_owner_remains_admin_when_admin_group_config_is_missing():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    config = SimpleNamespace(bot_owner_id=OWNER_ID, admin_chat_id=0)
    assert _is_admin_actor(OWNER_ID, chat, config) is True


def test_admin_panel_is_only_rendered_in_configured_admin_group():
    admin_chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID)
    player_chat = SimpleNamespace(type="supergroup", id=ADMIN_GROUP_ID - 1)
    private_chat = SimpleNamespace(type="private", id=OWNER_ID)
    assert _is_admin_panel_chat(OWNER_ID, admin_chat, CONFIG) is True
    assert _is_admin_panel_chat(OWNER_ID, player_chat, CONFIG) is False
    assert _is_admin_panel_chat(OWNER_ID, private_chat, CONFIG) is False
    assert _is_admin_panel_chat(OWNER_ID + 1, admin_chat, CONFIG) is False
