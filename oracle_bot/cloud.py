"""Облачный режим: webhook Telegram + push worker (Render / VPS)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
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
_seen_updates: dict[int, float] = {}
_SEEN_TTL_SEC = 3600

router_cloud = APIRouter()

ALLOWED_UPDATES = [
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


def cloud_enabled() -> bool:
    return os.getenv("ORACLE_CLOUD", "").strip() in {"1", "true", "True"} or bool(
        os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


def _prune_seen() -> None:
    if len(_seen_updates) < 5000:
        return
    cutoff = time.time() - _SEEN_TTL_SEC
    for uid, ts in list(_seen_updates.items()):
        if ts < cutoff:
            _seen_updates.pop(uid, None)


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
    logger.info("Облако: @%s webhook (sync feed_update)", me.username)
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
    await _bot.delete_webhook(drop_pending_updates=False)
    await _bot.set_webhook(
        webhook_url,
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=False,
    )
    logger.info("Webhook: %s", webhook_url)

    if ORACLE_PUSH_ENABLED:
        _push_task = asyncio.create_task(push_worker(_bot, ORACLE_PUSH_INTERVAL_SEC))
        logger.info("Push worker: каждые %s сек", ORACLE_PUSH_INTERVAL_SEC)

    from oracle_bot.config import ORACLE_DAILY_REPORT, ORACLE_DAILY_REPORT_HOUR_MSK
    from oracle_bot.daily_report import daily_report_worker

    if ORACLE_DAILY_REPORT:
        asyncio.create_task(daily_report_worker(_bot, hour_msk=ORACLE_DAILY_REPORT_HOUR_MSK))
        logger.info("Daily report: ~%s:00 MSK", ORACLE_DAILY_REPORT_HOUR_MSK)

    from oracle_bot.config import ORACLE_FREE_DAY_REPORT, ORACLE_FREE_DAY_REPORT_HOUR_MSK
    from oracle_bot.free_day import free_day_report_worker

    if ORACLE_FREE_DAY_REPORT:
        asyncio.create_task(
            free_day_report_worker(_bot, hour_msk=ORACLE_FREE_DAY_REPORT_HOUR_MSK)
        )
        logger.info("Free day report: ~%s:00 MSK", ORACLE_FREE_DAY_REPORT_HOUR_MSK)

    from oracle_bot.config import ORACLE_BOOKS_REPORT_HOUR_MSK
    from oracle_bot.campaign_report import books_report_worker

    asyncio.create_task(books_report_worker(_bot, hour_msk=ORACLE_BOOKS_REPORT_HOUR_MSK))
    logger.info("Books sales report: ~%s:00 MSK", ORACLE_BOOKS_REPORT_HOUR_MSK)

    if ORACLE_CHANNEL_POSTS_ENABLED:
        from oracle_bot.channel_queue import seed_week_queue

        if db.count_channel_posts(status="pending") == 0:
            seeded = seed_week_queue()
            logger.info("Channel queue auto-seed: %s", seeded)
        _channel_task = asyncio.create_task(
            channel_post_worker(_bot, ORACLE_CHANNEL_POST_INTERVAL_SEC)
        )
        logger.info("Channel post worker: каждые %s сек", ORACLE_CHANNEL_POST_INTERVAL_SEC)


async def stop_cloud() -> None:
    global _bot, _dp, _push_task, _channel_task
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
    _dp = None


@router_cloud.post("/webhook")
async def telegram_webhook(request: Request):
    """Как work_bot: await feed_update — иначе Render теряет фоновые задачи."""
    if not _bot or not _dp:
        logger.warning("webhook before bot ready")
        return {"ok": False}
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": _bot})
    except Exception:
        logger.exception("webhook parse error")
        return {"ok": True}

    if update.update_id in _seen_updates:
        logger.info("webhook duplicate %s skipped", update.update_id)
        return {"ok": True}

    kind = "callback" if update.callback_query else "message" if update.message else "other"
    preview = ""
    if update.message and update.message.text:
        preview = update.message.text[:48]
    logger.info("webhook %s %s %s", update.update_id, kind, preview)
    print(f"WEBHOOK {update.update_id} {kind} {preview}", flush=True)

    try:
        await _dp.feed_update(_bot, update)
        _prune_seen()
        _seen_updates[update.update_id] = time.time()
    except Exception:
        logger.exception("feed_update %s failed", update.update_id)
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
        "mode": "webhook_sync",
        "bot_ready": _bot is not None and _dp is not None,
        "bot": bot_user,
        "webapp": ORACLE_WEBAPP_URL or cloud_webapp_url(),
        "version": commit or "local",
        "routes": ["/landing", "/oferta", "/admin"],
    }


async def _robokassa_payload(request: Request) -> dict[str, str]:
    data = {k: str(v) for k, v in request.query_params.items()}
    if request.method == "POST":
        try:
            form = await request.form()
            data.update({k: str(v) for k, v in form.items()})
        except Exception:
            pass
    return data


async def _robokassa_fulfill(inv_id: int) -> None:
    """Выдать доступ по инвойсу + уведомить (идемпотентно)."""
    from oracle_bot.payments import fulfill_invoice, notify_paid

    inv = fulfill_invoice(inv_id)
    if inv and _bot:
        asyncio.create_task(notify_paid(_bot, inv))


@router_cloud.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request):
    """Сервер-сервер колбэк Робокассы. Ответ строго 'OK{InvId}'."""
    from fastapi.responses import PlainTextResponse

    from oracle_bot.robokassa import check_result_signature

    data = await _robokassa_payload(request)
    if not check_result_signature(data):
        logger.warning("robokassa result: bad signature inv=%s", data.get("InvId"))
        return PlainTextResponse("bad sign", status_code=400)
    try:
        inv_id = int(data["InvId"])
    except (KeyError, ValueError):
        return PlainTextResponse("bad inv", status_code=400)

    await _robokassa_fulfill(inv_id)
    return PlainTextResponse(f"OK{inv_id}")


def _back_to_bot_html(title: str, message: str) -> str:
    from oracle_bot.config import ORACLE_BOT_USERNAME

    link = f"https://t.me/{ORACLE_BOT_USERNAME}"
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#11101a;"
        "color:#eee;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
        ".card{max-width:420px;padding:32px;text-align:center}"
        "a.btn{display:inline-block;margin-top:24px;padding:14px 28px;border-radius:12px;"
        "background:#6c5ce7;color:#fff;text-decoration:none;font-weight:600}</style></head>"
        f"<body><div class='card'><h1>{title}</h1><p>{message}</p>"
        f"<a class='btn' href='{link}'>Вернуться в бот</a></div></body></html>"
    )


@router_cloud.api_route("/robokassa/success", methods=["GET", "POST"])
async def robokassa_success(request: Request):
    from fastapi.responses import HTMLResponse

    from oracle_bot.robokassa import check_success_signature

    data = await _robokassa_payload(request)
    if check_success_signature(data):
        try:
            inv_id = int(data["InvId"])
            await _robokassa_fulfill(inv_id)
        except (KeyError, ValueError, TypeError):
            pass
        return HTMLResponse(
            _back_to_bot_html("✅ Оплата получена", "Доступ активирован. Возвращайтесь в бот.")
        )
    return HTMLResponse(
        _back_to_bot_html("Оплата обрабатывается", "Если доступ не появился — напишите в бот.")
    )


@router_cloud.api_route("/robokassa/fail", methods=["GET", "POST"])
async def robokassa_fail(request: Request):
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        _back_to_bot_html("Оплата не завершена", "Платёж отменён. Можно попробовать снова в боте.")
    )


def cloud_runtime() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    return _bot, _dp
