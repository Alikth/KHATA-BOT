from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.game.warfare import answer_alliance


@pytest.mark.asyncio
async def test_target_lord_can_accept_canonical_alliance_when_target_is_castle_a():
    alliance = SimpleNamespace(
        id=3, owner_a_lord_id=22, owner_b_lord_id=11,
        castle_a_id=100, castle_b_id=200, status="pending",
        war_expedition_id=9, responded_at=None,
    )
    expedition = SimpleNamespace(
        id=9, target_castle_id=100, origin_castle_id=200,
        status="resolving", assets={}, units={},
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[alliance, expedition]),
    )

    result = await answer_alliance(session, 3, SimpleNamespace(id=22), True)

    assert result.status == "accepted"
    assert expedition.status == "completed"


@pytest.mark.asyncio
async def test_non_target_lord_cannot_respond_to_canonical_alliance():
    alliance = SimpleNamespace(
        id=3, owner_a_lord_id=22, owner_b_lord_id=11,
        castle_a_id=100, castle_b_id=200, status="pending",
        war_expedition_id=9, responded_at=None,
    )
    expedition = SimpleNamespace(
        id=9, target_castle_id=100, origin_castle_id=200,
        status="resolving", assets={}, units={},
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[alliance, expedition]),
    )

    with pytest.raises(ValueError, match="فقط لرد قلعه مقصد"):
        await answer_alliance(session, 3, SimpleNamespace(id=11), True)

    assert alliance.status == "pending"
