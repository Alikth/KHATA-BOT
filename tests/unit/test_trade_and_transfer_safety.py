from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.services as services
import bot.game.warfare as warfare
from bot.database.models import GarrisonAsset


@pytest.mark.asyncio
async def test_sender_can_cancel_only_their_pending_trade(monkeypatch):
    offer = SimpleNamespace(id=7, status="pending", sender_lord_id=11)
    sender = SimpleNamespace(id=11)
    session = SimpleNamespace(scalar=AsyncMock(return_value=offer))
    monkeypatch.setattr(services, "get_lord", AsyncMock(return_value=sender))

    result = await services.cancel_trade(session, 7, 123)

    assert result is offer
    assert offer.status == "cancelled"


@pytest.mark.asyncio
async def test_non_sender_cannot_cancel_trade(monkeypatch):
    offer = SimpleNamespace(id=7, status="pending", sender_lord_id=11)
    other = SimpleNamespace(id=12)
    session = SimpleNamespace(scalar=AsyncMock(return_value=offer))
    monkeypatch.setattr(services, "get_lord", AsyncMock(return_value=other))

    with pytest.raises(ValueError, match="فقط فرستنده"):
        await services.cancel_trade(session, 7, 456)

    assert offer.status == "pending"


@pytest.mark.asyncio
async def test_accepted_troop_transfer_changes_garrison_owner_to_receiver():
    request = SimpleNamespace(
        id=4, receiver_lord_id=22, sender_lord_id=11, status="pending",
        responded_at=None, expedition_id=9,
        assets={"army": {"swordsman": 5}},
    )
    expedition = SimpleNamespace(
        id=9, target_castle_id=200, origin_castle_id=100,
        attacker_lord_id=11, asset_origin="castle", status="resolving",
    )
    added = []
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[request, None]),
        get=AsyncMock(return_value=expedition),
        add=added.append,
    )
    lord = SimpleNamespace(id=22)

    result = await warfare.answer_transfer(session, 4, lord, True)

    assert result.status == "accepted"
    assert expedition.status == "completed"
    assert len(added) == 1
    assert isinstance(added[0], GarrisonAsset)
    assert added[0].owner_lord_id == 22
    assert added[0].count == 5


@pytest.mark.asyncio
async def test_expedition_cannot_be_cancelled_at_or_after_world_arrival(monkeypatch):
    now = datetime.now(timezone.utc)
    expedition = SimpleNamespace(
        id=3, attacker_lord_id=11, status="travelling", command=None,
        arrival_at=now - timedelta(seconds=1), assets={"army": {"swordsman": 5}},
        units={}, origin_castle_id=100, asset_origin="castle",
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=expedition))
    monkeypatch.setattr(
        "bot.game.engine.advance_world_clock", AsyncMock(return_value=now)
    )

    with pytest.raises(ValueError, match="مهلت لغو تمام شده"):
        await warfare.cancel_expedition(session, 3, SimpleNamespace(id=11))

    assert expedition.status == "travelling"
