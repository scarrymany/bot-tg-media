from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bot.services.detector import DetectedLink, Platform


class ExtractError(Exception):
    """yt-dlp failed to extract media metadata."""


class InstagramCookiesError(ExtractError):
    """Instagram login wall / rate-limit and no cookies configured."""


class UnsupportedMediaError(ExtractError):
    """Playlist, live, or otherwise unsupported media."""


@dataclass(slots=True)
class FormatOption:
    key: str
    label: str
    format_selector: str
    est_size_bytes: int | None
    has_audio: bool
    exceeds_limit: bool
    height: int | None = None
    width: int | None = None


@dataclass(slots=True)
class MediaInfo:
    source_url: str
    normalised_url: str
    platform: Platform
    title: str
    duration: int | None
    thumbnail: str | None
    uploader: str | None
    formats: list[FormatOption] = field(default_factory=list)
    width: int | None = None
    height: int | None = None


async def extract_media(
    link: DetectedLink,
    *,
    max_file_mb: int,
    cookies_file: Path | None = None,
) -> MediaInfo:
    raise ExtractError("extractor not implemented")


def build_format_options(
    info: dict[str, object],
    *,
    max_file_bytes: int,
    platform: Platform,
) -> list[FormatOption]:
    return []
