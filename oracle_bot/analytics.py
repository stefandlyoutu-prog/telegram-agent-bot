"""Аналитика Оракула: события, оплаты, отчёт для админа."""

from __future__ import annotations

from oracle_bot import storage as db


def track_signup(
    user_id: int,
    *,
    referred_by: int | None = None,
    source: str | None = None,
) -> None:
    parts: list[str] = []
    if referred_by:
        parts.append(f"ref={referred_by}")
    if source:
        parts.append(f"src={source}")
    db.log_event(user_id, "signup", ":".join(parts))


def track_reading(user_id: int, module: str, *, has_lock: bool = False) -> None:
    db.log_event(user_id, "reading", f"{module}:lock={int(has_lock)}")


def track_limit_hit(user_id: int, module: str) -> None:
    db.log_event(user_id, "limit_hit", module)


def track_payment(user_id: int, kind: str, stars: int, payload: str = "") -> None:
    db.record_payment(user_id, kind, stars, payload)


def track_payment_intent(user_id: int, kind: str) -> None:
    db.log_event(user_id, "payment_intent", kind)


def track_referral_prompt(user_id: int, source: str) -> None:
    db.log_event(user_id, "referral_prompt", source[:200])


def track_checkout(user_id: int, kind: str) -> None:
    db.log_event(user_id, "checkout", kind)


def track_miniapp(user_id: int, action: str, detail: str = "") -> None:
    db.log_event(user_id, "miniapp", f"{action}:{detail}"[:500])


def track_push_open(user_id: int, push_type: str) -> None:
    db.log_event(user_id, "push_open", push_type)


def track_click(user_id: int, target: str) -> None:
    db.log_event(user_id, "click", target[:500])


def funnel_snapshot() -> dict:
    """Воронка: этапы, события, гипотезы по отвалу."""
    from datetime import date, timedelta

    s = db.analytics_snapshot()
    week = (date.today() - timedelta(days=7)).isoformat()
    with db._connect() as conn:
        event_counts = {
            r[0]: r[1]
            for r in conn.execute(
                """
                SELECT event_type, COUNT(*) FROM events
                WHERE substr(created_at, 1, 10) >= ?
                GROUP BY event_type
                """,
                (week,),
            ).fetchall()
        }
        intents_week = event_counts.get("payment_intent", 0)
        checkouts_week = event_counts.get("checkout", 0)
        payments_week = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE substr(created_at, 1, 10) >= ?",
            (week,),
        ).fetchone()[0]
        miniapp_week = event_counts.get("miniapp", 0)
        readings_week = event_counts.get("reading", 0)
        limits_week = event_counts.get("limit_hit", 0)
        pushes_week = event_counts.get("push_sent", 0)
        recent = [
            dict(r)
            for r in conn.execute(
                """
                SELECT e.user_id, e.event_type, e.payload, e.created_at,
                       m.first_name, m.username
                FROM events e
                LEFT JOIN user_meta m ON m.user_id = e.user_id
                ORDER BY e.id DESC LIMIT 40
                """
            ).fetchall()
        ]
        stuck = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'limit_hit' AND substr(created_at, 1, 10) >= ?
            AND user_id NOT IN (SELECT user_id FROM payments)
            """,
            (week,),
        ).fetchone()[0]

    stages = [
        {"id": "signup", "label": "Зашли в бота", "count": s["total_users"], "hint": "Все user_id"},
        {"id": "active", "label": "Активны сегодня", "count": s["dau"], "hint": "Открывали бота"},
        {"id": "reading", "label": "Чтений сегодня", "count": s["readings_today"], "hint": "Модули таро и др."},
        {"id": "limit", "label": "Уперлись в лимит", "count": s["limit_hits_today"], "hint": "Готовы платить?"},
        {"id": "intent", "label": "Открыли счёт (7д)", "count": intents_week, "hint": "Кнопка Premium/🔓"},
        {"id": "checkout", "label": "Подтвердили оплату", "count": checkouts_week, "hint": "Pre-checkout OK"},
        {"id": "pay", "label": "Оплатили (7д)", "count": int(payments_week), "hint": "Stars зачислены"},
    ]

    insights: list[str] = []
    if s["limit_hits_today"] > 0 and intents_week == 0:
        insights.append(
            f"{s['limit_hits_today']} чел. уперлись в лимит сегодня, но никто не открыл счёт — "
            "усиль paywall или кнопку 🔓 после чтения."
        )
    if intents_week > payments_week and intents_week > 0:
        drop = intents_week - int(payments_week)
        insights.append(
            f"{drop} чел. открыли счёт, но не оплатили — возможно цена, Stars на аккаунте, "
            "или отвлеклись на шаге Telegram Pay."
        )
    if stuck > 0:
        insights.append(
            f"{stuck} чел. за неделю уперлись в лимит и так и не платили — "
            "пуш «unlock_tease» или скидка на первый раз."
        )
    if s["pushes_sent_week"] > 0 and s["dau"] < s["pushes_sent_week"] // 3:
        insights.append(
            f"Пушей {s['pushes_sent_week']}/7д, DAU {s['dau']} — часть не возвращается; "
            "проверь текст пуша и время отправки."
        )
    if not insights:
        insights.append("Мало данных — нужен трафик. Запусти канал / рекламу / рефералку.")

    return {
        "summary": s,
        "stages": stages,
        "events_7d": event_counts,
        "pushes_sent_week": s["pushes_sent_week"],
        "pushes_pending": s["pushes_pending"],
        "miniapp_actions_7d": miniapp_week,
        "readings_7d": readings_week,
        "limits_7d": limits_week,
        "recent_events": recent,
        "insights": insights,
    }


def format_stats_report() -> str:
    from oracle_bot.paywall import experiment_label, paywall_mode

    s = db.analytics_snapshot()
    mode = paywall_mode()
    mode_line = (
        f"🧪 Paywall: <b>рефералка</b> (эксперимент)\n"
        if mode == "referral"
        else "💳 Paywall: <b>Stars</b>\n"
    )
    exp = experiment_label()
    return (
        "📊 <b>Оракул — аналитика</b>\n\n"
        f"{mode_line}"
        + (exp if exp else "")
        + f"👥 Зашли в бота (всего): <b>{s['total_users']}</b> "
        f"(событий signup: {s.get('signups_total', s['total_users'])})\n"
        f"📅 +{s['new_week']} за 7д · +{s['new_today']} сегодня\n"
        f"🟢 Активных сегодня: <b>{s['dau']}</b>\n"
        f"⭐ Премиум сейчас: <b>{s['premium_now']}</b>\n\n"
        f"🔮 Чтений сегодня: <b>{s['readings_today']}</b>\n"
        f"🚫 Уперлись в лимит сегодня: <b>{s['limit_hits_today']}</b>\n\n"
        f"💰 <b>Оплатили (всего):</b> {s['payments_count']} "
        f"(премиум {s['premium_pays']} · 🔓 {s['deep_pays']}) · "
        f"<b>{s['stars_total']}⭐</b>\n"
        f"🧾 <b>Хотели оплатить:</b> открыли счёт {s.get('payment_intents_total', 0)} раз "
        f"({s.get('payment_intents_week', 0)} за 7д)\n"
        f"📈 Конверсия в оплату: <b>{s['conversion_pct']}%</b> "
        f"({s['paying_users']} из {s['total_users']})\n\n"
        f"🎁 Рефералов всего: <b>{s['referrals']}</b> "
        f"(+{s.get('referrals_week', 0)} за 7д)\n"
        f"📣 Показали «пригласи друга»: <b>{s.get('referral_prompts_week', 0)}</b> за 7д\n"
        f"📤 Пушей за 7д: <b>{s['pushes_sent_week']}</b> "
        f"(в очереди: {s['pushes_pending']})"
    )
