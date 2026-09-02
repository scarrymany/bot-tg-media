from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Platform = Literal["tiktok", "youtube", "youtube_shorts", "instagram_reels"]


@dataclass(frozen=True, slots=True)
class DetectedLink:
    raw_url: str
    normalised_url: str
    platform: Platform


def extract_raw_urls(text: str) -> list[str]:
    return []


def classify_url(url: str) -> DetectedLink | None:
    return None


def detect_links(text: str) -> list[DetectedLink]:
    return []


def looks_like_url(text: str) -> bool:
    return "http://" in text or "https://" in text or "www." in text
