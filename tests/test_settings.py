from __future__ import annotations

from aiogram import Bot
from bot.config import get_settings
from bot.handlers.settings import cmd_settings, on_settings
from bot.handlers.start import cmd_start
from bot.i18n import t
from bot.keyboards import SettingsCb
from bot.storage.users import get_user, set_lang, set_quality

from tests.conftest import make_callback, make_message


async def test_user_settings_persist(db: None) -> None:
    user = await set_quality(42, "720")
    assert user.quality == "720"
    user = await set_lang(42, "en")
    assert user.lang == "en"
    loaded = await get_user(42)
    assert loaded.quality == "720"
    assert loaded.lang == "en"


async def test_settings_command_keyboard(mocked_bot: tuple[Bot, object], db: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await cmd_settings(make_message("/settings", bot=bot))
    sent = session.requests[0]  # type: ignore[attr-defined]
    assert "Настройки" in (sent.text or "")
    texts = [b.text for row in sent.reply_markup.inline_keyboard for b in row]
    assert t("settings_quality_title", "ru") in texts
    assert t("settings_lang_title", "ru") in texts


async def test_switch_language_changes_start(mocked_bot: tuple[Bot, object], db: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await on_settings(
        make_callback(SettingsCb(a="lang", v="en").pack(), bot=bot),
        SettingsCb(a="lang", v="en"),
        settings=get_settings(),
    )
    user = await get_user(42)
    assert user.lang == "en"
    await cmd_start(make_message("/start", bot=bot))
    texts = [getattr(r, "text", "") or "" for r in session.requests]  # type: ignore[attr-defined]
    assert any("How to use" in text for text in texts)
    assert t("start_greeting", "en") in texts


async def test_set_default_quality(mocked_bot: tuple[Bot, object], db: None) -> None:
    bot, _session = mocked_bot
    await on_settings(
        make_callback(SettingsCb(a="qual", v="480").pack(), bot=bot),
        SettingsCb(a="qual", v="480"),
        settings=get_settings(),
    )
    assert (await get_user(42)).quality == "480"
