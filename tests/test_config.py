from __future__ import annotations

from pathlib import Path

import pytest
from bot.config import Settings, get_settings, reset_settings_cache


def test_settings_load_from_env(env_settings: None) -> None:
    settings = get_settings()
    assert settings.bot_token.startswith("123456:")
    assert settings.admin_ids == [100, 200]
    assert settings.max_file_mb == 50
    assert settings.max_file_bytes == 50 * 1024 * 1024
    assert settings.default_lang == "ru"
    assert settings.rate_limit_per_min == 5
    assert settings.max_concurrent_downloads == 3


def test_admin_ids_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:TESTTOKEN-scaffold")
    monkeypatch.setenv("ADMIN_IDS", "")
    reset_settings_cache()
    settings = Settings()  # type: ignore[call-arg]
    assert settings.admin_ids == []


def test_ig_cookies_empty_is_none() -> None:
    settings = Settings(bot_token="123456:TESTTOKEN-scaffold", ig_cookies_file="")  # type: ignore[call-arg]
    assert settings.ig_cookies_file is None


def test_ensure_dirs(tmp_path: Path) -> None:
    settings = Settings(
        bot_token="123456:TESTTOKEN-scaffold",
        download_dir=tmp_path / "dl",
        db_path=tmp_path / "data" / "bot.db",
        heartbeat_path=tmp_path / "run" / "hb",
    )
    settings.ensure_dirs()
    assert settings.download_dir.is_dir()
    assert settings.db_path.parent.is_dir()
    assert settings.heartbeat_path.parent.is_dir()


def test_invalid_lang_falls_back_to_ru() -> None:
    settings = Settings(bot_token="123456:TESTTOKEN-scaffold", default_lang="de")  # type: ignore[call-arg]
    assert settings.default_lang == "ru"
