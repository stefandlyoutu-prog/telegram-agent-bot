"""Уведомления админу: новый пользователь, визит в бота."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Не спамить админу, если тот же человек жмёт /start каждые 5 минут
_RETURN_COOLDOWN_SEC = 3600
_last_return_ping: dict[int, float] = {}


def admin_ids() -> set[int]:
    from oracle_bot.config import ORACLE_ADMIN_IDS

    return ORACLE_ADMIN_IDS


async def notify_admins(bot, text: str, *, skip_footer: bool = False) -> None:
    ids = admin_ids()
    if not ids:
        return
    footer = ""
    if not skip_footer:
        from oracle_bot.config import ORACLE_BOT_USERNAME

        footer = (
            f"\n\n📬 @{ORACLE_BOT_USERNAME} · "
            f"<a href=\"https://moracul.onrender.com\">дашборд</a>"
        )
    for aid in ids:
        if aid <= 0:
            continue
        try:
            await bot.send_message(aid, text + footer, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.warning("admin notify %s: %s", aid, e)


def _user_line(user: Any) -> str:
    if not user:
        return "неизвестный"
    name = (user.first_name or "").strip()
    uname = f"@{user.username}" if user.username else ""
    parts = [p for p in (name, uname, f"id{user.id}") if p]
    return " · ".join(parts[:2]) if len(parts) > 1 else parts[0]


def _source_line(args: str | None) -> str:
    raw = (args or "").strip()
    if not raw:
        return "органика /start"
    if raw.lower().startswith("ref"):
        return f"реферал <code>{raw}</code>"
    if raw.startswith("mod_"):
        return f"deeplink модуль <code>{raw[4:]}</code>"
    return f"источник <code>{raw[:80]}</code>"


async def notify_new_user(bot, user_id: int, user: Any, *, start_args: str | None = None) -> None:
    from oracle_bot.analytics import format_stats_report

    line = _user_line(user)
    src = _source_line(start_args)
    text = (
        "🆕 <b>Новый в @MOracul_bot</b>\n\n"
        f"👤 {line}\n"
        f"📍 {src}\n\n"
        + format_stats_report()
    )
    await notify_admins(bot, text, skip_footer=True)


async def notify_return_visit(bot, user_id: int, user: Any) -> None:
    if user_id in admin_ids():
        return
    now = time.time()
    last = _last_return_ping.get(user_id, 0)
    if now - last < _RETURN_COOLDOWN_SEC:
        return
    _last_return_ping[user_id] = now
    line = _user_line(user)
    text = f"↩️ <b>Снова в боте</b>\n👤 {line}"
    await notify_admins(bot, text)
