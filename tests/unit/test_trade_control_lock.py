from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.services as services
import bot.game.controls as controls


@pytest.mark.asyncio
async def test_trade_acceptance_is_blocked_when_admin_locks_trading(monkeypatch):
    offer = SimpleNamespace(id=8, status="pending", recipient_lord_id=22)
    recipient = SimpleNamespace(id=22)
    session = SimpleNamespace(scalar=AsyncMock(return_value=offer))
    monkeypatch.setattr(services, "get_lord", AsyncMock(return_value=recipient))
    monkeypatch.setattr(controls, "get_controls", AsyncMock(return_value={"trades_open": False}))

    with pytest.raises(ValueError, match="قفل"):
        await services.resolve_trade(session, 8, 123, True)

    assert offer.status == "pending"


@pytest.mark.asyncio
async def test_rejecting_existing_trade_remains_available_when_trading_is_locked(monkeypatch):
    offer = SimpleNamespace(id=8, status="pending", recipient_lord_id=22)
    recipient = SimpleNamespace(id=22)
    session = SimpleNamespace(scalar=AsyncMock(return_value=offer))
    monkeypatch.setattr(services, "get_lord", AsyncMock(return_value=recipient))

    result = await services.resolve_trade(session, 8, 123, False)

    assert result.status == "rejected"
