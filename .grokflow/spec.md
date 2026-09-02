# Telegram media downloader bot (aiogram 3 + yt-dlp)

Run: 20260902-542ec4
Branch: grokflow/telegram-media-downloader-bot-aiogram-3-20260902-542ec4 (from main)
Tracking issue: https://github.com/scarrymany/bot-tg-media/issues/1

## Goal

A production-quality Telegram bot (aiogram 3) that downloads media from **TikTok, YouTube, YouTube Shorts and Instagram Reels**. The user sends a link, the bot replies with inline buttons to choose a format (video quality or audio) and delivers the file directly in the chat. Russian is the default UI language, English is available.

## Non-goals

- Playlists, channels, whole profiles.
- Private / paid / age-gated content bypassing.
- Web admin panel.
- A local Telegram Bot API server for files above 50 MB (the bot works within the standard 50 MB upload limit).

## Stack

- Python 3.12, **aiogram 3.x** (Router-based handlers, FSM not required), **yt-dlp** (latest), **ffmpeg** (stream merge, mp3 extraction), **aiosqlite**, **pydantic-settings** (`.env`), **structlog**.
- Tests: **pytest**, **pytest-asyncio**, mocked yt-dlp (no network in unit tests), aiogram handlers tested with a mocked Bot / `MockedSession` pattern.
- Lint/format: **ruff** (check + format). Type hints everywhere; `mypy --strict` on `bot/` should pass or be close (not a blocker).
- Packaging: `pyproject.toml` with `[project.optional-dependencies] dev`. Entry point `python -m bot`.
- Docker: `Dockerfile` (python:3.12-slim + ffmpeg), `docker-compose.yml` with a named volume for the SQLite DB and a healthcheck. `.env.example` documented.
- CI: GitHub Actions workflow `ci.yml` running `ruff check`, `ruff format --check` and `pytest` on push/PR.

## Architecture (module layout)

```
bot/
  __main__.py          # python -m bot
  main.py              # build Dispatcher, register routers/middlewares, start polling, graceful shutdown
  config.py            # Settings: BOT_TOKEN, ADMIN_IDS, MAX_FILE_MB=50, RATE_LIMIT_PER_MIN=5, MAX_CONCURRENT_DOWNLOADS=3,
                       #           DOWNLOAD_DIR, DB_PATH, IG_COOKIES_FILE (optional), DEFAULT_LANG=ru, LOG_LEVEL
  handlers/
    start.py           # /start, /help
    settings.py        # /settings: default quality, language (inline keyboards)
    links.py           # any message containing a supported URL -> extract formats -> keyboard
    callbacks.py       # format chosen / cancel / "another format" -> download & send
    admin.py           # /stats for ADMIN_IDS
  services/
    detector.py        # find URLs in text, classify platform (tiktok, youtube, youtube_shorts, instagram_reels),
                       # normalise (youtu.be, m.youtube, shorts/, vm.tiktok.com, vt.tiktok.com, instagram.com/reel|reels|p)
    extractor.py       # yt_dlp.extract_info(download=False) in a thread executor; build a list of FormatOption
                       # (label 360p/480p/720p/1080p, format selector, est. size bytes, has_audio) + audio option
    downloader.py      # download selected format in executor with progress hook; merge via ffmpeg; mp3 extraction;
                       # size guard before and after download; temp dir per job; always cleanup
    sender.py          # send_video / send_audio with proper attributes (duration, width, height, title, performer, thumbnail)
  keyboards.py         # InlineKeyboardBuilder factories; CallbackData classes (FormatCb, CancelCb, AnotherCb, SettingsCb)
  middlewares/
    rate_limit.py      # per-user sliding window (RATE_LIMIT_PER_MIN)
    concurrency.py     # global asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS) around downloads
    logging.py         # structlog context (user_id, update_id)
  storage/
    db.py              # aiosqlite init + migrations (schema_version table)
    cache.py           # media_cache(url_norm, format_key) -> file_id, kind, created_at
    users.py           # user_settings(user_id, quality, lang), stats counters
  i18n/
    __init__.py        # t(key, lang, **kwargs)
    ru.py, en.py
tests/                 # unit + handler tests, fixtures with mocked yt-dlp and Bot
scripts/e2e_smoke.py   # manual end-to-end: sends a real link to the bot via a test account (documented, not in CI)
```

### Key behaviours

- **Link flow**: message with URL → reply "⏳ Получаю информацию…" → extractor → edit message into a card (title, duration, platform emoji) with inline keyboard: one button per available quality (only those ≤ MAX_FILE_MB by estimated size are shown as normal; larger ones are shown with "⚠️ >50 МБ" and lead to a message explaining the limit and offering smaller qualities), "🎵 Аудио (mp3)", "❌ Отмена".
- **Download flow**: on button press → answer callback → edit card to "⬇️ Загрузка… 0%" and update at most every 2 s (progress hook, throttled, ignores `TelegramBadRequest: message is not modified`) → send video (as `video`, streamable, with `supports_streaming=True`) or audio → delete/replace the progress card with a final card that has "🔁 Другой формат" → cleanup temp files.
- **Cache**: before downloading, look up `(normalised_url, format_key)`; if a `file_id` exists, resend immediately by `file_id`. After a successful send, store the `file_id`.
- **TikTok**: prefer a no-watermark format when yt-dlp exposes one.
- **Instagram**: if extraction fails with a login/rate-limit error and `IG_COOKIES_FILE` is unset, reply with a clear message (i18n) that Instagram requires cookies and how to configure them; with cookies configured pass `cookiefile` to yt-dlp.
- **Errors**: every yt-dlp / network / Telegram error is caught and turned into a short i18n message; never leak tracebacks to the user; log with structlog.
- **Rate limit**: exceeding RATE_LIMIT_PER_MIN → polite i18n refusal with the wait time.
- **/settings**: inline menu to set default quality (auto/360/480/720/1080) and language (ru/en). With a default quality set, the bot still shows the keyboard but marks the default with ✅.
- **/stats** (admins only): total users, downloads by platform, cache hit rate.
- **Shutdown**: SIGINT/SIGTERM → stop polling, wait for in-flight downloads (bounded), close DB.
- **Healthcheck**: the process writes a heartbeat file every 30 s; Docker healthcheck checks its mtime.

## Phases (commit + push after each, prefix `[grokflow build n/5]`)

1. **Scaffold** – pyproject, package layout, config, structlog, `/start`, `/help`, Dockerfile, docker-compose, `.env.example`, CI workflow, first tests (config loading, /start handler).
2. **Detection & formats** – `detector.py` (all URL shapes, tests with 20+ fixtures), `extractor.py` with mocked yt-dlp, `keyboards.py`, `links.py` handler producing the card + keyboard. Tests for keyboard contents and size flags.
3. **Download & send** – `downloader.py` (progress, ffmpeg merge, mp3, size guard, cleanup), `sender.py`, `callbacks.py`, error mapping, cancel button. Tests with a fake downloader and mocked Bot.
4. **Storage & UX** – SQLite migrations, file_id cache, user settings, `/settings`, i18n ru/en for every user-facing string, rate-limit + concurrency middlewares, `/stats`. Tests for cache, settings, rate limit.
5. **Production readiness** – Instagram cookies support, healthcheck + graceful shutdown, README (setup, env vars, Docker deploy, troubleshooting), `scripts/e2e_smoke.py`, final `ruff` + `pytest` green, mypy cleanup.

## How to run

- Install: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"` (Windows: `.venv\Scripts\activate`)
- Test: `pytest -q` and `ruff check .`
- Run: copy `.env.example` to `.env`, set `BOT_TOKEN`, then `python -m bot`
- Docker: `docker compose up -d --build`

ffmpeg must be installed on the host for local runs (the Docker image includes it).
## How to run
- Install: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest -q && ruff check .`
- Run: `python -m bot`
