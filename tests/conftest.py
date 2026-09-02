from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Audio, CallbackQuery, Chat, Message, User, Video
from bot.config import reset_settings_cache


class MockedSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def close(self) -> None:  # pragma: no cover
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        if False:
            yield b""
        return
        yield b""  # noqa: B901 — make this an async generator for type checkers

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        self.requests.append(method)
        method_name = getattr(method, "__api_method__", type(method).__name__)
        chat_id = getattr(method, "chat_id", 1)
        text = getattr(method, "text", None) or getattr(method, "caption", None)
        if method_name == "sendVideo":
            return Message(
                message_id=len(self.requests) + 10,
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id) if chat_id is not None else 1, type="private"),
                caption=text,
                video=Video(
                    file_id="vid-file-id",
                    file_unique_id="vid-uniq",
                    width=640,
                    height=360,
                    duration=1,
                ),
            ).as_(bot)
        if method_name == "sendAudio":
            return Message(
                message_id=len(self.requests) + 10,
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id) if chat_id is not None else 1, type="private"),
                audio=Audio(
                    file_id="aud-file-id",
                    file_unique_id="aud-uniq",
                    duration=1,
                ),
            ).as_(bot)
        if method_name in {"sendMessage", "editMessageText"}:
            return Message(
                message_id=len(self.requests) + 10,
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id) if chat_id is not None else 1, type="private"),
                text=text,
            ).as_(bot)
        return True


@pytest.fixture
def env_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Iterator[None]:
    monkeypatch.setenv("BOT_TOKEN", "123456:TESTTOKEN-scaffold")
    monkeypatch.setenv("ADMIN_IDS", "100,200")
    monkeypatch.setenv("DEFAULT_LANG", "ru")
    monkeypatch.setenv("MAX_FILE_MB", "50")
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "bot.db"))
    monkeypatch.setenv("HEARTBEAT_PATH", str(tmp_path / "hb"))
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def mocked_bot(env_settings: None) -> tuple[Bot, MockedSession]:
    session = MockedSession()
    bot = Bot(token="123456:TESTTOKEN-scaffold", session=session)
    return bot, session


def make_message(
    text: str,
    *,
    user_id: int = 42,
    bot: Bot | None = None,
) -> Message:
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )
    if bot is not None:
        return msg.as_(bot)
    return msg


def make_callback(
    data: str,
    *,
    bot: Bot,
    user_id: int = 42,
    message: Message | None = None,
) -> CallbackQuery:
    card = message or make_message("card", user_id=user_id, bot=bot)
    return CallbackQuery(
        id="cb1",
        from_user=User(id=user_id, is_bot=False, first_name="Test"),
        chat_instance="ci",
        message=card,
        data=data,
    ).as_(bot)
