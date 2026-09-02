from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import structlog

from bot.config import Settings
from bot.services.extractor import FormatOption, MediaInfo

log = structlog.get_logger("downloader")

ProgressCb = Callable[[int], Awaitable[None]]
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac"}
THUMB_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class DownloadError(Exception):
    """Download or post-process failed."""


class FileTooLargeError(DownloadError):
    """File exceeds MAX_FILE_MB after or before download."""


class DownloadCancelled(DownloadError):
    """User cancelled the job."""


@dataclass(slots=True)
class DownloadResult:
    path: Path
    workdir: Path
    kind: Literal["video", "audio"]
    duration: int | None
    width: int | None
    height: int | None
    title: str
    performer: str
    thumbnail: Path | None
    size_bytes: int


def map_error_key(exc: BaseException) -> str:
    if isinstance(exc, FileTooLargeError):
        return "err_too_large"
    if isinstance(exc, DownloadCancelled):
        return "err_cancelled"
    if isinstance(exc, DownloadError):
        return "err_download"
    return "err_generic"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


class ProgressGate:
    def __init__(self, min_interval: float = 2.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def allow(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if force or self._last == 0.0 or now - self._last >= self.min_interval:
            self._last = now
            return True
        return False


def make_progress_hook(
    loop: asyncio.AbstractEventLoop,
    progress: ProgressCb | None,
    cancel_event: asyncio.Event | None,
    gate: ProgressGate | None = None,
) -> Callable[[dict[str, Any]], None]:
    gate = gate or ProgressGate(2.0)

    def hook(status: dict[str, Any]) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled("cancelled")
        if status.get("status") != "downloading":
            return
        downloaded = int(status.get("downloaded_bytes") or 0)
        total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
        pct = int(downloaded * 100 / total) if total else 0
        pct = min(99, max(0, pct))
        if not gate.allow() or progress is None:
            return
        asyncio.run_coroutine_threadsafe(_ignore_progress_errors(progress, pct), loop)

    return hook


async def _ignore_progress_errors(progress: ProgressCb, pct: int) -> None:
    try:
        await progress(pct)
    except Exception:
        log.debug("progress_update_failed", pct=pct)


def _ydl_download(
    url: str,
    *,
    format_selector: str,
    outtmpl: str,
    is_audio: bool,
    cookiefile: str | None,
    progress_hooks: list[Callable[[dict[str, Any]], None]],
) -> None:
    import yt_dlp

    opts: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "progress_hooks": progress_hooks,
        "socket_timeout": 30,
        "retries": 2,
        "restrictfilenames": True,
        "writethumbnail": True,
    }
    if is_audio:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    if cookiefile:
        opts["cookiefile"] = cookiefile
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def _find_output(workdir: Path, kind: Literal["video", "audio"]) -> Path:
    files = [p for p in workdir.iterdir() if p.is_file()]
    preferred = AUDIO_EXTS if kind == "audio" else VIDEO_EXTS
    matched = [p for p in files if p.suffix.lower() in preferred]
    if not matched:
        matched = [
            p
            for p in files
            if p.suffix.lower() not in THUMB_EXTS | {".json", ".part", ".ytdl", ".info"}
        ]
    if not matched:
        raise DownloadError("no output file")
    return max(matched, key=lambda p: p.stat().st_size)


def _find_thumb(workdir: Path) -> Path | None:
    thumbs = [p for p in workdir.iterdir() if p.is_file() and p.suffix.lower() in THUMB_EXTS]
    return thumbs[0] if thumbs else None


def cleanup_dir(workdir: Path | None) -> None:
    if workdir is None:
        return
    try:
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
    except OSError:
        log.warning("cleanup_failed", path=str(workdir))


class Downloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def wait_idle(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while self._in_flight and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

    def cleanup(self, result: DownloadResult | None = None, workdir: Path | None = None) -> None:
        target = result.workdir if result is not None else workdir
        cleanup_dir(target)

    async def download(
        self,
        info: MediaInfo,
        option: FormatOption,
        *,
        progress: ProgressCb | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> DownloadResult:
        max_bytes = self.settings.max_file_bytes
        if option.exceeds_limit or (
            option.est_size_bytes is not None and option.est_size_bytes > max_bytes
        ):
            raise FileTooLargeError("estimated size exceeds limit")
        if option.key == "audio" and not ffmpeg_available():
            raise DownloadError("ffmpeg is required for mp3 extraction")

        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled("cancelled")

        self.settings.download_dir.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix="job_", dir=str(self.settings.download_dir)))
        kind: Literal["video", "audio"] = "audio" if option.key == "audio" else "video"
        self._in_flight += 1
        try:
            loop = asyncio.get_running_loop()
            hook = make_progress_hook(loop, progress, cancel_event)
            cookiefile = None
            cookies = self.settings.ig_cookies_file
            if cookies is not None and cookies.is_file():
                cookiefile = str(cookies)
            outtmpl = str(workdir / "%(id)s.%(ext)s")
            await loop.run_in_executor(
                None,
                lambda: _ydl_download(
                    info.normalised_url,
                    format_selector=option.format_selector,
                    outtmpl=outtmpl,
                    is_audio=kind == "audio",
                    cookiefile=cookiefile,
                    progress_hooks=[hook],
                ),
            )
            path = _find_output(workdir, kind)
            size = path.stat().st_size
            if size > max_bytes:
                raise FileTooLargeError("downloaded file exceeds limit")
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled("cancelled")
            return DownloadResult(
                path=path,
                workdir=workdir,
                kind=kind,
                duration=info.duration,
                width=option.width or info.width,
                height=option.height or info.height,
                title=info.title,
                performer=info.uploader or info.title,
                thumbnail=_find_thumb(workdir),
                size_bytes=size,
            )
        except DownloadCancelled:
            cleanup_dir(workdir)
            raise
        except FileTooLargeError:
            cleanup_dir(workdir)
            raise
        except DownloadError:
            cleanup_dir(workdir)
            raise
        except Exception as exc:
            cleanup_dir(workdir)
            log.exception("download_failed", url=info.normalised_url)
            raise DownloadError(str(exc)) from exc
        finally:
            self._in_flight = max(0, self._in_flight - 1)
