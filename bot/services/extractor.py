from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from bot.services.detector import DetectedLink, Platform

log = structlog.get_logger("extractor")

QUALITY_LADDER = (360, 480, 720, 1080)

_IG_AUTH_MARKERS = (
    "login required",
    "login",
    "rate-limit",
    "rate limit",
    "please wait a few minutes",
    "please wait",
    "cookies",
    "not available",
    "empty media response",
    "instagram sent an empty",
    "requested content is not available",
    "http error 401",
    "http error 403",
    "http error 429",
)


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

    def format_by_key(self, key: str) -> FormatOption | None:
        for option in self.formats:
            if option.key == key:
                return option
        return None


def _ydl_extract(url: str, opts: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise ExtractError("empty extract_info")
    return info


def _is_ig_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _IG_AUTH_MARKERS)


def build_ydl_opts(*, cookies_file: Path | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "extract_flat": False,
        "retries": 2,
    }
    if cookies_file is not None and cookies_file.is_file():
        opts["cookiefile"] = str(cookies_file)
    return opts


async def extract_media(
    link: DetectedLink,
    *,
    max_file_mb: int,
    cookies_file: Path | None = None,
) -> MediaInfo:
    opts = build_ydl_opts(cookies_file=cookies_file)
    cookies_set = "cookiefile" in opts
    loop = asyncio.get_running_loop()
    try:
        info = await loop.run_in_executor(None, _ydl_extract, link.normalised_url, opts)
    except Exception as exc:
        log.warning("extract_failed", url=link.normalised_url, error=str(exc))
        if link.platform == "instagram_reels" and _is_ig_auth_error(str(exc)) and not cookies_set:
            raise InstagramCookiesError(str(exc)) from exc
        raise ExtractError(str(exc)) from exc

    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if len(entries) == 1 and isinstance(entries[0], dict):
            info = entries[0]
        else:
            raise UnsupportedMediaError("playlist")
    if info.get("is_live"):
        raise UnsupportedMediaError("live")

    max_bytes = max_file_mb * 1024 * 1024
    formats = build_format_options(info, max_file_bytes=max_bytes, platform=link.platform)
    title = str(info.get("title") or info.get("fulltitle") or "video")
    duration = info.get("duration")
    duration_i = int(duration) if isinstance(duration, (int, float)) else None
    return MediaInfo(
        source_url=link.raw_url,
        normalised_url=link.normalised_url,
        platform=link.platform,
        title=title,
        duration=duration_i,
        thumbnail=info.get("thumbnail") if isinstance(info.get("thumbnail"), str) else None,
        uploader=str(info["uploader"]) if info.get("uploader") else None,
        formats=formats,
        width=info.get("width") if isinstance(info.get("width"), int) else None,
        height=info.get("height") if isinstance(info.get("height"), int) else None,
    )


def _is_video(fmt: dict[str, Any]) -> bool:
    vcodec = fmt.get("vcodec")
    return bool(vcodec and vcodec != "none")


def _is_audio(fmt: dict[str, Any]) -> bool:
    acodec = fmt.get("acodec")
    return bool(acodec and acodec != "none")


def _fmt_size(fmt: dict[str, Any]) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def _tiktok_score(fmt: dict[str, Any]) -> int:
    blob = " ".join(
        str(fmt.get(key) or "") for key in ("format_id", "format_note", "format", "protocol")
    ).lower()
    score = 0
    if any(token in blob for token in ("no-watermark", "no_watermark", "nowatermark")):
        score += 300
    elif "watermark" in blob:
        score -= 300
    if "download" in blob:
        score += 80
    tbr = fmt.get("tbr")
    if isinstance(tbr, (int, float)):
        score += int(tbr)
    return score


def _bucket(height: int) -> int:
    for step in QUALITY_LADDER:
        if height <= step:
            return step
    return QUALITY_LADDER[-1]


def _best_audio(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    audios = [f for f in formats if _is_audio(f) and not _is_video(f)]
    if not audios:
        return None

    def score(fmt: dict[str, Any]) -> tuple[int, int]:
        abr = fmt.get("abr") or fmt.get("tbr") or 0
        size = _fmt_size(fmt) or 0
        return (int(abr), size)

    return max(audios, key=score)


def build_format_options(
    info: dict[str, Any],
    *,
    max_file_bytes: int,
    platform: Platform,
) -> list[FormatOption]:
    raw_formats = list(info.get("formats") or [])
    if not raw_formats and info.get("url"):
        raw_formats = [
            {
                "format_id": str(info.get("format_id") or "best"),
                "height": info.get("height"),
                "width": info.get("width"),
                "vcodec": info.get("vcodec") or "avc1",
                "acodec": info.get("acodec") or "aac",
                "filesize": info.get("filesize") or info.get("filesize_approx"),
                "url": info.get("url"),
            }
        ]

    videos = [f for f in raw_formats if _is_video(f) and isinstance(f.get("height"), int)]
    audio = _best_audio(raw_formats)
    groups: dict[int, list[dict[str, Any]]] = {step: [] for step in QUALITY_LADDER}
    for fmt in videos:
        groups[_bucket(int(fmt["height"]))].append(fmt)

    options: list[FormatOption] = []
    for step in QUALITY_LADDER:
        candidates = groups[step]
        if not candidates:
            continue

        def score(fmt: dict[str, Any], *, _step: int = step) -> tuple[int, int, int]:
            combined = 1 if _is_audio(fmt) else 0
            nw = _tiktok_score(fmt) if platform == "tiktok" else 0
            # Prefer the format whose height is closest to the bucket from below.
            closeness = int(fmt.get("height") or 0)
            return (combined, nw, closeness)

        best = max(candidates, key=score)
        combined = _is_audio(best)
        video_size = _fmt_size(best)
        extra_audio = 0 if combined or audio is None else (_fmt_size(audio) or 0)
        est = None if video_size is None else video_size + extra_audio
        if combined:
            selector = str(best.get("format_id") or f"best[height<={step}]")
            has_audio = True
        elif audio is not None:
            selector = f"{best.get('format_id')}+{audio.get('format_id')}"
            has_audio = True
        else:
            selector = str(best.get("format_id") or f"best[height<={step}]")
            has_audio = False
        options.append(
            FormatOption(
                key=str(step),
                label=f"{step}p",
                format_selector=selector,
                est_size_bytes=est,
                has_audio=has_audio,
                exceeds_limit=bool(est is not None and est > max_file_bytes),
                height=int(best["height"]) if best.get("height") else step,
                width=int(best["width"]) if isinstance(best.get("width"), int) else None,
            )
        )

    audio_size = _fmt_size(audio) if audio else None
    if audio_size is None:
        duration = info.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            audio_size = int(duration * 192_000 / 8)
    options.append(
        FormatOption(
            key="audio",
            label="mp3",
            format_selector="bestaudio/best",
            est_size_bytes=audio_size,
            has_audio=True,
            exceeds_limit=bool(audio_size is not None and audio_size > max_file_bytes),
        )
    )
    return options
