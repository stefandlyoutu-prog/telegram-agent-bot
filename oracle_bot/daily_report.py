"""Ежедневный отчёт админу по Oracle."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_LAST_SENT_FILE = Path(__file__).resolve().parents[1] / "data" / "oracle_last_daily_report.txt"


def _last_sent_date() -> str | None:
    try:
        if _LAST_SENT_FILE.exists():
            return _LAST_SENT_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def _mark_sent(today: str) -> None:
    _LAST_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_SENT_FILE.write_text(today, encoding="utf-8")


async def send_daily_report(bot) -> None:
    from oracle_bot.admin_notify import admin_ids, notify_admins
    from oracle_bot.analytics import format_daily_report

    if not admin_ids():
        logger.warning("daily report: ORACLE_ADMIN_IDS пуст")
        return
    text = format_daily_report()
    await notify_admins(bot, text, skip_footer=True)
    logger.info("oracle daily report sent")


async def daily_report_worker(bot, *, hour_msk: int = 9) -> None:
    """Раз в сутки в ~hour_msk по Москве (устойчиво к рестартам)."""
    import asyncio
    from datetime import datetime, timedelta, timezone

    while True:
        try:
            msk = timezone(timedelta(hours=3))
            now = datetime.now(msk)
            today = now.date().isoformat()
            # Окно 09:00–09:59 MSK, дата в файле — не дублировать после рестарта
            if now.hour == hour_msk and _last_sent_date() != today:
                await send_daily_report(bot)
                _mark_sent(today)
        except Exception:
            logger.exception("daily_report_worker")
        await asyncio.sleep(300)
