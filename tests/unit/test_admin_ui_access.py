from types import SimpleNamespace

from bot.handlers.ui import _admin


OWNER_ID = 987654321
ADMIN_CHAT_ID = -1004475496519
CONFIG = SimpleNamespace(bot_owner_id=OWNER_ID, admin_chat_id=ADMIN_CHAT_ID)


def test_admin_ui_authorizes_owner_in_configured_admin_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_CHAT_ID)
    assert _admin(OWNER_ID, chat, CONFIG) is True


def test_admin_ui_authorizes_owner_in_private_chat():
    chat = SimpleNamespace(type="private", id=OWNER_ID)
    assert _admin(OWNER_ID, chat, CONFIG) is True


def test_admin_ui_authorizes_owner_in_player_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_CHAT_ID - 1)
    assert _admin(OWNER_ID, chat, CONFIG) is True


def test_admin_ui_rejects_non_owner_in_admin_group():
    chat = SimpleNamespace(type="supergroup", id=ADMIN_CHAT_ID)
    assert _admin(OWNER_ID + 1, chat, CONFIG) is False
