"""Чистое оформление сообщений — без спама эмодзи."""

from __future__ import annotations

import re

from oracle_bot.config import ORACLE_DEEP_STARS


def reading_header(title: str, name: str = "") -> str:
    title = title.strip()
    if name:
        return f"<b>{title}</b> · {name}"
    return f"<b>{title}</b>"


def clean_llm_part(text: str) -> str:
    """Убирает метки ЧАСТЬ 1/2 и лишние заголовки из ответа LLM."""
    t = text.strip()
    t = re.sub(r"^ЧАСТЬ\s*[12]\s*[:\-]?\s*", "", t, flags=re.I | re.M)
    t = re.sub(r"^#{1,3}\s*", "", t, flags=re.M)
    return t.strip()


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
