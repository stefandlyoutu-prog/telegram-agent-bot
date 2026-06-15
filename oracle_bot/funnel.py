"""Воронка: полезная бесплатная часть → платное углубление."""

from __future__ import annotations

from oracle_bot.config import LOCK_MARKER, ORACLE_DEEP_STARS, ORACLE_PREMIUM_STARS
from oracle_bot import storage as db
from oracle_bot.formatting import clean_llm_part


def parse_split(raw: str) -> tuple[str, str]:
    if LOCK_MARKER in raw:
        a, b = raw.split(LOCK_MARKER, 1)
        return clean_llm_part(a), clean_llm_part(b)
    words = raw.split()
    # ~65% бесплатно / 35% платно по объёму
    mid = max(120, int(len(words) * 0.65))
    return clean_llm_part(" ".join(words[:mid])), clean_llm_part(" ".join(words[mid:]))


def format_teaser(teaser: str) -> str:
    return (
        f"{teaser}\n\n"
        "──────────────\n"
        f"<b>Углубление</b> — персональные периоды, прогноз на месяцы и второй слой разбора.\n"
        f"🔓 {ORACLE_DEEP_STARS}⭐ · ⭐ Премиум {ORACLE_PREMIUM_STARS}⭐ / 30 д"
    )


def format_full(teaser: str, locked: str) -> str:
    return f"{teaser}\n\n{locked}"


def deliver(
    *,
    user_id: int,
    module: str,
    raw_text: str,
    header: str = "",
) -> tuple[str, int | None]:
    teaser, locked = parse_split(raw_text)
    if db.is_premium(user_id):
        body = format_full(teaser, locked)
        if header:
            return f"{header}\n\n{body}", None
        return body, None

    cont_id = db.save_continuation(user_id, module, teaser, locked)
    body = format_teaser(teaser)
    if header:
        return f"{header}\n\n{body}", cont_id
    return body, cont_id
