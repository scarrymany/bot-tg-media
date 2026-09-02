from __future__ import annotations

import time
from dataclasses import dataclass

from bot.storage.db import get_db_or_none

VALID_QUALITIES = ("auto", "360", "480", "720", "1080")
VALID_LANGS = ("ru", "en")


@dataclass(slots=True)
class UserSettings:
    user_id: int
    quality: str = "auto"
    lang: str = "ru"


@dataclass(slots=True)
class Stats:
    users: int
    downloads: int
    youtube: int
    youtube_shorts: int
    tiktok: int
    instagram_reels: int
    cache_hits: int
    hit_rate: str


async def get_user(user_id: int, default_lang: str = "ru") -> UserSettings:
    lang = default_lang if default_lang in VALID_LANGS else "ru"
    conn = get_db_or_none()
    if conn is None:
        return UserSettings(user_id=user_id, lang=lang)
    cur = await conn.execute(
        "SELECT quality, lang FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = await cur.fetchone()
    if row is None:
        await conn.execute(
            "INSERT INTO user_settings (user_id, quality, lang, created_at) VALUES (?, ?, ?, ?)",
            (user_id, "auto", lang, int(time.time())),
        )
        await conn.commit()
        return UserSettings(user_id=user_id, quality="auto", lang=lang)
    return UserSettings(user_id=user_id, quality=str(row["quality"]), lang=str(row["lang"]))


async def set_quality(user_id: int, quality: str, default_lang: str = "ru") -> UserSettings:
    if quality not in VALID_QUALITIES:
        quality = "auto"
    user = await get_user(user_id, default_lang)
    conn = get_db_or_none()
    if conn is None:
        user.quality = quality
        return user
    await conn.execute(
        "UPDATE user_settings SET quality = ? WHERE user_id = ?",
        (quality, user_id),
    )
    await conn.commit()
    user.quality = quality
    return user


async def set_lang(user_id: int, lang: str, default_lang: str = "ru") -> UserSettings:
    if lang not in VALID_LANGS:
        lang = default_lang if default_lang in VALID_LANGS else "ru"
    user = await get_user(user_id, default_lang)
    conn = get_db_or_none()
    if conn is None:
        user.lang = lang
        return user
    await conn.execute(
        "UPDATE user_settings SET lang = ? WHERE user_id = ?",
        (lang, user_id),
    )
    await conn.commit()
    user.lang = lang
    return user


async def record_event(user_id: int, platform: str, kind: str) -> None:
    conn = get_db_or_none()
    if conn is None:
        return
    await conn.execute(
        "INSERT INTO stats_events (user_id, platform, kind, created_at) VALUES (?, ?, ?, ?)",
        (user_id, platform, kind, int(time.time())),
    )
    await conn.commit()


async def get_stats() -> Stats:
    empty = Stats(
        users=0,
        downloads=0,
        youtube=0,
        youtube_shorts=0,
        tiktok=0,
        instagram_reels=0,
        cache_hits=0,
        hit_rate="0%",
    )
    conn = get_db_or_none()
    if conn is None:
        return empty
    users_row = await (await conn.execute("SELECT COUNT(*) FROM user_settings")).fetchone()
    users = int(users_row[0]) if users_row else 0
    hits_row = await (
        await conn.execute("SELECT COUNT(*) FROM stats_events WHERE kind = 'cache_hit'")
    ).fetchone()
    cache_hits = int(hits_row[0]) if hits_row else 0
    dl_row = await (
        await conn.execute("SELECT COUNT(*) FROM stats_events WHERE kind = 'download'")
    ).fetchone()
    downloads = int(dl_row[0]) if dl_row else 0
    by_platform = {
        "youtube": 0,
        "youtube_shorts": 0,
        "tiktok": 0,
        "instagram_reels": 0,
    }
    cur = await conn.execute(
        "SELECT platform, COUNT(*) AS n FROM stats_events WHERE kind = 'download' GROUP BY platform"
    )
    async for row in cur:
        key = str(row["platform"])
        if key in by_platform:
            by_platform[key] = int(row["n"])
    total = downloads + cache_hits
    hit_rate = f"{int(round(100 * cache_hits / total))}%" if total else "0%"
    return Stats(
        users=users,
        downloads=downloads,
        youtube=by_platform["youtube"],
        youtube_shorts=by_platform["youtube_shorts"],
        tiktok=by_platform["tiktok"],
        instagram_reels=by_platform["instagram_reels"],
        cache_hits=cache_hits,
        hit_rate=hit_rate,
    )
