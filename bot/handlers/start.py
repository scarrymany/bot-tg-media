from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import get_settings
from bot.i18n import t
from bot.storage.users import get_user


async def _lang(message: Message) -> str:
    settings = get_settings()
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    return user.lang


async def cmd_start(message: Message) -> None:
    await message.answer(t("start_greeting", await _lang(message)))


async def cmd_help(message: Message) -> None:
    await message.answer(
        t("help_text", await _lang(message), max_mb=get_settings().max_file_mb),
    )


def build_router() -> Router:
    """Build a fresh router so a Dispatcher can be constructed more than once."""
    router = Router(name="start")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    return router


router = build_router()
