from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Settings
from bot.i18n import t
from bot.storage.users import get_stats, get_user

router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    if user_id not in settings.admin_ids:
        await message.answer(t("stats_denied", user.lang))
        return
    stats = await get_stats()
    await message.answer(
        t(
            "stats_text",
            user.lang,
            users=stats.users,
            downloads=stats.downloads,
            youtube=stats.youtube,
            youtube_shorts=stats.youtube_shorts,
            tiktok=stats.tiktok,
            instagram_reels=stats.instagram_reels,
            cache_hits=stats.cache_hits,
            hit_rate=stats.hit_rate,
        )
    )
