from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from bot.services.extractor import MediaInfo
from bot.storage.db import get_db_or_none

JOB_TTL_SEC = 60 * 60


@dataclass(slots=True)
class Job:
    token: str
    info: MediaInfo
    user_id: int
    created_at: float = field(default_factory=monotonic)
    cancelled: bool = False
    busy: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


_JOBS: dict[str, Job] = {}


def _gc_jobs(now: float | None = None) -> None:
    current = now if now is not None else monotonic()
    expired = [token for token, job in _JOBS.items() if current - job.created_at > JOB_TTL_SEC]
    for token in expired:
        _JOBS.pop(token, None)


def put_job(info: MediaInfo, user_id: int) -> str:
    _gc_jobs()
    token = secrets.token_urlsafe(8).replace("_", "x").replace("-", "y")[:10]
    while token in _JOBS:
        token = secrets.token_urlsafe(8).replace("_", "x").replace("-", "y")[:10]
    _JOBS[token] = Job(token=token, info=info, user_id=user_id)
    return token


def get_job(token: str) -> Job | None:
    _gc_jobs()
    return _JOBS.get(token)


def cancel_job(token: str) -> Job | None:
    job = get_job(token)
    if job is not None:
        job.cancelled = True
        job.cancel_event.set()
    return job


def drop_job(token: str) -> None:
    _JOBS.pop(token, None)


def try_start_job(token: str) -> bool:
    """Claim a job for a download. Returns False when one is already running.

    Guards against a double tap on a quality button starting the same download
    twice (the callback is answered immediately, so Telegram lets the user tap
    again while the first job is still in flight).
    """
    job = _JOBS.get(token)
    if job is None or job.busy:
        return False
    job.busy = True
    return True


def finish_job(token: str) -> None:
    job = _JOBS.get(token)
    if job is not None:
        job.busy = False


def clear_jobs() -> None:
    _JOBS.clear()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    file_id: str
    kind: Literal["video", "audio"]
    created_at: int


async def get_cached(url_norm: str, format_key: str) -> CacheEntry | None:
    conn = get_db_or_none()
    if conn is None:
        return None
    cur = await conn.execute(
        "SELECT file_id, kind, created_at FROM media_cache WHERE url_norm = ? AND format_key = ?",
        (url_norm, format_key),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    kind = row["kind"]
    if kind not in {"video", "audio"}:
        return None
    return CacheEntry(file_id=str(row["file_id"]), kind=kind, created_at=int(row["created_at"]))


async def drop_cached(url_norm: str, format_key: str) -> None:
    """Forget a cached file_id (e.g. Telegram rejected it as expired/invalid)."""
    conn = get_db_or_none()
    if conn is None:
        return
    await conn.execute(
        "DELETE FROM media_cache WHERE url_norm = ? AND format_key = ?",
        (url_norm, format_key),
    )
    await conn.commit()


async def put_cached(
    url_norm: str,
    format_key: str,
    file_id: str,
    kind: Literal["video", "audio"],
) -> None:
    conn = get_db_or_none()
    if conn is None:
        return
    await conn.execute(
        "INSERT INTO media_cache (url_norm, format_key, file_id, kind, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(url_norm, format_key) DO UPDATE SET "
        "file_id = excluded.file_id, kind = excluded.kind, created_at = excluded.created_at",
        (url_norm, format_key, file_id, kind, int(time.time())),
    )
    await conn.commit()
