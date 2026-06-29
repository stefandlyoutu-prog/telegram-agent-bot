"""Выдача доступа по оплаченному инвойсу (Робокасса) — идемпотентно."""

from __future__ import annotations

import logging
from typing import Any, Optional

from oracle_bot import storage as db

logger = logging.getLogger(__name__)

_PREMIUM_PUSHES = [
    "unlock_tease",
    "limit_hit",
    "welcome_day1",
    "welcome_day2",
    "inactive",
    "referral_nudge",
]


def fulfill_invoice(inv_id: int) -> Optional[dict[str, Any]]:
    """Помечает инвойс оплаченным и выдаёт доступ ОДИН раз.

    Возвращает обогащённый инвойс, если выдача произошла впервые, иначе None.
    """
    inv = db.mark_invoice_paid(inv_id)
    if not inv:
        return None

    uid = int(inv["user_id"])
    kind = inv["kind"]
    amount = int(inv["amount_rub"])

    if kind == "premium_30d":
        db.grant_premium(uid, days=30)
        db.record_payment(uid, "premium_30d", 0, f"robokassa:{inv_id}", currency="RUB", amount=amount)
        db.cancel_pushes(uid, _PREMIUM_PUSHES)
        try:
            from oracle_bot.pushes import schedule_premium_renewal

            schedule_premium_renewal(uid, days=30)
        except Exception as e:
            logger.warning("renewal schedule: %s", e)
    elif kind == "deep_unlock":
        cont = None
        if inv.get("cont_id"):
            cont = db.unlock_continuation(int(inv["cont_id"]), uid)
        db.record_payment(uid, "deep_unlock", 0, f"robokassa:{inv_id}", currency="RUB", amount=amount)
        db.cancel_pushes(uid, ["unlock_tease", "limit_hit"])
        inv["_locked_text"] = cont["locked_text"] if cont else ""
        inv["_module"] = cont["module"] if cont else ""
    elif kind == "exclusive_hvd":
        db.record_payment(uid, "exclusive_hvd", 0, f"robokassa:{inv_id}", currency="RUB", amount=amount)
        inv["_deliver_hvd"] = True
    elif kind == "ultra_plus":
        db.record_payment(uid, "ultra_plus", 0, f"robokassa:{inv_id}", currency="RUB", amount=amount)
        inv["_deliver_ultra_plus"] = True
    else:
        logger.warning("fulfill_invoice: неизвестный kind=%s inv=%s", kind, inv_id)
    return inv


async def notify_paid(bot, inv: dict[str, Any]) -> None:
    """Сообщение пользователю + админам после успешной оплаты картой."""
    uid = int(inv["user_id"])
    kind = inv["kind"]
    amount = int(inv["amount_rub"])
    try:
        from oracle_bot.keyboards import kb_after_reading, kb_main

        if kind == "premium_30d":
            await bot.send_message(
                uid,
                "✅ <b>Премиум на 30 дней активирован!</b>\n"
                "Все разделы без лимита · продолжения без 🔒\n"
                "Выбирай что угодно 👇",
                reply_markup=kb_main(),
            )
        elif kind == "deep_unlock":
            locked = inv.get("_locked_text") or ""
            module = inv.get("_module") or ""
            if locked:
                await bot.send_message(
                    uid,
                    "🔓 <b>Продолжение открыто:</b>\n\n" + locked,
                    reply_markup=kb_after_reading(module, None, uid),
                )
            else:
                await bot.send_message(
                    uid,
                    "✅ Оплата получена. Чтение устарело — запроси новое из меню.",
                    reply_markup=kb_main(),
                )
        elif kind == "exclusive_hvd":
            from oracle_bot.exclusive_hvd.delivery import deliver_hvd_report

            await bot.send_message(uid, "✅ Оплата получена. Формирую полный разбор ХВД…")
            await deliver_hvd_report(bot, uid)
        elif kind == "ultra_plus":
            from oracle_bot.ultra_plus.delivery import deliver_ultra_plus_book

            await bot.send_message(uid, "✅ Оплата получена. Собираю персональную книгу PDF…")
            await deliver_ultra_plus_book(bot, uid)
    except Exception as e:
        logger.warning("notify_paid user %s: %s", uid, e)

    try:
        from oracle_bot.admin_notify import notify_admins

        label = (
            "Премиум 30д"
            if kind == "premium_30d"
            else "🔓 Продолжение"
            if kind == "deep_unlock"
            else "🔮 Эксклюзив HVD"
            if kind == "exclusive_hvd"
            else "📖 Ultra Plus"
        )
        await notify_admins(
            bot,
            f"💵 <b>Оракул: оплата картой (Робокасса)</b>\n"
            f"{label} · <b>{amount}₽</b> · user {uid} · inv {inv['inv_id']}",
        )
    except Exception as e:
        logger.warning("notify_paid admin: %s", e)
