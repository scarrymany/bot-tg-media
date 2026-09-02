from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.methods import SendAudio, SendVideo
from bot.services.downloader import DownloadResult
from bot.services.sender import send_by_file_id, send_media


def _result(tmp_path: Path, kind: str) -> DownloadResult:
    path = tmp_path / ("a.mp3" if kind == "audio" else "v.mp4")
    path.write_bytes(b"data")
    return DownloadResult(
        path=path,
        workdir=tmp_path,
        kind=kind,  # type: ignore[arg-type]
        duration=12,
        width=640,
        height=360,
        title="Song Title",
        performer="The Band",
        thumbnail=None,
        size_bytes=4,
    )


async def test_send_video_streaming(mocked_bot: tuple[Bot, object], tmp_path: Path) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    sent = await send_media(bot, 42, _result(tmp_path, "video"))
    req = session.requests[0]  # type: ignore[attr-defined]
    assert isinstance(req, SendVideo)
    assert req.supports_streaming is True
    assert sent.file_id == "vid-file-id"
    assert sent.kind == "video"


async def test_send_audio_title_performer(mocked_bot: tuple[Bot, object], tmp_path: Path) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    sent = await send_media(bot, 42, _result(tmp_path, "audio"))
    req = session.requests[0]  # type: ignore[attr-defined]
    assert isinstance(req, SendAudio)
    assert req.title == "Song Title"
    assert req.performer == "The Band"
    assert sent.file_id == "aud-file-id"


async def test_send_by_file_id(mocked_bot: tuple[Bot, object]) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await send_by_file_id(bot, 7, "cached-id", "video")
    req = session.requests[0]  # type: ignore[attr-defined]
    assert isinstance(req, SendVideo)
    assert req.video == "cached-id"
    assert req.supports_streaming is True
