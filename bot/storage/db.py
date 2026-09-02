from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger("db")

SCHEMA_VERSION = 1

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    quality TEXT NOT NULL DEFAULT 'auto',
    lang TEXT NOT NULL DEFAULT 'ru',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS media_cache (
    url_norm TEXT NOT NULL,
    format_key TEXT NOT NULL,
    file_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (url_norm, format_key)
);
CREATE TABLE IF NOT EXISTS stats_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    platform TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

_conn: aiosqlite.Connection | None = None


def get_db_or_none() -> aiosqlite.Connection | None:
    return _conn


async def get_db() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("database is not initialised")
    return _conn


async def init_db(db_path: Path) -> aiosqlite.Connection:
    global _conn
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")
    await _migrate(conn)
    _conn = conn
    log.info("db_ready", path=str(db_path))
    return conn


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def _migrate(conn: aiosqlite.Connection) -> None:
    await conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    cur = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    row = await cur.fetchone()
    current = int(row[0]) if row is not None else 0
    if current < 1:
        await conn.executescript(MIGRATION_1)
        await conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        await conn.commit()
        log.info("migrated", to_version=1)
