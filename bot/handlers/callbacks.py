from __future__ import annotations

import asyncio
from html import escape

import structlog
from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from bot.config import Settings, get_settings
from bot.handlers.common import safe_edit
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
from bot.services.extractor import FormatOption
from bot.services.sender import send_by_file_id, send_media
from bot.storage.cache import (
    Job,
    cancel_job,
    drop_cached,
    finish_job,
    get_cached,
    get_job,
    put_cached,
    try_start_job,
)
from bot.storage.users import get_user, record_event

log = structlog.get_logger("callbacks")


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


def _owns(job: Job, user_id: int) -> bool:
    """Buttons belong to the user who sent the link (matters in group chats)."""
    return not job.user_id or not user_id or job.user_id == user_id


async def _reject_foreign(callback: CallbackQuery, user_id: int) -> None:
    await callback.answer(t("err_foreign_job", await _lang_for(user_id)), show_alert=True)


async def on_format(
    callback: CallbackQuery,
    callback_data: FormatCb,
    settings: Settings,
    downloader: Downloader,
    download_sem: asyncio.Semaphore | None = None,
) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    job = get_job(callback_data.t)
    if job is not None and not _owns(job, user_id):
        await _reject_foreign(callback, user_id)
        return
    await callback.answer()
    lang = await _lang_for(user_id)
    message = callback.message if isinstance(callback.message, Message) else None
    if job is None or job.cancelled:
        await safe_edit(message, t("err_generic", lang))
        return

    option = job.info.format_by_key(callback_data.k)
    if option is None:
        await safe_edit(message, t("err_no_formats", lang))
        return

    if option.exceeds_limit:
        await safe_edit(
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

    bot = _bot_of(callback)
    if bot is None:
        return

    if not try_start_job(job.token):
        # Double tap while the first download is still running.
        log.info("job_already_running", token=job.token)
        return
    try:
        await _run_job(
            bot=bot,
            message=message,
            job=job,
            option=option,
            lang=lang,
            user_id=user_id,
            settings=settings,
            downloader=downloader,
            download_sem=download_sem,
        )
    finally:
        finish_job(job.token)


async def _try_cached(
    bot: Bot,
    message: Message,
    job: Job,
    format_key: str,
    lang: str,
    user_id: int,
) -> bool:
    """Resend from the file_id cache. False means nothing usable was cached."""
    # Keyed on the extractor-resolved identity, so a short link and the
    # canonical URL of the same video share one row.
    cached = await get_cached(job.info.cache_key, format_key)
    if cached is None:
        return False
    try:
        await send_by_file_id(
            bot,
            message.chat.id,
            cached.file_id,
            cached.kind,
            title=job.info.title,
            performer=job.info.uploader or job.info.title,
            duration=job.info.duration,
        )
    except TelegramAPIError as exc:
        # An expired / revoked / foreign file_id must not kill the request:
        # forget it and fall through to a fresh download.
        log.warning("cache_send_failed", error=str(exc), format_key=format_key)
        await drop_cached(job.info.cache_key, format_key)
        return False
    await record_event(user_id, job.info.platform, "cache_hit")
    log.info("sent", kind=cached.kind, cached=True)
    await safe_edit(
        message,
        t("download_done", lang, title=escape(job.info.title)[:200]),
        reply_markup=another_keyboard(job.token, lang),
    )
    return True


async def _run_job(
    *,
    bot: Bot,
    message: Message,
    job: Job,
    option: FormatOption,
    lang: str,
    user_id: int,
    settings: Settings,
    downloader: Downloader,
    download_sem: asyncio.Semaphore | None,
) -> None:
    if await _try_cached(bot, message, job, option.key, lang, user_id):
        return

    await safe_edit(message, t("downloading", lang, pct=0))

    # Progress updates are scheduled from the yt-dlp worker thread and can land
    # after the final card is drawn; this flag drops the stale ones so the
    # result card (with the "another format" button) is never overwritten.
    progress_open = True

    async def progress(pct: int) -> None:
        if not progress_open:
            return
        await safe_edit(message, t("downloading", lang, pct=pct))

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
        progress_open = False
        sent = await send_media(bot, message.chat.id, result)
        if sent.file_id:
            await put_cached(job.info.cache_key, option.key, sent.file_id, sent.kind)
        await record_event(user_id, job.info.platform, "download")
        log.info("sent", kind=sent.kind, cached=False)
        await safe_edit(
            message,
            t("download_done", lang, title=escape(job.info.title)[:200]),
            reply_markup=another_keyboard(job.token, lang),
        )
    except DownloadCancelled:
        progress_open = False
        await safe_edit(message, t("cancelled", lang))
    except FileTooLargeError:
        progress_open = False
        await safe_edit(
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
        progress_open = False
        log.exception("download_or_send_failed")
        await safe_edit(message, t(map_error_key(exc), lang, max_mb=settings.max_file_mb))
    finally:
        progress_open = False
        if result is not None:
            downloader.cleanup(result)


async def on_cancel(callback: CallbackQuery, callback_data: CancelCb) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    job = get_job(callback_data.t)
    if job is not None and not _owns(job, user_id):
        await _reject_foreign(callback, user_id)
        return
    await callback.answer()
    lang = await _lang_for(user_id)
    cancel_job(callback_data.t)
    message = callback.message if isinstance(callback.message, Message) else None
    await safe_edit(message, t("cancelled", lang))


async def on_another(
    callback: CallbackQuery,
    callback_data: AnotherCb,
    settings: Settings,
) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    job = get_job(callback_data.t)
    if job is not None and not _owns(job, user_id):
        await _reject_foreign(callback, user_id)
        return
    await callback.answer()
    lang = await _lang_for(user_id)
    message = callback.message if isinstance(callback.message, Message) else None
    if job is None:
        await safe_edit(message, t("err_generic", lang))
        return
    user = await get_user(user_id, settings.default_lang)
    await safe_edit(
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


def build_router() -> Router:
    """Build a fresh router so a Dispatcher can be constructed more than once."""
    router = Router(name="callbacks")
    router.callback_query.register(on_format, FormatCb.filter())
    router.callback_query.register(on_cancel, CancelCb.filter())
    router.callback_query.register(on_another, AnotherCb.filter())
    return router
