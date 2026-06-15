"""Сеть Telegram: сессия, прокси, повторы при обрывах."""

import asyncio
import logging
from typing import Callable, Optional, TypeVar

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError

from bot.config import TELEGRAM_PROXY

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 5
RETRY_BASE_SEC = 2.0


def create_telegram_session() -> AiohttpSession:
    kwargs = {"timeout": 120}
    if TELEGRAM_PROXY:
        kwargs["proxy"] = TELEGRAM_PROXY
        logger.info("Telegram: используется прокси из TELEGRAM_PROXY")
    return AiohttpSession(**kwargs)


def format_telegram_error(exc: Exception) -> str:
    msg = str(exc)
    if "api.telegram.org" in msg or "TelegramNetworkError" in type(exc).__name__:
        hint = (
            "Нет стабильной связи с Telegram (api.telegram.org).\n"
            "• Проверьте интернет или включите VPN\n"
            "• Если VPN локальный — добавьте в .env:\n"
            "  TELEGRAM_PROXY=socks5://127.0.0.1:1080\n"
            "• Перезапустите бота после изменения .env"
        )
        if TELEGRAM_PROXY:
            hint += f"\n• Сейчас прокси: {TELEGRAM_PROXY}"
        return hint
    return msg[:500]


async def telegram_retry(
    operation: str,
    coro_factory: Callable[[], T],
    *,
    attempts: int = MAX_ATTEMPTS,
) -> T:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except (TelegramNetworkError, asyncio.TimeoutError, OSError) as e:
            last_exc = e
            if attempt >= attempts:
                break
            delay = RETRY_BASE_SEC * attempt
            logger.warning(
                "%s: попытка %s/%s не удалась (%s), повтор через %.0f с",
                operation,
                attempt,
                attempts,
                e,
                delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
