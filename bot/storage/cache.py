from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from time import monotonic

from bot.services.extractor import MediaInfo

JOB_TTL_SEC = 60 * 60


@dataclass(slots=True)
class Job:
    token: str
    info: MediaInfo
    user_id: int
    created_at: float = field(default_factory=monotonic)
    cancelled: bool = False


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
    return job


def drop_job(token: str) -> None:
    _JOBS.pop(token, None)


def clear_jobs() -> None:
    _JOBS.clear()
