"""Persistent game controls shared by player actions and the admin panel."""
from bot.database.models import GameSetting

DEFAULT_CONTROLS = {
    "expeditions_open": True,
    "trades_open": True,
    "castle_selection_open": True,
    "expedition_order_minutes": 90,
    "scenario_deadline_hours": 24,
    "roll_interval_hours": 48,
}


async def get_controls(session):
    row = await session.get(GameSetting, "world_controls")
    values = dict(DEFAULT_CONTROLS)
    if row and isinstance(row.value, dict):
        values.update(row.value)
    return values


async def update_controls(session, **changes):
    row = await session.get(GameSetting, "world_controls", with_for_update=True)
    values = await get_controls(session)
    values.update(changes)
    if row is None:
        row = GameSetting(key="world_controls", value=values)
        session.add(row)
    else:
        row.value = values
    return values
