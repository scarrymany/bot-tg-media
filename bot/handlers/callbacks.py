from __future__ import annotations

import asyncio
from html import escape

import structlog
from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Settings, get_settings
from bot.handlers.links import render_card
from bot.i18n import t
from bot.keyboards import (
    AnotherCb,
    CancelCb,
    FormatCb,
    another_keyboard,
    formats_keyboard,
)
from bot.services.downloader import (
    DownloadCancelled,
    Downloader,
    FileTooLargeError,
    map_error_key,
)
from bot.services.sender import send_by_file_id, send_media
from bot.storage.cache import cancel_job, get_cached, get_job, put_cached
from bot.storage.users import get_user, record_event

router = Router(name="callbacks")
log = structlog.get_logger("callbacks")


async def _safe_edit(
    message: Message | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        log.warning("edit_failed", error=str(exc))


def _bot_of(callback: CallbackQuery) -> Bot | None:
    bot = callback.bot
    if isinstance(bot, Bot):
        return bot
    if isinstance(callback.message, Message) and isinstance(callback.message.bot, Bot):
        return callback.message.bot
    return None


async def _lang_for(user_id: int) -> str:
    settings = get_settings()
    user = await get_user(user_id, settings.default_lang)
    return user.lang


@router.callback_query(FormatCb.filter())
async def on_format(
    callback: CallbackQuery,
    callback_data: FormatCb,
    settings: Settings,
    downloader: Downloader,
    download_sem: asyncio.Semaphore | None = None,
) -> None:
    await callback.answer()
    user_id = callback.from_user.id if callback.from_user else 0
    lang = await _lang_for(user_id)
    message = callback.message if isinstance(callback.message, Message) else None
    job = get_job(callback_data.t)
    if job is None or job.cancelled:
        await _safe_edit(message, t("err_generic", lang))
        return

    option = job.info.format_by_key(callback_data.k)
    if option is None:
        await _safe_edit(message, t("err_no_formats", lang))
        return

    if option.exceeds_limit:
        await _safe_edit(
            message,
            t("err_too_large", lang, max_mb=settings.max_file_mb),
            reply_markup=formats_keyboard(
                job.info,
                job.token,
                lang=lang,
                default_quality=(await get_user(user_id, settings.default_lang)).quality,
                max_mb=settings.max_file_mb,
            ),
        )
        return

    if message is None:
        return

    cached = await get_cached(job.info.normalised_url, option.key)
    bot = _bot_of(callback)
    if bot is None:
        return
    if cached is not None:
        await send_by_file_id(
            bot,
            message.chat.id,
            cached.file_id,
            cached.kind,
            title=job.info.title,
            performer=job.info.uploader or job.info.title,
            duration=job.info.duration,
        )
        await record_event(user_id, job.info.platform, "cache_hit")
        log.info("sent", kind=cached.kind, cached=True)
        await _safe_edit(
            message,
            t("download_done", lang, title=escape(job.info.title)[:200]),
            reply_markup=another_keyboard(job.token, lang),
        )
        return

    await _safe_edit(message, t("downloading", lang, pct=0))

    async def progress(pct: int) -> None:
        await _safe_edit(message, t("downloading", lang, pct=pct))

    sem = download_sem or asyncio.Semaphore(settings.max_concurrent_downloads)
    result = None
    try:
        async with sem:
            result = await downloader.download(
                job.info,
                option,
                progress=progress,
                cancel_event=job.cancel_event,
            )
        sent = await send_media(bot, message.chat.id, result)
        if sent.file_id:
            await put_cached(job.info.normalised_url, option.key, sent.file_id, sent.kind)
        await record_event(user_id, job.info.platform, "download")
        log.info("sent", kind=sent.kind, cached=False)
        await _safe_edit(
            message,
            t("download_done", lang, title=escape(job.info.title)[:200]),
            reply_markup=another_keyboard(job.token, lang),
        )
    except DownloadCancelled:
        await _safe_edit(message, t("cancelled", lang))
    except FileTooLargeError:
        await _safe_edit(
            message,
            t("err_too_large", lang, max_mb=settings.max_file_mb),
            reply_markup=formats_keyboard(
                job.info,
                job.token,
                lang=lang,
                default_quality="auto",
                max_mb=settings.max_file_mb,
            ),
        )
    except Exception as exc:
        log.exception("download_or_send_failed")
        await _safe_edit(message, t(map_error_key(exc), lang, max_mb=settings.max_file_mb))
    finally:
        if result is not None:
            downloader.cleanup(result)


@router.callback_query(CancelCb.filter())
async def on_cancel(callback: CallbackQuery, callback_data: CancelCb) -> None:
    await callback.answer()
    lang = await _lang_for(callback.from_user.id if callback.from_user else 0)
    cancel_job(callback_data.t)
    message = callback.message if isinstance(callback.message, Message) else None
    await _safe_edit(message, t("cancelled", lang))


@router.callback_query(AnotherCb.filter())
async def on_another(
    callback: CallbackQuery,
    callback_data: AnotherCb,
    settings: Settings,
) -> None:
    await callback.answer()
    user_id = callback.from_user.id if callback.from_user else 0
    lang = await _lang_for(user_id)
    message = callback.message if isinstance(callback.message, Message) else None
    job = get_job(callback_data.t)
    if job is None:
        await _safe_edit(message, t("err_generic", lang))
        return
    user = await get_user(user_id, settings.default_lang)
    await _safe_edit(
        message,
        render_card(job.info, lang),
        reply_markup=formats_keyboard(
            job.info,
            job.token,
            lang=lang,
            default_quality=user.quality,
            max_mb=settings.max_file_mb,
        ),
    )
