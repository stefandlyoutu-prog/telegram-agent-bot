"""VPN-бот: локальный запуск (long polling)."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.services.telegram_net import create_telegram_session
from vpn_bot.config import VPN_BOT_TOKEN
from vpn_bot.handlers import router
from vpn_bot.storage import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("vpn_bot")


async def main() -> None:
    if not VPN_BOT_TOKEN:
        logger.error("Задай VPN_BOT_TOKEN в .env")
        sys.exit(1)
    init_db()
    bot = Bot(
        token=VPN_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.get_me()
    logger.info("VPN-бот @%s запущен (polling)", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
