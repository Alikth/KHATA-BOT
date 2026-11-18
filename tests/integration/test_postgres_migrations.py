import os

import asyncpg
import pytest

from bot.database.base import Base
from bot.database import models  # noqa: F401 - register all mapped tables


@pytest.mark.asyncio
async def test_postgres_migrations_cover_all_orm_tables():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        actual = {row["table_name"] for row in rows}
        expected = set(Base.metadata.tables)
        assert expected <= actual, f"missing tables: {sorted(expected - actual)}"

        for table_name, table in Base.metadata.tables.items():
            columns = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1",
                table_name,
            )
            actual_columns = {row["column_name"] for row in columns}
            expected_columns = {column.name for column in table.columns}
            assert expected_columns <= actual_columns, (
                f"{table_name} missing columns: "
                f"{sorted(expected_columns - actual_columns)}"
            )
        version = await conn.fetchval("SELECT MAX(version) FROM schema_version")
        assert version == 3
    finally:
        await conn.close()
