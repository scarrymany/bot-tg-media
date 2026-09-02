from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pydantic import ValidationError

from bot.config import Settings, get_settings
from bot.handlers import setup_routers
from bot.middlewares.concurrency import ConcurrencyMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.services.downloader import Downloader, ffmpeg_available
from bot.storage.db import close_db, init_db

log = structlog.get_logger("bot")


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp["settings"] = settings
    dp["downloader"] = Downloader(settings)
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(RateLimitMiddleware(settings.rate_limit_per_min))
    dp.update.outer_middleware(ConcurrencyMiddleware(settings.max_concurrent_downloads))
    dp.include_router(setup_routers())
    return dp


async def _heartbeat_loop(path: str | None, stop: asyncio.Event) -> None:
    if not path:
        return
    from pathlib import Path

    heartbeat = Path(path)
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        heartbeat.write_text(str(int(time.time())), encoding="utf-8")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            continue


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    setup_logging(settings)
    settings.ensure_dirs()
    bot = create_bot(settings)
    dp = create_dispatcher(settings)
    stop = asyncio.Event()

    async def on_startup() -> None:
        await init_db(settings.db_path)
        cookies = settings.ig_cookies_file
        if cookies is None:
            log.info("ig_cookies", configured=False)
        elif cookies.is_file():
            log.info("ig_cookies", configured=True, path=str(cookies))
        else:
            log.warning("ig_cookies_missing", path=str(cookies))
        if not ffmpeg_available():
            log.warning("ffmpeg_missing")
        log.info("startup")

    async def on_shutdown() -> None:
        stop.set()
        downloader = dp.workflow_data.get("downloader")
        if isinstance(downloader, Downloader):
            log.info("waiting_inflight", count=downloader.in_flight)
            await downloader.wait_idle(timeout=30)
        await close_db()
        log.info("shutdown")
        await bot.session.close()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(str(settings.heartbeat_path), stop),
        name="heartbeat",
    )
    log.info("polling_start")
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        stop.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.stderr.write(
            f"Invalid configuration. Copy .env.example to .env and set BOT_TOKEN.\n{exc}\n"
        )
        raise SystemExit(2) from exc
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()


# Keep a typed alias for tests / future hooks.
ShutdownHook = Callable[[], Awaitable[None]]
