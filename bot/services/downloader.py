from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


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
