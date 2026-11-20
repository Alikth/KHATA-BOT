from types import SimpleNamespace

import pytest

from bot.game.warfare import validate_expedition_origin


def test_public_inventory_can_only_be_dispatched_from_lords_own_castle():
    lord = SimpleNamespace(id=10, castle_id=100)

    validate_expedition_origin(lord, 100, use_garrison=False)

    with pytest.raises(ValueError, match="موجودی عمومی"):
        validate_expedition_origin(lord, 200, use_garrison=False)


def test_lord_may_dispatch_only_their_own_garrison_from_another_castle():
    lord = SimpleNamespace(id=10, castle_id=100)

    # The caller must subsequently load GarrisonAsset rows filtered by lord.id.
    validate_expedition_origin(lord, 200, use_garrison=True)
