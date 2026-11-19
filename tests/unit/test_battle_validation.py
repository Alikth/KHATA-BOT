from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.game.warfare import review_battle, answer_transfer


@pytest.mark.asyncio
async def test_battle_rejects_unknown_attacker_casualty_asset_kind():
    expedition = SimpleNamespace(
        id=12, command="attack", outcome=None, attacker_lord_id=1,
        target_castle_id=20, assets={"army": {"swordsman": 10}},
        units={}, defender_assets={"army": {"archer": 10}},
    )
    defender = SimpleNamespace(id=2)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[expedition, defender]),
        get=AsyncMock(return_value=SimpleNamespace(id=1)),
    )

    with pytest.raises(ValueError, match="نوع دارایی مهاجم"):
        await review_battle(session, 12, "attacker", {"magic": {"dragon": 1}}, {})


@pytest.mark.asyncio
async def test_battle_rejects_non_dictionary_casualty_payload():
    expedition = SimpleNamespace(
        id=12, command="attack", outcome=None, attacker_lord_id=1,
        target_castle_id=20, assets={"army": {"swordsman": 10}},
        units={}, defender_assets={"army": {"archer": 10}},
    )
    defender = SimpleNamespace(id=2)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[expedition, defender]),
        get=AsyncMock(return_value=SimpleNamespace(id=1)),
    )

    with pytest.raises(ValueError, match="ساختار گزارش تلفات"):
        await review_battle(session, 12, "attacker", [], {})


@pytest.mark.asyncio
async def test_transfer_response_requires_matching_resolving_expedition():
    request = SimpleNamespace(
        id=4, receiver_lord_id=22, status="pending", expedition_id=9,
    )
    expedition = SimpleNamespace(id=9, status="completed")
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[request, expedition]),
    )

    with pytest.raises(ValueError, match="سازگار نیست"):
        await answer_transfer(session, 4, SimpleNamespace(id=22), True)

    assert request.status == "pending"
