"""Аналитика Оракула: события, оплаты, отчёт для админа."""

from __future__ import annotations

from oracle_bot import storage as db


def track_return_visit(user_id: int, *, start_args: str | None = None) -> None:
    payload = (start_args or "")[:120]
    db.log_event(user_id, "return_visit", payload)


def track_push_open(user_id: int, push_type: str) -> None:
    db.log_event(user_id, "push_open", push_type)


def daily_metrics() -> dict:
    """Метрики за сегодня и вчера для ежедневного отчёта."""
    from datetime import date, timedelta

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    s = db.analytics_snapshot()
    with db._connect() as conn:
        new_yesterday = conn.execute(
            "SELECT COUNT(*) FROM users WHERE substr(created_at, 1, 10) = ?", (yesterday,)
        ).fetchone()[0]
        returning_today = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'return_visit' AND substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        returning_week = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'return_visit' AND substr(created_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        push_opens_today = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'push_open' AND substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        push_sent_today = conn.execute(
            """
            SELECT COUNT(*) FROM push_queue
            WHERE sent_at IS NOT NULL AND substr(sent_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        sources = conn.execute(
            """
            SELECT COALESCE(NULLIF(signup_source, ''), 'органика') AS src, COUNT(*) AS c
            FROM user_meta
            GROUP BY src ORDER BY c DESC LIMIT 8
            """
        ).fetchall()
        ref_total = conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
        ref_today = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE substr(created_at, 1, 10) = ?", (today,)
        ).fetchone()[0]
        ref_week = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE substr(created_at, 1, 10) >= ?", (week_ago,)
        ).fetchone()[0]
        ref_prompts_today = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'referral_prompt' AND substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        ref_prompts_week = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'referral_prompt' AND substr(created_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        top_referrers = conn.execute(
            """
            SELECT r.referrer_id,
                   COUNT(*) AS cnt,
                   COALESCE(m.username, '') AS username
            FROM referrals r
            LEFT JOIN user_meta m ON m.user_id = r.referrer_id
            GROUP BY r.referrer_id
            ORDER BY cnt DESC
            LIMIT 5
            """
        ).fetchall()
    return {
        **s,
        "new_yesterday": int(new_yesterday),
        "returning_today": int(returning_today),
        "returning_week": int(returning_week),
        "push_opens_today": int(push_opens_today),
        "push_sent_today": int(push_sent_today),
        "sources": [{"source": r[0], "count": int(r[1])} for r in sources],
        "referrals_total": int(ref_total),
        "referrals_today": int(ref_today),
        "referrals_week": int(ref_week),
        "referral_prompts_today": int(ref_prompts_today),
        "referral_prompts_week": int(ref_prompts_week),
        "top_referrers": [
            {
                "id": int(r[0]),
                "count": int(r[1]),
                "username": (r[2] or "").strip(),
            }
            for r in top_referrers
        ],
    }


def format_daily_report() -> str:
    """Ежедневный отчёт для Telegram админу."""
    from datetime import date

    m = daily_metrics()
    src_lines = "\n".join(
        f"  • {r['source']}: {r['count']}" for r in (m.get("sources") or [])[:6]
    ) or "  • пока нет данных"
    ref_top = m.get("top_referrers") or []
    ref_top_lines = "\n".join(
        (
            f"  • @{r['username']}: {r['count']} друзей"
            if r.get("username")
            else f"  • id{r['id']}: {r['count']} друзей"
        )
        for r in ref_top[:5]
    ) or "  • пока никто не привёл"
    return (
        f"📅 <b>Оракул — отчёт за {date.today().strftime('%d.%m.%Y')}</b>\n\n"
        f"👥 <b>Пользователи</b>\n"
        f"  Всего: <b>{m['total_users']}</b>\n"
        f"  🆕 Новых сегодня: <b>{m['new_today']}</b> (вчера: {m['new_yesterday']})\n"
        f"  ↩️ Вернулось сегодня: <b>{m['returning_today']}</b>\n"
        f"  🟢 Активных сегодня (DAU): <b>{m['dau']}</b>\n"
        f"  ↩️ Возвраты за 7д: {m['returning_week']}\n\n"
        f"🎁 <b>Приведи друга</b>\n"
        f"  Рефералов всего: <b>{m['referrals_total']}</b>\n"
        f"  Сегодня: +<b>{m['referrals_today']}</b> · за 7д: +{m.get('referrals_week', 0)}\n"
        f"  Показали кнопку «пригласи»: {m.get('referral_prompts_today', 0)} сегодня, "
        f"{m.get('referral_prompts_week', 0)} за 7д\n"
        f"  <b>Топ приглашающих:</b>\n{ref_top_lines}\n\n"
        f"📣 <b>Источники (все время)</b>\n{src_lines}\n\n"
        f"🔮 Чтений сегодня: <b>{m['readings_today']}</b>\n"
        f"🚫 Лимит сегодня: {m['limit_hits_today']}\n"
        f"💰 Оплат сегодня: {m['payments_today']} ({m['stars_today']}⭐)\n"
        f"⭐ Премиум сейчас: {m['premium_now']}\n\n"
        f"📤 <b>Пуши</b>\n"
        f"  Отправлено сегодня: {m['push_sent_today']}\n"
        f"  Открыли (клик): {m['push_opens_today']}\n"
        f"  В очереди: {m['pushes_pending']}\n"
        f"  За 7д: {m['pushes_sent_week']}\n\n"
        f"🔔 <b>Подписка на пуши</b>\n"
        f"  ✅ Активны: <b>{m['push_active']}</b>\n"
        f"  🔕 Отключили (/stop_push): <b>{m['push_opt_out']}</b>\n"
        f"  Сегодня отключили: {m.get('push_opt_out_today', 0)}\n\n"
        f"📈 Конверсия: {m['conversion_pct']}% · /stats · /funnel"
    )


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
        {
            "id": "ref_prompt",
            "label": "Увидели «пригласи» (7д)",
            "count": event_counts.get("referral_prompt", 0),
            "hint": "Paywall рефералка",
        },
        {
            "id": "ref_join",
            "label": "Новых рефералов (7д)",
            "count": s.get("referrals_week", 0),
            "hint": "Друзья по ссылке ref",
        },
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


def format_funnel_report() -> str:
    """Воронка для /funnel — как CRM."""
    f = funnel_snapshot()
    s = f["summary"]
    lines = ["🎯 <b>Оракул — воронка (CRM)</b>\n"]
    prev = max(s["total_users"], 1)
    for st in f["stages"]:
        cnt = st["count"]
        pct = int(100 * cnt / prev) if prev else 0
        bar = "█" * min(12, pct // 8) + "░" * max(0, 12 - pct // 8)
        lines.append(f"{st['label']}: <b>{cnt}</b> {bar} {pct}%")
        lines.append(f"  <i>{st['hint']}</i>")
        if cnt > 0:
            prev = cnt
    lines.append("\n🎁 <b>Рефералка</b>")
    lines.append(f"  Всего приглашений: {s.get('referrals', 0)} (+{s.get('referrals_week', 0)} / 7д)")
    lines.append(f"  Показов кнопки: {s.get('referral_prompts_week', 0)} / 7д")
    lines.append("\n💡 <b>Гипотезы</b>")
    for ins in f["insights"][:4]:
        lines.append(f"  • {ins}")
    return "\n".join(lines)


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
        f"💵 <b>Рубли (Робокасса):</b> {s.get('rub_total', 0)}₽ всего · "
        f"{s.get('rub_today', 0)}₽ сегодня\n"
        f"🧾 <b>Хотели оплатить:</b> открыли счёт {s.get('payment_intents_total', 0)} раз "
        f"({s.get('payment_intents_week', 0)} за 7д)\n"
        f"📈 Конверсия в оплату: <b>{s['conversion_pct']}%</b> "
        f"({s['paying_users']} из {s['total_users']})\n\n"
        f"🎁 Рефералов всего: <b>{s['referrals']}</b> "
        f"(+{s.get('referrals_week', 0)} за 7д)\n"
        f"📣 Показали «пригласи друга»: <b>{s.get('referral_prompts_week', 0)}</b> за 7д\n"
        f"📤 Пушей за 7д: <b>{s['pushes_sent_week']}</b> "
        f"(в очереди: {s['pushes_pending']})\n"
        f"🔔 Пуши: ✅ <b>{s.get('push_active', 0)}</b> · "
        f"🔕 отключили: <b>{s.get('push_opt_out', 0)}</b>"
    )
