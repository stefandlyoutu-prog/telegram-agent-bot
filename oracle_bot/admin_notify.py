"""Уведомления админу: новый пользователь, визит в бота."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Не спамить админу: уведомлять о возврате не чаще 1 раза в сутки на пользователя
_RETURN_COOLDOWN_SEC = 86400
# Уведомлять только если пользователь не заходил N+ дней (активные /start — без пинга)
_RETURN_NOTIFY_MIN_DAYS_AWAY = int(
    __import__("os").getenv("ORACLE_ADMIN_RETURN_NOTIFY_DAYS", "7")
)
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
    from oracle_bot.user_context import format_source_block, format_stats_line, user_admin_context

    line = _user_line(user)
    ctx = user_admin_context(user_id)
    src_block = format_source_block(ctx, start_args)
    stats = format_stats_line(ctx)
    text = (
        "🆕 <b>НОВЫЙ пользователь</b> @MOracul_bot\n\n"
        f"👤 {line}\n"
        f"{src_block}\n\n"
        f"📊 {stats}"
    )
    await notify_admins(bot, text, skip_footer=True)


async def notify_return_visit(
    bot, user_id: int, user: Any, *, start_args: str | None = None
) -> None:
    if user_id in admin_ids():
        return

    from oracle_bot.user_context import user_admin_context

    ctx = user_admin_context(user_id)
    days_away = ctx.get("days_since_last", 0)

    # Обычный /start активного пользователя — только в аналитику, без SMS админу
    raw = (start_args or "").strip().lower()
    ref_deeplink = raw.startswith("ref")
    if days_away < _RETURN_NOTIFY_MIN_DAYS_AWAY and not ref_deeplink:
        from oracle_bot import analytics as analytics_mod

        analytics_mod.track_return_visit(user_id, start_args=start_args)
        return

    now = time.time()
    last = _last_return_ping.get(user_id, 0)
    if now - last < _RETURN_COOLDOWN_SEC:
        from oracle_bot import analytics as analytics_mod

        analytics_mod.track_return_visit(user_id, start_args=start_args)
        return
    _last_return_ping[user_id] = now

    from oracle_bot import analytics as analytics_mod
    from oracle_bot.user_context import (
        format_source_block,
        format_stats_line,
        format_visit_badge,
    )

    analytics_mod.track_return_visit(user_id, start_args=start_args)
    line = _user_line(user)
    badge = format_visit_badge(ctx, is_new=False)
    src = format_source_block(ctx, start_args)
    stats = format_stats_line(ctx)
    text = (
        f"{badge}\n\n"
        f"👤 {line}\n"
        f"{src}\n\n"
        f"📊 {stats}"
    )
    await notify_admins(bot, text)
