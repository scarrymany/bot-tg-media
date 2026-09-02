# Acceptance checklist (run 20260902-542ec4)

Every item must be verified by actually running the software, not by reading the code.

1. [ ] On a clean clone: `pip install -e ".[dev]"`, `pytest -q` and `ruff check .` all pass.
2. [ ] With a valid BOT_TOKEN the bot starts via `python -m bot`; /start replies with a Russian greeting and usage instructions; /help lists supported platforms.
3. [ ] Sending a public YouTube link produces, within 5 seconds, a card with inline buttons: at least one quality option, an audio option and a cancel button.
4. [ ] Pressing a quality button delivers the video as a Telegram video message that plays inline (public YouTube video under 50 MB).
5. [ ] A YouTube Shorts link works exactly like a regular YouTube link.
6. [ ] A TikTok link delivers the video, without watermark when such a format is available.
7. [ ] A public Instagram Reels link delivers the video; if Instagram blocks extraction without cookies, the bot replies with a clear message about configuring IG_COOKIES_FILE instead of crashing.
8. [ ] The audio button delivers an mp3 as a Telegram audio message with title and performer filled.
9. [ ] For a video whose chosen quality exceeds 50 MB the bot explains the limit and offers smaller qualities; no exception is raised.
10. [ ] An unsupported or malformed link yields a friendly message; no traceback is sent or logged as unhandled.
11. [ ] The progress message is updated while downloading and is replaced by the result card with a 'another format' button.
12. [ ] Requesting the same URL and format a second time is answered instantly from the file_id cache (no re-download, verified via logs or timing).
13. [ ] Exceeding RATE_LIMIT_PER_MIN yields a polite refusal that states the wait time.
14. [ ] /settings allows changing the default quality and the language; after switching to English all bot replies are in English.
15. [ ] `docker compose up -d --build` starts the bot and the container healthcheck becomes healthy.
