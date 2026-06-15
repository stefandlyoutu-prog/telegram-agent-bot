"""Реферальная программа: пригласи друга → бонусные расклады."""

from __future__ import annotations

from urllib.parse import quote

from oracle_bot.config import (
    ORACLE_BOT_USERNAME,
    ORACLE_REFERRAL_BONUS,
    ORACLE_REFERRAL_WELCOME,
)
from oracle_bot import storage as db


def parse_ref_payload(payload: str | None) -> int | None:
    if not payload:
        return None
    raw = payload.strip()
    if raw.lower().startswith("ref"):
        raw = raw[3:]
    try:
        uid = int(raw)
    except ValueError:
        return None
    return uid if uid > 0 else None


def referral_link(user_id: int) -> str:
    bot = ORACLE_BOT_USERNAME.lstrip("@")
    return f"https://t.me/{bot}?start=ref{user_id}"


def share_url(user_id: int) -> str:
    link = referral_link(user_id)
    text = "🔮 Попробуй m-Oracul — таро, ладонь, натальная и 25+ практик. Бесплатно!"
    return f"https://t.me/share/url?url={quote(link)}&text={quote(text)}"


def stats_text(user_id: int) -> str:
    st = db.referral_stats(user_id)
    credits = st["credits"]
    invited = st["invited"]
    link = referral_link(user_id)
    lines = [
        "🎁 <b>Пригласи друга — получи расклады</b>",
        "",
        f"За каждого нового пользователя по твоей ссылке: "
        f"<b>+{ORACLE_REFERRAL_BONUS}</b> бонусных чтений.",
    ]
    if ORACLE_REFERRAL_WELCOME > 0:
        lines.append(
            f"Друг тоже получит <b>+{ORACLE_REFERRAL_WELCOME}</b> при первом входе."
        )
    lines.extend(
        [
            "",
            f"👥 Приглашено: <b>{invited}</b>",
            f"🎟 Бонусных раскладов: <b>{credits}</b>",
            "",
            "Бонусы тратятся, когда дневной лимит в разделе исчерпан.",
            "",
            f"Твоя ссылка:\n<code>{link}</code>",
        ]
    )
    return "\n".join(lines)


def process_new_user(referred_id: int, payload: str | None) -> tuple[bool, int | None]:
    """
    Вызывается при первом /start.
    Возвращает (успех, referrer_id для уведомления).
    """
    referrer_id = parse_ref_payload(payload)
    if not referrer_id:
        return False, None
    ok = db.register_referral(referrer_id, referred_id)
    return ok, referrer_id if ok else None
