"""SQLite-хранилище VPN-бота: пользователи, инвойсы, подписки на VPN-ключ."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from vpn_bot.config import VPN_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    marzban_username TEXT UNIQUE,
    trial_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_active_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    inv_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tariff_id TEXT NOT NULL,
    days INTEGER NOT NULL,
    amount_rub INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'robokassa',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    paid_at TEXT
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY,
    marzban_username TEXT NOT NULL,
    plan TEXT,
    expires_at TEXT,
    updated_at TEXT NOT NULL
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active_at);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dir() -> None:
    Path(VPN_DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _ensure_dir()
    conn = sqlite3.connect(VPN_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def marzban_username_for(user_id: int) -> str:
    return f"tg{user_id}"


def ensure_user(
    user_id: int, *, username: str | None = None, first_name: str | None = None
) -> dict[str, Any]:
    now = _now_iso()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, marzban_username,
                                    trial_used, created_at, last_active_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (user_id, username, first_name, marzban_username_for(user_id), now, now),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ?, last_active_at = ? WHERE user_id = ?",
                (username or row["username"], first_name or row["first_name"], now, user_id),
            )
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row)


def get_user(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def mark_trial_used(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET trial_used = 1 WHERE user_id = ?", (user_id,))


def create_invoice(user_id: int, tariff_id: str, days: int, amount_rub: int) -> int:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO invoices (user_id, tariff_id, days, amount_rub, provider, status, created_at)
            VALUES (?, ?, ?, ?, 'robokassa', 'pending', ?)
            """,
            (user_id, tariff_id, days, amount_rub, now),
        )
        return int(cur.lastrowid)


def get_invoice(inv_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE inv_id = ?", (inv_id,)).fetchone()
    return dict(row) if row else None


def mark_invoice_paid(inv_id: int) -> Optional[dict[str, Any]]:
    """Идемпотентно помечает инвойс оплаченным (pending → paid один раз)."""
    now = _now_iso()
    with _connect() as conn:
        # Используем эксклюзивную транзакцию для защиты от race condition
        conn.execute("BEGIN EXCLUSIVE TRANSACTION")
        try:
            cur = conn.execute(
                "UPDATE invoices SET status = 'paid', paid_at = ? WHERE inv_id = ? AND status = 'pending'",
                (now, inv_id),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                return None
            row = conn.execute("SELECT * FROM invoices WHERE inv_id = ?", (inv_id,)).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return dict(row) if row else None


def upsert_subscription(
    user_id: int, *, marzban_username: str, plan: str | None, expires_at: str | None
) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO subscriptions (user_id, marzban_username, plan, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                marzban_username = excluded.marzban_username,
                plan = excluded.plan,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            (user_id, marzban_username, plan, expires_at, now),
        )


def get_subscription(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def stats() -> dict[str, Any]:
    with _connect() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        paid_invoices = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM invoices WHERE status = 'paid'"
        ).fetchone()
        active_subs = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE expires_at IS NOT NULL AND expires_at > ?",
            (_now_iso(),),
        ).fetchone()[0]
    return {
        "users": users,
        "paid_invoices": paid_invoices[0],
        "revenue_rub": paid_invoices[1],
        "active_subscriptions": active_subs,
    }
