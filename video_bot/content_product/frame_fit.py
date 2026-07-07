"""Вписывание кадра в 9:16 без обрезки важных частей."""

from __future__ import annotations

from video_bot.generate import H, W

# Тёмный фон под letterbox / blur
_PAD_COLOR = "0x0c0c14"


def pad_fit_chain(extra: str = "") -> str:
    """Фото/кадр целиком: scale down + тёмные поля (ничего не отрезаем)."""
    chain = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={_PAD_COLOR}"
    )
    if extra:
        return f"{chain},{extra}"
    return chain


def blur_fit_overlay(extra: str = "") -> str:
    """Видео: размытый фон + оригинал по центру (как в ТВ-репортажах)."""
    tail = f",{extra}" if extra else ""
    return (
        f"split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=lr=22:lp=2[bg];"
        f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2{tail}"
    )
