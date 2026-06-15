"""Серия дней подряд — бонус за активность."""

from __future__ import annotations

from datetime import date, timedelta

from oracle_bot import storage as db

_STREAK_BONUS_EVERY = 3  # каждые 3 дня +1 кредит


def record_visit(user_id: int) -> dict[str, int]:
    """Вызывается при активности. Возвращает {streak, bonus_granted}."""
    today = date.today().isoformat()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT streak_count, last_day FROM streaks WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO streaks (user_id, streak_count, last_day) VALUES (?, 1, ?)",
                (user_id, today),
            )
            return {"streak": 1, "bonus_granted": 0}

        last = row["last_day"]
        count = int(row["streak_count"] or 0)
        if last == today:
            return {"streak": count, "bonus_granted": 0}

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last == yesterday:
            count += 1
        else:
            count = 1

        bonus = 0
        if count > 0 and count % _STREAK_BONUS_EVERY == 0:
            db.add_referral_credits(user_id, 1)
            bonus = 1

        conn.execute(
            "UPDATE streaks SET streak_count = ?, last_day = ? WHERE user_id = ?",
            (count, today, user_id),
        )
        return {"streak": count, "bonus_granted": bonus}


def get_streak(user_id: int) -> int:
    with db._connect() as conn:
        row = conn.execute(
            "SELECT streak_count, last_day FROM streaks WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return 0
    if row["last_day"] != date.today().isoformat():
        last = row["last_day"]
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last != yesterday:
            return 0
    return int(row["streak_count"] or 0)
