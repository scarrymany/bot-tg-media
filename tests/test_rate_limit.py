from __future__ import annotations

from aiogram import Bot
from aiogram.types import User
from bot.i18n import t
from bot.middlewares.rate_limit import RateLimitMiddleware

from tests.conftest import make_callback, make_message


async def test_rate_limit_blocks_sixth_url(mocked_bot: tuple[Bot, object]) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    mw = RateLimitMiddleware(limit_per_min=5)
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1
        return "ok"

    user = User(id=7, is_bot=False, first_name="U")
    for _ in range(5):
        msg = make_message("https://youtu.be/dQw4w9WgXcQ", user_id=7, bot=bot)
        result = await mw(handler, msg, {"event_from_user": user})
        assert result == "ok"
    assert calls["n"] == 5

    sixth = make_message("https://youtu.be/dQw4w9WgXcQ", user_id=7, bot=bot)
    result = await mw(handler, sixth, {"event_from_user": user})
    assert result is None
    assert calls["n"] == 5
    sent = session.requests[-1]  # type: ignore[attr-defined]
    assert "Подождите" in (sent.text or "")
    assert t("rate_limited", "ru", seconds=mw.wait_seconds(7)) == sent.text


async def test_commands_not_rate_limited(mocked_bot: tuple[Bot, object]) -> None:
    bot, _session = mocked_bot
    mw = RateLimitMiddleware(limit_per_min=1)
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1
        return "ok"

    user = User(id=8, is_bot=False, first_name="U")
    for _ in range(3):
        msg = make_message("/start", user_id=8, bot=bot)
        await mw(handler, msg, {"event_from_user": user})
    assert calls["n"] == 3


async def test_cancel_callback_not_limited(mocked_bot: tuple[Bot, object]) -> None:
    bot, _session = mocked_bot
    mw = RateLimitMiddleware(limit_per_min=1)
    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1
        return "ok"

    user = User(id=9, is_bot=False, first_name="U")
    for _ in range(3):
        cb = make_callback("c:tok", bot=bot, user_id=9)
        await mw(handler, cb, {"event_from_user": user})
    assert calls["n"] == 3
