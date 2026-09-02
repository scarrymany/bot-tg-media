from __future__ import annotations

from bot.i18n import t
from bot.keyboards import CancelCb, FormatCb, formats_keyboard
from bot.services.extractor import FormatOption, MediaInfo


def _info() -> MediaInfo:
    return MediaInfo(
        source_url="https://youtu.be/dQw4w9WgXcQ",
        normalised_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform="youtube",
        title="Test",
        duration=12,
        thumbnail=None,
        uploader="x",
        formats=[
            FormatOption("360", "360p", "18", 5_000_000, True, False, 360, 640),
            FormatOption("720", "720p", "22", 20_000_000, True, False, 720, 1280),
            FormatOption("1080", "1080p", "137+140", 82_000_000, True, True, 1080, 1920),
            FormatOption("audio", "mp3", "bestaudio/best", 2_000_000, True, False),
        ],
    )


def _button_texts(markup) -> list[str]:
    texts: list[str] = []
    for row in markup.inline_keyboard:
        for button in row:
            texts.append(button.text)
    return texts


def test_keyboard_has_quality_audio_cancel() -> None:
    markup = formats_keyboard(_info(), "tok1234567", lang="ru", max_mb=50)
    texts = _button_texts(markup)
    assert any("360p" in text for text in texts)
    assert any("720p" in text for text in texts)
    assert t("btn_audio", "ru") in texts
    assert t("btn_cancel", "ru") in texts
    packed = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any(item.startswith(FormatCb(t="tok1234567", k="720").pack()) for item in packed)
    assert CancelCb(t="tok1234567").pack() in packed


def test_oversize_flag_on_button() -> None:
    markup = formats_keyboard(_info(), "tok1234567", lang="ru", max_mb=50)
    texts = _button_texts(markup)
    oversize = t("btn_quality_oversize", "ru", label="1080p", max_mb=50)
    assert oversize in texts
    assert "⚠️" in oversize


def test_default_quality_checkmark() -> None:
    markup = formats_keyboard(_info(), "tok1234567", lang="ru", default_quality="720", max_mb=50)
    texts = _button_texts(markup)
    assert t("btn_quality_default", "ru", label="720p") in texts
    assert "✅" in "".join(texts)
