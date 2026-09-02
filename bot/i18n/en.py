STRINGS: dict[str, str] = {
    "start_greeting": (
        "👋 Hi! I download videos from TikTok, YouTube, YouTube Shorts and Instagram Reels.\n\n"
        "How to use:\n"
        "1. Send a video link\n"
        "2. Pick a quality or audio\n"
        "3. Get the file in this chat\n\n"
        "Commands:\n"
        "/help — help\n"
        "/settings — default quality and language"
    ),
    "help_text": (
        "Supported platforms:\n"
        "• TikTok\n"
        "• YouTube\n"
        "• YouTube Shorts\n"
        "• Instagram Reels\n\n"
        "Size limit: {max_mb} MB (Telegram Bot API).\n"
        "Send a link and I will show available formats."
    ),
    "getting_info": "⏳ Fetching info…",
    "card": "{emoji} {platform}\n\n<b>{title}</b>\n⏱ {duration}",
    "btn_quality": "{label}",
    "btn_quality_oversize": "{label} ⚠️ >{max_mb} MB",
    "btn_quality_default": "✅ {label}",
    "btn_audio": "🎵 Audio (mp3)",
    "btn_cancel": "❌ Cancel",
    "btn_another": "🔁 Another format",
    "downloading": "⬇️ Downloading… {pct}%",
    "download_done": "✅ Done: {title}",
    "cancelled": "Cancelled.",
    "err_unsupported": (
        "I cannot download that. Send a TikTok, YouTube, Shorts or Instagram Reels link."
    ),
    "err_extract": "Could not fetch video info. Try another link.",
    "err_ig_cookies": (
        "Instagram refused the video (login wall or rate limit).\n\n"
        "Export a Netscape cookies.txt, set IG_COOKIES_FILE (see .env.example), "
        "and restart the bot."
    ),
    "err_too_large": (
        "This option is larger than {max_mb} MB — Telegram Bot API will reject it.\n"
        "Pick a smaller quality."
    ),
    "err_download": "Download failed. Try again later or another quality.",
    "err_cancelled": "Download cancelled.",
    "err_generic": "Something went wrong. Please try again.",
    "err_no_formats": "No suitable formats found for this video.",
    "rate_limited": "Too many requests. Wait {seconds}s and try again.",
    "settings_title": "Settings\n\nDefault quality: {quality}\nLanguage: {language}",
    "settings_quality_title": "Default quality",
    "settings_lang_title": "Interface language",
    "quality_auto": "Auto",
    "quality_360": "360p",
    "quality_480": "480p",
    "quality_720": "720p",
    "quality_1080": "1080p",
    "lang_ru": "Русский",
    "lang_en": "English",
    "settings_saved": "Saved.",
    "btn_back": "← Back",
    "stats_text": (
        "📊 Stats\n\n"
        "Users: {users}\n"
        "Downloads: {downloads}\n"
        "• YouTube: {youtube}\n"
        "• Shorts: {youtube_shorts}\n"
        "• TikTok: {tiktok}\n"
        "• Instagram: {instagram_reels}\n"
        "Cache hits: {cache_hits}\n"
        "Hit rate: {hit_rate}"
    ),
    "stats_denied": "Not authorized.",
    "duration_unknown": "—",
    "platform_tiktok": "TikTok",
    "platform_youtube": "YouTube",
    "platform_youtube_shorts": "YouTube Shorts",
    "platform_instagram_reels": "Instagram Reels",
}
