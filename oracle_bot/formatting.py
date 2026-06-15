"""Чистое оформление сообщений — без спама эмодзи."""

from __future__ import annotations

import re

from oracle_bot.config import ORACLE_DEEP_STARS


def reading_header(title: str, name: str = "") -> str:
    title = title.strip()
    if name:
        return f"<b>{title}</b>\n{name}"
    return f"<b>{title}</b>"


def clean_llm_part(text: str) -> str:
    """Убирает метки ЧАСТЬ 1/2 и лишние заголовки из ответа LLM."""
    t = text.strip()
    t = re.sub(r"^ЧАСТЬ\s*[12]\s*[:\-]?\s*", "", t, flags=re.I | re.M)
    t = re.sub(r"^#{1,3}\s*", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def format_reading_body(text: str) -> str:
    """Разбивает «простыню» на абзацы по предложениям."""
    t = clean_llm_part(text)
    if not t:
        return t
    sentences = re.split(r"(?<=[.!?…])\s+", t)
    if len(sentences) <= 3:
        return t
    chunks: list[str] = []
    buf: list[str] = []
    for s in sentences:
        if not s.strip():
            continue
        buf.append(s.strip())
        if len(buf) >= 3:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return "\n\n".join(chunks)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
