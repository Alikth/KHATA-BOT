"""Authenticated bridge to the KHATA-GAMES Worker.

PostgreSQL remains an independent bot-side database. This module mirrors verified
castle snapshots from D1 and routes supported mutations through the website's
validated domain API. It never creates website user accounts.
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

import aiohttp
from sqlalchemy import select

from bot.config import get_settings
from bot.database.models import (
    Lord, Castle, ResourceBalance, ProductionLevel, CampLevel,
    SpecialCampLevel, ArmyUnit, EquipmentItem, FleetShip, CastleEconomyState,
)

class SiteApiError(RuntimeError):
    pass


def configured() -> bool:
    cfg = get_settings()
    return bool(cfg.site_api_url.strip() and cfg.site_api_secret.strip())


async def _request(method: str, path: str, *, payload: dict | None = None):
    cfg = get_settings()
    if not configured():
        raise SiteApiError("ارتباط امن سایت تنظیم نشده است. SITE_API_URL و SITE_API_SECRET را در تنظیمات بات تعریف کن.")
    base = cfg.site_api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {cfg.site_api_secret}", "Accept": "application/json"}
    timeout = aiohttp.ClientTimeout(total=cfg.site_api_timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as client:
            async with client.request(method, f"{base}{path}", json=payload) as response:
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {}
                if response.status < 200 or response.status >= 300:
                    raise SiteApiError(str(data.get("error") or f"خطای ارتباط با سایت ({response.status})"))
                return data
    except SiteApiError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise SiteApiError("ارتباط با سایت برقرار نشد؛ عملیات انجام نشد و دوباره قابل تلاش است.") from exc


async def assign_lord_on_site(telegram_user_id: int, castle_name: str, assigned_by: int) -> dict:
    await _request("POST", "/api/integration/v1/assign-lord", payload={
        "telegramUserId": str(telegram_user_id),
        "castle": castle_name,
        "assignedBy": str(assigned_by),
    })
    try:
        return await fetch_site_snapshot(telegram_user_id, castle_name)
    except Exception:
        # Do not leave a D1 assignment behind if the initial snapshot cannot be read.
        try:
            await revoke_lord_on_site(telegram_user_id)
        except Exception:
            import logging
            logging.exception("Could not roll back incomplete website lord assignment")
        raise


async def revoke_lord_on_site(telegram_user_id: int) -> None:
    await _request("DELETE", f"/api/integration/v1/assign-lord?telegramUserId={quote(str(telegram_user_id))}")


async def fetch_site_snapshot(telegram_user_id: int, castle_name: str) -> dict:
    data = await _request(
        "GET",
        f"/api/integration/v1/snapshot?telegramUserId={quote(str(telegram_user_id))}&castle={quote(castle_name)}",
    )
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("castle") != castle_name:
        raise SiteApiError("پاسخ موجودی قلعه از سایت معتبر نیست.")
    return snapshot


async def sync_snapshot_to_postgres(session, lord: Lord, snapshot: dict) -> None:
    """Apply a complete D1 snapshot to the bot's local mirror in one PG transaction."""
    if snapshot.get("castle") is None:
        raise SiteApiError("نام قلعه در پاسخ سایت وجود ندارد.")
    castle = await session.get(Castle, lord.castle_id)
    if not castle or castle.name != snapshot["castle"] or castle.region != snapshot.get("region"):
        raise SiteApiError("تطبیق نام یا منطقه قلعه لرد با پاسخ سایت نامعتبر است.")

    resources = snapshot.get("resources") or {}
    rows = (await session.scalars(
        select(ResourceBalance).where(ResourceBalance.lord_id == lord.id).with_for_update()
    )).all()
    existing = {row.resource_code: row for row in rows}
    for key, raw in resources.items():
        value = Decimal(str(raw or 0))
        if value < 0:
            raise SiteApiError(f"موجودی منفی نامعتبر برای {key}")
        if key in existing:
            existing[key].amount = value
        else:
            session.add(ResourceBalance(lord_id=lord.id, resource_code=key, amount=value))

    async def sync_levels(model, field: str, values: dict):
        current = (await session.scalars(
            select(model).where(model.castle_id == lord.castle_id).with_for_update()
        )).all()
        index = {getattr(row, field): row for row in current}
        for key, row in index.items():
            if key not in values:
                row.level = 0
        for key, item in values.items():
            level = int((item or {}).get("level", 0))
            row = index.get(key)
            if row:
                row.level = level
            else:
                session.add(model(castle_id=lord.castle_id, **{field: key}, level=level))

    await sync_levels(ProductionLevel, "production_key", snapshot.get("production") or {})
    await sync_levels(CampLevel, "camp_key", snapshot.get("camps") or {})
    await sync_levels(SpecialCampLevel, "camp_key", snapshot.get("specialCamps") or {})

    async def sync_counts(model, field: str, values: dict):
        current = (await session.scalars(
            select(model).where(model.castle_id == lord.castle_id).with_for_update()
        )).all()
        index = {getattr(row, field): row for row in current}
        for key, row in index.items():
            if key not in values:
                row.count = 0
        for key, raw in values.items():
            count = int(raw or 0)
            if count < 0:
                raise SiteApiError(f"تعداد منفی نامعتبر برای {key}")
            row = index.get(key)
            if row:
                row.count = count
            else:
                session.add(model(castle_id=lord.castle_id, **{field: key}, count=count))

    await sync_counts(ArmyUnit, "unit_key", snapshot.get("army") or {})
    await sync_counts(EquipmentItem, "item_key", snapshot.get("equipment") or {})
    await sync_counts(FleetShip, "ship_key", snapshot.get("fleet") or {})

    economy = await session.get(CastleEconomyState, lord.castle_id, with_for_update=True)
    if economy is None:
        economy = CastleEconomyState(castle_id=lord.castle_id)
        session.add(economy)
    workshop = snapshot.get("workshop") or {}
    port = snapshot.get("port") or {}
    debt = snapshot.get("foodDebt") or {}
    economy.workshop_level = int(workshop.get("level", 0))
    economy.port_enabled = bool(port.get("enabled", False))
    economy.port_level = int(port.get("level", 0))
    economy.food_debt = int(debt.get("grain", 0))
    if debt.get("dueAt"):
        from datetime import datetime
        value = datetime.fromisoformat(str(debt["dueAt"]).replace("Z", "+00:00"))
        economy.food_debt_due_at = value
    else:
        economy.food_debt_due_at = None
    await session.flush()


async def upgrade_on_site(telegram_user_id: int, castle_name: str, category: str, key: str) -> dict:
    import uuid
    result = await _request("POST", "/api/integration/v1/upgrade", payload={
        "telegramUserId": str(telegram_user_id),
        "castle": castle_name,
        "category": category,
        "key": key,
        "operationId": str(uuid.uuid4()),
    })
    snapshot = result.get("snapshot")
    if not isinstance(snapshot, dict):
        raise SiteApiError("ارتقا انجام شد اما تصویر به‌روز قلعه از سایت دریافت نشد.")
    return {"result": result.get("result") or {}, "snapshot": snapshot}



async def fetch_site_events(after_cursor: int = 0) -> dict:
    return await _request("GET", f"/api/integration/v1/events?after={max(0, int(after_cursor))}&limit=100")


async def acknowledge_site_events(cursor: int) -> None:
    await _request("POST", "/api/integration/v1/events/ack", payload={"cursor": max(0, int(cursor))})


async def synchronize_site_events(session_factory) -> int:
    """Consume website change events and refresh assigned castle snapshots in PostgreSQL."""
    if not configured():
        return 0
    from sqlalchemy import select
    from bot.database.models import GameState
    cursor = 0
    async with session_factory() as session:
        state = await session.get(GameState, "site_sync_cursor")
        if state:
            cursor = int((state.value or {}).get("cursor", 0))
    response = await fetch_site_events(cursor)
    events = response.get("events") or []
    if not events:
        await acknowledge_site_events(cursor)
        return 0

    applied = 0
    for event in events:
        castle_name = str(event.get("castle") or "")
        event_id = int(event.get("id") or 0)
        if not castle_name or event_id <= cursor:
            continue
        try:
            async with session_factory() as session, session.begin():
                castle = await session.scalar(select(Castle).where(Castle.name == castle_name))
                if castle:
                    lord = await session.scalar(select(Lord).where(
                        Lord.castle_id == castle.id, Lord.status == "active"
                    ))
                    if lord:
                        snapshot = await fetch_site_snapshot(lord.telegram_user_id, castle_name)
                        await sync_snapshot_to_postgres(session, lord, snapshot)
                state = await session.get(GameState, "site_sync_cursor")
                value = dict(state.value or {}) if state else {}
                value["cursor"] = event_id
                if state:
                    state.value = value
                else:
                    session.add(GameState(key="site_sync_cursor", value=value))
            cursor = event_id
            applied += 1
        except Exception:
            # Do not advance past a failed event; the next polling cycle retries it.
            raise
    await acknowledge_site_events(cursor)
    return applied
