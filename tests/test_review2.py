"""Regression tests for the second review pass.

Each test pins one of the low-severity findings left open by review pass 1.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.methods import SendVideo
from bot.config import get_settings
from bot.handlers.callbacks import on_format
from bot.keyboards import FormatCb
from bot.services.detector import DetectedLink, classify_url
from bot.services.downloader import DownloadResult
from bot.services.extractor import (
    ExtractError,
    FormatOption,
    InstagramCookiesError,
    MediaInfo,
    extract_media,
)
from bot.storage.cache import clear_jobs, get_cached, put_cached, put_job

from tests.conftest import make_callback

# --------------------------------------------------------------------------
# cache identity: short links must share a row with the canonical URL
# --------------------------------------------------------------------------

TIKTOK_RESOLVED: dict[str, Any] = {
    "id": "7212345678901234567",
    "extractor_key": "TikTok",
    "webpage_url": "https://www.tiktok.com/@user/video/7212345678901234567",
    "title": "dance",
    "duration": 8,
    "formats": [
        {
            "format_id": "play_addr",
            "height": 720,
            "width": 720,
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": 3_000_000,
        }
    ],
}


def _link(url: str) -> DetectedLink:
    detected = classify_url(url)
    assert detected is not None, url
    return detected


async def test_short_and_canonical_tiktok_links_share_a_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vm.tiktok.com short link and the canonical URL are the same video.

    They normalise differently, so keying the file_id cache on the typed URL
    stored two rows and re-downloaded the video for the second shape.
    """
    monkeypatch.setattr(
        "bot.services.extractor._ydl_extract", lambda url, opts: dict(TIKTOK_RESOLVED)
    )
    short = await extract_media(_link("https://vm.tiktok.com/ZMabcdef/"), max_file_mb=50)
    canonical = await extract_media(
        _link("https://www.tiktok.com/@user/video/7212345678901234567"), max_file_mb=50
    )
    assert short.normalised_url != canonical.normalised_url
    assert short.cache_key == canonical.cache_key == "tiktok:7212345678901234567"


def test_cache_key_falls_back_to_webpage_url_then_normalised_url() -> None:
    base: dict[str, Any] = {
        "source_url": "https://youtu.be/aaaaaaaaaaa",
        "normalised_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "platform": "youtube",
        "title": "Clip",
        "duration": 1,
        "thumbnail": None,
        "uploader": None,
    }
    assert MediaInfo(**base).cache_key == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    with_page = MediaInfo(
        **base, webpage_url="https://www.youtube.com/watch?v=aaaaaaaaaaa&si=track"
    )
    # Tracking parameters must not split the cache either.
    assert with_page.cache_key == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    with_id = MediaInfo(**base, media_id="aaaaaaaaaaa", extractor="Youtube")
    assert with_id.cache_key == "youtube:aaaaaaaaaaa"


def _cached_info(normalised_url: str) -> MediaInfo:
    return MediaInfo(
        source_url=normalised_url,
        normalised_url=normalised_url,
        platform="tiktok",
        title="dance",
        duration=8,
        thumbnail=None,
        uploader="user",
        formats=[FormatOption("720", "720p", "play_addr", 3_000_000, True, False, 720, 720)],
        media_id="7212345678901234567",
        extractor="tiktok",
    )


class _NeverCalledDownloader:
    def __init__(self) -> None:
        self.called = 0

    async def download(self, info: Any, option: Any, **kwargs: Any) -> DownloadResult:
        self.called += 1
        raise AssertionError("cache hit expected, the downloader must not run")

    def cleanup(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return None


async def test_short_link_hits_the_cache_written_by_the_canonical_url(
    mocked_bot: tuple[Bot, Any], db: None
) -> None:
    clear_jobs()
    canonical = _cached_info("https://www.tiktok.com/@user/video/7212345678901234567")
    await put_cached(canonical.cache_key, "720", "cached-file-id", "video")

    bot, session = mocked_bot
    short = _cached_info("https://vm.tiktok.com/ZMabcdef")
    token = put_job(short, 42)
    downloader = _NeverCalledDownloader()
    await on_format(
        make_callback(FormatCb(t=token, k="720").pack(), bot=bot),
        FormatCb(t=token, k="720"),
        settings=get_settings(),
        downloader=downloader,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    assert downloader.called == 0
    video = next(r for r in session.requests if isinstance(r, SendVideo))
    assert video.video == "cached-file-id"


async def test_successful_download_stores_under_the_cache_key(
    mocked_bot: tuple[Bot, Any], db: None, tmp_path: Path
) -> None:
    clear_jobs()
    info = _cached_info("https://vm.tiktok.com/ZMabcdef")
    token = put_job(info, 42)

    class _Fake:
        async def download(self, media: Any, option: Any, **kwargs: Any) -> DownloadResult:
            path = tmp_path / "v.mp4"
            path.write_bytes(b"media")
            return DownloadResult(
                path=path,
                workdir=tmp_path,
                kind="video",
                duration=8,
                width=720,
                height=720,
                title="dance",
                performer="user",
                thumbnail=None,
                size_bytes=5,
            )

        def cleanup(self, *args: Any, **kwargs: Any) -> None:
            return None

    bot, _ = mocked_bot
    await on_format(
        make_callback(FormatCb(t=token, k="720").pack(), bot=bot),
        FormatCb(t=token, k="720"),
        settings=get_settings(),
        downloader=_Fake(),  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    assert await get_cached("tiktok:7212345678901234567", "720") is not None
    # The typed URL must no longer be used as a key.
    assert await get_cached(info.normalised_url, "720") is None


# --------------------------------------------------------------------------
# Instagram: only a real login wall may be reported as a cookies problem
# --------------------------------------------------------------------------

IG_LINK = "https://www.instagram.com/reel/CabcDEfGh/"


async def _ig_extract(monkeypatch: pytest.MonkeyPatch, message: str) -> BaseException:
    def boom(url: str, opts: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(message)

    monkeypatch.setattr("bot.services.extractor._ydl_extract", boom)
    with pytest.raises(ExtractError) as excinfo:
        await extract_media(_link(IG_LINK), max_file_mb=50, cookies_file=None)
    return excinfo.value


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [Instagram] Cabc: Requested content is not available, rate-limit reached "
        "or login required. Use --cookies-from-browser or --cookies for the authentication.",
        "ERROR: [Instagram] Cabc: Login required",
        "ERROR: [Instagram] Cabc: You need to log in to access this content",
        "HTTP Error 429: Too Many Requests",
    ],
)
async def test_instagram_login_wall_asks_for_cookies(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    assert isinstance(await _ig_extract(monkeypatch, message), InstagramCookiesError)


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [Instagram] Cabc: Video not available",
        "ERROR: [Instagram] Cabc: The requested content is not available",
        "ERROR: [Instagram] Cabc: Unable to download webpage: HTTP Error 404: Not Found",
        "ERROR: [Instagram] Cabc: This post is unavailable, it may have been deleted",
        "ERROR: [Instagram] Cabc: Unable to extract shared data",
        "HTTP Error 403: Forbidden",
    ],
)
async def test_instagram_missing_content_is_a_plain_extract_error(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    """A deleted or private post used to be reported as 'configure IG_COOKIES_FILE',
    sending the user off to set up cookies that would not have helped."""
    error = await _ig_extract(monkeypatch, message)
    assert not isinstance(error, InstagramCookiesError)


# --------------------------------------------------------------------------
# graceful shutdown must wait for uploads, not only downloads
# --------------------------------------------------------------------------


async def test_wait_idle_waits_for_an_upload_in_flight(tmp_path: Path) -> None:
    """SIGTERM used to cut a sendVideo in progress: only downloads were counted."""
    from bot.config import Settings
    from bot.services.downloader import Downloader
    from bot.services.inflight import uploads as counter

    downloader = Downloader(
        Settings(
            bot_token="123456:TESTTOKEN-scaffold",
            download_dir=tmp_path / "dl",
            db_path=tmp_path / "db" / "bot.db",
        )
    )
    assert downloader.busy == 0
    assert await downloader.wait_idle(timeout=0.2) is True

    with counter:
        assert downloader.in_flight == 0
        assert downloader.busy == 1
        assert await downloader.wait_idle(timeout=0.2) is False
    assert downloader.busy == 0
    assert await downloader.wait_idle(timeout=0.2) is True


async def test_send_media_is_counted_while_it_runs(
    mocked_bot: tuple[Bot, Any], tmp_path: Path
) -> None:
    from bot.services.downloader import DownloadResult
    from bot.services.inflight import uploads as counter
    from bot.services.sender import send_media

    bot, session = mocked_bot
    seen: list[int] = []

    original = session.make_request

    async def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(counter.count)
        return await original(*args, **kwargs)

    session.make_request = spy  # type: ignore[method-assign]
    path = tmp_path / "v.mp4"
    path.write_bytes(b"media")
    await send_media(
        bot,
        1,
        DownloadResult(
            path=path,
            workdir=tmp_path,
            kind="video",
            duration=1,
            width=2,
            height=3,
            title="t",
            performer="p",
            thumbnail=None,
            size_bytes=5,
        ),
    )
    assert seen == [1], "the upload must be counted while the request is running"
    assert counter.count == 0, "and released afterwards"


# --------------------------------------------------------------------------
# a failed ffmpeg merge must not ship a silent video
# --------------------------------------------------------------------------


def test_looks_unmerged_recognises_ytdlp_part_names() -> None:
    from bot.services.downloader import looks_unmerged

    assert looks_unmerged(Path("video.f137.mp4")) is True
    assert looks_unmerged(Path("video.f251.webm")) is True
    assert looks_unmerged(Path("video.mp4")) is False
    assert looks_unmerged(Path("my.f-clip.mp4")) is False


def test_map_error_key_covers_a_failed_merge() -> None:
    from bot.i18n import LANGS
    from bot.services.downloader import MergeFailedError, map_error_key

    assert map_error_key(MergeFailedError("x")) == "err_merge"
    assert "err_merge" in LANGS["ru"]
    assert "err_merge" in LANGS["en"]


def _dl_settings(tmp_path: Path, max_file_mb: int = 50) -> Any:
    from bot.config import Settings

    return Settings(
        bot_token="123456:TESTTOKEN-scaffold",
        download_dir=tmp_path / "dl",
        db_path=tmp_path / "db" / "bot.db",
        max_file_mb=max_file_mb,
    )


def _dl_info() -> MediaInfo:
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


async def test_unmerged_leftover_is_rejected_instead_of_sent_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ffmpeg fails to mux, yt-dlp leaves the video-only part behind and
    _find_output picks it: the user used to receive a silent video."""
    from bot.services.downloader import Downloader, MergeFailedError

    settings = _dl_settings(tmp_path)

    def fake_ydl(url: str, **kwargs: Any) -> None:
        dest = Path(kwargs["outtmpl"]).parent
        (dest / "clip.f137.mp4").write_bytes(b"video-only")
        (dest / "clip.f140.m4a").write_bytes(b"audio")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    option = FormatOption("720", "720p", "137+140", None, True, False, 720, 1280)
    with pytest.raises(MergeFailedError):
        await Downloader(settings).download(_dl_info(), option)
    assert list(settings.download_dir.glob("job_*")) == [], "the workdir must be cleaned"


async def test_merged_output_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bot.services.downloader import Downloader

    def fake_ydl(url: str, **kwargs: Any) -> None:
        (Path(kwargs["outtmpl"]).parent / "clip.mp4").write_bytes(b"merged")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    monkeypatch.setattr("bot.services.downloader.probe_has_audio", lambda path: True)
    option = FormatOption("720", "720p", "137+140", None, True, False, 720, 1280)
    result = await Downloader(_dl_settings(tmp_path)).download(_dl_info(), option)
    assert result.path.name == "clip.mp4"


async def test_output_without_an_audio_stream_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bot.services.downloader import Downloader, MergeFailedError

    def fake_ydl(url: str, **kwargs: Any) -> None:
        (Path(kwargs["outtmpl"]).parent / "clip.mp4").write_bytes(b"merged")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    monkeypatch.setattr("bot.services.downloader.probe_has_audio", lambda path: False)
    option = FormatOption("720", "720p", "137+140", None, True, False, 720, 1280)
    with pytest.raises(MergeFailedError):
        await Downloader(_dl_settings(tmp_path)).download(_dl_info(), option)


async def test_an_unprobeable_file_is_still_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffprobe missing or unhappy must never reject a file that is actually fine."""
    from bot.services.downloader import Downloader

    def fake_ydl(url: str, **kwargs: Any) -> None:
        (Path(kwargs["outtmpl"]).parent / "clip.mp4").write_bytes(b"merged")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    monkeypatch.setattr("bot.services.downloader.probe_has_audio", lambda path: None)
    option = FormatOption("720", "720p", "137+140", None, True, False, 720, 1280)
    result = await Downloader(_dl_settings(tmp_path)).download(_dl_info(), option)
    assert result.path.name == "clip.mp4"


def test_probe_has_audio_never_raises_on_a_junk_file(tmp_path: Path) -> None:
    from bot.services.downloader import probe_has_audio

    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert probe_has_audio(junk) in {None, False}


# --------------------------------------------------------------------------
# peak temp usage: the parts together, not each part, must fit MAX_FILE_MB
# --------------------------------------------------------------------------


def test_progress_hook_caps_the_sum_of_the_parts() -> None:
    """Each part used to be capped on its own, so a merged download could put
    2 x MAX_FILE_MB into DOWNLOAD_DIR before anything complained."""
    from bot.services.downloader import FileTooLargeError, ProgressGate, make_progress_hook

    loop = asyncio.new_event_loop()
    try:
        hook = make_progress_hook(loop, None, None, ProgressGate(0.0), max_bytes=100)
        hook({"status": "downloading", "downloaded_bytes": 60, "total_bytes": 60})
        hook({"status": "finished", "total_bytes": 60})
        # 60 already on disk + a 50-byte audio part is over the 100-byte cap.
        with pytest.raises(FileTooLargeError):
            hook({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 50})
    finally:
        loop.close()


def test_progress_hook_allows_parts_that_fit_together() -> None:
    from bot.services.downloader import ProgressGate, make_progress_hook

    loop = asyncio.new_event_loop()
    try:
        hook = make_progress_hook(loop, None, None, ProgressGate(0.0), max_bytes=100)
        hook({"status": "downloading", "downloaded_bytes": 60, "total_bytes": 60})
        hook({"status": "finished", "total_bytes": 60})
        hook({"status": "downloading", "downloaded_bytes": 30, "total_bytes": 30})
        hook({"status": "finished", "total_bytes": 30})
    finally:
        loop.close()


# --------------------------------------------------------------------------
# Dockerfile: unprivileged user with a writable /data
# --------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_dockerfile_runs_unprivileged_with_a_writable_data_dir() -> None:
    """Docker seeds a fresh named volume from the image directory, ownership
    included - but only what exists at the time VOLUME is declared. Getting the
    order wrong yields a root-owned /data that the app user cannot write, and
    that cannot be verified without a Docker daemon, hence this check."""
    lines = [
        line.strip()
        for line in (_repo_root() / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    index = {}
    for position, line in enumerate(lines):
        if line.startswith("RUN useradd"):
            index["useradd"] = position
        elif line.startswith("RUN mkdir -p /data") and "chown" in line:
            index["chown"] = position
        elif line.startswith("VOLUME"):
            index["volume"] = position
        elif line.startswith("USER "):
            index["user"] = position
        elif line.startswith("CMD"):
            index["cmd"] = position
    assert set(index) == {"useradd", "chown", "volume", "user", "cmd"}, index
    assert index["useradd"] < index["chown"] < index["volume"], "chown must precede VOLUME"
    assert index["volume"] < index["user"] < index["cmd"]
    assert lines[index["user"]] == "USER app"


def test_compose_healthcheck_is_unchanged_and_needs_no_write_access() -> None:
    compose = (_repo_root() / "docker-compose.yml").read_text(encoding="utf-8")
    assert "HEARTBEAT_PATH: /tmp/bot-heartbeat" in compose
    # The check only reads an mtime, so it works for a non-root user too.
    assert "os.path.getmtime(p)" in compose
    assert "start_period: 40s" in compose
