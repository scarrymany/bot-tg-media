from __future__ import annotations

from aiogram import Bot
from bot.config import get_settings
from bot.handlers.admin import cmd_stats
from bot.i18n import t
from bot.storage.users import get_user, record_event

from tests.conftest import make_message


async def test_stats_denied_for_stranger(mocked_bot: tuple[Bot, object], db: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await cmd_stats(make_message("/stats", user_id=999, bot=bot), settings=get_settings())
    assert session.requests[0].text == t("stats_denied", "ru")  # type: ignore[attr-defined]


async def test_stats_for_admin(mocked_bot: tuple[Bot, object], db: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await get_user(100, "ru")
    await record_event(100, "youtube", "download")
    await record_event(100, "youtube", "cache_hit")
    await cmd_stats(make_message("/stats", user_id=100, bot=bot), settings=get_settings())
    text = session.requests[0].text or ""  # type: ignore[attr-defined]
    assert "YouTube" in text or "youtube" in text.lower()
    assert "50%" in text or "Hit" in text or "кэш" in text.lower() or "кэш" in text
