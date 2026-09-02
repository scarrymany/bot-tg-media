from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, Message

from bot.services.downloader import DownloadResult
from bot.services.inflight import uploads

log = structlog.get_logger("sender")


@dataclass(slots=True)
class SendResult:
    file_id: str
    kind: Literal["video", "audio"]
    message_id: int


def _clip(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


async def send_media(bot: Bot, chat_id: int, result: DownloadResult) -> SendResult:
    # Counted so shutdown waits for the upload, not just for the download.
    with uploads:
        return await _send_media(bot, chat_id, result)


async def _send_media(bot: Bot, chat_id: int, result: DownloadResult) -> SendResult:
    if result.kind == "audio":
        message = await bot.send_audio(
            chat_id,
            audio=FSInputFile(result.path),
            title=_clip(result.title, 64) or "audio",
            performer=_clip(result.performer, 64) or "unknown",
            duration=result.duration,
        )
        file_id = _audio_file_id(message)
    else:
        thumb = FSInputFile(result.thumbnail) if result.thumbnail else None

        async def _send(with_thumb: bool) -> Message:
            return await bot.send_video(
                chat_id,
                video=FSInputFile(result.path),
                duration=result.duration,
                width=result.width,
                height=result.height,
                supports_streaming=True,
                thumbnail=thumb if with_thumb else None,
                caption=_clip(result.title, 1024),
            )

        try:
            message = await _send(thumb is not None)
        except TelegramBadRequest as exc:
            if thumb is None:
                raise
            # A thumbnail Telegram dislikes must not cost us the whole upload.
            log.warning("send_video_thumb_rejected", error=str(exc))
            message = await _send(False)
        file_id = _video_file_id(message)
    return SendResult(file_id=file_id, kind=result.kind, message_id=message.message_id)


async def send_by_file_id(
    bot: Bot,
    chat_id: int,
    file_id: str,
    kind: Literal["video", "audio"],
    *,
    title: str = "",
    performer: str = "",
    duration: int | None = None,
) -> SendResult:
    with uploads:
        return await _send_by_file_id(
            bot, chat_id, file_id, kind, title=title, performer=performer, duration=duration
        )


async def _send_by_file_id(
    bot: Bot,
    chat_id: int,
    file_id: str,
    kind: Literal["video", "audio"],
    *,
    title: str = "",
    performer: str = "",
    duration: int | None = None,
) -> SendResult:
    if kind == "audio":
        message = await bot.send_audio(
            chat_id,
            audio=file_id,
            title=_clip(title, 64) or "audio",
            performer=_clip(performer, 64) or "unknown",
            duration=duration,
        )
        resolved = _audio_file_id(message)
    else:
        message = await bot.send_video(
            chat_id,
            video=file_id,
            supports_streaming=True,
            duration=duration,
        )
        resolved = _video_file_id(message)
    return SendResult(file_id=resolved or file_id, kind=kind, message_id=message.message_id)


def _video_file_id(message: Message) -> str:
    if message.video is not None:
        return message.video.file_id
    if message.document is not None:
        return message.document.file_id
    log.warning("missing_video_file_id")
    return ""


def _audio_file_id(message: Message) -> str:
    if message.audio is not None:
        return message.audio.file_id
    if message.document is not None:
        return message.document.file_id
    log.warning("missing_audio_file_id")
    return ""
