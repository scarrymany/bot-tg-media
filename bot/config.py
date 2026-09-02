from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(..., min_length=1)
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    max_file_mb: int = 50
    rate_limit_per_min: int = 5
    max_concurrent_downloads: int = 3
    download_dir: Path = Path("./downloads")
    db_path: Path = Path("./data/bot.db")
    ig_cookies_file: Path | None = None
    default_lang: str = "ru"
    log_level: str = "INFO"
    heartbeat_path: Path = Path("/tmp/bot-heartbeat")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: Any) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(x) for x in value]
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                import json

                parsed = json.loads(raw)
                return [int(x) for x in parsed]
            return [int(part.strip()) for part in raw.split(",") if part.strip()]
        return [int(value)]

    @field_validator("ig_cookies_file", mode="before")
    @classmethod
    def _empty_optional_path(cls, value: Any) -> Path | None:
        if value is None or value == "":
            return None
        return Path(value)

    @field_validator("default_lang", mode="before")
    @classmethod
    def _norm_lang(cls, value: Any) -> str:
        lang = str(value or "ru").strip().lower()
        return lang if lang in {"ru", "en"} else "ru"

    @field_validator("log_level", mode="before")
    @classmethod
    def _norm_log_level(cls, value: Any) -> str:
        return str(value or "INFO").strip().upper()

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb) * 1024 * 1024

    def ensure_dirs(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
