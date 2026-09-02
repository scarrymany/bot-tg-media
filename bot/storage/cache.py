from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from bot.services.extractor import MediaInfo


@dataclass(slots=True)
class Job:
    token: str
    info: MediaInfo
    user_id: int
    created_at: float = field(default_factory=monotonic)
    cancelled: bool = False


_JOBS: dict[str, Job] = {}


def put_job(info: MediaInfo, user_id: int) -> str:
    raise NotImplementedError


def get_job(token: str) -> Job | None:
    return _JOBS.get(token)


def cancel_job(token: str) -> Job | None:
    job = _JOBS.get(token)
    if job is not None:
        job.cancelled = True
    return job
