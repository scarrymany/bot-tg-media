STRINGS: dict[str, str] = {
    "start_greeting": (
        "👋 Привет! Я скачаю видео из TikTok, YouTube, YouTube Shorts и Instagram Reels.\n\n"
        "Как пользоваться:\n"
        "1. Пришлите ссылку на видео\n"
        "2. Выберите качество или аудио\n"
        "3. Получите файл прямо в чат\n\n"
        "Команды:\n"
        "/help — справка\n"
        "/settings — качество по умолчанию и язык"
    ),
    "help_text": (
        "Поддерживаемые платформы:\n"
        "• TikTok\n"
        "• YouTube\n"
        "• YouTube Shorts\n"
        "• Instagram Reels\n\n"
        "Ограничение размера: {max_mb} МБ (лимит Telegram Bot API).\n"
        "Пришлите ссылку — покажу доступные форматы."
    ),
    "getting_info": "⏳ Получаю информацию…",
    "card": "{emoji} {platform}\n\n<b>{title}</b>\n⏱ {duration}",
    "btn_quality": "{label}",
    "btn_quality_oversize": "{label} ⚠️ >{max_mb} МБ",
    "btn_quality_default": "✅ {label}",
    "btn_audio": "🎵 Аудио (mp3)",
    "btn_cancel": "❌ Отмена",
    "btn_another": "🔁 Другой формат",
    "downloading": "⬇️ Загрузка… {pct}%",
    "download_done": "✅ Готово: {title}",
    "cancelled": "Отменено.",
    "err_unsupported": (
        "Не могу скачать это. Пришлите ссылку на TikTok, YouTube, Shorts или Instagram Reels."
    ),
    "err_extract": "Не удалось получить информацию о видео. Попробуйте другую ссылку.",
    "err_ig_cookies": (
        "Instagram не отдаёт видео без авторизации (логин или лимит запросов).\n\n"
        "Положите cookies.txt в Netscape-формате и укажите путь в IG_COOKIES_FILE "
        "(см. .env.example). Затем перезапустите бота."
    ),
    "err_too_large": (
        "Этот вариант больше {max_mb} МБ — Telegram Bot API его не примет.\n"
        "Выберите качество поменьше."
    ),
    "err_download": "Не удалось скачать файл. Попробуйте позже или другое качество.",
    "err_cancelled": "Загрузка отменена.",
    "err_generic": "Что-то пошло не так. Попробуйте ещё раз.",
    "err_no_formats": "Не нашёл подходящих форматов для этого видео.",
    "rate_limited": "Слишком часто. Подождите {seconds} с и попробуйте снова.",
    "settings_title": "Настройки\n\nКачество по умолчанию: {quality}\nЯзык: {language}",
    "settings_quality_title": "Качество по умолчанию",
    "settings_lang_title": "Язык интерфейса",
    "quality_auto": "Авто",
    "quality_360": "360p",
    "quality_480": "480p",
    "quality_720": "720p",
    "quality_1080": "1080p",
    "lang_ru": "Русский",
    "lang_en": "English",
    "settings_saved": "Сохранено.",
    "btn_back": "← Назад",
    "stats_text": (
        "📊 Статистика\n\n"
        "Пользователи: {users}\n"
        "Скачивания: {downloads}\n"
        "• YouTube: {youtube}\n"
        "• Shorts: {youtube_shorts}\n"
        "• TikTok: {tiktok}\n"
        "• Instagram: {instagram_reels}\n"
        "Попадания в кэш: {cache_hits}\n"
        "Hit rate: {hit_rate}"
    ),
    "stats_denied": "Недостаточно прав.",
    "duration_unknown": "—",
    "platform_tiktok": "TikTok",
    "platform_youtube": "YouTube",
    "platform_youtube_shorts": "YouTube Shorts",
    "platform_instagram_reels": "Instagram Reels",
}
