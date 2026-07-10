"""Дожим «горячих» лидов: payment_intent или lock=1 без оплаты → прямо Robokassa."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.config import ORACLE_DEEP_FIRST_PRICE_RUB, ORACLE_DEEP_PRICE_RUB, robokassa_configured

logger = logging.getLogger(__name__)


def _deep_price(uid: int, *, flash_price: int | None = None) -> int:
    if db.has_paid(uid, "deep_unlock"):
        return ORACLE_DEEP_PRICE_RUB
    if flash_price is not None:
        return flash_price
    return ORACLE_DEEP_FIRST_PRICE_RUB


def _pay_url(uid: int, cont_id: int, *, flash_price: int | None = None) -> str | None:
    if not robokassa_configured():
        return None
    from oracle_bot.robokassa import build_payment_url

    price = _deep_price(uid, flash_price=flash_price)
    inv_id = db.create_invoice(uid, "deep_unlock", price, cont_id=cont_id)
    return build_payment_url(
        inv_id=inv_id,
        out_sum=price,
        description="Оракул — Сценарий 2 / полное продолжение",
        shp={"Shp_uid": str(uid), "Shp_kind": "deep_unlock"},
    )


def recovery_message(
    uid: int,
    cont_id: int,
    *,
    flash_price: int | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    price = _deep_price(uid, flash_price=flash_price)
    p = db.get_profile(uid)
    name = (p.get("name") or "друг").split()[0]
    if flash_price is not None:
        text = (
            f"⚡ <b>{name}, сегодня только — {price}₽</b>\n\n"
            "Ты уже открывал(а) оплату Сценария 2, но не завершил(а).\n"
            f"Сейчас — <b>flash-цена {price}₽</b> вместо 49₽ "
            f"(обычно {ORACLE_DEEP_PRICE_RUB}₽).\n\n"
            "🟢 Конкретные шаги на 2 недели + прогноз по твоей ситуации.\n"
            "Предложение до конца суток — одно нажатие 👇"
        )
    else:
        text = (
            f"🟢 <b>{name}, Сценарий 2 ждёт тебя</b>\n\n"
            "Ты уже видел(а) 🔴 что будет, если ничего не менять.\n"
            "В полной части — <b>конкретные шаги на 2 недели</b> и прогноз по твоей ситуации.\n\n"
            f"Открыть сейчас — <b>{price}₽</b> (одно нажатие, карта или СБП).\n"
            "Если передумал(а) — просто проигнорируй это сообщение."
        )
    url = _pay_url(uid, cont_id, flash_price=flash_price)
    label = f"💳 Открыть за {price}₽" if flash_price is None else f"⚡ Забрать за {price}₽ сегодня"
    if not url:
        return text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔓 Открыть · {price}₽", callback_data=f"deep:{cont_id}")]
        ])
    return text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, url=url)],
    ])


async def run_hot_recovery(
    bot,
    *,
    limit: int = 30,
    intent_only: bool = False,
    flash_price: int | None = None,
    hours: int = 72,
) -> dict[str, Any]:
    sent = skip = fail = 0
    details: list[str] = []
    if intent_only:
        uids = db.payment_intent_lead_ids(hours=hours)[:limit]
    else:
        uids = db.hot_lead_user_ids(hours=hours)[:limit]
    for uid in uids:
        if db.has_paid(uid, "deep_unlock"):
            skip += 1
            continue
        meta = db.get_user_meta(uid)
        if meta.get("push_opt_out"):
            skip += 1
            continue
        cont_id = db.latest_deep_intent_cont(uid)
        if not cont_id and not intent_only:
            cont_id = db.latest_locked_continuation(uid)
        if not cont_id:
            skip += 1
            continue
        text, kb = recovery_message(uid, cont_id, flash_price=flash_price)
        try:
            await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            sent += 1
            tag = f"flash={flash_price}" if flash_price is not None else "std"
            details.append(f"✔ {uid} cont={cont_id} {tag}")
            db.log_event(uid, "hot_recovery", f"cont={cont_id};{tag}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            details.append(f"✖ {uid}: {str(e)[:60]}")
    return {
        "sent": sent,
        "skip": skip,
        "fail": fail,
        "intent_only": intent_only,
        "flash_price": flash_price,
        "details": details,
    }
