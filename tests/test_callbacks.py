from __future__ import annotations

import asyncio
from pathlib import Path

from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SendAudio, SendVideo
from bot.config import get_settings
from bot.handlers.callbacks import on_another, on_cancel, on_format
from bot.i18n import t
from bot.keyboards import AnotherCb, CancelCb, FormatCb
from bot.services.downloader import DownloadError, DownloadResult, FileTooLargeError
from bot.services.extractor import FormatOption, MediaInfo
from bot.storage.cache import clear_jobs, put_job

from tests.conftest import make_callback, make_message


def _info() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/aaaaaaaaaaa",
        normalised_url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
        platform="youtube",
        title="Clip",
        duration=10,
        thumbnail=None,
        uploader="Author",
        formats=[
            FormatOption("360", "360p", "18", 1_000, True, False, 360, 640),
            FormatOption("1080", "1080p", "137", 90_000_000, True, True, 1080, 1920),
            FormatOption("audio", "mp3", "bestaudio/best", 1000, True, False),
        ],
    )


class FakeDownloader:
    def __init__(self, tmp_path: Path, *, fail: bool = False) -> None:
        self.tmp_path = tmp_path
        self.fail = fail
        self.cleaned: list[Path] = []
        self.called = 0

    async def download(self, info, option, *, progress=None, cancel_event=None):
        self.called += 1
        if self.fail:
            raise DownloadError("boom")
        if option.exceeds_limit:
            raise FileTooLargeError("big")
        if progress:
            await progress(40)
        kind = "audio" if option.key == "audio" else "video"
        path = self.tmp_path / ("a.mp3" if kind == "audio" else "v.mp4")
        path.write_bytes(b"media")
        return DownloadResult(
            path=path,
            workdir=self.tmp_path,
            kind=kind,
            duration=info.duration,
            width=option.width,
            height=option.height,
            title=info.title,
            performer=info.uploader or "x",
            thumbnail=None,
            size_bytes=5,
        )

    def cleanup(self, result=None, workdir=None) -> None:
        target = result.workdir if result is not None else workdir
        if target is not None:
            self.cleaned.append(target)


async def test_format_sends_video(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    fake = FakeDownloader(tmp_path)
    cb = make_callback(FormatCb(t=token, k="360").pack(), bot=bot)
    await on_format(
        cb,
        FormatCb(t=token, k="360"),
        settings=get_settings(),
        downloader=fake,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    kinds = [type(r).__name__ for r in session.requests]  # type: ignore[attr-defined]
    assert "SendVideo" in kinds
    video = next(r for r in session.requests if isinstance(r, SendVideo))  # type: ignore[attr-defined]
    assert video.supports_streaming is True
    assert fake.cleaned
    edits = [r for r in session.requests if type(r).__name__ == "EditMessageText"]  # type: ignore[attr-defined]
    assert any(t("btn_another", "ru") in str(getattr(r, "reply_markup", "")) for r in edits) or any(
        t("download_done", "ru", title="Clip") == getattr(r, "text", None) for r in edits
    )


async def test_audio_button(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    fake = FakeDownloader(tmp_path)
    await on_format(
        make_callback(FormatCb(t=token, k="audio").pack(), bot=bot),
        FormatCb(t=token, k="audio"),
        settings=get_settings(),
        downloader=fake,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    audio = next(r for r in session.requests if isinstance(r, SendAudio))  # type: ignore[attr-defined]
    assert audio.title == "Clip"
    assert audio.performer == "Author"


async def test_oversize_explains(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    fake = FakeDownloader(tmp_path)
    await on_format(
        make_callback(FormatCb(t=token, k="1080").pack(), bot=bot),
        FormatCb(t=token, k="1080"),
        settings=get_settings(),
        downloader=fake,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    assert fake.called == 0
    texts = [getattr(r, "text", "") for r in session.requests]  # type: ignore[attr-defined]
    assert any("50" in (text or "") and "МБ" in (text or "") for text in texts)


async def test_cancel_button(mocked_bot: tuple[Bot, object], env_settings: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    await on_cancel(
        make_callback(CancelCb(t=token).pack(), bot=bot),
        CancelCb(t=token),
    )
    texts = [getattr(r, "text", "") for r in session.requests]  # type: ignore[attr-defined]
    assert t("cancelled", "ru") in texts
    assert any(isinstance(r, AnswerCallbackQuery) for r in session.requests)  # type: ignore[attr-defined]


async def test_download_error_no_traceback(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    await on_format(
        make_callback(FormatCb(t=token, k="360").pack(), bot=bot),
        FormatCb(t=token, k="360"),
        settings=get_settings(),
        downloader=FakeDownloader(tmp_path, fail=True),  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    texts = [getattr(r, "text", "") or "" for r in session.requests]  # type: ignore[attr-defined]
    assert t("err_download", "ru") in texts
    assert not any("Traceback" in text for text in texts)


async def test_another_format_restores_keyboard(
    mocked_bot: tuple[Bot, object], env_settings: None
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    await on_another(
        make_callback(AnotherCb(t=token).pack(), bot=bot),
        AnotherCb(t=token),
        settings=get_settings(),
    )
    edits = [r for r in session.requests if type(r).__name__ == "EditMessageText"]  # type: ignore[attr-defined]
    assert edits
    markup = edits[-1].reply_markup
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert any("360p" in text for text in texts)
    assert t("btn_cancel", "ru") in texts


def test_make_message_helper_smoke() -> None:
    assert make_message("x").text == "x"
