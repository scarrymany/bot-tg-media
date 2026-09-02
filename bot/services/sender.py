from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class SendResult:
    file_id: str
    kind: Literal["video", "audio"]
    message_id: int
