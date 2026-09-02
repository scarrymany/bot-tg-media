from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, callbacks, links, settings, start


def setup_routers() -> Router:
    """Assemble a fresh router tree.

    Every module hands back a newly built Router: aiogram refuses to attach a
    Router to a second parent, so reusing the module-level singletons would
    make ``create_dispatcher`` usable exactly once per process.

    Order matters — ``links`` matches any text message, so the command routers
    must be registered before it.
    """
    root = Router(name="root")
    root.include_router(start.build_router())
    root.include_router(settings.build_router())
    root.include_router(admin.build_router())
    root.include_router(links.build_router())
    root.include_router(callbacks.build_router())
    return root
