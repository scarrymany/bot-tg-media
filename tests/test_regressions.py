"""Regression tests for bugs found in the review pass.

Each test here pins a defect that shipped in the build phases; they are kept
together so the reason a behaviour exists stays obvious.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo, TelegramMethod
from aiogram.types import Chat, Message, Update, User
from bot.config import Settings, get_settings
from bot.handlers.callbacks import on_format
from bot.i18n import t
from bot.keyboards import FormatCb
from bot.middlewares.rate_limit import RateLimitMiddleware, unwrap_event
from bot.services.downloader import (
    Downloader,
    FfmpegMissingError,
    FileTooLargeError,
    _find_thumb,
    make_progress_hook,
    map_error_key,
)
from bot.services.extractor import FormatOption, MediaInfo
from bot.services.sender import send_media
from bot.storage.cache import (
    clear_jobs,
    finish_job,
    get_cached,
    put_cached,
    put_job,
    try_start_job,
)

from tests.conftest import MockedSession, make_callback, make_message

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _info() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/aaaaaaaaaaa",
        normalised_url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
        platform="youtube",
        title="Clip",
        duration=10,
        thumbnail=None,
        uploader="Author",
        formats=[
            FormatOption("360", "360p", "18", 1_000, True, False, 360, 640),
            FormatOption("audio", "mp3", "bestaudio/best", 1_000, True, False),
        ],
    )


def _settings(tmp_path: Path, max_file_mb: int = 50) -> Settings:
    return Settings(
        bot_token="123456:TESTTOKEN-scaffold",
        download_dir=tmp_path / "dl",
        db_path=tmp_path / "db" / "bot.db",
        max_file_mb=max_file_mb,
    )


class RecordingDownloader:
    """Minimal Downloader stand-in that counts invocations."""

    def __init__(self, tmp_path: Path, *, gate: asyncio.Event | None = None) -> None:
        self.tmp_path = tmp_path
        self.called = 0
        self.gate = gate
        self.progress_cbs: list[Any] = []

    async def download(self, info, option, *, progress=None, cancel_event=None):  # type: ignore[no-untyped-def]
        self.called += 1
        if progress is not None:
            self.progress_cbs.append(progress)
        if self.gate is not None:
            await self.gate.wait()
        path = self.tmp_path / f"v{self.called}.mp4"
        path.write_bytes(b"media")
        from bot.services.downloader import DownloadResult

        return DownloadResult(
            path=path,
            workdir=self.tmp_path / f"work{self.called}",
            kind="video",
            duration=info.duration,
            width=option.width,
            height=option.height,
            title=info.title,
            performer=info.uploader or "x",
            thumbnail=None,
            size_bytes=5,
        )

    def cleanup(self, result=None, workdir=None) -> None:  # type: ignore[no-untyped-def]
        return None


# --------------------------------------------------------------------------
# rate limit: the middleware sits on dp.update and receives an Update
# --------------------------------------------------------------------------


def _update(text: str, user_id: int) -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="U"),
            text=text,
        ),
    )


def test_unwrap_event_resolves_update_payload() -> None:
    upd = _update("hi", 1)
    assert unwrap_event(upd) is upd.message
    assert unwrap_event(upd.message) is upd.message  # type: ignore[arg-type]


async def test_rate_limit_fires_on_update_events(mocked_bot: tuple[Bot, object]) -> None:
    """Regression: aiogram hands update-level middlewares an Update, not a Message.

    The type checks used to look at the Update itself, so the limiter never
    triggered in production even though the unit test passed a bare Message.
    """
    bot, session = mocked_bot  # type: ignore[misc]
    mw = RateLimitMiddleware(limit_per_min=2)
    calls = {"n": 0}

    async def handler(event, data):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return "ok"

    user = User(id=77, is_bot=False, first_name="U")
    for _ in range(2):
        upd = _update("https://youtu.be/dQw4w9WgXcQ", 77)
        upd.message._bot = bot  # type: ignore[union-attr]
        assert await mw(handler, upd, {"event_from_user": user}) == "ok"
    assert calls["n"] == 2

    blocked = _update("https://youtu.be/dQw4w9WgXcQ", 77)
    blocked.message._bot = bot  # type: ignore[union-attr]
    assert await mw(handler, blocked, {"event_from_user": user}) is None
    assert calls["n"] == 2
    assert "Подождите" in (session.requests[-1].text or "")  # type: ignore[attr-defined]


async def test_rate_limit_ignores_commands_inside_update(
    mocked_bot: tuple[Bot, object],
) -> None:
    bot, _session = mocked_bot
    mw = RateLimitMiddleware(limit_per_min=1)
    calls = {"n": 0}

    async def handler(event, data):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return "ok"

    user = User(id=78, is_bot=False, first_name="U")
    for _ in range(3):
        upd = _update("/start", 78)
        upd.message._bot = bot  # type: ignore[union-attr]
        await mw(handler, upd, {"event_from_user": user})
    assert calls["n"] == 3


async def test_rate_limit_gc_drops_stale_users(mocked_bot: tuple[Bot, object]) -> None:
    """The per-user deque map used to grow forever."""
    bot, _session = mocked_bot
    mw = RateLimitMiddleware(limit_per_min=5)

    async def handler(event, data):  # type: ignore[no-untyped-def]
        return "ok"

    for uid in range(50):
        upd = _update("https://youtu.be/dQw4w9WgXcQ", uid)
        upd.message._bot = bot  # type: ignore[union-attr]
        await mw(handler, upd, {"event_from_user": User(id=uid, is_bot=False, first_name="U")})
    assert len(mw._hits) == 50

    # Age every recorded hit past the window and force the GC to run.
    for hits in mw._hits.values():
        for i in range(len(hits)):
            hits[i] -= 120.0
    mw._last_gc -= 10_000.0
    upd = _update("https://youtu.be/dQw4w9WgXcQ", 999)
    upd.message._bot = bot  # type: ignore[union-attr]
    await mw(handler, upd, {"event_from_user": User(id=999, is_bot=False, first_name="U")})
    assert len(mw._hits) == 1


# --------------------------------------------------------------------------
# cached file_id that Telegram rejects
# --------------------------------------------------------------------------


class RejectFileIdSession(MockedSession):
    """Fails sendVideo when it carries a (stale) file_id string."""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        if isinstance(method, SendVideo) and isinstance(method.video, str):
            self.requests.append(method)
            raise TelegramBadRequest(method=method, message="wrong file identifier")
        return await super().make_request(bot, method, timeout)


async def test_stale_cache_entry_falls_back_to_download(
    env_settings: None, db: None, tmp_path: Path
) -> None:
    """Regression: a rejected file_id used to escape as an unhandled exception."""
    session = RejectFileIdSession()
    bot = Bot(token="123456:TESTTOKEN-scaffold", session=session)
    clear_jobs()
    info = _info()
    token = put_job(info, 42)
    await put_cached(info.normalised_url, "360", "dead-file-id", "video")
    downloader = RecordingDownloader(tmp_path)

    await on_format(
        make_callback(FormatCb(t=token, k="360").pack(), bot=bot),
        FormatCb(t=token, k="360"),
        settings=get_settings(),
        downloader=downloader,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )

    assert downloader.called == 1, "should fall through to a real download"
    # The dead row is replaced by the freshly uploaded file_id.
    entry = await get_cached(info.normalised_url, "360")
    assert entry is not None and entry.file_id == "vid-file-id"


# --------------------------------------------------------------------------
# progress races and double taps
# --------------------------------------------------------------------------


async def test_late_progress_does_not_overwrite_result_card(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    """Regression: a progress edit queued from the yt-dlp thread could land
    after the final card and wipe out the 'another format' button."""
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    downloader = RecordingDownloader(tmp_path)

    await on_format(
        make_callback(FormatCb(t=token, k="360").pack(), bot=bot),
        FormatCb(t=token, k="360"),
        settings=get_settings(),
        downloader=downloader,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )

    before = len(session.requests)  # type: ignore[attr-defined]
    # Fire a progress callback the way a straggling yt-dlp hook would.
    assert downloader.progress_cbs
    await downloader.progress_cbs[0](77)
    assert len(session.requests) == before, "stale progress must be dropped"  # type: ignore[attr-defined]

    edits = [r for r in session.requests if type(r).__name__ == "EditMessageText"]  # type: ignore[attr-defined]
    assert t("btn_another", "ru") in str(edits[-1].reply_markup)


async def test_double_tap_starts_one_download(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    """Regression: the callback is answered immediately, so a second tap used
    to launch a duplicate download of the same job."""
    bot, _session = mocked_bot
    clear_jobs()
    token = put_job(_info(), 42)
    gate = asyncio.Event()
    downloader = RecordingDownloader(tmp_path, gate=gate)

    async def tap() -> None:
        await on_format(
            make_callback(FormatCb(t=token, k="360").pack(), bot=bot),
            FormatCb(t=token, k="360"),
            settings=get_settings(),
            downloader=downloader,  # type: ignore[arg-type]
            download_sem=asyncio.Semaphore(2),
        )

    first = asyncio.create_task(tap())
    await asyncio.sleep(0)
    second = asyncio.create_task(tap())
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(first, second)
    assert downloader.called == 1


def test_job_busy_flag_round_trip() -> None:
    clear_jobs()
    token = put_job(_info(), 42)
    assert try_start_job(token) is True
    assert try_start_job(token) is False
    finish_job(token)
    assert try_start_job(token) is True
    assert try_start_job("no-such-token") is False


# --------------------------------------------------------------------------
# job ownership
# --------------------------------------------------------------------------


async def test_other_user_cannot_press_the_buttons(
    mocked_bot: tuple[Bot, object], env_settings: None, tmp_path: Path
) -> None:
    bot, session = mocked_bot  # type: ignore[misc]
    clear_jobs()
    token = put_job(_info(), 42)
    downloader = RecordingDownloader(tmp_path)

    await on_format(
        make_callback(FormatCb(t=token, k="360").pack(), bot=bot, user_id=999),
        FormatCb(t=token, k="360"),
        settings=get_settings(),
        downloader=downloader,  # type: ignore[arg-type]
        download_sem=asyncio.Semaphore(1),
    )
    assert downloader.called == 0
    answers = [r for r in session.requests if type(r).__name__ == "AnswerCallbackQuery"]  # type: ignore[attr-defined]
    assert answers and answers[-1].text == t("err_foreign_job", "ru")


# --------------------------------------------------------------------------
# bounded temp files
# --------------------------------------------------------------------------


def test_progress_hook_aborts_past_the_size_cap() -> None:
    """Regression: a multi-GB source was fully written to disk before the
    post-download size check rejected it."""
    loop = asyncio.new_event_loop()
    try:
        hook = make_progress_hook(loop, None, None, max_bytes=1_000)
        hook({"status": "downloading", "downloaded_bytes": 500, "total_bytes": 900})
        with pytest.raises(FileTooLargeError):
            hook({"status": "downloading", "downloaded_bytes": 1_001, "total_bytes": 0})
        with pytest.raises(FileTooLargeError):
            hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 5_000})
    finally:
        loop.close()


async def test_max_filesize_is_passed_to_ytdlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_ydl(url: str, **kwargs: Any) -> None:
        captured.update(kwargs)
        Path(kwargs["outtmpl"]).parent.joinpath("ok.mp4").write_bytes(b"x")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    settings = _settings(tmp_path, max_file_mb=7)
    await Downloader(settings).download(
        _info(), FormatOption("360", "360p", "18", None, True, False, 360, 640)
    )
    assert captured["max_filesize"] == 7 * 1024 * 1024


# --------------------------------------------------------------------------
# thumbnails Telegram will accept
# --------------------------------------------------------------------------


def test_find_thumb_rejects_webp_and_oversized(tmp_path: Path) -> None:
    """Regression: yt-dlp writes .webp thumbnails for YouTube and Telegram
    rejects them, which used to fail the whole sendVideo call."""
    work = tmp_path / "job"
    work.mkdir()
    (work / "a.webp").write_bytes(b"webp")
    assert _find_thumb(work) is None

    (work / "b.jpg").write_bytes(b"\0" * (300 * 1024))
    assert _find_thumb(work) is None, "over 200 kB must be dropped"

    good = work / "c.jpg"
    good.write_bytes(b"\0" * 1024)
    assert _find_thumb(work) == good


class ThumbHostileSession(MockedSession):
    """Rejects the first sendVideo that carries a thumbnail."""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        if isinstance(method, SendVideo) and method.thumbnail is not None:
            self.requests.append(method)
            raise TelegramBadRequest(method=method, message="THUMBNAIL_INVALID")
        return await super().make_request(bot, method, timeout)


async def test_send_video_retries_without_thumbnail(env_settings: None, tmp_path: Path) -> None:
    from bot.services.downloader import DownloadResult

    session = ThumbHostileSession()
    bot = Bot(token="123456:TESTTOKEN-scaffold", session=session)
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"jpeg")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"data")
    result = DownloadResult(
        path=video,
        workdir=tmp_path,
        kind="video",
        duration=5,
        width=640,
        height=360,
        title="Clip",
        performer="Author",
        thumbnail=thumb,
        size_bytes=4,
    )
    sent = await send_media(bot, 42, result)
    assert sent.file_id == "vid-file-id"
    videos = [r for r in session.requests if isinstance(r, SendVideo)]
    assert len(videos) == 2
    assert videos[0].thumbnail is not None
    assert videos[1].thumbnail is None


# --------------------------------------------------------------------------
# ffmpeg absent
# --------------------------------------------------------------------------


async def test_audio_without_ffmpeg_is_a_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bot.services.downloader.ffmpeg_available", lambda: False)
    downloader = Downloader(_settings(tmp_path))
    with pytest.raises(FfmpegMissingError) as excinfo:
        await downloader.download(
            _info(), FormatOption("audio", "mp3", "bestaudio/best", 100, True, False)
        )
    assert map_error_key(excinfo.value) == "err_no_ffmpeg"
    assert t("err_no_ffmpeg", "ru") and t("err_no_ffmpeg", "en")


async def test_merged_selector_degrades_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ffmpeg a `137+140` selector can never be muxed; fall back to a
    progressive stream instead of failing the download."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr("bot.services.downloader.ffmpeg_available", lambda: False)

    def fake_ydl(url: str, **kwargs: Any) -> None:
        captured.update(kwargs)
        Path(kwargs["outtmpl"]).parent.joinpath("ok.mp4").write_bytes(b"x")

    monkeypatch.setattr("bot.services.downloader._ydl_download", fake_ydl)
    await Downloader(_settings(tmp_path)).download(
        _info(), FormatOption("720", "720p", "137+140", None, True, False, 720, 1280)
    )
    assert "+" not in captured["format_selector"]
    assert "height<=720" in captured["format_selector"]


# --------------------------------------------------------------------------
# "message is not modified" and other edit failures
# --------------------------------------------------------------------------


class EditHostileSession(MockedSession):
    """Rejects every editMessageText, the way Telegram does for an identical body."""

    def __init__(self, message: str = "Bad Request: message is not modified") -> None:
        super().__init__()
        self.failure = message

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        if type(method).__name__ == "EditMessageText":
            self.requests.append(method)
            raise TelegramBadRequest(method=method, message=self.failure)
        return await super().make_request(bot, method, timeout)


@pytest.mark.parametrize(
    "failure",
    [
        "Bad Request: message is not modified",
        "Bad Request: message to edit not found",
    ],
)
async def test_settings_survives_a_failing_edit(env_settings: None, db: None, failure: str) -> None:
    """Regression: /settings edited messages unguarded, so re-picking the
    quality you already have raised an unhandled 'message is not modified'."""
    from bot.handlers.settings import on_settings
    from bot.keyboards import SettingsCb

    session = EditHostileSession(failure)
    bot = Bot(token="123456:TESTTOKEN-scaffold", session=session)
    for action, value in (("qual", "720"), ("lang", "ru"), ("qmenu", "-"), ("back", "-")):
        await on_settings(
            make_callback(SettingsCb(a=action, v=value).pack(), bot=bot),
            SettingsCb(a=action, v=value),
            settings=get_settings(),
        )
    assert any(type(r).__name__ == "EditMessageText" for r in session.requests)


async def test_links_survives_a_failing_edit(
    env_settings: None, db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: links.py used raw edit_text, so a failed card edit escaped."""
    from bot.handlers.links import on_text

    session = EditHostileSession("Bad Request: message to edit not found")
    bot = Bot(token="123456:TESTTOKEN-scaffold", session=session)

    async def fake_extract(*args: Any, **kwargs: Any) -> MediaInfo:
        return _info()

    monkeypatch.setattr("bot.handlers.links.extract_media", fake_extract)
    await on_text(make_message("https://youtu.be/dQw4w9WgXcQ", bot=bot))

    async def boom(*args: Any, **kwargs: Any) -> MediaInfo:
        raise RuntimeError("nope")

    monkeypatch.setattr("bot.handlers.links.extract_media", boom)
    await on_text(make_message("https://youtu.be/dQw4w9WgXcQ", bot=bot))


async def test_heartbeat_survives_an_unwritable_path(tmp_path: Path) -> None:
    """A heartbeat write error used to kill the task and resurface at shutdown."""
    from bot.main import _heartbeat_loop

    stop = asyncio.Event()
    # A directory where the heartbeat file should be: every write fails.
    blocked = tmp_path / "hb"
    blocked.mkdir()
    task = asyncio.create_task(_heartbeat_loop(str(blocked), stop))
    await asyncio.sleep(0.05)
    assert not task.done(), "the loop must keep running despite write errors"
    stop.set()
    await asyncio.wait_for(task, timeout=2)


def test_bad_token_exits_cleanly(
    env_settings: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A wrong BOT_TOKEN is the commonest startup failure; it printed a raw
    aiogram traceback instead of telling the operator what to fix."""
    from aiogram.exceptions import TelegramUnauthorizedError
    from aiogram.methods import GetMe
    from bot import main as main_mod

    async def unauthorized(*args: Any, **kwargs: Any) -> None:
        raise TelegramUnauthorizedError(method=GetMe(), message="Unauthorized")

    monkeypatch.setattr(main_mod, "run", unauthorized)
    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "BOT_TOKEN" in err
    assert "Traceback" not in err


def test_message_helper_still_works() -> None:
    assert make_message("x").text == "x"
