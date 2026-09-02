from __future__ import annotations

import asyncio
from pathlib import Path

from bot.i18n import LANGS
from bot.main import _heartbeat_loop
from bot.services.downloader import ffmpeg_available


async def test_heartbeat_writes_and_stops(tmp_path: Path) -> None:
    path = tmp_path / "hb"
    stop = asyncio.Event()
    task = asyncio.create_task(_heartbeat_loop(str(path), stop))
    for _ in range(50):
        if path.exists():
            break
        await asyncio.sleep(0.02)
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip().isdigit()
    stop.set()
    await asyncio.wait_for(task, timeout=1)


def test_i18n_keys_match() -> None:
    assert set(LANGS["ru"]) == set(LANGS["en"])


def test_ffmpeg_helper_runs() -> None:
    assert ffmpeg_available() in {True, False}
