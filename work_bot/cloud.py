"""Облако: webhook для Render."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import APIRouter, Request

from bot.services.telegram_net import create_telegram_session
from work_bot.config import WORK_BOT_TOKEN, WORK_PUSH_ENABLED, WORK_PUSH_INTERVAL_SEC
from work_bot.handlers import router
from work_bot.pushes import push_worker
from work_bot.storage import init_db

logger = logging.getLogger("work_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
_push_task: Optional[asyncio.Task] = None

router_cloud = APIRouter()


def cloud_enabled() -> bool:
    return os.getenv("WORK_CLOUD", "").strip() in {"1", "true", "True"} or bool(
        os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


async def start_cloud() -> None:
    global _bot, _dp, _push_task
    if not WORK_BOT_TOKEN:
        raise RuntimeError("WORK_BOT_TOKEN не задан")
    init_db()
    _bot = Bot(
        token=WORK_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())
    _dp.include_router(router)
    me = await _bot.get_me()
    logger.info("Work cloud: @%s", me.username)

    base = os.getenv("WORK_WEBHOOK_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if not base:
        raise RuntimeError("RENDER_EXTERNAL_URL или WORK_WEBHOOK_URL")
    webhook_url = base.rstrip("/") + "/webhook"
    await _bot.delete_webhook(drop_pending_updates=True)
    await _bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook: %s", webhook_url)

    if WORK_PUSH_ENABLED:
        _push_task = asyncio.create_task(push_worker(_bot, WORK_PUSH_INTERVAL_SEC))


async def stop_cloud() -> None:
    global _bot, _push_task
    if _push_task:
        _push_task.cancel()
        try:
            await _push_task
        except asyncio.CancelledError:
            pass
        _push_task = None
    if _bot:
        try:
            await _bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        await _bot.session.close()
        _bot = None


@router_cloud.post("/webhook")
async def webhook(request: Request):
    if not _bot or not _dp:
        return {"ok": False}
    data = await request.json()
    await _dp.feed_update(_bot, Update.model_validate(data))
    return {"ok": True}
