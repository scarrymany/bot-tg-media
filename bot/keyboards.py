from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
