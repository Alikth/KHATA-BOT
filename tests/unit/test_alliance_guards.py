from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.game.warfare import answer_alliance


@pytest.mark.asyncio
async def test_alliance_response_requires_linked_resolving_expedition():
    alliance = SimpleNamespace(
        id=3, owner_b_lord_id=22, status="pending",
        war_expedition_id=9, responded_at=None,
    )
    expedition = SimpleNamespace(id=9, status="completed")
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[alliance, expedition]),
    )

    with pytest.raises(ValueError, match="لشکر مرتبط"):
        await answer_alliance(session, 3, SimpleNamespace(id=22), True)

    assert alliance.status == "pending"
