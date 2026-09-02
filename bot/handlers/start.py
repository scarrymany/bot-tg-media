from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import get_settings
from bot.i18n import t

router = Router(name="start")


def _lang(message: Message) -> str:
    user_lang = getattr(message, "user_lang", None)
    if isinstance(user_lang, str) and user_lang in {"ru", "en"}:
        return user_lang
    return get_settings().default_lang


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(t("start_greeting", _lang(message)))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        t("help_text", _lang(message), max_mb=get_settings().max_file_mb),
    )
