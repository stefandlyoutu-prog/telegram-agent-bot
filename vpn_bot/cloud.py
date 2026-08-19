"""Облачный режим VPN-бота: монтируется в moracul (webhook + Robokassa)."""

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

from vpn_bot.config import VPN_BOT_TOKEN, VPN_BOT_USERNAME
from vpn_bot.handlers import router as vpn_router
from vpn_bot.storage import init_db
from vpn_bot.telegram_net import create_telegram_session

logger = logging.getLogger("vpn_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
_seen_updates: dict[int, float] = {}
_SEEN_TTL_SEC = 3600

router_vpn = APIRouter()
ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]


def _webhook_base() -> str:
    # Приоритет: VPN_WEBHOOK_URL → ORACLE_WEBHOOK_URL → ORACLE_WEBAPP_URL → RENDER_EXTERNAL_URL
    return (
        os.getenv("VPN_WEBHOOK_URL", "").strip()
        or os.getenv("ORACLE_WEBHOOK_URL", "").strip()
        or os.getenv("ORACLE_WEBAPP_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


def _prune_seen() -> None:
    if len(_seen_updates) < 5000:
        return
    cutoff = time.time() - _SEEN_TTL_SEC
    for uid, ts in list(_seen_updates.items()):
        if ts < cutoff:
            _seen_updates.pop(uid, None)


async def init_vpn_bot() -> None:
    """Поднимает VPN-бота и вешает webhook на /webhook/vpn (если задан VPN_BOT_TOKEN)."""
    global _bot, _dp
    if not VPN_BOT_TOKEN:
        logger.info("VPN bot: токен не задан — пропуск")
        return
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

    _dp.include_router(vpn_router)
    me = await _bot.get_me()
    logger.info("VPN bot: @%s", me.username)
    print(f"vpn_bot ready on moracul: @{me.username}", flush=True)

    webhook_base = _webhook_base()
    if not webhook_base:
        # Попробуем получить URL из render.yaml через переменную окружения
        webhook_base = "https://moracul.ru"  # Хардкод как fallback
        logger.warning("VPN bot: используем fallback URL: %s", webhook_base)

    webhook_url = webhook_base.rstrip("/") + "/webhook/vpn"
    try:
        await _bot.delete_webhook(drop_pending_updates=False)
        await _bot.set_webhook(webhook_url, allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False)
        logger.info("VPN webhook установлен: %s", webhook_url)
        print(f"VPN webhook установлен: {webhook_url}", flush=True)
    except Exception as e:
        logger.error("Ошибка установки VPN webhook: %s", e)
        print(f"ОШИБКА VPN webhook: {e}", flush=True)


async def stop_vpn_bot() -> None:
    global _bot, _dp
    if _bot:
        try:
            await _bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        await _bot.session.close()
        _bot = None
    _dp = None


def vpn_runtime() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    return _bot, _dp


@router_vpn.get("/webhook/vpn")
async def vpn_webhook_get():
    """GET endpoint для отладки webhook"""
    return {
        "ok": True,
        "bot_ready": _bot is not None,
        "dp_ready": _dp is not None,
        "seen_updates_count": len(_seen_updates),
        "last_updates": list(_seen_updates.keys())[-5:] if _seen_updates else []
    }

@router_vpn.post("/webhook/vpn")
async def vpn_webhook(request: Request):
    if not _bot or not _dp:
        logger.warning("vpn webhook before bot ready")
        return {"ok": False}
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": _bot})
    except Exception:
        logger.exception("vpn webhook parse error")
        return {"ok": True}

    if update.update_id in _seen_updates:
        logger.info("vpn webhook: duplicate update %s", update.update_id)
        return {"ok": True}
    try:
        await _dp.feed_update(_bot, update)
        _prune_seen()
        _seen_updates[update.update_id] = time.time()
        logger.info("vpn webhook: processed update %s", update.update_id)
    except Exception:
        logger.exception("vpn feed_update %s failed", update.update_id)
    return {"ok": True}


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


@router_vpn.api_route("/vpn/robokassa/result", methods=["GET", "POST"])
async def vpn_robokassa_result(request: Request):
    from vpn_bot.robokassa import check_result_signature

    data = await _robokassa_payload(request)
    if not check_result_signature(data):
        logger.warning("vpn robokassa result: bad signature inv=%s", data.get("InvId"))
        return PlainTextResponse("bad sign", status_code=400)
    try:
        inv_id = int(data["InvId"])
    except (KeyError, ValueError):
        return PlainTextResponse("bad inv", status_code=400)
    await _robokassa_fulfill(inv_id)
    return PlainTextResponse(f"OK{inv_id}")


@router_vpn.api_route("/vpn/robokassa/success", methods=["GET", "POST"])
async def vpn_robokassa_success(request: Request):
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


@router_vpn.api_route("/vpn/robokassa/fail", methods=["GET", "POST"])
async def vpn_robokassa_fail(request: Request):
    return HTMLResponse(
        _back_to_bot_html("Оплата не завершена", "Платёж отменён. Можно попробовать снова в боте.")
    )


@router_vpn.post("/vpn/admin/reset_trial")
async def admin_reset_trial(request: Request):
    """Admin endpoint для сброса trial периода пользователя"""
    from vpn_bot import storage as db
    from vpn_bot.config import VPN_DB_PATH
    
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid user_id"}
    
    # Простая проверка авторизации (можно улучшить)
    admin_id = 5845195049  # Твой user_id из render.yaml
    if user_id != admin_id:
        return {"ok": False, "error": "Unauthorized"}
    
    try:
        with db._connect() as conn:
            cursor = conn.cursor()
            
            # Проверяем текущее состояние
            cursor.execute("SELECT trial_used FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"ok": False, "error": "User not found"}
            
            current_trial = result[0]
            
            # Сбрасываем trial_used
            cursor.execute("UPDATE users SET trial_used = 0 WHERE user_id = ?", (user_id,))
            
            # Удаляем подписку
            cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
            
            # Удаляем инвойсы
            cursor.execute("DELETE FROM invoices WHERE user_id = ?", (user_id,))
            
            logger.info("Admin reset trial for user %s (was %s)", user_id, current_trial)
            
            return {
                "ok": True,
                "user_id": user_id,
                "previous_trial_used": current_trial,
                "new_trial_used": 0
            }
        
    except Exception as e:
        logger.exception("Admin reset trial failed for user %s", user_id)
        return {"ok": False, "error": str(e)}


@router_vpn.get("/vpn/debug")
async def vpn_debug():
    """Отладочная информация VPN бота"""
    return {
        "bot_ready": _bot is not None,
        "dp_ready": _dp is not None,
        "webhook_base": _webhook_base(),
        "env_vars": {
            "VPN_WEBHOOK_URL": os.getenv("VPN_WEBHOOK_URL", "").strip(),
            "ORACLE_WEBHOOK_URL": os.getenv("ORACLE_WEBHOOK_URL", "").strip(),
            "ORACLE_WEBAPP_URL": os.getenv("ORACLE_WEBAPP_URL", "").strip(),
            "RENDER_EXTERNAL_URL": os.getenv("RENDER_EXTERNAL_URL", "").strip(),
        },
        "marzban_config": {
            "base_url": os.getenv("MARZBAN_BASE_URL", "").strip(),
            "username": bool(os.getenv("MARZBAN_USERNAME", "").strip()),
            "password": bool(os.getenv("MARZBAN_PASSWORD", "").strip()),
        }
    }
