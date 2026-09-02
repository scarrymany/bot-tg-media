from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UserSettings:
    user_id: int
    quality: str = "auto"
    lang: str = "ru"


async def get_user(user_id: int, default_lang: str = "ru") -> UserSettings:
    return UserSettings(user_id=user_id, lang=default_lang)
