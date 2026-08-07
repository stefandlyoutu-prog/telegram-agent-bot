"""Telegram-сессия для VPN-бота (без зависимости от bot.services)."""

from __future__ import annotations

import logging
import os

from aiogram.client.session.aiohttp import AiohttpSession

logger = logging.getLogger(__name__)


def create_telegram_session() -> AiohttpSession:
    proxy = os.getenv("TELEGRAM_PROXY", "").strip() or None
    kwargs: dict = {"timeout": 120}
    if proxy:
        kwargs["proxy"] = proxy
        logger.info("Telegram: используется прокси из TELEGRAM_PROXY")
    return AiohttpSession(**kwargs)
