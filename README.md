# bot-tg-media

Telegram-бот на **aiogram 3 + yt-dlp**: скачивает видео из TikTok, YouTube, YouTube Shorts и Instagram Reels. Пользователь кидает ссылку → инлайн-кнопки качества / аудио → файл в чат. UI по умолчанию русский, английский переключается в `/settings`.

Лимит Telegram Bot API — **50 МБ**. Плейлисты, каналы и обход логина/пейволла не поддерживаются.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Нужен **ffmpeg** в `PATH` (merge видео+аудио и mp3). В Docker он уже в образе.

```bash
# Debian/Ubuntu
sudo apt-get install -y ffmpeg
```

```bash
cp .env.example .env
# пропиши BOT_TOKEN от @BotFather
pytest -q && ruff check .
python -m bot
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | токен бота, обязателен |
| `ADMIN_IDS` | пусто | Telegram user id через запятую; им доступен `/stats` |
| `MAX_FILE_MB` | `50` | порог, выше которого качество помечается `⚠️ >50 МБ` |
| `RATE_LIMIT_PER_MIN` | `5` | скользящее окно на ссылки и скачивания |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | глобальный семафор yt-dlp |
| `DOWNLOAD_DIR` | `./downloads` | временные файлы (удаляются после отправки) |
| `DB_PATH` | `./data/bot.db` | SQLite: кэш `file_id`, настройки, статистика |
| `IG_COOKIES_FILE` | пусто | Netscape `cookies.txt` для Instagram |
| `DEFAULT_LANG` | `ru` | `ru` или `en` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `HEARTBEAT_PATH` | `/tmp/bot-heartbeat` | файл для Docker healthcheck (mtime ≤ 90 с) |

## Commands

- `/start` — приветствие и инструкция
- `/help` — список платформ
- `/settings` — качество по умолчанию (`auto` / 360 / 480 / 720 / 1080) и язык
- `/stats` — админы: пользователи, скачивания по платформам, cache hit rate

Ссылка в чате → карточка с кнопками качества, «🎵 Аудио (mp3)», «❌ Отмена». Повтор того же URL+формата уходит из кэша `file_id` без скачивания.

## Instagram cookies

Если Instagram отвечает login / rate-limit и `IG_COOKIES_FILE` пуст, бот пишет, как положить cookies, и **не падает**.

1. Залогинься в Instagram в браузере.
2. Экспортируй cookies в Netscape-формате (расширение вроде «Get cookies.txt LOCALLY»).
3. Сохрани файл, например `./cookies/instagram.txt`.
4. `IG_COOKIES_FILE=./cookies/instagram.txt` и перезапусти бота.

yt-dlp получит `cookiefile` и на extract, и на download. Файл не коммить.

## Docker

```bash
cp .env.example .env   # BOT_TOKEN обязателен
docker compose up -d --build
docker compose ps      # healthcheck → healthy после старта (~40 с start_period)
```

- Образ: `python:3.12-slim` + ffmpeg.
- Volume `bot-data` → `/data` (`DB_PATH=/data/bot.db`, `DOWNLOAD_DIR=/data/downloads`).
- Healthcheck: mtime `HEARTBEAT_PATH` свежее 90 секунд (процесс пишет файл каждые 30 с).
- `SIGINT`/`SIGTERM`: стоп polling, ждёт in-flight download (до 30 с), закрывает SQLite.

Логи: `docker compose logs -f bot`.

## Troubleshooting

| Симптом | Что проверить |
|---|---|
| бот не стартует | `BOT_TOKEN` в `.env`, формат `123456:AA...` |
| «не удалось получить информацию» | ссылка публичная? не плейлист/канал? yt-dlp свежий (`pip install -U yt-dlp`) |
| Instagram просит cookies | см. секцию выше; без cookies это ожидаемо |
| видео с водяным знаком TikTok | yt-dlp отдаёт no-watermark — бот его предпочитает; иначе остаётся то, что есть |
| «больше 50 МБ» | выбери качество ниже; локальный Bot API server не используется |
| нет звука / нет mp3 | `ffmpeg -version`; в контейнере ffmpeg уже есть |
| rate limit | `RATE_LIMIT_PER_MIN`, подожди указанное число секунд |
| healthcheck unhealthy | контейнер должен прожить `start_period`; нет `BOT_TOKEN` → процесс сразу умирает |
| повтор качает заново | тот же нормализованный URL + тот же `format_key`; кэш в SQLite |

## Tests / lint

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
ruff format --check .
mypy --strict bot   # близко к чистому, не блокер CI
```

Ручной смоук (не в CI):

```bash
python scripts/e2e_smoke.py
E2E_EXTRACT=1 python scripts/e2e_smoke.py   # ещё и yt-dlp extract публичного YouTube
```

`scripts/e2e_smoke.py` бьёт `getMe` и опционально extract. Чтобы **отправить ссылку боту**, нужен user-аккаунт (Telethon/Pyrogram) — в скрипте расписаны ручные шаги.
