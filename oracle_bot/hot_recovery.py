"""Дожим «горячих» лидов: payment_intent или lock=1 без оплаты → прямо Robokassa."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.config import ORACLE_DEEP_FIRST_PRICE_RUB, ORACLE_DEEP_PRICE_RUB, robokassa_configured

logger = logging.getLogger(__name__)


def _deep_price(uid: int) -> int:
    if not db.has_paid(uid, "deep_unlock"):
        return ORACLE_DEEP_FIRST_PRICE_RUB
    return ORACLE_DEEP_PRICE_RUB


def _pay_url(uid: int, cont_id: int) -> str | None:
    if not robokassa_configured():
        return None
    from oracle_bot.robokassa import build_payment_url

    price = _deep_price(uid)
    inv_id = db.create_invoice(uid, "deep_unlock", price, cont_id=cont_id)
    return build_payment_url(
        inv_id=inv_id,
        out_sum=price,
        description="Оракул — Сценарий 2 / полное продолжение",
        shp={"Shp_uid": str(uid), "Shp_kind": "deep_unlock"},
    )


def recovery_message(uid: int, cont_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    price = _deep_price(uid)
    p = db.get_profile(uid)
    name = (p.get("name") or "друг").split()[0]
    text = (
        f"🟢 <b>{name}, Сценарий 2 ждёт тебя</b>\n\n"
        "Ты уже видел(а) 🔴 что будет, если ничего не менять.\n"
        "В полной части — <b>конкретные шаги на 2 недели</b> и прогноз по твоей ситуации.\n\n"
        f"Открыть сейчас — <b>{price}₽</b> (одно нажатие, карта или СБП).\n"
        "Если передумал(а) — просто проигнорируй это сообщение."
    )
    url = _pay_url(uid, cont_id)
    if not url:
        return text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔓 Открыть · {price}₽", callback_data=f"deep:{cont_id}")]
        ])
    return text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Открыть Сценарий 2 · {price}₽", url=url)],
    ])


async def run_hot_recovery(bot, *, limit: int = 30) -> dict[str, Any]:
    sent = skip = fail = 0
    details: list[str] = []
    for uid in db.hot_lead_user_ids(hours=72)[:limit]:
        if db.has_paid(uid, "deep_unlock"):
            skip += 1
            continue
        meta = db.get_user_meta(uid)
        if meta.get("push_opt_out"):
            skip += 1
            continue
        cont_id = db.latest_deep_intent_cont(uid) or db.latest_locked_continuation(uid)
        if not cont_id:
            skip += 1
            continue
        text, kb = recovery_message(uid, cont_id)
        try:
            await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            sent += 1
            details.append(f"✔ {uid} cont={cont_id}")
            db.log_event(uid, "hot_recovery", f"cont={cont_id}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            details.append(f"✖ {uid}: {str(e)[:60]}")
    return {"sent": sent, "skip": skip, "fail": fail, "details": details}
