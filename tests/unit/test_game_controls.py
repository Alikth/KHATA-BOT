from unittest.mock import AsyncMock
import pytest

from bot.game.controls import DEFAULT_CONTROLS, get_controls, update_controls


@pytest.mark.asyncio
async def test_controls_use_safe_defaults_when_no_admin_settings_exist():
    session = type("Session", (), {"get": AsyncMock(return_value=None)})()
    values = await get_controls(session)
    assert values == DEFAULT_CONTROLS


@pytest.mark.asyncio
async def test_admin_can_update_and_persist_game_controls():
    row = type("Setting", (), {"value": dict(DEFAULT_CONTROLS)})()
    session = type("Session", (), {"get": AsyncMock(return_value=row), "add": lambda self, item: None})()
    values = await update_controls(session, trades_open=False, roll_interval_hours=72)
    assert values["trades_open"] is False
    assert values["roll_interval_hours"] == 72
    assert row.value == values
