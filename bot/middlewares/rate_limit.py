from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from bot.config import Settings
from bot.i18n import t
from bot.keyboards import FormatCb
from bot.services.detector import looks_like_url
from bot.storage.users import get_user

log = structlog.get_logger("rate_limit")

_GC_INTERVAL = 300.0
_FORMAT_PREFIX = f"{FormatCb.__prefix__}{FormatCb.__separator__}"


def unwrap_event(event: TelegramObject) -> TelegramObject:
    """Resolve the concrete event when the middleware is attached to ``dp.update``.

    aiogram passes an :class:`Update` to update-level middlewares, so type checks
    against ``Message`` / ``CallbackQuery`` must look at the payload instead.
    """
    if isinstance(event, Update):
        return event.message or event.edited_message or event.callback_query or event
    return event


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_per_min: int = 5) -> None:
        self.limit = max(1, limit_per_min)
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._last_gc = time.monotonic()

    def _prune(self, user_id: int, now: float) -> deque[float]:
        hits = self._hits[user_id]
        while hits and now - hits[0] >= 60.0:
            hits.popleft()
        return hits

    def _gc(self, now: float) -> None:
        """Drop per-user deques that no longer hold any live hit."""
        if now - self._last_gc < _GC_INTERVAL:
            return
        self._last_gc = now
        stale = [
            user_id for user_id, hits in self._hits.items() if not hits or now - hits[-1] >= 60.0
        ]
        for user_id in stale:
            self._hits.pop(user_id, None)

    def wait_seconds(self, user_id: int) -> int:
        """Whole seconds until the oldest hit leaves the 60 s window.

        ``ceil`` (rather than ``int(...) + 1``) keeps the value stable across a
        sub-second gap, so the number quoted to the user matches the one a
        caller reads back a moment later.
        """
        hits = self._hits.get(user_id)
        if not hits:
            return 1
        remaining = 60.0 - (time.monotonic() - hits[0])
        return min(60, max(1, math.ceil(remaining)))

    def _should_limit(self, event: TelegramObject) -> bool:
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/"):
                return False
            return looks_like_url(text)
        if isinstance(event, CallbackQuery):
            data = event.data or ""
            return data.startswith(_FORMAT_PREFIX)
        return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        target = unwrap_event(event)
        if not self._should_limit(target):
            return await handler(event, data)
        user = data.get("event_from_user")
        if not isinstance(user, User):
            return await handler(event, data)
        now = time.monotonic()
        self._gc(now)
        hits = self._prune(user.id, now)
        if len(hits) >= self.limit:
            wait = self.wait_seconds(user.id)
            settings = data.get("settings")
            default_lang = settings.default_lang if isinstance(settings, Settings) else "ru"
            lang = (await get_user(user.id, default_lang)).lang
            text = t("rate_limited", lang, seconds=wait)
            log.info("rate_limited", user_id=user.id, wait=wait)
            if isinstance(target, Message):
                await target.answer(text)
            elif isinstance(target, CallbackQuery):
                await target.answer(text, show_alert=True)
            return None
        hits.append(now)
        return await handler(event, data)
