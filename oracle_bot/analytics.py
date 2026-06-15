"""Аналитика Оракула: события, оплаты, отчёт для админа."""

from __future__ import annotations

from oracle_bot import storage as db


def track_signup(user_id: int, *, referred_by: int | None = None) -> None:
    payload = f"ref={referred_by}" if referred_by else ""
    db.log_event(user_id, "signup", payload)


def track_reading(user_id: int, module: str, *, has_lock: bool = False) -> None:
    db.log_event(user_id, "reading", f"{module}:lock={int(has_lock)}")


def track_limit_hit(user_id: int, module: str) -> None:
    db.log_event(user_id, "limit_hit", module)


def track_payment(user_id: int, kind: str, stars: int, payload: str = "") -> None:
    db.record_payment(user_id, kind, stars, payload)


def format_stats_report() -> str:
    s = db.analytics_snapshot()
    return (
        "📊 <b>Оракул — аналитика</b>\n\n"
        f"👥 Пользователей: <b>{s['total_users']}</b> "
        f"(+{s['new_week']} за 7д · +{s['new_today']} сегодня)\n"
        f"🟢 Активных сегодня: <b>{s['dau']}</b>\n"
        f"⭐ Премиум сейчас: <b>{s['premium_now']}</b>\n\n"
        f"🔮 Чтений сегодня: <b>{s['readings_today']}</b>\n"
        f"🚫 Уперлись в лимит: <b>{s['limit_hits_today']}</b>\n\n"
        f"💰 Оплат всего: <b>{s['payments_count']}</b> "
        f"(премиум {s['premium_pays']} · 🔓 {s['deep_pays']})\n"
        f"⭐ Stars всего: <b>{s['stars_total']}</b>\n"
        f"💳 Сегодня: <b>{s['payments_today']}</b> оплат · "
        f"<b>{s['stars_today']}</b>⭐\n"
        f"📈 Конверсия в оплату: <b>{s['conversion_pct']}%</b> "
        f"({s['paying_users']} из {s['total_users']})\n\n"
        f"🎁 Рефералов: <b>{s['referrals']}</b>\n"
        f"📤 Пушей за 7д: <b>{s['pushes_sent_week']}</b> "
        f"(в очереди: {s['pushes_pending']})"
    )
