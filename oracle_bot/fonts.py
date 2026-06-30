"""Единый загрузчик Unicode-шрифта для PDF (кириллица на любой платформе)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_VENDOR = Path(__file__).resolve().parent / "assets" / "fonts"

# Порядок: свой вшитый DejaVu (есть на Render) → системные macOS/Linux.
_CANDIDATES = [
    (_VENDOR / "DejaVuSans.ttf", _VENDOR / "DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def unicode_font_paths() -> tuple[str | None, str | None]:
    for reg, bold in _CANDIDATES:
        if os.path.exists(reg):
            bold_path = str(bold) if os.path.exists(bold) else str(reg)
            return str(reg), bold_path
    return None, None


def register_pdf_font(pdf) -> tuple[str, str, bool]:
    """Регистрирует Unicode-шрифт в FPDF. Возвращает (regular, bold, unicode?)."""
    reg, bold = unicode_font_paths()
    if reg:
        try:
            pdf.add_font("Body", "", reg)
            pdf.add_font("BodyB", "", bold)
            return "Body", "BodyB", True
        except Exception as e:  # noqa: BLE001
            logger.warning("pdf font register failed (%s): %s", reg, e)
    return "Helvetica", "Helvetica", False
