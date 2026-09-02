from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import t
from bot.services.extractor import MediaInfo


class FormatCb(CallbackData, prefix="f"):
    t: str
    k: str


class CancelCb(CallbackData, prefix="c"):
    t: str


class AnotherCb(CallbackData, prefix="a"):
    t: str


class SettingsCb(CallbackData, prefix="s"):
    a: str
    v: str = "-"


def empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().as_markup()


def formats_keyboard(
    info: MediaInfo,
    token: str,
    *,
    lang: str,
    default_quality: str = "auto",
    max_mb: int = 50,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option in info.formats:
        if option.key == "audio":
            continue
        if option.exceeds_limit:
            text = t("btn_quality_oversize", lang, label=option.label, max_mb=max_mb)
        elif default_quality != "auto" and option.key == default_quality:
            text = t("btn_quality_default", lang, label=option.label)
        else:
            text = t("btn_quality", lang, label=option.label)
        builder.button(text=text, callback_data=FormatCb(t=token, k=option.key))
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text=t("btn_audio", lang),
            callback_data=FormatCb(t=token, k="audio").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_cancel", lang),
            callback_data=CancelCb(t=token).pack(),
        )
    )
    return builder.as_markup()


def another_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_another", lang), callback_data=AnotherCb(t=token))
    return builder.as_markup()


def settings_root_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("settings_quality_title", lang), callback_data=SettingsCb(a="qmenu"))
    builder.button(text=t("settings_lang_title", lang), callback_data=SettingsCb(a="lmenu"))
    builder.adjust(1)
    return builder.as_markup()


def quality_keyboard(lang: str, current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quality in ("auto", "360", "480", "720", "1080"):
        label = t(f"quality_{quality}", lang)
        if quality == current:
            label = f"✅ {label}"
        builder.button(text=label, callback_data=SettingsCb(a="qual", v=quality))
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=SettingsCb(a="back").pack())
    )
    return builder.as_markup()


def language_keyboard(lang: str, current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in ("ru", "en"):
        label = t(f"lang_{code}", lang)
        if code == current:
            label = f"✅ {label}"
        builder.button(text=label, callback_data=SettingsCb(a="lang", v=code))
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=SettingsCb(a="back").pack())
    )
    return builder.as_markup()
