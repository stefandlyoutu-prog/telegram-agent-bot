"""Выдача/продление VPN-ключа: пробный период и оплаченные тарифы."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from vpn_bot import storage as db
from vpn_bot.config import VPN_ADMIN_IDS, VPN_DATA_LIMIT_BYTES, VPN_TRIAL_DAYS, get_tariff
from vpn_bot.marzban_client import MarzbanClient

logger = logging.getLogger(__name__)


def _expire_ts(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


async def grant_or_extend(user_id: int, days: int, *, plan_label: str) -> dict[str, Any]:
    """Создаёт/продлевает ключ пользователя в Marzban, сохраняет в локальную БД.

    Возвращает {"subscription_url": ..., "expires_at": ISO str}.
    """
    user = db.ensure_user(user_id)
    marzban_username = user["marzban_username"]
    client = MarzbanClient()
    obj = await client.ensure_active_user(
        marzban_username,
        extend_expire_ts=_expire_ts(days),
        data_limit_bytes=VPN_DATA_LIMIT_BYTES,
        note=f"tg:{user_id}",
    )
    expire_ts = int(obj.get("expire") or 0)
    expires_at = (
        datetime.fromtimestamp(expire_ts, tz=timezone.utc).isoformat(timespec="seconds")
        if expire_ts
        else None
    )
    db.upsert_subscription(
        user_id, marzban_username=marzban_username, plan=plan_label, expires_at=expires_at
    )
    return {
        "subscription_url": MarzbanClient.subscription_url(obj),
        "expires_at": expires_at,
    }


async def start_trial(user_id: int) -> Optional[dict[str, Any]]:
    """Выдаёт пробный ключ один раз на пользователя. None, если уже использован."""
    user = db.ensure_user(user_id)
    if user["trial_used"]:
        return None
    result = await grant_or_extend(user_id, VPN_TRIAL_DAYS, plan_label="trial")
    db.mark_trial_used(user_id)
    return result


def fulfill_invoice_sync(inv_id: int) -> Optional[dict[str, Any]]:
    """Помечает инвойс оплаченным (идемпотентно). Продление ключа — отдельным await."""
    return db.mark_invoice_paid(inv_id)


async def fulfill_invoice(inv_id: int) -> Optional[dict[str, Any]]:
    """Полный цикл: пометить paid → продлить ключ в Marzban. None если уже обработан."""
    inv = db.mark_invoice_paid(inv_id)
    if not inv:
        return None
    user_id = int(inv["user_id"])
    days = int(inv["days"])
    tariff = get_tariff(inv["tariff_id"])
    label = tariff["title"] if tariff else inv["tariff_id"]
    try:
        granted = await grant_or_extend(user_id, days, plan_label=inv["tariff_id"])
        inv["_subscription_url"] = granted["subscription_url"]
        inv["_expires_at"] = granted["expires_at"]
        inv["_plan_label"] = label
    except Exception:
        logger.exception("fulfill_invoice: marzban grant failed for inv=%s user=%s", inv_id, user_id)
        inv["_grant_failed"] = True
    return inv


async def notify_paid(bot, inv: dict[str, Any]) -> None:
    from vpn_bot.keyboards import kb_main

    user_id = int(inv["user_id"])
    amount = int(inv["amount_rub"])
    label = inv.get("_plan_label", inv["tariff_id"])
    if inv.get("_grant_failed"):
        await bot.send_message(
            user_id,
            "✅ Оплата получена, но при выдаче ключа возникла ошибка.\n"
            "Мы уже разбираемся — ключ будет выдан вручную, извините за неудобство.",
        )
    else:
        exp = inv.get("_expires_at") or ""
        exp_str = exp[:10] if exp else "—"
        await bot.send_message(
            user_id,
            f"✅ <b>Оплата получена: {label}</b>\n"
            f"Ключ активен до <b>{exp_str}</b>.\n\n"
            f"Открой «🔑 Мой ключ» — там ссылка и QR для подключения.",
            reply_markup=kb_main(),
        )
    for admin_id in VPN_ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💵 <b>VPN: оплата (Робокасса)</b>\n{label} · <b>{amount}₽</b> · user {user_id} · inv {inv['inv_id']}",
            )
        except Exception:
            logger.warning("notify admin %s failed", admin_id)
