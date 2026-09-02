from __future__ import annotations

from pathlib import Path

import pytest
from bot.services.detector import DetectedLink
from bot.services.extractor import (
    ExtractError,
    InstagramCookiesError,
    build_format_options,
    extract_media,
)

MAX_BYTES = 50 * 1024 * 1024

FAKE_INFO: dict = {
    "title": "Test Video",
    "duration": 12,
    "thumbnail": "http://example.com/t.jpg",
    "uploader": "Someone",
    "width": 1920,
    "height": 1080,
    "formats": [
        {
            "format_id": "18",
            "height": 360,
            "width": 640,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "filesize": 5_000_000,
            "ext": "mp4",
        },
        {
            "format_id": "22",
            "height": 720,
            "width": 1280,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "filesize": 20_000_000,
            "ext": "mp4",
        },
        {
            "format_id": "137",
            "height": 1080,
            "width": 1920,
            "vcodec": "avc1",
            "acodec": "none",
            "filesize": 80_000_000,
            "ext": "mp4",
        },
        {
            "format_id": "140",
            "vcodec": "none",
            "acodec": "mp4a",
            "filesize": 2_000_000,
            "ext": "m4a",
            "abr": 128,
        },
    ],
}

TIKTOK_INFO: dict = {
    "title": "dance",
    "duration": 8,
    "formats": [
        {
            "format_id": "watermarked",
            "height": 720,
            "width": 720,
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": 4_000_000,
            "format_note": "with watermark",
        },
        {
            "format_id": "download",
            "height": 720,
            "width": 720,
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": 3_500_000,
            "format_note": "no-watermark",
        },
    ],
}


def test_size_flags() -> None:
    options = build_format_options(FAKE_INFO, max_file_bytes=MAX_BYTES, platform="youtube")
    by_key = {opt.key: opt for opt in options}
    assert by_key["360"].exceeds_limit is False
    assert by_key["720"].exceeds_limit is False
    assert by_key["1080"].exceeds_limit is True
    assert by_key["1080"].est_size_bytes == 82_000_000
    assert by_key["audio"].key == "audio"
    assert by_key["360"].has_audio is True


def test_tiktok_prefers_no_watermark() -> None:
    options = build_format_options(TIKTOK_INFO, max_file_bytes=MAX_BYTES, platform="tiktok")
    video = next(opt for opt in options if opt.key == "720")
    assert video.format_selector == "download"


async def test_extract_media_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bot.services.extractor._ydl_extract", lambda url, opts: FAKE_INFO)
    link = DetectedLink(
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "youtube",
    )
    info = await extract_media(link, max_file_mb=50)
    assert info.title == "Test Video"
    assert info.duration == 12
    assert {opt.key for opt in info.formats} >= {"360", "720", "1080", "audio"}


async def test_instagram_login_without_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, opts: dict) -> dict:
        raise RuntimeError("Login required to download this upload")

    monkeypatch.setattr("bot.services.extractor._ydl_extract", boom)
    link = DetectedLink(
        "https://www.instagram.com/reel/AbCdef12345/",
        "https://www.instagram.com/reel/AbCdef12345/",
        "instagram_reels",
    )
    with pytest.raises(InstagramCookiesError):
        await extract_media(link, max_file_mb=50, cookies_file=None)


async def test_instagram_error_with_cookies_is_extract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cookies = tmp_path / "ig.txt"
    cookies.write_text("# netscape\n", encoding="utf-8")

    def boom(url: str, opts: dict) -> dict:
        assert opts.get("cookiefile") == str(cookies)
        raise RuntimeError("Login required")

    monkeypatch.setattr("bot.services.extractor._ydl_extract", boom)
    link = DetectedLink(
        "https://www.instagram.com/reel/AbCdef12345/",
        "https://www.instagram.com/reel/AbCdef12345/",
        "instagram_reels",
    )
    with pytest.raises(ExtractError) as exc:
        await extract_media(link, max_file_mb=50, cookies_file=cookies)
    assert not isinstance(exc.value, InstagramCookiesError)


async def test_generic_extract_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bot.services.extractor._ydl_extract",
        lambda url, opts: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    link = DetectedLink("x", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube")
    with pytest.raises(ExtractError):
        await extract_media(link, max_file_mb=50)
