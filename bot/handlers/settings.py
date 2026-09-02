from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import Settings, get_settings
from bot.i18n import t
from bot.keyboards import (
    SettingsCb,
    language_keyboard,
    quality_keyboard,
    settings_root_keyboard,
)
from bot.storage.users import get_user, set_lang, set_quality

router = Router(name="settings")


def _settings_text(quality: str, lang: str) -> str:
    return t(
        "settings_title",
        lang,
        quality=t(f"quality_{quality}", lang),
        language=t(f"lang_{lang}", lang),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    settings = get_settings()
    user_id = message.from_user.id if message.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    await message.answer(
        _settings_text(user.quality, user.lang),
        reply_markup=settings_root_keyboard(user.lang),
    )


@router.callback_query(SettingsCb.filter())
async def on_settings(
    callback: CallbackQuery,
    callback_data: SettingsCb,
    settings: Settings,
) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    user = await get_user(user_id, settings.default_lang)
    action = callback_data.a
    if action == "qmenu":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                t("settings_quality_title", user.lang),
                reply_markup=quality_keyboard(user.lang, user.quality),
            )
        return
    if action == "lmenu":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                t("settings_lang_title", user.lang),
                reply_markup=language_keyboard(user.lang, user.lang),
            )
        return
    if action == "qual":
        user = await set_quality(user_id, callback_data.v, settings.default_lang)
        await callback.answer(t("settings_saved", user.lang))
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                _settings_text(user.quality, user.lang),
                reply_markup=settings_root_keyboard(user.lang),
            )
        return
    if action == "lang":
        user = await set_lang(user_id, callback_data.v, settings.default_lang)
        await callback.answer(t("settings_saved", user.lang))
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                _settings_text(user.quality, user.lang),
                reply_markup=settings_root_keyboard(user.lang),
            )
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            _settings_text(user.quality, user.lang),
            reply_markup=settings_root_keyboard(user.lang),
        )
