from __future__ import annotations

from bot.storage.cache import get_cached, put_cached
from bot.storage.db import get_db


async def test_file_id_cache_roundtrip(db: None) -> None:
    assert await get_cached("https://www.youtube.com/watch?v=aaaaaaaaaaa", "360") is None
    await put_cached("https://www.youtube.com/watch?v=aaaaaaaaaaa", "360", "file-AAA", "video")
    entry = await get_cached("https://www.youtube.com/watch?v=aaaaaaaaaaa", "360")
    assert entry is not None
    assert entry.file_id == "file-AAA"
    assert entry.kind == "video"


async def test_cache_upsert(db: None) -> None:
    url = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    await put_cached(url, "audio", "old", "audio")
    await put_cached(url, "audio", "new", "audio")
    entry = await get_cached(url, "audio")
    assert entry is not None
    assert entry.file_id == "new"


async def test_schema_version(db: None) -> None:
    conn = await get_db()
    row = await (await conn.execute("SELECT MAX(version) FROM schema_version")).fetchone()
    assert row is not None
    assert int(row[0]) == 1
    tables = await (
        await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()
    names = {r[0] for r in tables}
    assert {"user_settings", "media_cache", "stats_events", "schema_version"} <= names
