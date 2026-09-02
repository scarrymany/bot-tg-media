from __future__ import annotations

from aiogram import Bot
from aiogram.methods import SendMessage
from bot.handlers.start import cmd_help, cmd_start
from bot.i18n import t

from tests.conftest import make_message


async def test_start_russian(mocked_bot: tuple[Bot, object], env_settings: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    msg = make_message("/start", bot=bot)
    await cmd_start(msg)
    assert session.requests  # type: ignore[attr-defined]
    sent = session.requests[0]  # type: ignore[attr-defined]
    assert isinstance(sent, SendMessage)
    assert sent.text is not None
    assert "TikTok" in sent.text
    assert "YouTube" in sent.text
    assert "Instagram" in sent.text
    assert sent.text == t("start_greeting", "ru")


async def test_help_lists_platforms(mocked_bot: tuple[Bot, object], env_settings: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    msg = make_message("/help", bot=bot)
    await cmd_help(msg)
    sent = session.requests[0]  # type: ignore[attr-defined]
    assert isinstance(sent, SendMessage)
    text = sent.text or ""
    for name in ("TikTok", "YouTube", "YouTube Shorts", "Instagram Reels"):
        assert name in text


async def test_i18n_english_start() -> None:
    text = t("start_greeting", "en")
    assert "TikTok" in text
    assert "How to use" in text


async def test_i18n_unknown_key_falls_back() -> None:
    assert t("missing_key_xyz", "ru") == "missing_key_xyz"
