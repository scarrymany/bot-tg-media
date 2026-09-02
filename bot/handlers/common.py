from __future__ import annotations

import structlog
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

log = structlog.get_logger("handlers")


async def safe_edit(
    message: Message | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Edit a message, swallowing the errors that are not worth a user-facing failure.

    Telegram answers "message is not modified" whenever the new text and markup
    are byte-identical to the current ones — which happens routinely (tapping
    the already-selected quality, a progress tick that lands on the same
    percentage). Every other API error is logged rather than propagated: the
    card is cosmetic, and losing it must not abort the request or surface a
    traceback to the user.

    Returns True when the edit was applied.
    """
    if message is None:
        return False
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc).lower():
            return False
        log.warning("edit_failed", error=str(exc))
        return False
    except TelegramAPIError as exc:
        log.warning("edit_failed", error=str(exc))
        return False
    return True
