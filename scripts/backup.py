"""Create and verify a PostgreSQL custom-format backup."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bot.config import get_settings


def connection_parts(raw: str) -> dict[str, str]:
    parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL.")
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/").split("?")[0]),
    }


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is missing in .env")
    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        raise RuntimeError("PostgreSQL client tools (pg_dump and pg_restore) must be installed and on PATH.")
    parts = connection_parts(settings.database_url)
    if not parts["database"]:
        raise RuntimeError("Database name is missing in DATABASE_URL.")

    directory = Path(settings.backup_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = directory / f"khata-{stamp}.dump"
    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]

    command = [
        pg_dump, "--format=custom", "--no-owner", "--no-acl",
        "--host", parts["host"], "--port", parts["port"],
        "--username", parts["user"], "--dbname", parts["database"],
        "--file", str(archive),
    ]
    subprocess.run(command, env=env, check=True)
    if not archive.is_file() or archive.stat().st_size < 128:
        raise RuntimeError("Backup archive was not created or is unexpectedly small.")

    listing = subprocess.run(
        [pg_restore, "--list", str(archive)],
        env=env, check=True, capture_output=True, text=True,
    )
    if "DATABASE" not in listing.stdout and "TABLE" not in listing.stdout:
        raise RuntimeError("pg_restore could not verify the archive contents.")

    hasher = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Verified backup: {archive}")
    print(f"Size: {archive.stat().st_size:,} bytes")
    print(f"SHA-256: {digest}")
    print("Note: a verified archive listing is not a substitute for a test restore.")


if __name__ == "__main__":
    main()
