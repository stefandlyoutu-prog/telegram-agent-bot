"""Фоновые задачи: rollover и отчёт в полночь."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from business_dashboard.config import AUTO_CLOSE_DAY

logger = logging.getLogger(__name__)


async def run_background_loop() -> None:
    last_close_date = None
    while True:
        try:
            from business_dashboard.storage import rollover_periods

            rollover_periods()
            if AUTO_CLOSE_DAY:
                today = date.today().isoformat()
                now = datetime.now().astimezone()
                if now.hour == 0 and now.minute < 2 and last_close_date != today:
                    from business_dashboard.daily import close_day_report, get_report
                    from datetime import timedelta

                    yesterday = (date.today() - timedelta(days=1)).isoformat()
                    if not get_report(yesterday):
                        close_day_report(note="авто полночь")
                        logger.info("Авто-отчёт за %s", yesterday)
                    last_close_date = today
        except Exception as e:
            logger.warning("scheduler: %s", e)
        await asyncio.sleep(45)
