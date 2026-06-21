from __future__ import annotations

import logging

from work_bot.config import WORK_ADMIN_IDS, WORK_BOT_USERNAME

logger = logging.getLogger(__name__)


async def notify_admins(bot, text: str) -> None:
    footer = f"\n\n📬 @{WORK_BOT_USERNAME}"
    for aid in WORK_ADMIN_IDS:
        if aid <= 0:
            continue
        try:
            await bot.send_message(aid, text + footer, parse_mode="HTML")
        except Exception as e:
            logger.warning("work admin notify %s: %s", aid, e)
