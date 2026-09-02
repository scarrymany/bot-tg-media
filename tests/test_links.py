from __future__ import annotations

from aiogram import Bot
from aiogram.methods import EditMessageText, SendMessage
from bot.handlers.links import on_text, render_card
from bot.i18n import t
from bot.services.detector import DetectedLink
from bot.services.extractor import (
    ExtractError,
    FormatOption,
    InstagramCookiesError,
    MediaInfo,
)
from bot.storage.cache import clear_jobs

from tests.conftest import make_message


def _media() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/dQw4w9WgXcQ",
        normalised_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform="youtube",
        title="Rick",
        duration=212,
        thumbnail=None,
        uploader="Rick",
        formats=[
            FormatOption("360", "360p", "18", 5_000_000, True, False, 360, 640),
            FormatOption("audio", "mp3", "bestaudio/best", 1_000_000, True, False),
        ],
    )


async def test_link_card_and_keyboard(
    mocked_bot: tuple[Bot, object], env_settings: None, monkeypatch
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()

    async def fake_extract(link: DetectedLink, **kwargs):
        assert link.platform in {"youtube", "youtube_shorts"}
        return _media()

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)
    msg = make_message("https://youtu.be/dQw4w9WgXcQ", bot=bot)
    await on_text(msg)
    assert isinstance(session.requests[0], SendMessage)  # type: ignore[attr-defined]
    assert session.requests[0].text == t("getting_info", "ru")  # type: ignore[attr-defined]
    edit = session.requests[1]  # type: ignore[attr-defined]
    assert isinstance(edit, EditMessageText)
    assert "Rick" in (edit.text or "")
    assert edit.reply_markup is not None
    texts = [b.text for row in edit.reply_markup.inline_keyboard for b in row]
    assert any("360p" in text for text in texts)
    assert t("btn_audio", "ru") in texts
    assert t("btn_cancel", "ru") in texts


async def test_unsupported_link(mocked_bot: tuple[Bot, object], env_settings: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    msg = make_message("https://vimeo.com/12345", bot=bot)
    await on_text(msg)
    sent = session.requests[0]  # type: ignore[attr-defined]
    assert sent.text == t("err_unsupported", "ru")


async def test_plain_text_ignored(mocked_bot: tuple[Bot, object], env_settings: None) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    await on_text(make_message("просто текст без ссылки", bot=bot))
    assert session.requests == []  # type: ignore[attr-defined]


async def test_ig_cookies_message(
    mocked_bot: tuple[Bot, object], env_settings: None, monkeypatch
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]

    async def boom(*args, **kwargs):
        raise InstagramCookiesError("login")

    monkeypatch.setattr("bot.handlers.links.extract_media", boom)
    await on_text(make_message("https://www.instagram.com/reel/AbCdef12345/", bot=bot))
    edit = session.requests[1]  # type: ignore[attr-defined]
    assert edit.text == t("err_ig_cookies", "ru")
    assert "IG_COOKIES_FILE" in (edit.text or "")


async def test_extract_error_friendly(
    mocked_bot: tuple[Bot, object], env_settings: None, monkeypatch
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]

    async def boom(*args, **kwargs):
        raise ExtractError("nope")

    monkeypatch.setattr("bot.handlers.links.extract_media", boom)
    await on_text(make_message("https://youtu.be/dQw4w9WgXcQ", bot=bot))
    edit = session.requests[1]  # type: ignore[attr-defined]
    assert edit.text == t("err_extract", "ru")
    assert "Traceback" not in (edit.text or "")


def test_render_card_escapes_html() -> None:
    info = _media()
    info.title = "<script>alert(1)</script>"
    card = render_card(info, "ru")
    assert "<script>" not in card
    assert "&lt;script&gt;" in card
