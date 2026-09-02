from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import get_settings
from bot.i18n import t
from bot.storage.users import get_user

router = Router(name="start")


async def _lang(message: Message) -> str:
    settings = get_settings()
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    return user.lang


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(t("start_greeting", await _lang(message)))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        t("help_text", await _lang(message), max_mb=get_settings().max_file_mb),
    )
