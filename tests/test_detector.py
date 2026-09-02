from __future__ import annotations

import pytest
from bot.services.detector import classify_url, detect_links, looks_like_url

# (raw, platform, normalised)
CASES: list[tuple[str, str, str]] = [
    (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://youtube.com/watch?v=dQw4w9WgXcQ&si=abc123",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://youtu.be/dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "http://youtu.be/dQw4w9WgXcQ?t=12",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "www.youtube.com/watch?v=dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxx",
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    (
        "https://www.youtube.com/shorts/abcDEF-_123",
        "youtube_shorts",
        "https://www.youtube.com/shorts/abcDEF-_123",
    ),
    (
        "https://youtube.com/shorts/abcDEF-_123?feature=share",
        "youtube_shorts",
        "https://www.youtube.com/shorts/abcDEF-_123",
    ),
    (
        "https://m.youtube.com/shorts/abcDEF-_123",
        "youtube_shorts",
        "https://www.youtube.com/shorts/abcDEF-_123",
    ),
    (
        "https://www.tiktok.com/@some.user/video/7123456789012345678",
        "tiktok",
        "https://www.tiktok.com/@some.user/video/7123456789012345678",
    ),
    (
        "https://tiktok.com/@user/video/7123456789012345678?is_from_webapp=1",
        "tiktok",
        "https://www.tiktok.com/@user/video/7123456789012345678",
    ),
    (
        "https://vm.tiktok.com/ZMabcdefg/",
        "tiktok",
        "https://vm.tiktok.com/ZMabcdefg",
    ),
    (
        "https://vt.tiktok.com/ZSxyzABC/",
        "tiktok",
        "https://vt.tiktok.com/ZSxyzABC",
    ),
    (
        "https://www.tiktok.com/t/ZTabcdeFG/",
        "tiktok",
        "https://www.tiktok.com/t/ZTabcdeFG",
    ),
    (
        "https://m.tiktok.com/v/7123456789012345678.html",
        "tiktok",
        "https://www.tiktok.com/video/7123456789012345678",
    ),
    (
        "https://www.instagram.com/reel/AbCdef12345/",
        "instagram_reels",
        "https://www.instagram.com/reel/AbCdef12345/",
    ),
    (
        "https://www.instagram.com/reels/AbCdef12345/?igsh=xxxx",
        "instagram_reels",
        "https://www.instagram.com/reel/AbCdef12345/",
    ),
    (
        "https://instagram.com/p/AbCdef12345/",
        "instagram_reels",
        "https://www.instagram.com/p/AbCdef12345/",
    ),
    (
        "https://www.instagram.com/p/AbCdef12345/?igshid=abc",
        "instagram_reels",
        "https://www.instagram.com/p/AbCdef12345/",
    ),
]


@pytest.mark.parametrize(("raw", "platform", "normalised"), CASES)
def test_classify_url_shapes(raw: str, platform: str, normalised: str) -> None:
    link = classify_url(raw)
    assert link is not None
    assert link.platform == platform
    assert link.normalised_url == normalised


def test_detect_in_sentence() -> None:
    text = "смотри https://youtu.be/dQw4w9WgXcQ вот это"
    links = detect_links(text)
    assert len(links) == 1
    assert links[0].platform == "youtube"


def test_detect_dedupes() -> None:
    text = "https://youtu.be/dQw4w9WgXcQ and https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    links = detect_links(text)
    assert len(links) == 1


def test_unsupported_vimeo() -> None:
    assert classify_url("https://vimeo.com/12345") is None
    assert looks_like_url("https://vimeo.com/12345")


def test_unsupported_playlist_and_profile() -> None:
    assert classify_url("https://www.youtube.com/playlist?list=PLxxxx") is None
    assert classify_url("https://www.instagram.com/someuser/") is None
    assert classify_url("https://www.youtube.com/@channel") is None


def test_twenty_plus_fixtures() -> None:
    assert len(CASES) >= 20
