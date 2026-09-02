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
