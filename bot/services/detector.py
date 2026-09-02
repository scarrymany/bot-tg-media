from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

Platform = Literal["tiktok", "youtube", "youtube_shorts", "instagram_reels"]

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TIKTOK_VIDEO_ID = re.compile(r"^(\d{5,})$")
_IG_CODE = re.compile(r"^[A-Za-z0-9_-]+$")

# Bare hosts + http(s). Trailing punctuation is stripped later.
_URL_FINDER = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?(?:"
    r"(?:m\.|music\.)?youtube\.com|youtu\.be|"
    r"(?:vm\.|vt\.|m\.)?tiktok\.com|"
    r"instagram\.com|instagr\.am"
    r")/[^\s<>'\"\]|]+"
)
_GENERIC_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}
_IG_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
}
_DROP_QS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "si",
    "feature",
    "pp",
    "fbclid",
    "gclid",
    "igsh",
    "igshid",
    "ref",
    "spm",
    "t",
}


@dataclass(frozen=True, slots=True)
class DetectedLink:
    raw_url: str
    normalised_url: str
    platform: Platform


def extract_raw_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in _URL_FINDER.finditer(text or ""):
        url = _trim_url(match.group(0))
        if url:
            found.append(url)
    return found


def looks_like_url(text: str) -> bool:
    return bool(_GENERIC_URL.search(text or "") or _URL_FINDER.search(text or ""))


def classify_url(url: str) -> DetectedLink | None:
    raw = _trim_url(url)
    if not raw:
        return None
    parsed = _parse(raw)
    if parsed is None:
        return None
    host = parsed.netloc.lower()
    if host in _YOUTUBE_HOSTS:
        return _classify_youtube(raw, parsed)
    if host in _TIKTOK_HOSTS:
        return _classify_tiktok(raw, parsed)
    if host in _IG_HOSTS:
        return _classify_instagram(raw, parsed)
    return None


def detect_links(text: str) -> list[DetectedLink]:
    seen: set[str] = set()
    out: list[DetectedLink] = []
    for raw in extract_raw_urls(text):
        link = classify_url(raw)
        if link is None or link.normalised_url in seen:
            continue
        seen.add(link.normalised_url)
        out.append(link)
    return out


def _trim_url(url: str) -> str:
    return url.strip().rstrip(".,);!?]>'\"")


def _parse(url: str) -> ParseResult | None:
    candidate = url if "://" in url else f"https://{url}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return None
    return parsed


def _classify_youtube(raw: str, parsed: ParseResult) -> DetectedLink | None:
    host = parsed.netloc.lower()
    path = parsed.path or ""
    qs = parse_qs(parsed.query)
    parts = [p for p in path.split("/") if p]

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parts[0] if parts else ""
        if not _YOUTUBE_ID.match(video_id):
            return None
        return DetectedLink(raw, f"https://www.youtube.com/watch?v={video_id}", "youtube")

    if parts and parts[0] == "shorts" and len(parts) >= 2:
        video_id = parts[1]
        if not _YOUTUBE_ID.match(video_id):
            return None
        return DetectedLink(raw, f"https://www.youtube.com/shorts/{video_id}", "youtube_shorts")

    if parts and parts[0] in {"embed", "live", "v"} and len(parts) >= 2:
        video_id = parts[1]
        if not _YOUTUBE_ID.match(video_id):
            return None
        return DetectedLink(raw, f"https://www.youtube.com/watch?v={video_id}", "youtube")

    video_id = (qs.get("v") or [""])[0]
    if _YOUTUBE_ID.match(video_id):
        return DetectedLink(raw, f"https://www.youtube.com/watch?v={video_id}", "youtube")
    return None


def _classify_tiktok(raw: str, parsed: ParseResult) -> DetectedLink | None:
    host = parsed.netloc.lower()
    path = parsed.path or ""
    parts = [p for p in path.split("/") if p]

    if host in {"vm.tiktok.com", "vt.tiktok.com"}:
        if not parts:
            return None
        return DetectedLink(raw, f"https://{host}/{parts[0]}", "tiktok")

    if parts and parts[0] == "t" and len(parts) >= 2:
        return DetectedLink(raw, f"https://www.tiktok.com/t/{parts[1]}", "tiktok")

    if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "video":
        vid = parts[2].split(".")[0]
        user = parts[0]
        return DetectedLink(raw, f"https://www.tiktok.com/{user}/video/{vid}", "tiktok")

    if parts and parts[0] == "v" and len(parts) >= 2:
        vid = parts[1].split(".")[0]
        if _TIKTOK_VIDEO_ID.match(vid):
            return DetectedLink(raw, f"https://www.tiktok.com/video/{vid}", "tiktok")

    if len(parts) >= 2 and parts[0] == "video":
        vid = parts[1].split(".")[0]
        if _TIKTOK_VIDEO_ID.match(vid):
            return DetectedLink(raw, f"https://www.tiktok.com/video/{vid}", "tiktok")

    if parts:
        # Unknown but clearly a tiktok media path — keep host+path, drop tracking.
        norm_host = "www.tiktok.com" if host.endswith("tiktok.com") else host
        clean = urlunparse(("https", norm_host, path, "", "", ""))
        return DetectedLink(raw, clean.rstrip("/"), "tiktok") if len(path) > 1 else None
    return None


def _classify_instagram(raw: str, parsed: ParseResult) -> DetectedLink | None:
    path = parsed.path or ""
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    kind, code = parts[0], parts[1]
    if kind not in {"reel", "reels", "p"}:
        return None
    if not _IG_CODE.match(code):
        return None
    prefix = "reel" if kind in {"reel", "reels"} else "p"
    return DetectedLink(raw, f"https://www.instagram.com/{prefix}/{code}/", "instagram_reels")


def strip_tracking(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    qs = parse_qs(parsed.query, keep_blank_values=False)
    kept = {k: v for k, v in qs.items() if k.lower() not in _DROP_QS}
    query = urlencode({k: v[0] for k, v in kept.items()}) if kept else ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))
