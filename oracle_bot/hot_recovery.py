"""Дожим «горячих» лидов: payment_intent / lock / незакрытый Сценарий 2 → Robokassa."""

from __future__ import annotations

import logging
from typing import Any, Literal

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.config import ORACLE_DEEP_FIRST_PRICE_RUB, ORACLE_DEEP_PRICE_RUB, robokassa_configured

logger = logging.getLogger(__name__)

Variant = Literal["flash", "last_chance", "std"]


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
    variant: Variant = "flash",
) -> tuple[str, InlineKeyboardMarkup | None]:
    price = _deep_price(uid, flash_price=flash_price)
    p = db.get_profile(uid)
    name = (p.get("name") or "друг").split()[0]

    if variant == "last_chance":
        text = (
            f"⏱ <b>{name}, последнее напоминание</b>\n\n"
            f"Сценарий 2 всё ещё закрыт 🔒 — а у тебя уже есть 🔴 часть.\n"
            f"Открыть 🟢 шаги на 2 недели сейчас — <b>{price}₽</b> "
            f"(вместо {ORACLE_DEEP_PRICE_RUB}₽).\n\n"
            "После этого сообщения спеццену не повторяю. Одно нажатие 👇"
        )
    elif flash_price is not None or variant == "flash":
        text = (
            f"⚡ <b>{name}, сегодня — {price}₽</b>\n\n"
            "Ты уже видел(а) 🔴 Сценарий 1. Полная часть ждёт:\n"
            "🟢 что изменить и конкретные шаги на 2 недели.\n\n"
            f"<b>{price}₽</b> вместо {ORACLE_DEEP_PRICE_RUB}₽ · карта или СБП 👇"
        )
    else:
        text = (
            f"🟢 <b>{name}, Сценарий 2 ждёт тебя</b>\n\n"
            "Ты уже видел(а) 🔴 что будет, если ничего не менять.\n"
            "В полной части — <b>конкретные шаги на 2 недели</b>.\n\n"
            f"Открыть — <b>{price}₽</b> (карта или СБП) 👇"
        )

    url = _pay_url(uid, cont_id, flash_price=flash_price if flash_price is not None else None)
    if flash_price is not None or variant in ("flash", "last_chance"):
        label = f"⚡ Забрать за {price}₽"
    else:
        label = f"💳 Открыть за {price}₽"
    if not url:
        return text, InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🔓 Открыть · {price}₽", callback_data=f"deep:{cont_id}")]
            ]
        )
    return text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def _pick_uids(*, intent_only: bool, hours: int, limit: int) -> list[int]:
    if intent_only:
        return db.payment_intent_lead_ids(hours=hours)[:limit]
    # Сначала «горячие» по событиям, потом все с незакрытым lock
    seen: set[int] = set()
    out: list[int] = []
    for uid in db.hot_lead_user_ids(hours=hours) + db.locked_continuation_lead_ids(limit=limit * 2):
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
        if len(out) >= limit:
            break
    return out


async def run_hot_recovery(
    bot,
    *,
    limit: int = 30,
    intent_only: bool = False,
    flash_price: int | None = None,
    hours: int = 72,
    skip_recent_hours: int = 18,
    second_nudge: bool = True,
) -> dict[str, Any]:
    """Дожим.

    skip_recent_hours — не спамить тем, кому уже слали recovery недавно.
    second_nudge — кому слали 18–72ч назад и не купили — «последний шанс».
    """
    sent = skip = fail = 0
    details: list[str] = []
    uids = _pick_uids(intent_only=intent_only, hours=hours, limit=limit)

    for uid in uids:
        if db.has_paid(uid, "deep_unlock"):
            skip += 1
            continue
        if db.is_bot_blocked(uid):
            skip += 1
            continue
        meta = db.get_user_meta(uid)
        if meta.get("push_opt_out"):
            skip += 1
            continue

        recent = db.hours_since_event(uid, "hot_recovery")
        if recent is not None and recent < skip_recent_hours:
            skip += 1
            continue

        cont_id = db.latest_deep_intent_cont(uid)
        if not cont_id and not intent_only:
            cont_id = db.latest_locked_continuation(uid)
        if not cont_id:
            skip += 1
            continue

        variant: Variant = "flash"
        if second_nudge and recent is not None and skip_recent_hours <= recent < 72:
            variant = "last_chance"

        fp = flash_price if flash_price is not None else (
            ORACLE_DEEP_FIRST_PRICE_RUB if variant in ("flash", "last_chance") else None
        )
        text, kb = recovery_message(uid, cont_id, flash_price=fp, variant=variant)
        try:
            await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            sent += 1
            tag = f"{variant};flash={fp}"
            details.append(f"✔ {uid} cont={cont_id} {tag}")
            db.log_event(uid, "hot_recovery", f"cont={cont_id};{tag}")
        except TelegramForbiddenError:
            fail += 1
            db.mark_bot_blocked(uid)
            details.append(f"✖ {uid}: blocked")
        except Exception as e:  # noqa: BLE001
            fail += 1
            err = str(e)[:60]
            if "blocked" in err.lower() or "Forbidden" in err:
                db.mark_bot_blocked(uid)
            details.append(f"✖ {uid}: {err}")

    return {
        "sent": sent,
        "skip": skip,
        "fail": fail,
        "intent_only": intent_only,
        "flash_price": flash_price,
        "pool": len(uids),
        "details": details,
    }


async def run_winback_broadcast(
    bot,
    *,
    flash_price: int = 19,
    limit: int = 200,
) -> dict[str, Any]:
    """Мягкая рассылка по живой базе: CTA в 2 сценария + премиум (без спама blocked)."""
    from oracle_bot.config import ORACLE_PREMIUM_PRICE_RUB

    text = (
        f"⚡ <b>Сегодня Сценарий 2 — от {flash_price}₽</b>\n\n"
        "🔴 что будет, если ничего не менять\n"
        "🟢 что изменить и шаги на 2 недели\n\n"
        f"Первая часть бесплатно → углубление <b>{flash_price}₽</b> "
        f"(обычно {ORACLE_DEEP_PRICE_RUB}₽).\n"
        f"Или Премиум без 🔒 — {ORACLE_PREMIUM_PRICE_RUB}₽ / 30 дней."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴🟢 2 сценария — начать", callback_data="nav:awareness")],
            [
                InlineKeyboardButton(
                    text=f"⭐ Премиум · {ORACLE_PREMIUM_PRICE_RUB}₽",
                    callback_data="mod:premium",
                )
            ],
        ]
    )
    ok = fail = skip = 0
    details: list[str] = []
    for uid in db.broadcast_candidate_ids(limit=limit):
        if db.is_bot_blocked(uid) or db.is_premium(uid):
            skip += 1
            continue
        # Не дублировать тех, кому только что слали deep-recovery
        recent = db.hours_since_event(uid, "hot_recovery")
        if recent is not None and recent < 6:
            skip += 1
            continue
        try:
            await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            ok += 1
            db.log_event(uid, "winback_broadcast", f"flash={flash_price}")
            details.append(f"✔ {uid}")
        except TelegramForbiddenError:
            fail += 1
            db.mark_bot_blocked(uid)
            details.append(f"✖ {uid}: blocked")
        except Exception as e:  # noqa: BLE001
            fail += 1
            details.append(f"✖ {uid}: {str(e)[:50]}")
        import asyncio

        await asyncio.sleep(0.05)
    return {"ok": ok, "fail": fail, "skip": skip, "details": details[:40]}
