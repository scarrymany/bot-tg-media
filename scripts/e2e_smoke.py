#!/usr/bin/env python3
"""Manual end-to-end smoke. Not part of CI.

Checks that the process can talk to Telegram and (optionally) that yt-dlp
can extract a public YouTube URL. Sending a link *to* the bot requires a
user account (Telethon / Pyrogram) — see the steps at the bottom.

Usage:
    cp .env.example .env   # set BOT_TOKEN
    python scripts/e2e_smoke.py
    E2E_EXTRACT=1 python scripts/e2e_smoke.py

Optional live user-send (not wired by default):
    TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION + a user client
    that messages the bot with a public YouTube URL, then reads the reply.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAMPLE_YOUTUBE = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


async def _get_me(token: str) -> str:
    from aiogram import Bot

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return f"@{me.username}" if me.username else str(me.id)
    finally:
        await bot.session.close()


def _extract_sample() -> str:
    from bot.services.detector import classify_url
    from bot.services.extractor import _ydl_extract, build_ydl_opts

    link = classify_url(SAMPLE_YOUTUBE)
    if link is None:
        raise RuntimeError("sample URL did not classify")
    info = _ydl_extract(link.normalised_url, build_ydl_opts())
    title = str(info.get("title") or "?")
    n_fmt = len(info.get("formats") or [])
    return f"{title!r} formats={n_fmt}"


def main() -> int:
    from bot.config import Settings, reset_settings_cache

    reset_settings_cache()
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:
        sys.stderr.write(f"config error (set BOT_TOKEN in .env): {exc}\n")
        return 2

    print(f"python     {sys.version.split()[0]}")
    ffmpeg = shutil.which("ffmpeg")
    print(f"ffmpeg     {ffmpeg or 'MISSING (required for merge / mp3)'}")
    print(f"download   {settings.download_dir}")
    print(f"db         {settings.db_path}")
    print(f"ig_cookies {settings.ig_cookies_file or '(unset)'}")

    try:
        who = asyncio.run(_get_me(settings.bot_token))
    except Exception as exc:
        sys.stderr.write(f"getMe failed: {exc}\n")
        return 1
    print(f"bot        {who}")

    if os.environ.get("E2E_EXTRACT") == "1":
        print(f"extract    {SAMPLE_YOUTUBE}")
        try:
            print(f"extract    {_extract_sample()}")
        except Exception as exc:
            sys.stderr.write(f"extract failed: {exc}\n")
            return 1

    print()
    print("Manual Telegram checks (need a real chat):")
    print("  1. /start  → Russian greeting + usage")
    print("  2. /help   → TikTok, YouTube, Shorts, Instagram Reels")
    print("  3. send a public YouTube URL → card < 5s with quality / audio / cancel")
    print("  4. tap a quality ≤50 MB → inline video")
    print("  5. tap audio → mp3 with title + performer")
    print("  6. /settings → switch language to English, /start again")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
