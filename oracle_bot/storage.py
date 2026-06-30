from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_default_db = Path(__file__).resolve().parents[1] / "data" / "oracle_bot.db"
DB_PATH = Path(os.getenv("ORACLE_DB_PATH", str(_default_db)))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                premium_until TEXT,
                referral_credits INTEGER NOT NULL DEFAULT 0,
                referred_by INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                module TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day, module)
            );
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                birth_date TEXT,
                zodiac TEXT,
                birth_time TEXT,
                birth_place TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS continuations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                teaser_text TEXT NOT NULL,
                locked_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                unlocked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS client_sessions (
                user_id INTEGER PRIMARY KEY,
                last_module TEXT,
                last_pain TEXT,
                last_snippet TEXT,
                last_context TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dialogues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id INTEGER PRIMARY KEY,
                referrer_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                stars INTEGER NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices (
                inv_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                cont_id INTEGER,
                amount_rub INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'robokassa',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                paid_at TEXT
            );
            CREATE TABLE IF NOT EXISTS push_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                push_type TEXT NOT NULL,
                send_after TEXT NOT NULL,
                sent_at TEXT,
                context TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_meta (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_active_at TEXT,
                last_module TEXT,
                push_opt_out INTEGER NOT NULL DEFAULT 0,
                signup_at TEXT,
                topic TEXT
            );
            CREATE TABLE IF NOT EXISTS streaks (
                user_id INTEGER PRIMARY KEY,
                streak_count INTEGER NOT NULL DEFAULT 0,
                last_day TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_events_type_created ON events(event_type, created_at);
            CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at);
            CREATE INDEX IF NOT EXISTS idx_push_due ON push_queue(send_after, sent_at);
            CREATE TABLE IF NOT EXISTS channel_post_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                variant_id TEXT,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                error TEXT,
                message_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_channel_post_due ON channel_post_queue(status, scheduled_at);
            CREATE TABLE IF NOT EXISTS app_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hvd_pending (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ultra_plus_pending (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pdf_source (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, kind)
            );
            """
        )
        for table, col in (("profiles", "birth_time"), ("profiles", "birth_place"), ("client_sessions", "last_context")):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        for col, sql in (
            ("referral_credits", "ALTER TABLE users ADD COLUMN referral_credits INTEGER NOT NULL DEFAULT 0"),
            ("referred_by", "ALTER TABLE users ADD COLUMN referred_by INTEGER"),
        ):
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE user_meta ADD COLUMN topic TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE user_meta ADD COLUMN signup_source TEXT")
        except sqlite3.OperationalError:
            pass
        for col, sql in (
            ("currency", "ALTER TABLE payments ADD COLUMN currency TEXT NOT NULL DEFAULT 'XTR'"),
            ("amount", "ALTER TABLE payments ADD COLUMN amount INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status, created_at)"
        )


def _today() -> str:
    return date.today().isoformat()


def ensure_user(user_id: int) -> bool:
    """Создаёт пользователя. True — если запись новая."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return False
        conn.execute(
            """
            INSERT INTO users (user_id, premium_until, referral_credits, referred_by, created_at)
            VALUES (?, NULL, 0, NULL, ?)
            """,
            (user_id, now),
        )
        return True


def spend_referral_credit(user_id: int) -> bool:
    """Списать 1 бонусный расклад. True если списали."""
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE users SET referral_credits = referral_credits - 1
            WHERE user_id = ? AND referral_credits > 0
            """,
            (user_id,),
        )
        return cur.rowcount > 0


def get_referral_credits(user_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT referral_credits FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return 0
    return int(row["referral_credits"] or 0)


def add_referral_credits(user_id: int, amount: int) -> None:
    """Бонусные чтения (streak, акции)."""
    if amount <= 0:
        return
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET referral_credits = referral_credits + ? WHERE user_id = ?",
            (amount, user_id),
        )


def register_referral(referrer_id: int, referred_id: int) -> bool:
    from oracle_bot.config import ORACLE_REFERRAL_BONUS, ORACLE_REFERRAL_WELCOME

    if referrer_id <= 0 or referred_id <= 0 or referrer_id == referred_id:
        return False
    ensure_user(referrer_id)
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        if conn.execute(
            "SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,)
        ).fetchone():
            return False
        try:
            conn.execute(
                """
                INSERT INTO referrals (referred_id, referrer_id, created_at)
                VALUES (?, ?, ?)
                """,
                (referred_id, referrer_id, now),
            )
        except sqlite3.IntegrityError:
            return False
        conn.execute(
            """
            UPDATE users SET referral_credits = referral_credits + ?
            WHERE user_id = ?
            """,
            (ORACLE_REFERRAL_BONUS, referrer_id),
        )
        conn.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ?",
            (referrer_id, referred_id),
        )
        if ORACLE_REFERRAL_WELCOME > 0:
            conn.execute(
                """
                UPDATE users SET referral_credits = referral_credits + ?
                WHERE user_id = ?
                """,
                (ORACLE_REFERRAL_WELCOME, referred_id),
            )
    return True


def referral_stats(user_id: int) -> dict[str, int]:
    ensure_user(user_id)
    with _connect() as conn:
        invited = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ).fetchone()[0]
        credits = conn.execute(
            "SELECT referral_credits FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return {
        "invited": int(invited or 0),
        "credits": int(credits["referral_credits"] if credits else 0),
    }


def is_premium(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT premium_until FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row or not row["premium_until"]:
        return False
    try:
        until = datetime.fromisoformat(row["premium_until"])
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)
    except ValueError:
        return False


def grant_premium(user_id: int, days: int = 30) -> None:
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, premium_until, referral_credits, referred_by, created_at)
            VALUES (?, ?, 0, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET premium_until = excluded.premium_until
            """,
            (user_id, until.isoformat(), now.isoformat()),
        )


def usage_count(user_id: int, module: str) -> int:
    d = _today()
    with _connect() as conn:
        row = conn.execute(
            "SELECT count FROM usage WHERE user_id = ? AND day = ? AND module = ?",
            (user_id, d, module),
        ).fetchone()
    return int(row["count"]) if row else 0


def total_usage_today(user_id: int) -> int:
    d = _today()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM usage WHERE user_id = ? AND day = ?",
            (user_id, d),
        ).fetchone()
    return int(row["total"]) if row else 0


def bump_usage(user_id: int, module: str, *, free_limit: int | None = None) -> None:
    from oracle_bot.config import ORACLE_FREE_PER_DAY

    limit = ORACLE_FREE_PER_DAY if free_limit is None else free_limit
    d = _today()
    with _connect() as conn:
        from oracle_bot.access import has_full_access

        if not has_full_access(user_id):
            row = conn.execute(
                "SELECT count FROM usage WHERE user_id = ? AND day = ? AND module = ?",
                (user_id, d, module),
            ).fetchone()
            count = int(row["count"]) if row else 0
            if count >= limit:
                cur = conn.execute(
                    """
                    UPDATE users SET referral_credits = referral_credits - 1
                    WHERE user_id = ? AND referral_credits > 0
                    """,
                    (user_id,),
                )
                if cur.rowcount == 0:
                    pass
        conn.execute(
            """
            INSERT INTO usage (user_id, day, module, count) VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, day, module) DO UPDATE SET count = count + 1
            """,
            (user_id, d, module),
        )


def all_user_ids() -> list[int]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT user_id FROM users
            UNION
            SELECT user_id FROM user_meta
            """
        ).fetchall()
    return sorted({int(r["user_id"]) for r in rows if r["user_id"]})


def can_use(user_id: int, module: str, free_limit: int) -> bool:
    from oracle_bot.access import has_full_access

    if has_full_access(user_id):
        return True
    if usage_count(user_id, module) < free_limit:
        return True
    return get_referral_credits(user_id) > 0


def premium_until(user_id: int) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT premium_until FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["premium_until"] if row else None


def get_profile(user_id: int) -> dict[str, Optional[str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, birth_date, zodiac, birth_time, birth_place FROM profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return {
            "name": None,
            "birth_date": None,
            "zodiac": None,
            "birth_time": None,
            "birth_place": None,
        }
    return {
        "name": row["name"],
        "birth_date": row["birth_date"],
        "zodiac": row["zodiac"],
        "birth_time": row["birth_time"],
        "birth_place": row["birth_place"],
    }


def save_profile(
    user_id: int,
    *,
    name: Optional[str] = None,
    birth_date: Optional[str] = None,
    zodiac: Optional[str] = None,
    birth_time: Optional[str] = None,
    birth_place: Optional[str] = None,
) -> None:
    cur = get_profile(user_id)
    if name is not None:
        cur["name"] = name
    if birth_date is not None:
        cur["birth_date"] = birth_date
    if zodiac is not None:
        cur["zodiac"] = zodiac
    if birth_time is not None:
        cur["birth_time"] = birth_time
    if birth_place is not None:
        cur["birth_place"] = birth_place
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profiles (user_id, name, birth_date, zodiac, birth_time, birth_place, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                birth_date = excluded.birth_date,
                zodiac = excluded.zodiac,
                birth_time = excluded.birth_time,
                birth_place = excluded.birth_place,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                cur["name"],
                cur["birth_date"],
                cur["zodiac"],
                cur["birth_time"],
                cur["birth_place"],
                now,
            ),
        )


def save_continuation(
    user_id: int,
    module: str,
    teaser_text: str,
    locked_text: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO continuations (user_id, module, teaser_text, locked_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, module, teaser_text, locked_text, now),
        )
        return int(cur.lastrowid)


def get_continuation(cont_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM continuations WHERE id = ?", (cont_id,)
        ).fetchone()
    return dict(row) if row else None


def unlock_continuation(cont_id: int, user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM continuations WHERE id = ? AND user_id = ?",
            (cont_id, user_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE continuations SET unlocked = 1 WHERE id = ?", (cont_id,)
        )
    return dict(row)


def save_session(
    user_id: int,
    *,
    module: str = "",
    pain: str = "",
    snippet: str = "",
    last_context: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cur = get_session(user_id)
    if module:
        cur["last_module"] = module
    if pain:
        cur["last_pain"] = pain
    if snippet:
        cur["last_snippet"] = snippet
    if last_context:
        cur["last_context"] = last_context
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO client_sessions (user_id, last_module, last_pain, last_snippet, last_context, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_module = excluded.last_module,
                last_pain = excluded.last_pain,
                last_snippet = excluded.last_snippet,
                last_context = excluded.last_context,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                cur.get("last_module"),
                cur.get("last_pain"),
                cur.get("last_snippet"),
                cur.get("last_context"),
                now,
            ),
        )


def get_session(user_id: int) -> dict[str, Optional[str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_module, last_pain, last_snippet, last_context FROM client_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return {
            "last_module": None,
            "last_pain": None,
            "last_snippet": None,
            "last_context": None,
        }
    return {
        "last_module": row["last_module"],
        "last_pain": row["last_pain"],
        "last_snippet": row["last_snippet"],
        "last_context": row["last_context"],
    }


def append_dialogue(user_id: int, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO dialogues (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content[:2000], now),
        )
        # храним последние 20 реплик
        conn.execute(
            """
            DELETE FROM dialogues WHERE user_id = ? AND id NOT IN (
                SELECT id FROM dialogues WHERE user_id = ? ORDER BY id DESC LIMIT 20
            )
            """,
            (user_id, user_id),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(user_id: int | None, event_type: str, payload: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (user_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_type, payload[:500], _now_iso()),
        )


def record_payment(
    user_id: int,
    kind: str,
    stars: int,
    payload: str = "",
    *,
    currency: str = "XTR",
    amount: int = 0,
) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO payments (user_id, kind, stars, payload, currency, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, kind, stars, payload[:200], currency, amount, now),
        )
    log_event(user_id, "payment", f"{kind}:{currency}:{amount or stars}")


def create_invoice(
    user_id: int,
    kind: str,
    amount_rub: int,
    *,
    cont_id: int | None = None,
    provider: str = "robokassa",
) -> int:
    """Создаёт инвойс (pending) и возвращает InvId для платёжной ссылки."""
    now = _now_iso()
    ensure_user(user_id)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO invoices (user_id, kind, cont_id, amount_rub, provider, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, kind, cont_id, amount_rub, provider, now),
        )
        return int(cur.lastrowid)


def get_invoice(inv_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE inv_id = ?", (inv_id,)).fetchone()
    return dict(row) if row else None


def mark_invoice_paid(inv_id: int) -> Optional[dict[str, Any]]:
    """Идемпотентно помечает инвойс оплаченным.

    Возвращает данные инвойса ТОЛЬКО при первом переходе pending→paid
    (чтобы не выдать доступ дважды). Если уже paid — None.
    """
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ? WHERE inv_id = ? AND status = 'pending'",
            (now, inv_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM invoices WHERE inv_id = ?", (inv_id,)).fetchone()
    return dict(row) if row else None


def touch_user(
    user_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    module: str | None = None,
) -> None:
    now = _now_iso()
    ensure_user(user_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT signup_at FROM user_meta WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE user_meta SET
                    username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_active_at = ?,
                    last_module = COALESCE(?, last_module)
                WHERE user_id = ?
                """,
                (username, first_name, now, module, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_meta (user_id, username, first_name, last_active_at, last_module, push_opt_out, signup_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (user_id, username, first_name, now, module, now),
            )


def get_user_meta(user_id: int) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM user_meta WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {}


def signups_by_source(days: int = 30) -> list[dict[str, Any]]:
    """Сколько пользователей и оплат пришло по каждому источнику (src_*).

    Источник = user_meta.signup_source (из deeplink ?start=src_<код>).
    Для атрибуции: какой канал качает трафик и кто из них платит.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    with _connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(payments)").fetchall()}
        has_rub = "currency" in cols and "amount" in cols
        rub_expr = (
            "COALESCE(SUM(CASE WHEN pay.currency = 'RUB' THEN pay.amount ELSE 0 END), 0)"
            if has_rub
            else "0"
        )
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(NULLIF(m.signup_source, ''), '(прямой/без метки)') AS source,
                COUNT(DISTINCT m.user_id) AS users,
                COUNT(DISTINCT pay.user_id) AS payers,
                {rub_expr} AS rub
            FROM user_meta m
            LEFT JOIN payments pay ON pay.user_id = m.user_id
            WHERE COALESCE(m.signup_at, '') >= ? OR m.signup_at IS NULL
            GROUP BY source
            ORDER BY users DESC
            """,
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_signup_source(user_id: int, source: str) -> None:
    src = (source or "").strip().lower()[:64]
    if not src:
        return
    ensure_user(user_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT signup_source FROM user_meta WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["signup_source"]:
            return
        if row:
            conn.execute(
                "UPDATE user_meta SET signup_source = ? WHERE user_id = ?",
                (src, user_id),
            )
        else:
            now = _now_iso()
            conn.execute(
                """
                INSERT INTO user_meta (user_id, signup_source, push_opt_out, signup_at, last_active_at)
                VALUES (?, ?, 0, ?, ?)
                """,
                (user_id, src, now, now),
            )


def schedule_push(
    user_id: int,
    push_type: str,
    delay_hours: float,
    context: str = "",
) -> None:
    if get_user_meta(user_id).get("push_opt_out"):
        return
    now = datetime.now(timezone.utc)
    send_after = (now + timedelta(hours=delay_hours)).isoformat()
    with _connect() as conn:
        pending = conn.execute(
            """
            SELECT 1 FROM push_queue
            WHERE user_id = ? AND push_type = ? AND sent_at IS NULL
            """,
            (user_id, push_type),
        ).fetchone()
        if pending:
            return
        conn.execute(
            """
            INSERT INTO push_queue (user_id, push_type, send_after, sent_at, context, created_at)
            VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (user_id, push_type, send_after, context[:500], now.isoformat()),
        )


def cancel_pushes(user_id: int, push_types: list[str] | None = None) -> None:
    with _connect() as conn:
        if push_types:
            placeholders = ",".join("?" * len(push_types))
            conn.execute(
                f"""
                UPDATE push_queue SET sent_at = ?
                WHERE user_id = ? AND push_type IN ({placeholders}) AND sent_at IS NULL
                """,
                [_now_iso(), user_id, *push_types],
            )
        else:
            conn.execute(
                """
                UPDATE push_queue SET sent_at = ?
                WHERE user_id = ? AND sent_at IS NULL
                """,
                (_now_iso(), user_id),
            )


def fetch_due_pushes(limit: int = 40) -> list[dict[str, Any]]:
    now = _now_iso()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM push_queue
            WHERE sent_at IS NULL AND send_after <= ?
            ORDER BY send_after ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_push_sent(push_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE push_queue SET sent_at = ? WHERE id = ?",
            (_now_iso(), push_id),
        )


def set_push_opt_out(user_id: int) -> None:
    now = _now_iso()
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_meta (user_id, push_opt_out, signup_at, last_active_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET push_opt_out = 1
            """,
            (user_id, now, now),
        )
        conn.execute(
            "UPDATE push_queue SET sent_at = ? WHERE user_id = ? AND sent_at IS NULL",
            (now, user_id),
        )
    log_event(user_id, "push_opt_out", "stop_push")


def analytics_snapshot() -> dict[str, Any]:
    today = _today()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    with _connect() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        new_today = conn.execute(
            "SELECT COUNT(*) FROM users WHERE substr(created_at, 1, 10) = ?", (today,)
        ).fetchone()[0]
        new_week = conn.execute(
            "SELECT COUNT(*) FROM users WHERE substr(created_at, 1, 10) >= ?", (week_ago,)
        ).fetchone()[0]
        premium_now = conn.execute(
            """
            SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL
            AND premium_until > ?
            """,
            (_now_iso(),),
        ).fetchone()[0]
        payments_total = conn.execute("SELECT COUNT(*), COALESCE(SUM(stars), 0) FROM payments").fetchone()
        pay_count = int(payments_total[0] or 0)
        stars_total = int(payments_total[1] or 0)
        rub_total = int(
            conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE currency = 'RUB'"
            ).fetchone()[0]
            or 0
        )
        rub_today = int(
            conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE currency = 'RUB' AND substr(created_at, 1, 10) = ?",
                (today,),
            ).fetchone()[0]
            or 0
        )
        pay_today = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(stars), 0) FROM payments
            WHERE substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()
        premium_pays = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE kind = 'premium_30d'"
        ).fetchone()[0]
        deep_pays = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE kind = 'deep_unlock'"
        ).fetchone()[0]
        referrals = conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
        readings_today = conn.execute(
            """
            SELECT COALESCE(SUM(count), 0) FROM usage WHERE day = ?
            """,
            (today,),
        ).fetchone()[0]
        dau = conn.execute(
            """
            SELECT COUNT(*) FROM user_meta
            WHERE substr(last_active_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        pushes_sent_week = conn.execute(
            """
            SELECT COUNT(*) FROM push_queue
            WHERE sent_at IS NOT NULL AND substr(sent_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        pushes_pending = conn.execute(
            "SELECT COUNT(*) FROM push_queue WHERE sent_at IS NULL"
        ).fetchone()[0]
        paying_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM payments"
        ).fetchone()[0]
        limit_hits_today = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'limit_hit' AND substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
        payment_intents_total = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'payment_intent'"
        ).fetchone()[0]
        payment_intents_week = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'payment_intent' AND substr(created_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        referral_prompts_week = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'referral_prompt' AND substr(created_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        referrals_week = conn.execute(
            """
            SELECT COUNT(*) FROM referrals WHERE substr(created_at, 1, 10) >= ?
            """,
            (week_ago,),
        ).fetchone()[0]
        signups_total = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'signup'"
        ).fetchone()[0]
        push_opt_out = conn.execute(
            "SELECT COUNT(*) FROM user_meta WHERE push_opt_out = 1"
        ).fetchone()[0]
        push_active = conn.execute(
            "SELECT COUNT(*) FROM user_meta WHERE push_opt_out = 0 OR push_opt_out IS NULL"
        ).fetchone()[0]
        push_opt_out_today = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'push_opt_out' AND substr(created_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]
    conv = (paying_users / total_users * 100) if total_users else 0.0
    return {
        "total_users": int(total_users),
        "new_today": int(new_today),
        "new_week": int(new_week),
        "premium_now": int(premium_now),
        "payments_count": pay_count,
        "stars_total": stars_total,
        "rub_total": rub_total,
        "rub_today": rub_today,
        "payments_today": int(pay_today[0] or 0),
        "stars_today": int(pay_today[1] or 0),
        "premium_pays": int(premium_pays),
        "deep_pays": int(deep_pays),
        "referrals": int(referrals),
        "readings_today": int(readings_today),
        "dau": int(dau),
        "pushes_sent_week": int(pushes_sent_week),
        "pushes_pending": int(pushes_pending),
        "paying_users": int(paying_users),
        "conversion_pct": round(conv, 2),
        "limit_hits_today": int(limit_hits_today),
        "payment_intents_total": int(payment_intents_total),
        "payment_intents_week": int(payment_intents_week),
        "referral_prompts_week": int(referral_prompts_week),
        "referrals_week": int(referrals_week),
        "signups_total": int(signups_total),
        "push_opt_out": int(push_opt_out),
        "push_active": int(push_active),
        "push_opt_out_today": int(push_opt_out_today),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_channel_post(
    channel: str,
    scheduled_at: str,
    kind: str,
    body: str,
    *,
    variant_id: str = "",
) -> int:
    u = channel.strip().lstrip("@")
    now = _utc_now()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO channel_post_queue (
                channel, scheduled_at, kind, variant_id, body, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (u, scheduled_at, kind, variant_id or None, body, now),
        )
        return int(cur.lastrowid)


def fetch_due_channel_posts(*, limit: int = 8) -> list[sqlite3.Row]:
    now = _utc_now()
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM channel_post_queue
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()


def mark_channel_post_sent(post_id: int, message_id: int) -> None:
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE channel_post_queue
            SET status = 'sent', sent_at = ?, message_id = ?
            WHERE id = ?
            """,
            (now, message_id, post_id),
        )


def mark_channel_post_failed(post_id: int, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE channel_post_queue
            SET status = 'failed', error = ?
            WHERE id = ?
            """,
            (error[:500], post_id),
        )


def count_channel_posts(*, status: str = "pending") -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM channel_post_queue WHERE status = ?",
            (status,),
        ).fetchone()
    return int(row[0] or 0)


def clear_pending_channel_posts_from(day_iso: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            DELETE FROM channel_post_queue
            WHERE status = 'pending' AND substr(scheduled_at, 1, 10) >= ?
            """,
            (day_iso,),
        )
        return cur.rowcount


def channel_queue_summary() -> dict[str, Any]:
    with _connect() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM channel_post_queue WHERE status = 'pending'"
        ).fetchone()[0]
        sent = conn.execute(
            "SELECT COUNT(*) FROM channel_post_queue WHERE status = 'sent'"
        ).fetchone()[0]
        promo_sent = conn.execute(
            """
            SELECT variant_id, COUNT(*) AS c FROM channel_post_queue
            WHERE status = 'sent' AND kind = 'promo'
            GROUP BY variant_id ORDER BY c DESC
            """
        ).fetchall()
    return {
        "pending": int(pending or 0),
        "sent": int(sent or 0),
        "promo_variants": {r["variant_id"]: int(r["c"]) for r in promo_sent},
    }


def kv_get(key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_kv WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def kv_set(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_kv (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, _now_iso()),
        )


def save_hvd_pending(user_id: int, name: str, birth_date: str) -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO hvd_pending (user_id, name, birth_date, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                birth_date = excluded.birth_date,
                updated_at = excluded.updated_at
            """,
            (user_id, name[:120], birth_date[:16], _now_iso()),
        )


def get_hvd_pending(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, birth_date FROM hvd_pending WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def clear_hvd_pending(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM hvd_pending WHERE user_id = ?", (user_id,))


def save_ultra_plus_pending(user_id: int, name: str, birth_date: str) -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ultra_plus_pending (user_id, name, birth_date, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                birth_date = excluded.birth_date,
                updated_at = excluded.updated_at
            """,
            (user_id, name[:120], birth_date[:16], _now_iso()),
        )


def get_ultra_plus_pending(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, birth_date FROM ultra_plus_pending WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def clear_ultra_plus_pending(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM ultra_plus_pending WHERE user_id = ?", (user_id,))


def save_pdf_source(user_id: int, kind: str, title: str, content: str) -> None:
    """Сохраняет исходный текст разбора для последующей выгрузки в PDF."""
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO pdf_source (user_id, kind, title, content, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, kind) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (user_id, kind, title[:200], content[:60000], _now_iso()),
        )


def get_pdf_source(user_id: int, kind: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT title, content FROM pdf_source WHERE user_id = ? AND kind = ?",
            (user_id, kind),
        ).fetchone()
    return dict(row) if row else None

