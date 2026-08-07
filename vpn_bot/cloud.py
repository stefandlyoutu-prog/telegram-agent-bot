"""Облачный режим VPN-бота: webhook Telegram + Robokassa callbacks (Render)."""

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
from aiogram.types import ErrorEvent, Update
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from bot.services.telegram_net import create_telegram_session
from vpn_bot.config import VPN_BOT_TOKEN, VPN_BOT_USERNAME
from vpn_bot.handlers import router
from vpn_bot.storage import init_db

logger = logging.getLogger("vpn_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
_seen_updates: dict[int, float] = {}
_SEEN_TTL_SEC = 3600

router_cloud = APIRouter()

ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]


def _prune_seen() -> None:
    if len(_seen_updates) < 5000:
        return
    cutoff = time.time() - _SEEN_TTL_SEC
    for uid, ts in list(_seen_updates.items()):
        if ts < cutoff:
            _seen_updates.pop(uid, None)


async def start_cloud() -> None:
    global _bot, _dp
    if not VPN_BOT_TOKEN:
        raise RuntimeError("VPN_BOT_TOKEN не задан")
    init_db()
    _bot = Bot(
        token=VPN_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())

    @_dp.errors()
    async def _on_handler_error(event: ErrorEvent) -> bool:
        logger.exception("handler error: %s", event.exception)
        return True

    _dp.include_router(router)
    me = await _bot.get_me()
    logger.info("VPN-бот облако: @%s webhook", me.username)
    print(f"vpn_bot cloud ready: @{me.username}", flush=True)

    webhook_base = (
        os.getenv("VPN_WEBHOOK_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )
    if not webhook_base:
        raise RuntimeError("Задай VPN_WEBHOOK_URL / RENDER_EXTERNAL_URL")
    webhook_url = webhook_base.rstrip("/") + "/webhook"
    await _bot.delete_webhook(drop_pending_updates=False)
    await _bot.set_webhook(webhook_url, allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False)
    logger.info("Webhook: %s", webhook_url)


async def stop_cloud() -> None:
    global _bot, _dp
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
        return {"ok": True}
    try:
        await _dp.feed_update(_bot, update)
        _prune_seen()
        _seen_updates[update.update_id] = time.time()
    except Exception:
        logger.exception("feed_update %s failed", update.update_id)
    return {"ok": True}


@router_cloud.get("/health")
async def health():
    bot_user = None
    if _bot:
        try:
            me = await _bot.get_me()
            bot_user = me.username
        except Exception:
            bot_user = "error"
    return {"ok": True, "bot_ready": _bot is not None and _dp is not None, "bot": bot_user}


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
    from vpn_bot.access import fulfill_invoice, notify_paid

    inv = await fulfill_invoice(inv_id)
    if inv and _bot:
        asyncio.create_task(notify_paid(_bot, inv))


@router_cloud.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request):
    from vpn_bot.robokassa import check_result_signature

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
    link = f"https://t.me/{VPN_BOT_USERNAME}" if VPN_BOT_USERNAME else "https://t.me/"
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
    from vpn_bot.robokassa import check_success_signature

    data = await _robokassa_payload(request)
    if check_success_signature(data):
        try:
            inv_id = int(data["InvId"])
            await _robokassa_fulfill(inv_id)
        except (KeyError, ValueError, TypeError):
            pass
        return HTMLResponse(
            _back_to_bot_html("✅ Оплата получена", "Ключ активирован. Возвращайтесь в бот.")
        )
    return HTMLResponse(
        _back_to_bot_html("Оплата обрабатывается", "Если ключ не появился — напишите в поддержку.")
    )


@router_cloud.api_route("/robokassa/fail", methods=["GET", "POST"])
async def robokassa_fail(request: Request):
    return HTMLResponse(
        _back_to_bot_html("Оплата не завершена", "Платёж отменён. Можно попробовать снова в боте.")
    )


def cloud_runtime() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    return _bot, _dp
