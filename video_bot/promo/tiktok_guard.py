"""Флаг бана TikTok (spam_risk) — Instagram продолжаем постить."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

_FLAG = Path(__file__).resolve().parents[2] / "data" / "video_bot" / "promo" / "tiktok_banned.flag"


def mark_tiktok_banned(*, hours: int = 72) -> None:
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    _FLAG.parent.mkdir(parents=True, exist_ok=True)
    _FLAG.write_text(until.isoformat(), encoding="utf-8")


def tiktok_posting_disabled() -> bool:
    if os.getenv("TIKTOK_POSTING_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return True
    if not _FLAG.exists():
        return False
    try:
        until = datetime.fromisoformat(_FLAG.read_text(encoding="utf-8").strip())
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < until:
            return True
        _FLAG.unlink(missing_ok=True)
    except (ValueError, OSError):
        _FLAG.unlink(missing_ok=True)
    return False


def note_uploadpost_errors(errors: list[str]) -> None:
    if any("spam_risk" in e.lower() or "banned_from_posting" in e.lower() for e in errors):
        mark_tiktok_banned(hours=72)
