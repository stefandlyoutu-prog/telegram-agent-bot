"""SQLite: сеть Telegram-каналов."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from business_dashboard.storage import DB_PATH, _connect

SEED_CHANNELS: List[Dict[str, Any]] = [
    {
        "username": "M_Topgoroskop",
        "title": "Топ гороскоп 💖",
        "niche": "horoscope",
        "funnel_url": "https://t.me/MOracul_bot",
        "monetization": "yandex_browser,oracle_stars",
        "yandex_status": "moderation",
        "is_flagship": 1,
        "note": "Яндекс Дистрибуция · на модерации",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_tg_channels(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_channels (
            username TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            niche TEXT DEFAULT '',
            funnel_url TEXT DEFAULT 'https://t.me/MOracul_bot',
            monetization TEXT DEFAULT '',
            yandex_status TEXT DEFAULT 'none',
            is_flagship INTEGER DEFAULT 0,
            bot_admin INTEGER DEFAULT 0,
            can_post INTEGER DEFAULT 0,
            can_edit INTEGER DEFAULT 0,
            subscribers INTEGER DEFAULT 0,
            last_sync_at TEXT,
            last_post_at TEXT,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    now = _now()
    for ch in SEED_CHANNELS:
        conn.execute(
            """
            INSERT INTO tg_channels (
                username, title, niche, funnel_url, monetization, yandex_status,
                is_flagship, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                title = excluded.title,
                niche = COALESCE(NULLIF(excluded.niche, ''), tg_channels.niche),
                note = CASE WHEN excluded.note != '' THEN excluded.note ELSE tg_channels.note END,
                updated_at = excluded.updated_at
            """,
            (
                ch["username"],
                ch.get("title", ""),
                ch.get("niche", ""),
                ch.get("funnel_url", "https://t.me/MOracul_bot"),
                ch.get("monetization", ""),
                ch.get("yandex_status", "none"),
                ch.get("is_flagship", 0),
                ch.get("note", ""),
                now,
                now,
            ),
        )


def list_tg_channels() -> List[Dict[str, Any]]:
    with _connect() as conn:
        init_tg_channels(conn)
        rows = conn.execute(
            "SELECT * FROM tg_channels ORDER BY is_flagship DESC, title"
        ).fetchall()
    return [_row(r) for r in rows]


def get_tg_channel(username: str) -> Optional[Dict[str, Any]]:
    u = username.lstrip("@").replace("https://t.me/", "").split("/")[0]
    with _connect() as conn:
        init_tg_channels(conn)
        row = conn.execute("SELECT * FROM tg_channels WHERE username = ?", (u,)).fetchone()
    return _row(row) if row else None


def add_tg_channel(
    username: str,
    *,
    niche: str = "",
    funnel_url: str = "https://t.me/MOracul_bot",
    monetization: str = "",
    note: str = "",
) -> Dict[str, Any]:
    u = username.lstrip("@").replace("https://t.me/", "").split("/")[0]
    now = _now()
    with _connect() as conn:
        init_tg_channels(conn)
        conn.execute(
            """
            INSERT INTO tg_channels (username, niche, funnel_url, monetization, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                niche = COALESCE(NULLIF(excluded.niche, ''), tg_channels.niche),
                funnel_url = excluded.funnel_url,
                monetization = COALESCE(NULLIF(excluded.monetization, ''), tg_channels.monetization),
                note = CASE WHEN excluded.note != '' THEN excluded.note ELSE tg_channels.note END,
                updated_at = excluded.updated_at
            """,
            (u, niche, funnel_url, monetization, note, now, now),
        )
        row = conn.execute("SELECT * FROM tg_channels WHERE username = ?", (u,)).fetchone()
    out = sync_tg_channel(u)
    return out or _row(row)


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["url"] = f"https://t.me/{d['username']}"
    d["ready"] = bool(d.get("bot_admin") and d.get("can_post"))
    return d


def sync_tg_channel(username: str) -> Optional[Dict[str, Any]]:
    from telegram_channels.client import ChannelBot, ChannelBotError

    u = username.lstrip("@")
    ch = get_tg_channel(u)
    if not ch:
        return None
    now = _now()
    title = ch.get("title") or ""
    bot_admin = can_post = can_edit = 0
    try:
        bot = ChannelBot()
        chat = bot.get_chat(u)
        title = chat.get("title") or title
        st = bot.admin_status(u)
        bot_admin = 1 if st["bot_admin"] else 0
        can_post = 1 if st["can_post"] else 0
        can_edit = 1 if st["can_edit"] else 0
        note_extra = f"bot={st['status']}"
    except ChannelBotError as e:
        note_extra = str(e)[:120]
    with _connect() as conn:
        conn.execute(
            """
            UPDATE tg_channels SET
                title = ?, bot_admin = ?, can_post = ?, can_edit = ?,
                last_sync_at = ?, note = CASE WHEN ? != '' THEN ? ELSE note END,
                updated_at = ?
            WHERE username = ?
            """,
            (title, bot_admin, can_post, can_edit, now, note_extra, note_extra, now, u),
        )
        row = conn.execute("SELECT * FROM tg_channels WHERE username = ?", (u,)).fetchone()
    return _row(row) if row else None


def sync_all_tg_channels() -> List[Dict[str, Any]]:
    return [sync_tg_channel(c["username"]) for c in list_tg_channels()]


def mark_posted(username: str) -> None:
    u = username.lstrip("@")
    now = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE tg_channels SET last_post_at = ?, updated_at = ? WHERE username = ?",
            (now, now, u),
        )
