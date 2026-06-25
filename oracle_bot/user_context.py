"""Контекст пользователя для админ-уведомлений."""

from __future__ import annotations

from datetime import date, datetime, timezone

from oracle_bot import storage as db


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def user_admin_context(user_id: int) -> dict:
    """Сводка: новый/старый, источник, реферал, активность."""
    meta = db.get_user_meta(user_id)
    with db._connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        ref_row = conn.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,)
        ).fetchone()
        visits = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE user_id = ? AND event_type = 'return_visit'
            """,
            (user_id,),
        ).fetchone()[0]
        readings = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM usage WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    created = _parse_iso(dict(user)["created_at"] if user else None) or _parse_iso(
        meta.get("signup_at")
    )
    last = _parse_iso(meta.get("last_active_at"))
    now = datetime.now(timezone.utc)
    days_since = (now - created).days if created else 0
    days_away = (now - last).days if last else 0

    ref_id = int(ref_row["referrer_id"]) if ref_row else None
    ref_meta = db.get_user_meta(ref_id) if ref_id else {}
    ref_label = ""
    if ref_id:
        un = ref_meta.get("username")
        ref_label = f"@{un}" if un else f"id{ref_id}"

    src = (meta.get("signup_source") or "").strip()
    source_label = src if src else "органика"

    return {
        "user_id": user_id,
        "signup_source": source_label,
        "referred_by": ref_id,
        "referrer_label": ref_label,
        "days_since_signup": days_since,
        "days_since_last": days_away,
        "return_visits": int(visits),
        "readings_total": int(readings or 0),
        "payments_count": int(paid or 0),
        "is_premium": bool(user and dict(user).get("premium_until")),
        "last_module": meta.get("last_module") or "—",
    }


def format_visit_badge(ctx: dict, *, is_new: bool) -> str:
    if is_new:
        return "🆕 <b>ПЕРВЫЙ ВХОД</b>"
    if ctx["days_since_last"] >= 7:
        return f"💤 <b>ВЕРНУЛСЯ</b> (не был {ctx['days_since_last']} дн.)"
    if ctx["return_visits"] <= 1:
        return "↩️ <b>Повторный визит</b>"
    return f"↩️ <b>Снова в боте</b> (#{ctx['return_visits'] + 1})"


def format_source_block(ctx: dict, start_args: str | None = None) -> str:
    lines = []
    raw = (start_args or "").strip()
    if raw.lower().startswith("ref"):
        lines.append(f"👥 <b>Реферал</b> от {ctx['referrer_label'] or raw}")
    elif ctx["referrer_label"]:
        lines.append(f"👥 Пришёл по рефералке от {ctx['referrer_label']}")
    if raw.lower().startswith("src_"):
        lines.append(f"📣 Источник: <code>{raw[4:]}</code>")
    elif ctx["signup_source"] and ctx["signup_source"] != "органика":
        lines.append(f"📣 Источник: <code>{ctx['signup_source']}</code>")
    elif not lines:
        lines.append("📍 Органика /start")
    if raw.startswith("mod_"):
        lines.append(f"🔗 Deeplink: <code>{raw[4:]}</code>")
    return "\n".join(lines)


def format_stats_line(ctx: dict) -> str:
    parts = [
        f"с нами {ctx['days_since_signup']} дн.",
        f"чтений: {ctx['readings_total']}",
    ]
    if ctx["payments_count"]:
        parts.append(f"оплат: {ctx['payments_count']}")
    parts.append(f"модуль: {ctx['last_module']}")
    return " · ".join(parts)
