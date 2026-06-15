"""SQLite-хранилище идей, метрик, планов и отчётов."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from business_dashboard.channels import channel_for, expected_daily_for
from business_dashboard.registry import SEED_IDEAS

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "business_dashboard.db"

_IDEA_COLUMNS = (
    "slug", "title", "category", "cluster", "tier", "channel", "status",
    "action_required", "potential_rub", "automation_pct", "expected_daily_rub",
    "revenue_today", "revenue_month", "note", "last_event_at", "created_at", "updated_at",
)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _today_str() -> str:
    return date.today().isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _month_prefix() -> str:
    return date.today().strftime("%Y-%m")


def actual_revenue_month() -> float:
    mp = _month_prefix()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS s FROM revenue_events
            WHERE substr(created_at, 1, 7) = ?
            """,
            (mp,),
        ).fetchone()
    return float(row["s"] or 0)


def sync_idea_revenue_from_events(conn: sqlite3.Connection) -> None:
    """Синхронизирует revenue_today / revenue_month из revenue_events."""
    d = _today_str()
    mp = _month_prefix()
    slugs = [r[0] for r in conn.execute("SELECT slug FROM ideas").fetchall()]
    for slug in slugs:
        today = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM revenue_events
            WHERE slug = ? AND substr(created_at, 1, 10) = ?
            """,
            (slug, d),
        ).fetchone()[0]
        month = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM revenue_events
            WHERE slug = ? AND substr(created_at, 1, 7) = ?
            """,
            (slug, mp),
        ).fetchone()[0]
        conn.execute(
            "UPDATE ideas SET revenue_today = ?, revenue_month = ? WHERE slug = ?",
            (today, month, slug),
        )


def rollover_periods() -> None:
    """Смена дня/месяца: синхронизация доходов из событий."""
    d = _today_str()
    mp = _month_prefix()
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        last_day = conn.execute(
            "SELECT value FROM system_meta WHERE key = 'last_day'"
        ).fetchone()
        last_month = conn.execute(
            "SELECT value FROM system_meta WHERE key = 'last_month'"
        ).fetchone()
        prev_day = last_day["value"] if last_day else ""
        prev_month = last_month["value"] if last_month else ""

        if prev_day and prev_day != d:
            sync_idea_revenue_from_events(conn)
        if prev_month and prev_month != mp:
            sync_idea_revenue_from_events(conn)

        sync_idea_revenue_from_events(conn)
        conn.execute(
            "INSERT INTO system_meta (key, value) VALUES ('last_day', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (d,),
        )
        conn.execute(
            "INSERT INTO system_meta (key, value) VALUES ('last_month', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (mp,),
        )


def rollover_day_if_needed() -> None:
    rollover_periods()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ideas)").fetchall()}
    for col, typedef in (
        ("cluster", "TEXT DEFAULT ''"),
        ("tier", "TEXT DEFAULT 'strong'"),
        ("channel", "TEXT DEFAULT 'online'"),
        ("expected_daily_rub", "REAL DEFAULT 0"),
        ("priority", "INTEGER DEFAULT 50"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE ideas ADD COLUMN {col} {typedef}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_date TEXT NOT NULL,
            slug TEXT NOT NULL,
            expected_rub REAL DEFAULT 0,
            promotion TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(plan_date, slug),
            FOREIGN KEY (slug) REFERENCES ideas(slug)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_date TEXT PRIMARY KEY,
            expected_total REAL DEFAULT 0,
            actual_total REAL DEFAULT 0,
            gap_rub REAL DEFAULT 0,
            gap_reason TEXT DEFAULT '',
            suggestions TEXT DEFAULT '',
            next_actions TEXT DEFAULT '',
            plan_json TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_history (
            hist_date TEXT PRIMARY KEY,
            expected_total REAL DEFAULT 0,
            actual_total REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            blocker_type TEXT DEFAULT 'other',
            description TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            done_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_assets (
            asset_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            hint TEXT DEFAULT '',
            done INTEGER DEFAULT 0,
            done_at TEXT,
            note TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            slug TEXT PRIMARY KEY,
            query_text TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            volume_score INTEGER DEFAULT 0,
            monetization_score INTEGER DEFAULT 0,
            solution_type TEXT DEFAULT 'bot',
            proposal TEXT DEFAULT '',
            pipeline_stage TEXT DEFAULT 'scout',
            expected_daily_rub REAL DEFAULT 0,
            linked_idea_slug TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _seed_row(idea: Dict[str, Any], now: str) -> tuple:
    slug = idea["slug"]
    return (
        slug,
        idea["title"],
        idea["category"],
        idea.get("cluster", ""),
        idea.get("tier", "strong"),
        idea.get("channel", channel_for(slug)),
        idea.get("status", "needs_action"),
        idea.get("action_required", ""),
        idea.get("potential_rub", ""),
        idea.get("automation_pct", 0),
        float(idea.get("expected_daily_rub", expected_daily_for(slug))),
        float(idea.get("revenue_today", 0)),
        float(idea.get("revenue_month", 0)),
        idea.get("note", ""),
        now if idea.get("status") == "running" else None,
        now,
        now,
    )


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'needs_action',
                action_required TEXT DEFAULT '',
                potential_rub TEXT DEFAULT '',
                automation_pct INTEGER DEFAULT 0,
                revenue_today REAL DEFAULT 0,
                revenue_month REAL DEFAULT 0,
                note TEXT DEFAULT '',
                last_event_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS revenue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                amount REAL NOT NULL,
                source TEXT DEFAULT 'manual',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (slug) REFERENCES ideas(slug)
            )
            """
        )
        _migrate(conn)
        existing = {r[0] for r in conn.execute("SELECT slug FROM ideas").fetchall()}
        now = _now_iso()
        for idea in SEED_IDEAS:
            if idea["slug"] not in existing:
                placeholders = ", ".join("?" * len(_IDEA_COLUMNS))
                conn.execute(
                    f"INSERT INTO ideas ({', '.join(_IDEA_COLUMNS)}) VALUES ({placeholders})",
                    _seed_row(idea, now),
                )
        _init_user_assets(conn)
        from telegram_channels.storage import init_tg_channels

        init_tg_channels(conn)
        from business_dashboard.idea_scout import init_opportunities
        init_opportunities(conn)


def _init_user_assets(conn: sqlite3.Connection) -> None:
    from business_dashboard.user_assets import ASSET_CATALOG

    for a in ASSET_CATALOG:
        conn.execute(
            """
            INSERT INTO user_assets (asset_key, label, hint, done, done_at, note)
            VALUES (?, ?, ?, 0, NULL, '')
            ON CONFLICT(asset_key) DO UPDATE SET label = excluded.label, hint = excluded.hint
            """,
            (a["key"], a["label"], a.get("hint", "")),
        )
    """Deprecated — блокеры создаются при добавлении в план на сегодня."""
    pass


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def actual_revenue_today() -> float:
    d = _today_str()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS s FROM revenue_events
            WHERE substr(created_at, 1, 10) = ?
            """,
            (d,),
        ).fetchone()
    return float(row["s"] or 0)


def list_ideas(channel: Optional[str] = None) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if channel and channel != "all":
            rows = conn.execute(
                "SELECT * FROM ideas WHERE channel = ? ORDER BY priority DESC, title",
                (channel,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ideas ORDER BY priority DESC, category, title"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_done_asset_keys() -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT asset_key FROM user_assets WHERE done = 1").fetchall()
    return {r["asset_key"] for r in rows}


def list_user_assets() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM user_assets ORDER BY label").fetchall()
    return [_row_to_dict(r) for r in rows]


def set_user_asset(asset_key: str, done: bool = True, note: str = "") -> Optional[Dict[str, Any]]:
    from business_dashboard.user_assets import ASSET_CATALOG

    catalog = {a["key"]: a for a in ASSET_CATALOG}
    if asset_key not in catalog:
        return None
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_assets (asset_key, label, hint, done, done_at, note)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_key) DO UPDATE SET
                done = excluded.done,
                done_at = excluded.done_at,
                note = excluded.note
            """,
            (
                asset_key,
                catalog[asset_key]["label"],
                catalog[asset_key].get("hint", ""),
                1 if done else 0,
                now if done else None,
                note,
            ),
        )
        _auto_complete_blockers_for_asset(conn, asset_key)
        row = conn.execute("SELECT * FROM user_assets WHERE asset_key = ?", (asset_key,)).fetchone()
    return _row_to_dict(row) if row else None


def _auto_complete_blockers_for_asset(conn: sqlite3.Connection, asset_key: str) -> None:
    from business_dashboard.user_assets import IDEA_ASSET_REQUIRES

    done = {r[0] for r in conn.execute("SELECT asset_key FROM user_assets WHERE done = 1").fetchall()}
    now = _now_iso()
    for slug, required in IDEA_ASSET_REQUIRES.items():
        if asset_key not in required:
            continue
        if not all(r in done for r in required):
            continue
        conn.execute(
            """
            UPDATE user_blockers SET done = 1, done_at = ?
            WHERE slug = ? AND done = 0 AND blocker_type = 'setup'
            """,
            (now, slug),
        )


def enrich_idea(idea: Dict[str, Any], done_keys: set[str]) -> Dict[str, Any]:
    from business_dashboard.user_assets import assets_for_idea, effective_action_required, missing_assets

    slug = idea["slug"]
    out = dict(idea)
    out["required_assets"] = assets_for_idea(slug)
    out["missing_assets"] = [m["key"] for m in missing_assets(slug, done_keys)]
    out["effective_action"] = effective_action_required(slug, idea.get("action_required") or "", done_keys)
    out["user_needed"] = len(out["missing_assets"]) > 0
    return out


def list_blockers(open_only: bool = True) -> List[Dict[str, Any]]:
    with _connect() as conn:
        q = "SELECT b.*, i.title FROM user_blockers b LEFT JOIN ideas i ON i.slug = b.slug"
        if open_only:
            q += " WHERE b.done = 0"
        q += " ORDER BY b.id DESC"
        rows = conn.execute(q).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_blocker(description: str, slug: str = "", blocker_type: str = "other") -> Dict[str, Any]:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO user_blockers (slug, blocker_type, description, done, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            (slug or None, blocker_type, description, now),
        )
        row = conn.execute("SELECT * FROM user_blockers WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


def complete_blocker(blocker_id: int) -> Optional[Dict[str, Any]]:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "UPDATE user_blockers SET done = 1, done_at = ? WHERE id = ?",
            (now, blocker_id),
        )
        row = conn.execute("SELECT * FROM user_blockers WHERE id = ?", (blocker_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_dashboard(channel: Optional[str] = None) -> Dict[str, Any]:
    from business_dashboard.daily import get_money_metrics, get_report, get_today_plan
    from business_dashboard.idea_scout import get_pipeline_summary, list_opportunities

    from telegram_channels.storage import list_tg_channels

    done_keys = get_done_asset_keys()
    raw_ideas = list_ideas(channel if channel and channel != "all" else None)
    ideas = [enrich_idea(i, done_keys) for i in raw_ideas]

    connected = [i for i in ideas if i["status"] in ("connected", "running")]
    running = [i for i in ideas if i["status"] == "running"]
    needs_action = [i for i in ideas if i["status"] == "needs_action"]
    online = [i for i in ideas if i.get("channel") == "online"]
    physical = [i for i in ideas if i.get("channel") == "physical"]
    user_only = [i for i in needs_action if i.get("user_needed")]

    metrics = get_money_metrics()
    opps = list_opportunities()

    return {
        "connected": connected,
        "running": running,
        "needs_action": needs_action,
        "needs_user_only": user_only,
        "all": ideas,
        "online": online,
        "physical": physical,
        "today_plan": get_today_plan(),
        "blockers": list_blockers(open_only=True),
        "user_assets": list_user_assets(),
        "assets_done_count": len(done_keys),
        "opportunities": opps,
        "tg_channels": list_tg_channels(),
        "pipeline": get_pipeline_summary(),
        "metrics": metrics,
        "report_today": get_report(_today_str()),
        "totals": {
            "revenue_today": metrics["actual_today"],
            "revenue_month": actual_revenue_month(),
            "connected_count": len(connected),
            "running_count": len(running),
            "pending_count": len(needs_action),
            "online_count": len(online),
            "physical_count": len(physical),
        },
        "updated_at": _now_iso(),
    }


def update_status(slug: str, status: str) -> Optional[Dict[str, Any]]:
    if status not in ("needs_action", "connected", "running"):
        return None
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "UPDATE ideas SET status = ?, updated_at = ?, last_event_at = ? WHERE slug = ?",
            (status, now, now if status == "running" else None, slug),
        )
        row = conn.execute("SELECT * FROM ideas WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def update_idea_fields(slug: str, **fields: Any) -> Optional[Dict[str, Any]]:
    allowed = {"expected_daily_rub", "priority", "note", "action_required"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None
    now = _now_iso()
    sets = ", ".join(f"{k} = ?" for k in updates)
    with _connect() as conn:
        conn.execute(
            f"UPDATE ideas SET {sets}, updated_at = ? WHERE slug = ?",
            (*updates.values(), now, slug),
        )
        row = conn.execute("SELECT * FROM ideas WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def add_revenue(slug: str, amount: float, note: str = "", source: str = "manual") -> Optional[Dict[str, Any]]:
    now = _now_iso()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM ideas WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        conn.execute(
            """
            INSERT INTO revenue_events (slug, amount, source, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (slug, amount, source, note, now),
        )
        d = _today_str()
        slug_today = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS s FROM revenue_events
            WHERE slug = ? AND substr(created_at, 1, 10) = ?
            """,
            (slug, d),
        ).fetchone()["s"]
        month = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS s FROM revenue_events
            WHERE slug = ? AND substr(created_at, 1, 7) = ?
            """,
            (slug, _month_prefix()),
        ).fetchone()["s"]
        conn.execute(
            """
            UPDATE ideas SET revenue_today = ?, revenue_month = ?,
                status = 'running', updated_at = ?, last_event_at = ?
            WHERE slug = ?
            """,
            (slug_today, month, now, now, slug),
        )
        updated = conn.execute("SELECT * FROM ideas WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(updated) if updated else None


def sync_registry_titles(force: bool = False) -> int:
    """Явное обновление метаданных из registry (scripts/sync_registry.py)."""
    from business_dashboard.registry import SEED_IDEAS

    now = _now_iso()
    updated = 0
    by_slug = {i["slug"]: i for i in SEED_IDEAS}
    with _connect() as conn:
        for slug, idea in by_slug.items():
            if not force:
                continue
            conn.execute(
                """
                UPDATE ideas SET title = ?, category = ?, cluster = ?, tier = ?,
                    channel = ?, potential_rub = ?, automation_pct = ?,
                    expected_daily_rub = ?, updated_at = ?
                WHERE slug = ?
                """,
                (
                    idea["title"],
                    idea["category"],
                    idea.get("cluster", ""),
                    idea.get("tier", "strong"),
                    channel_for(slug),
                    idea.get("potential_rub", ""),
                    idea.get("automation_pct", 0),
                    expected_daily_for(slug),
                    now,
                    slug,
                ),
            )
            updated += 1
    return updated
