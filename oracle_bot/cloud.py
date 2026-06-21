"""Облачный режим: webhook Telegram + push worker (Render / VPS)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import APIRouter, Request

from bot.services.telegram_net import create_telegram_session
from oracle_bot.config import (
    ORACLE_BOT_TOKEN,
    ORACLE_CHANNEL_POST_INTERVAL_SEC,
    ORACLE_CHANNEL_POSTS_ENABLED,
    ORACLE_PUSH_ENABLED,
    ORACLE_PUSH_INTERVAL_SEC,
    ORACLE_WEBAPP_URL,
    cloud_webapp_url,
)
from oracle_bot.channel_queue import channel_post_worker
from oracle_bot.handlers import router
from oracle_bot.pushes import push_worker
from oracle_bot import storage as db
from oracle_bot.storage import init_db
from oracle_bot.voice import router as voice_router

logger = logging.getLogger("oracle_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
_push_task: Optional[asyncio.Task] = None
_channel_task: Optional[asyncio.Task] = None

router_cloud = APIRouter()


def cloud_enabled() -> bool:
    return os.getenv("ORACLE_CLOUD", "").strip() in {"1", "true", "True"} or bool(
        os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


async def start_cloud() -> None:
    global _bot, _dp, _push_task, _channel_task
    if not ORACLE_BOT_TOKEN:
        raise RuntimeError("ORACLE_BOT_TOKEN не задан")
    init_db()
    _bot = Bot(
        token=ORACLE_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())
    _dp.include_router(router)
    _dp.include_router(voice_router)
    me = await _bot.get_me()
    logger.info("Облако: @%s webhook", me.username)

    webapp_url = cloud_webapp_url()
    if webapp_url:
        try:
            await _bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Приложение",
                    web_app=WebAppInfo(url=webapp_url),
                )
            )
            logger.info("WebApp menu: %s", webapp_url)
        except Exception as e:
            logger.warning("WebApp menu: %s", e)

    webhook_base = os.getenv("ORACLE_WEBHOOK_URL", "").strip() or os.getenv(
        "RENDER_EXTERNAL_URL", ""
    ).strip()
    if not webhook_base:
        raise RuntimeError("Задай RENDER_EXTERNAL_URL или ORACLE_WEBHOOK_URL")
    webhook_url = webhook_base.rstrip("/") + "/webhook"
    allowed = [
        "message",
        "edited_message",
        "callback_query",
        "pre_checkout_query",
        "inline_query",
        "chosen_inline_result",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ]
    await _bot.delete_webhook(drop_pending_updates=True)
    await _bot.set_webhook(
        webhook_url,
        allowed_updates=allowed,
        drop_pending_updates=True,
    )
    logger.info("Webhook: %s (updates: %s)", webhook_url, len(allowed))

    if ORACLE_PUSH_ENABLED:
        _push_task = asyncio.create_task(push_worker(_bot, ORACLE_PUSH_INTERVAL_SEC))
        logger.info("Push worker: каждые %s сек", ORACLE_PUSH_INTERVAL_SEC)

    if ORACLE_CHANNEL_POSTS_ENABLED:
        from oracle_bot.channel_queue import seed_week_queue

        summary = db.count_channel_posts(status="pending")
        if summary == 0:
            seeded = seed_week_queue()
            logger.info("Channel queue auto-seed: %s", seeded)
        _channel_task = asyncio.create_task(
            channel_post_worker(_bot, ORACLE_CHANNEL_POST_INTERVAL_SEC)
        )
        logger.info("Channel post worker: каждые %s сек", ORACLE_CHANNEL_POST_INTERVAL_SEC)


async def stop_cloud() -> None:
    global _bot, _push_task, _channel_task
    if _channel_task:
        _channel_task.cancel()
        try:
            await _channel_task
        except asyncio.CancelledError:
            pass
        _channel_task = None
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
async def telegram_webhook(request: Request):
    if not _bot or not _dp:
        return {"ok": False}
    data = await request.json()
    update = Update.model_validate(data)
    asyncio.create_task(_dp.feed_update(_bot, update))
    return {"ok": True}


@router_cloud.get("/health")
async def health():
    return {"ok": True, "webapp": ORACLE_WEBAPP_URL or cloud_webapp_url()}
