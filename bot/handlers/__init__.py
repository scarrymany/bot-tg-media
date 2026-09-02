from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, callbacks, links, settings, start


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(settings.router)
    root.include_router(admin.router)
    root.include_router(links.router)
    root.include_router(callbacks.router)
    return root
