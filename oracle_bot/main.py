from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.services.telegram_net import create_telegram_session
from oracle_bot.config import (
    ORACLE_BOT_TOKEN,
    ORACLE_CHANNEL_POST_INTERVAL_SEC,
    ORACLE_CHANNEL_POSTS_ENABLED,
    ORACLE_DAILY_REPORT,
    ORACLE_DAILY_REPORT_HOUR_MSK,
    ORACLE_PUSH_ENABLED,
    ORACLE_PUSH_INTERVAL_SEC,
    ORACLE_WEBAPP_URL,
)
from oracle_bot.daily_report import daily_report_worker
from oracle_bot.handlers import router
from oracle_bot.voice import router as voice_router
from oracle_bot.storage import init_db
from oracle_bot.pushes import push_worker
from oracle_bot.channel_queue import channel_post_worker, seed_week_queue
from oracle_bot import storage as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("oracle_bot")


def _lock() -> None:
    try:
        import fcntl

        root = os.path.dirname(os.path.dirname(__file__))
        f = open(os.path.join(root, ".oracle.lock"), "w")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
        f.flush()
    except BlockingIOError:
        logger.error("Оракул уже запущен (.oracle.lock)")
        sys.exit(2)
    except Exception as e:
        logger.warning("lock: %s", e)


async def main() -> None:
    if not ORACLE_BOT_TOKEN:
        logger.error("Задайте ORACLE_BOT_TOKEN в .env")
        sys.exit(1)
    _lock()
    init_db()
    bot = Bot(
        token=ORACLE_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.include_router(voice_router)
    me = await bot.get_me()
    logger.info("Оракул @%s запущен", me.username)
    if ORACLE_WEBAPP_URL:
        from aiogram.types import MenuButtonWebApp, WebAppInfo

        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Приложение",
                    web_app=WebAppInfo(url=ORACLE_WEBAPP_URL),
                )
            )
            logger.info("WebApp: %s", ORACLE_WEBAPP_URL)
        except Exception as e:
            logger.warning("WebApp menu: %s", e)
    if ORACLE_PUSH_ENABLED:
        asyncio.create_task(push_worker(bot, ORACLE_PUSH_INTERVAL_SEC))
        logger.info("Push worker: каждые %s сек", ORACLE_PUSH_INTERVAL_SEC)
    if ORACLE_DAILY_REPORT:
        asyncio.create_task(daily_report_worker(bot, hour_msk=ORACLE_DAILY_REPORT_HOUR_MSK))
        logger.info("Daily report: ~%s:00 MSK", ORACLE_DAILY_REPORT_HOUR_MSK)
    from oracle_bot.config import ORACLE_FREE_DAY_REPORT, ORACLE_FREE_DAY_REPORT_HOUR_MSK
    from oracle_bot.free_day import free_day_report_worker

    if ORACLE_FREE_DAY_REPORT:
        asyncio.create_task(
            free_day_report_worker(bot, hour_msk=ORACLE_FREE_DAY_REPORT_HOUR_MSK)
        )
        logger.info("Free day report: ~%s:00 MSK", ORACLE_FREE_DAY_REPORT_HOUR_MSK)
    if ORACLE_CHANNEL_POSTS_ENABLED:
        if db.count_channel_posts(status="pending") == 0:
            seeded = seed_week_queue()
            logger.info("Channel queue seeded: %s", seeded)
        asyncio.create_task(channel_post_worker(bot, ORACLE_CHANNEL_POST_INTERVAL_SEC))
        logger.info("Channel post worker: каждые %s сек", ORACLE_CHANNEL_POST_INTERVAL_SEC)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
