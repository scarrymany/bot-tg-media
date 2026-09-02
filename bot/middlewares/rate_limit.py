from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.config import Settings
from bot.i18n import t
from bot.services.detector import looks_like_url
from bot.storage.users import get_user

log = structlog.get_logger("rate_limit")


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_per_min: int = 5) -> None:
        self.limit = max(1, limit_per_min)
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def _prune(self, user_id: int, now: float) -> deque[float]:
        hits = self._hits[user_id]
        while hits and now - hits[0] >= 60.0:
            hits.popleft()
        return hits

    def wait_seconds(self, user_id: int) -> int:
        hits = self._hits.get(user_id)
        if not hits:
            return 1
        return max(1, int(60.0 - (time.monotonic() - hits[0])) + 1)

    def _should_limit(self, event: TelegramObject) -> bool:
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/"):
                return False
            return looks_like_url(text)
        if isinstance(event, CallbackQuery):
            data = event.data or ""
            return data.startswith("f:")
        return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._should_limit(event):
            return await handler(event, data)
        user = data.get("event_from_user")
        if not isinstance(user, User):
            return await handler(event, data)
        now = time.monotonic()
        hits = self._prune(user.id, now)
        if len(hits) >= self.limit:
            wait = self.wait_seconds(user.id)
            settings = data.get("settings")
            default_lang = settings.default_lang if isinstance(settings, Settings) else "ru"
            lang = (await get_user(user.id, default_lang)).lang
            text = t("rate_limited", lang, seconds=wait)
            log.info("rate_limited", user_id=user.id, wait=wait)
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None
        hits.append(now)
        return await handler(event, data)
