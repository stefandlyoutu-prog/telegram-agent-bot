"""Воронка: полезная бесплатная часть → платное углубление."""

from __future__ import annotations

from oracle_bot.config import LOCK_MARKER, ORACLE_DEEP_STARS, ORACLE_PREMIUM_STARS
from oracle_bot import storage as db
from oracle_bot.formatting import format_reading_body


def parse_split(raw: str) -> tuple[str, str]:
    if LOCK_MARKER in raw:
        a, b = raw.split(LOCK_MARKER, 1)
        return format_reading_body(a), format_reading_body(b)
    words = raw.split()
    mid = max(120, int(len(words) * 0.65))
    return format_reading_body(" ".join(words[:mid])), format_reading_body(" ".join(words[mid:]))


def format_teaser(teaser: str) -> str:
    from oracle_bot.config import ORACLE_DEEP_FIRST_PRICE_RUB, ORACLE_DEEP_PRICE_RUB

    first = ORACLE_DEEP_FIRST_PRICE_RUB
    regular = ORACLE_DEEP_PRICE_RUB
    price_hint = f"{first}₽ (первый раз)" if first < regular else f"{regular}₽"
    return (
        f"{teaser}\n\n"
        "────────────\n"
        "🔒 <b>Сценарий 2</b> — что изменится и конкретные шаги, если работать с картой.\n"
        f"Открой за <b>{price_hint}</b> · ⭐ Премиум {ORACLE_PREMIUM_STARS}⭐ / 30 д"
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
    from oracle_bot.access import has_full_access

    teaser, locked = parse_split(raw_text)
    if has_full_access(user_id):
        body = format_full(teaser, locked)
        if header:
            return f"{header}\n\n{body}", None
        return body, None

    cont_id = db.save_continuation(user_id, module, teaser, locked)
    body = format_teaser(teaser)
    if header:
        return f"{header}\n\n{body}", cont_id
    return body, cont_id
