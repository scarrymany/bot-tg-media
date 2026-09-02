"""End-to-end tests through a real aiogram Dispatcher.

The unit tests call handlers and middlewares directly, which hides wiring bugs
(the rate limiter silently did nothing in production because update-level
middlewares receive an ``Update``, not a ``Message``). These tests feed real
``Update`` objects through ``create_dispatcher`` so the registration order,
middleware chain and dependency injection are all exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SendVideo
from bot.config import get_settings, reset_settings_cache
from bot.i18n import t
from bot.keyboards import FormatCb, SettingsCb
from bot.main import create_dispatcher
from bot.services.extractor import FormatOption, MediaInfo
from bot.storage.cache import clear_jobs, put_cached
from bot.storage.users import get_user

from tests.conftest import MockedSession

CHAT_ID = 4242


@pytest.fixture
def rate_limited_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    monkeypatch.setenv("BOT_TOKEN", "123456:TESTTOKEN-scaffold")
    monkeypatch.setenv("ADMIN_IDS", "100")
    monkeypatch.setenv("DEFAULT_LANG", "ru")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "2")
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "bot.db"))
    monkeypatch.setenv("HEARTBEAT_PATH", str(tmp_path / "hb"))
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
async def wired(rate_limited_env: None) -> Any:
    """A real Dispatcher plus a Bot whose session records outgoing calls."""
    from bot.storage.db import close_db, init_db

    settings = get_settings()
    await init_db(settings.db_path)
    session = MockedSession()
    bot = Bot(token=settings.bot_token, session=session)
    dp = create_dispatcher(settings)
    clear_jobs()
    yield dp, bot, session, settings
    await close_db()


def _msg_update(text: str, update_id: int = 1, user_id: int = CHAT_ID) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "T"},
            "text": text,
        },
    }


def _cb_update(data: str, update_id: int = 1, user_id: int = CHAT_ID) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "chat_instance": "ci",
            "from": {"id": user_id, "is_bot": False, "first_name": "T"},
            "data": data,
            "message": {
                "message_id": 500,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": {"id": user_id, "type": "private"},
                "text": "card",
            },
        },
    }


async def _feed(dp: Any, bot: Bot, payload: dict[str, Any]) -> None:
    from aiogram.types import Update

    await dp.feed_update(bot, Update.model_validate(payload, context={"bot": bot}))


def _texts(session: MockedSession) -> list[str]:
    out = []
    for req in session.requests:
        text = getattr(req, "text", None)
        if isinstance(text, str):
            out.append(text)
    return out


def _info() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/dQw4w9WgXcQ",
        normalised_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform="youtube",
        title="Clip",
        duration=10,
        thumbnail=None,
        uploader="Author",
        formats=[
            FormatOption("360", "360p", "18", 1_000, True, False, 360, 640),
            FormatOption("1080", "1080p", "137+140", 90_000_000, True, True, 1080, 1920),
            FormatOption("audio", "mp3", "bestaudio/best", 1_000, True, False),
        ],
    )


# ---------------------------------------------------------------- acceptance 2


async def test_start_replies_in_russian(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("/start"))
    sent = [r for r in session.requests if isinstance(r, SendMessage)]
    assert sent and sent[0].text == t("start_greeting", "ru")
    assert "TikTok" in sent[0].text


async def test_help_lists_platforms(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("/help"))
    text = _texts(session)[-1]
    for platform in ("TikTok", "YouTube", "Shorts", "Instagram"):
        assert platform in text


# --------------------------------------------------------------- acceptance 10


async def test_unsupported_link_is_friendly(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("https://example.com/whatever.mp4"))
    texts = _texts(session)
    assert t("err_unsupported", "ru") in texts
    assert not any("Traceback" in text for text in texts)


async def test_plain_text_is_ignored(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("просто сообщение"))
    assert not session.requests


async def test_extractor_failure_never_leaks_a_traceback(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dp, bot, session, _settings = wired

    async def boom(*args: Any, **kwargs: Any) -> MediaInfo:
        raise RuntimeError("yt-dlp exploded with a very internal message")

    monkeypatch.setattr("bot.handlers.links.extract_media", boom)
    await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ"))
    texts = _texts(session)
    assert t("err_generic", "ru") in texts
    assert not any("yt-dlp exploded" in text or "Traceback" in text for text in texts)


# --------------------------------------------------------------- acceptance 13


async def test_rate_limit_refuses_through_the_dispatcher(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression that mattered: this path is the one production uses."""
    dp, bot, session, settings = wired
    assert settings.rate_limit_per_min == 2

    async def fake_extract(*args: Any, **kwargs: Any) -> MediaInfo:
        return _info()

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)

    for i in range(2):
        await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ", update_id=i + 1))
    assert not any(text.startswith("Слишком часто") for text in _texts(session))

    session.requests.clear()
    await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ", update_id=99))
    texts = _texts(session)
    assert len(texts) == 1
    assert texts[0].startswith("Слишком часто")
    # The refusal states how long to wait.
    assert any(char.isdigit() for char in texts[0])


async def test_commands_bypass_the_rate_limit(wired: Any) -> None:
    dp, bot, session, _settings = wired
    for i in range(6):
        await _feed(dp, bot, _msg_update("/start", update_id=i + 1))
    assert len([r for r in session.requests if isinstance(r, SendMessage)]) == 6


# --------------------------------------------------------------- acceptance 12


async def test_cache_hit_sends_without_downloading(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dp, bot, session, _settings = wired
    info = _info()

    async def fake_extract(*args: Any, **kwargs: Any) -> MediaInfo:
        return info

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)
    await put_cached(info.normalised_url, "360", "cached-file-id", "video")

    called = {"n": 0}

    async def never(*args: Any, **kwargs: Any) -> None:
        called["n"] += 1
        raise AssertionError("cache hit must not download")

    monkeypatch.setattr("bot.services.downloader.Downloader.download", never)

    await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ"))
    edits = [r for r in session.requests if isinstance(r, EditMessageText)]
    markup = edits[-1].reply_markup
    token = None
    for row in markup.inline_keyboard:
        for button in row:
            unpacked = button.callback_data or ""
            if unpacked.startswith("f:") and unpacked.endswith(":360"):
                token = unpacked.split(":")[1]
    assert token, "the card must offer the 360p button"

    session.requests.clear()
    await _feed(dp, bot, _cb_update(FormatCb(t=token, k="360").pack(), update_id=2))
    videos = [r for r in session.requests if isinstance(r, SendVideo)]
    assert called["n"] == 0
    assert len(videos) == 1
    assert videos[0].video == "cached-file-id"


# ----------------------------------------------------------- acceptance 9 / 14


async def test_oversized_quality_explains_the_limit(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dp, bot, session, _settings = wired
    info = _info()

    async def fake_extract(*args: Any, **kwargs: Any) -> MediaInfo:
        return info

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)
    await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ"))
    edits = [r for r in session.requests if isinstance(r, EditMessageText)]
    labels = [b.text for row in edits[-1].reply_markup.inline_keyboard for b in row]
    assert any("1080p" in label and "50" in label for label in labels), labels

    token = None
    for row in edits[-1].reply_markup.inline_keyboard:
        for button in row:
            data = button.callback_data or ""
            if data.endswith(":1080"):
                token = data.split(":")[1]
    assert token

    session.requests.clear()
    await _feed(dp, bot, _cb_update(FormatCb(t=token, k="1080").pack(), update_id=3))
    texts = _texts(session)
    assert any("50" in text for text in texts)
    # The smaller qualities are offered again.
    edits = [r for r in session.requests if isinstance(r, EditMessageText)]
    labels = [b.text for row in edits[-1].reply_markup.inline_keyboard for b in row]
    assert any("360p" in label for label in labels)


async def test_language_switch_makes_replies_english(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("/settings"))
    session.requests.clear()

    await _feed(dp, bot, _cb_update(SettingsCb(a="lang", v="en").pack(), update_id=2))
    answers = [r for r in session.requests if isinstance(r, AnswerCallbackQuery)]
    assert answers and answers[-1].text == t("settings_saved", "en")
    assert (await get_user(CHAT_ID)).lang == "en"

    session.requests.clear()
    await _feed(dp, bot, _msg_update("/start", update_id=3))
    assert _texts(session)[-1] == t("start_greeting", "en")

    session.requests.clear()
    await _feed(dp, bot, _msg_update("https://example.com/nope", update_id=4))
    assert t("err_unsupported", "en") in _texts(session)


async def test_default_quality_is_marked_on_the_card(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dp, bot, session, _settings = wired

    async def fake_extract(*args: Any, **kwargs: Any) -> MediaInfo:
        return _info()

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)
    await _feed(dp, bot, _cb_update(SettingsCb(a="qual", v="360").pack(), update_id=1))
    assert (await get_user(CHAT_ID)).quality == "360"

    session.requests.clear()
    await _feed(dp, bot, _msg_update("https://youtu.be/dQw4w9WgXcQ", update_id=2))
    edits = [r for r in session.requests if isinstance(r, EditMessageText)]
    labels = [b.text for row in edits[-1].reply_markup.inline_keyboard for b in row]
    assert "✅ 360p" in labels


# --------------------------------------------------------------- admin / stats


async def test_stats_denied_for_non_admin(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("/stats"))
    assert t("stats_denied", "ru") in _texts(session)


async def test_stats_allowed_for_admin(wired: Any) -> None:
    dp, bot, session, _settings = wired
    await _feed(dp, bot, _msg_update("/stats", user_id=100))
    text = _texts(session)[-1]
    assert "Hit rate" in text
    assert "{" not in text, "every placeholder must be filled"
