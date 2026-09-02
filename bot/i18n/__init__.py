from __future__ import annotations

from bot.i18n import en, ru

LANGS: dict[str, dict[str, str]] = {
    "ru": ru.STRINGS,
    "en": en.STRINGS,
}


def t(key: str, lang: str = "ru", **kwargs: object) -> str:
    table = LANGS.get(lang, LANGS["ru"])
    template = table.get(key) or LANGS["ru"].get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template
