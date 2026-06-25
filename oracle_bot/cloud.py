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
from aiogram.types import ErrorEvent, MenuButtonWebApp, Update, WebAppInfo
from fastapi import APIRouter, Request

from bot.services.telegram_net import create_telegram_session
from oracle_bot.channel_queue import channel_post_worker
from oracle_bot.config import (
    ORACLE_BOT_TOKEN,
    ORACLE_CHANNEL_POST_INTERVAL_SEC,
    ORACLE_CHANNEL_POSTS_ENABLED,
    ORACLE_PUSH_ENABLED,
    ORACLE_PUSH_INTERVAL_SEC,
    ORACLE_WEBAPP_URL,
    cloud_webapp_url,
)
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
_webhook_tasks: set[asyncio.Task] = set()

router_cloud = APIRouter()

# Команды и callback — ждём ответа до 200 OK (иначе Render теряет фоновые задачи).
_WEBHOOK_AWAIT_SEC = float(os.getenv("ORACLE_WEBHOOK_AWAIT_SEC", "25"))


def cloud_enabled() -> bool:
    return os.getenv("ORACLE_CLOUD", "").strip() in {"1", "true", "True"} or bool(
        os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


def _webhook_should_await(update: Update) -> bool:
    if update.callback_query:
        return True
    text = (update.message.text or "").strip() if update.message else ""
    if not text:
        return False
    first = text.split()[0].split("@")[0].lower()
    return first.startswith("/")


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

    @_dp.errors()
    async def _on_handler_error(event: ErrorEvent) -> bool:
        logger.exception("handler error: %s", event.exception)
        return True

    _dp.include_router(router)
    _dp.include_router(voice_router)
    me = await _bot.get_me()
    logger.info("Облако: @%s webhook", me.username)
    print(f"m-Oracul cloud ready: @{me.username}", flush=True)

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
    await _bot.delete_webhook(drop_pending_updates=False)
    await _bot.set_webhook(
        webhook_url,
        allowed_updates=allowed,
        drop_pending_updates=False,
    )
    logger.info("Webhook: %s (updates: %s)", webhook_url, len(allowed))

    if ORACLE_PUSH_ENABLED:
        _push_task = asyncio.create_task(push_worker(_bot, ORACLE_PUSH_INTERVAL_SEC))
        logger.info("Push worker: каждые %s сек", ORACLE_PUSH_INTERVAL_SEC)

    from oracle_bot.config import ORACLE_DAILY_REPORT, ORACLE_DAILY_REPORT_HOUR_MSK
    from oracle_bot.daily_report import daily_report_worker

    if ORACLE_DAILY_REPORT:
        asyncio.create_task(daily_report_worker(_bot, hour_msk=ORACLE_DAILY_REPORT_HOUR_MSK))
        logger.info("Daily report: ~%s:00 MSK", ORACLE_DAILY_REPORT_HOUR_MSK)

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


async def _run_update(update: Update) -> None:
    if not _bot or not _dp:
        logger.error("webhook: bot not ready, drop %s", update.update_id)
        return
    try:
        await _dp.feed_update(_bot, update)
    except Exception:
        logger.exception("feed_update %s failed", update.update_id)


@router_cloud.post("/webhook")
async def telegram_webhook(request: Request):
    if not _bot or not _dp:
        logger.warning("webhook before bot ready")
        return {"ok": False, "error": "bot_not_ready"}
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": _bot})
    except Exception:
        logger.exception("webhook parse error")
        return {"ok": True}

    kind = "callback" if update.callback_query else "message" if update.message else "other"
    text_preview = ""
    if update.message and update.message.text:
        text_preview = update.message.text[:40]
    logger.info("webhook %s %s %s", update.update_id, kind, text_preview)
    print(f"WEBHOOK {update.update_id} {kind} {text_preview}", flush=True)

    task = asyncio.create_task(_run_update(update))
    _webhook_tasks.add(task)
    task.add_done_callback(_webhook_tasks.discard)

    if _webhook_should_await(update):
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=_WEBHOOK_AWAIT_SEC)
        except asyncio.TimeoutError:
            logger.warning("webhook %s slow (>%ss), continues in background", update.update_id, _WEBHOOK_AWAIT_SEC)
    else:
        await asyncio.sleep(0.05)

    return {"ok": True}


@router_cloud.get("/health")
async def health():
    commit = os.getenv("RENDER_GIT_COMMIT", "").strip()[:12]
    bot_user = None
    if _bot:
        try:
            me = await _bot.get_me()
            bot_user = me.username
        except Exception:
            bot_user = "error"
    return {
        "ok": True,
        "bot_ready": _bot is not None and _dp is not None,
        "bot": bot_user,
        "webhook_tasks": len(_webhook_tasks),
        "webapp": ORACLE_WEBAPP_URL or cloud_webapp_url(),
        "version": commit or "local",
        "routes": ["/landing", "/oferta", "/admin"],
    }


def cloud_runtime() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    return _bot, _dp
