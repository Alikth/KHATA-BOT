from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.game.engine as engine
import bot.services as services


@pytest.mark.asyncio
async def test_trade_offer_is_blocked_when_sender_castle_is_under_siege(monkeypatch):
    sender = SimpleNamespace(id=1, castle_id=100)
    recipient = SimpleNamespace(id=2, castle_id=200)
    monkeypatch.setattr(services, "get_lord", AsyncMock(return_value=recipient))
    monkeypatch.setattr(
        engine, "ensure_castle_not_under_siege",
        AsyncMock(side_effect=ValueError("قلعه در محاصره است")),
    )

    with pytest.raises(ValueError, match="محاصره"):
        await services.create_trade(
            SimpleNamespace(), sender, 222, "wood", 10, "iron", 5
        )


@pytest.mark.asyncio
async def test_siege_guard_rejects_active_siege_and_ignores_completed_one(monkeypatch):
    session = SimpleNamespace(scalar=AsyncMock(return_value=55))
    with pytest.raises(ValueError, match="محاصره"):
        await engine.ensure_castle_not_under_siege(session, 100)

    session.scalar = AsyncMock(return_value=None)
    await engine.ensure_castle_not_under_siege(session, 100)
