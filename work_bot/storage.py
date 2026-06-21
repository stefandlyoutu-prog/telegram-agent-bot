from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from work_bot.config import WORK_DB_PATH


def _connect() -> sqlite3.Connection:
    WORK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WORK_DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workers (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance_rub REAL NOT NULL DEFAULT 0,
                total_earned_rub REAL NOT NULL DEFAULT 0,
                total_withdrawn_rub REAL NOT NULL DEFAULT 0,
                approved_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                mode TEXT,
                push_opt_out INTEGER NOT NULL DEFAULT 0,
                blocked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_active_at TEXT
            );
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                proof_text TEXT,
                proof_file_id TEXT,
                reward_rub REAL NOT NULL DEFAULT 0,
                submitted_at TEXT,
                reviewed_at TEXT,
                admin_note TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_rub REAL NOT NULL,
                payment_details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                processed_at TEXT
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
            CREATE INDEX IF NOT EXISTS idx_assign_user ON assignments(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_withdraw_pending ON withdrawals(status);
            CREATE INDEX IF NOT EXISTS idx_push_due ON push_queue(send_after, sent_at);
            """
        )


def ensure_worker(user_id: int, *, username: str = "", first_name: str = "") -> bool:
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM workers WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE workers SET username = COALESCE(NULLIF(?, ''), username),
                    first_name = COALESCE(NULLIF(?, ''), first_name),
                    last_active_at = ?
                WHERE user_id = ?
                """,
                (username, first_name, now, user_id),
            )
            return False
        conn.execute(
            """
            INSERT INTO workers (user_id, username, first_name, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username or None, first_name or None, now, now),
        )
        return True


def get_worker(user_id: int) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {}


def set_mode(user_id: int, mode: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE workers SET mode = ? WHERE user_id = ?", (mode, user_id))


def active_assignment(user_id: int, task_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM assignments
            WHERE user_id = ? AND task_id = ? AND status IN ('active', 'submitted')
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, task_id),
        ).fetchone()
    return dict(row) if row else None


def create_assignment(user_id: int, task_id: str, reward_rub: float) -> int:
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO assignments (user_id, task_id, status, reward_rub, created_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (user_id, task_id, reward_rub, now),
        )
        return int(cur.lastrowid)


def submit_assignment(assignment_id: int, *, proof_text: str, proof_file_id: str) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE assignments
            SET status = 'submitted', proof_text = ?, proof_file_id = ?,
                submitted_at = ?
            WHERE id = ?
            """,
            (proof_text[:2000], proof_file_id, now, assignment_id),
        )


def get_assignment(assignment_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    return dict(row) if row else None


def approve_assignment(assignment_id: int, *, note: str = "") -> Optional[dict[str, Any]]:
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        if not row or row["status"] != "submitted":
            return None
        uid = int(row["user_id"])
        reward = float(row["reward_rub"])
        conn.execute(
            """
            UPDATE assignments
            SET status = 'approved', reviewed_at = ?, admin_note = ?
            WHERE id = ?
            """,
            (now, note[:500], assignment_id),
        )
        conn.execute(
            """
            UPDATE workers
            SET balance_rub = balance_rub + ?,
                total_earned_rub = total_earned_rub + ?,
                approved_count = approved_count + 1
            WHERE user_id = ?
            """,
            (reward, reward, uid),
        )
        out = dict(row)
        out["status"] = "approved"
        return out


def reject_assignment(assignment_id: int, *, note: str = "") -> Optional[dict[str, Any]]:
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        if not row or row["status"] != "submitted":
            return None
        uid = int(row["user_id"])
        conn.execute(
            """
            UPDATE assignments
            SET status = 'rejected', reviewed_at = ?, admin_note = ?
            WHERE id = ?
            """,
            (now, note[:500], assignment_id),
        )
        conn.execute(
            "UPDATE workers SET rejected_count = rejected_count + 1 WHERE user_id = ?",
            (uid,),
        )
        return dict(row)


def user_assignments(user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM assignments WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def create_withdrawal(user_id: int, amount: float, details: str) -> int:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE workers SET balance_rub = balance_rub - ? WHERE user_id = ? AND balance_rub >= ?",
            (amount, user_id, amount),
        )
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            raise ValueError("insufficient_balance")
        cur = conn.execute(
            """
            INSERT INTO withdrawals (user_id, amount_rub, payment_details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, amount, details[:3000], now),
        )
        conn.execute(
            "UPDATE workers SET total_withdrawn_rub = total_withdrawn_rub + ? WHERE user_id = ?",
            (amount, user_id),
        )
        return int(cur.lastrowid)


def get_withdrawal(wid: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
    return dict(row) if row else None


def schedule_push(user_id: int, push_type: str, delay_hours: float, context: str = "{}") -> None:
    send_after = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO push_queue (user_id, push_type, send_after, context, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, push_type, send_after, context, _now()),
        )


def fetch_due_pushes() -> list[sqlite3.Row]:
    now = _now()
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM push_queue
            WHERE sent_at IS NULL AND send_after <= ?
            ORDER BY send_after LIMIT 30
            """,
            (now,),
        ).fetchall()


def mark_push_sent(push_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE push_queue SET sent_at = ? WHERE id = ?",
            (_now(), push_id),
        )


def set_push_opt_out(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE workers SET push_opt_out = 1 WHERE user_id = ?", (user_id,))


def admin_stats() -> dict[str, Any]:
    with _connect() as conn:
        workers = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
        pending_review = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE status = 'submitted'"
        ).fetchone()[0]
        pending_withdraw = conn.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'"
        ).fetchone()[0]
        balance_total = conn.execute(
            "SELECT COALESCE(SUM(balance_rub), 0) FROM workers"
        ).fetchone()[0]
    return {
        "workers": int(workers),
        "pending_review": int(pending_review),
        "pending_withdraw": int(pending_withdraw),
        "balance_total": float(balance_total or 0),
    }
