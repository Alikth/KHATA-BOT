"""Apply the checked-in PostgreSQL migrations in order.

Run only after taking a verified backup. This script never drops or resets data.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from bot.config import get_settings

MIGRATIONS = {
    1: "0001_initial.sql",
    2: "0002_warfare_trade_parity.sql",
    3: "0003_missing_model_tables.sql",
}


async def apply() -> None:
    settings = get_settings()
    url = settings.database_url.strip()
    if not url:
        raise RuntimeError("DATABASE_URL is missing in .env")
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url.removeprefix("postgresql+asyncpg://")

    root = Path(__file__).resolve().parents[1]
    migration_dir = root / "bot" / "database" / "migrations"
    conn = await asyncpg.connect(url)
    try:
        try:
            current = await conn.fetchval("SELECT MAX(version) FROM schema_version")
            current = int(current or 0)
        except asyncpg.UndefinedTableError:
            current = 0

        if current > max(MIGRATIONS):
            raise RuntimeError(f"Database schema version {current} is newer than this bot.")
        if current == max(MIGRATIONS):
            print(f"Database schema is already current (version {current}).")
            return

        for version in range(current + 1, max(MIGRATIONS) + 1):
            path = migration_dir / MIGRATIONS[version]
            print(f"Applying migration {version}: {path.name}")
            await conn.execute(path.read_text(encoding="utf-8"))
            saved = await conn.fetchval("SELECT MAX(version) FROM schema_version")
            if int(saved or 0) < version:
                raise RuntimeError(f"Migration {version} did not record its schema version.")
        print(f"Database migrations complete (version {max(MIGRATIONS)}).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply())
