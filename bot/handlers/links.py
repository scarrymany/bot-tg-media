from __future__ import annotations

from html import escape

import structlog
from aiogram import F, Router
from aiogram.types import Message

from bot.config import get_settings
from bot.handlers.common import safe_edit
from bot.i18n import t
from bot.keyboards import formats_keyboard
from bot.services.detector import detect_links, looks_like_url
from bot.services.extractor import (
    ExtractError,
    InstagramCookiesError,
    MediaInfo,
    extract_media,
)
from bot.storage.cache import put_job
from bot.storage.users import get_user

log = structlog.get_logger("links")

PLATFORM_EMOJI = {
    "tiktok": "🎵",
    "youtube": "▶️",
    "youtube_shorts": "📱",
    "instagram_reels": "📸",
}


def format_duration(seconds: int | None, lang: str) -> str:
    if not seconds:
        return t("duration_unknown", lang)
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def render_card(info: MediaInfo, lang: str) -> str:
    title = escape(info.title)[:200]
    return t(
        "card",
        lang,
        emoji=PLATFORM_EMOJI.get(info.platform, "▶️"),
        platform=t(f"platform_{info.platform}", lang),
        title=title,
        duration=format_duration(info.duration, lang),
    )


async def on_text(message: Message) -> None:
    text = message.text or ""
    if text.startswith("/"):
        return

    settings = get_settings()
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    lang = user.lang

    links = detect_links(text)
    if not links:
        if looks_like_url(text):
            await message.answer(t("err_unsupported", lang))
        return

    link = links[0]
    status = await message.answer(t("getting_info", lang))
    try:
        info = await extract_media(
            link,
            max_file_mb=settings.max_file_mb,
            cookies_file=settings.ig_cookies_file,
        )
    except InstagramCookiesError:
        log.info("ig_cookies_required", url=link.normalised_url)
        await safe_edit(status, t("err_ig_cookies", lang))
        return
    except ExtractError:
        log.warning("extract_error", url=link.normalised_url)
        await safe_edit(status, t("err_extract", lang))
        return
    except Exception:
        log.exception("extract_unhandled", url=link.normalised_url)
        await safe_edit(status, t("err_generic", lang))
        return

    if not any(opt.key != "audio" for opt in info.formats):
        await safe_edit(status, t("err_no_formats", lang))
        return

    token = put_job(info, user.user_id)
    keyboard = formats_keyboard(
        info,
        token,
        lang=lang,
        default_quality=user.quality,
        max_mb=settings.max_file_mb,
    )
    await safe_edit(status, render_card(info, lang), reply_markup=keyboard)


def build_router() -> Router:
    """Build a fresh router so a Dispatcher can be constructed more than once."""
    router = Router(name="links")
    router.message.register(on_text, F.text)
    return router


router = build_router()
