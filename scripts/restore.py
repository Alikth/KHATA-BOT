"""Restore a verified backup into a separate, empty PostgreSQL database only."""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
from urllib.parse import unquote, urlsplit

import asyncpg

from bot.config import get_settings


def connection_parts(raw: str) -> dict[str, str]:
    parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("Target must be a PostgreSQL URL.")
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/").split("?")[0]),
    }


async def ensure_empty_and_verify(target: str, before: bool) -> None:
    conn = await asyncpg.connect(target)
    try:
        if before:
            count = await conn.fetchval(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
            if count:
                raise RuntimeError("Restore target is not empty. Refusing to overwrite any database.")
        else:
            try:
                version = await conn.fetchval("SELECT MAX(version) FROM schema_version")
            except asyncpg.UndefinedTableError as exc:
                raise RuntimeError("Restore finished but schema_version is missing.") from exc
            if int(version or 0) < 3:
                raise RuntimeError(f"Restored schema is incomplete (version={version}).")
    finally:
        await conn.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", help="Path to a .dump created by scripts/backup.py")
    args = parser.parse_args()

    source = get_settings().database_url
    target = os.environ.get("RESTORE_DATABASE_URL", "").strip()
    if not source or not target:
        raise RuntimeError("Set DATABASE_URL in .env and RESTORE_DATABASE_URL in the process environment.")
    src, dst = connection_parts(source), connection_parts(target)
    if (src["host"], src["port"], src["database"]) == (dst["host"], dst["port"], dst["database"]):
        raise RuntimeError("Restore target must be a different database from DATABASE_URL.")

    archive = os.path.abspath(args.archive)
    if not os.path.isfile(archive):
        raise RuntimeError(f"Backup archive not found: {archive}")
    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise RuntimeError("pg_restore must be installed and on PATH.")
    env = os.environ.copy()
    if dst["password"]:
        env["PGPASSWORD"] = dst["password"]

    subprocess.run([pg_restore, "--list", archive], env=env, check=True, capture_output=True)
    await ensure_empty_and_verify(target, before=True)
    print(f"About to restore {archive} into EMPTY database {dst['database']}.")
    if input("Type RESTORE to continue: ").strip() != "RESTORE":
        raise SystemExit("Restore cancelled.")

    command = [
        pg_restore, "--no-owner", "--no-acl", "--exit-on-error",
        "--host", dst["host"], "--port", dst["port"],
        "--username", dst["user"], "--dbname", dst["database"], archive,
    ]
    subprocess.run(command, env=env, check=True)
    await ensure_empty_and_verify(target, before=False)
    print("Restore completed and schema version 3 was verified.")


if __name__ == "__main__":
    asyncio.run(main())
