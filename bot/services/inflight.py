"""Counters for work a graceful shutdown must not cut short.

A download is only half of a job: the upload to Telegram that follows it can
easily be the longer half for a 50 MB file. Shutdown used to wait for the
downloader alone, so SIGTERM could kill a sendVideo mid-flight and leave the
user with a dead progress card.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType


class InFlight:
    """A re-entrant counter usable as a context manager.

    Deliberately synchronous: it is entered and left inside coroutines that
    never await between the increment and the ``try`` block, so no lock is
    needed on a single event loop.
    """

    __slots__ = ("_count",)

    def __init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def __enter__(self) -> InFlight:
        self._count += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._count = max(0, self._count - 1)

    async def wait_idle(self, timeout: float = 30.0) -> bool:
        """Wait until the counter drops to zero. False means the wait timed out."""
        deadline = time.monotonic() + timeout
        while self._count and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        return self._count == 0


#: Uploads to Telegram currently in progress (see :mod:`bot.services.sender`).
uploads = InFlight()
