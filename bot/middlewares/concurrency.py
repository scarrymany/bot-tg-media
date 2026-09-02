from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ConcurrencyMiddleware(BaseMiddleware):
    """Expose a global download semaphore via handler data."""

    def __init__(self, limit: int = 3) -> None:
        self.semaphore = asyncio.Semaphore(max(1, limit))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["download_sem"] = self.semaphore
        return await handler(event, data)
