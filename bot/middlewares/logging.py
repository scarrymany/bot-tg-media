from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        update = data.get("event_update")
        user_id = user.id if isinstance(user, User) else None
        update_id = update.update_id if isinstance(update, Update) else None
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(user_id=user_id, update_id=update_id)
        log = structlog.get_logger("update")
        log.debug("update", event_type=type(event).__name__)
        return await handler(event, data)
