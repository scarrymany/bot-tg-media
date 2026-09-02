from __future__ import annotations

from bot.config import Settings
from bot.main import create_bot, create_dispatcher, setup_logging


def test_package_layout_imports() -> None:
    import bot.handlers.admin as admin
    import bot.handlers.callbacks as callbacks
    import bot.handlers.links as links
    import bot.handlers.settings as settings_h
    import bot.handlers.start as start
    import bot.i18n
    import bot.keyboards
    import bot.middlewares.concurrency
    import bot.middlewares.logging
    import bot.middlewares.rate_limit
    import bot.services.detector
    import bot.services.downloader
    import bot.services.extractor
    import bot.services.sender
    import bot.storage.cache
    import bot.storage.db
    import bot.storage.users

    assert start.router is not None
    assert settings_h.router is not None
    assert links.router is not None
    assert callbacks.router is not None
    assert admin.router is not None
    assert bot.i18n.t("btn_cancel", "ru")


def test_create_dispatcher(env_settings: None) -> None:
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings)
    bot = create_bot(settings)
    dp = create_dispatcher(settings)
    assert bot.token is not None and bot.token.endswith("scaffold")
    assert dp.sub_routers
