from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from bot.config import Settings
from bot.services.downloader import (
    DownloadCancelled,
    Downloader,
    DownloadError,
    FileTooLargeError,
    ProgressGate,
    _find_output,
    cleanup_dir,
    make_progress_hook,
    map_error_key,
)
from bot.services.extractor import FormatOption, MediaInfo


def _settings(tmp_path: Path, max_file_mb: int = 50) -> Settings:
    return Settings(
        bot_token="123456:TESTTOKEN-scaffold",
        download_dir=tmp_path / "dl",
        db_path=tmp_path / "db" / "bot.db",
        max_file_mb=max_file_mb,
    )


def _info() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/aaaaaaaaaaa",
        normalised_url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
        platform="youtube",
        title="Clip",
        duration=10,
        thumbnail=None,
        uploader="Author",
        formats=[],
        width=640,
        height=360,
    )


def _opt(*, key: str = "360", exceeds: bool = False, size: int | None = 1_000) -> FormatOption:
    return FormatOption(key, f"{key}p", "18", size, True, exceeds, 360, 640)


def test_progress_gate_throttles() -> None:
    gate = ProgressGate(min_interval=10.0)
    assert gate.allow() is True
    assert gate.allow() is False
    assert gate.allow(force=True) is True


def test_map_error_key() -> None:
    assert map_error_key(FileTooLargeError()) == "err_too_large"
    assert map_error_key(DownloadCancelled()) == "err_cancelled"
    assert map_error_key(DownloadError("x")) == "err_download"
    assert map_error_key(RuntimeError("x")) == "err_generic"


def test_find_output_and_cleanup(tmp_path: Path) -> None:
    work = tmp_path / "job"
    work.mkdir()
    (work / "thumb.jpg").write_bytes(b"t")
    video = work / "out.mp4"
    video.write_bytes(b"video-bytes")
    assert _find_output(work, "video") == video
    cleanup_dir(work)
    assert not work.exists()


async def test_size_guard_before(tmp_path: Path) -> None:
    downloader = Downloader(_settings(tmp_path))
    with pytest.raises(FileTooLargeError):
        await downloader.download(_info(), _opt(exceeds=True, size=99_000_000))


async def test_size_guard_after_cleans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, max_file_mb=1)
    downloader = Downloader(settings)

    def fake_ydl(url: str, **kwargs) -> None:
        dest = Path(kwargs["outtmpl"]).parent
        (dest / "big.mp4").write_bytes(b"\0" * (1024 * 1024 + 50))

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    with pytest.raises(FileTooLargeError):
        await downloader.download(_info(), _opt(size=None))
    assert list(settings.download_dir.glob("job_*")) == []


async def test_download_success_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    downloader = Downloader(settings)
    percents: list[int] = []

    def fake_ydl(url: str, **kwargs) -> None:
        dest = Path(kwargs["outtmpl"]).parent
        hook = kwargs["progress_hooks"][0]
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        hook({"status": "finished"})
        (dest / "ok.mp4").write_bytes(b"mp4data")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)

    async def on_progress(pct: int) -> None:
        percents.append(pct)

    result = await downloader.download(_info(), _opt(size=None), progress=on_progress)
    assert result.path.exists()
    assert result.kind == "video"
    assert result.title == "Clip"
    assert result.size_bytes == 7
    await asyncio.sleep(0.05)
    assert percents
    downloader.cleanup(result)
    assert not result.workdir.exists()


async def test_cancel_via_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloader = Downloader(_settings(tmp_path))
    cancel = asyncio.Event()

    def fake_ydl(url: str, **kwargs) -> None:
        hook = kwargs["progress_hooks"][0]
        cancel.set()
        hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    with pytest.raises(DownloadCancelled):
        await downloader.download(_info(), _opt(size=None), cancel_event=cancel)


async def test_audio_passes_ffmpeg_postprocessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}
    monkeypatch.setattr("bot.services.downloader.ffmpeg_available", lambda: True)

    def fake_ydl(url: str, **kwargs) -> None:
        captured.update(kwargs)
        dest = Path(kwargs["outtmpl"]).parent
        (dest / "a.mp3").write_bytes(b"id3")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    result = await Downloader(_settings(tmp_path)).download(
        _info(), FormatOption("audio", "mp3", "bestaudio/best", 100, True, False)
    )
    assert result.kind == "audio"
    assert captured.get("is_audio") is True


def test_progress_hook_cancel_sync() -> None:
    loop = asyncio.new_event_loop()
    cancel = asyncio.Event()
    cancel.set()
    hook = make_progress_hook(loop, None, cancel)
    with pytest.raises(DownloadCancelled):
        hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})
    loop.close()
