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
from work_bot.config import WORK_BOT_TOKEN, WORK_PUSH_ENABLED, WORK_PUSH_INTERVAL_SEC
from work_bot.handlers import router
from work_bot.pushes import push_worker
from work_bot.storage import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("work_bot")


async def main() -> None:
    if not WORK_BOT_TOKEN:
        logger.error("Задайте WORK_BOT_TOKEN в .env")
        sys.exit(1)
    init_db()
    bot = Bot(
        token=WORK_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.get_me()
    logger.info("Работа онлайн @%s запущен", me.username)
    if WORK_PUSH_ENABLED:
        asyncio.create_task(push_worker(bot, WORK_PUSH_INTERVAL_SEC))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
