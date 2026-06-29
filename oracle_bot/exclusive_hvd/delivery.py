"""Доставка отчёта ХВД в Telegram после оплаты."""

from __future__ import annotations

import logging
from datetime import datetime

from oracle_bot import storage as db
from oracle_bot.exclusive_hvd import build_report_parts, calculate
from oracle_bot.keyboards import kb_main

logger = logging.getLogger(__name__)


async def deliver_hvd_report(bot, user_id: int) -> bool:
    pending = db.get_hvd_pending(user_id)
    if not pending:
        try:
            await bot.send_message(
                user_id,
                "⚠️ Данные для разбора не найдены. Зайди в меню → "
                "<b>Эксклюзив HVD</b> и введи имя с датой рождения заново.",
                reply_markup=kb_main(),
            )
        except Exception as e:
            logger.warning("deliver_hvd no pending %s: %s", user_id, e)
        return False

    try:
        birth = datetime.strptime(pending["birth_date"], "%Y-%m-%d").date()
    except ValueError:
        await bot.send_message(user_id, "⚠️ Некорректная дата. Запроси разбор заново.", reply_markup=kb_main())
        return False

    try:
        profile = calculate(pending["name"], birth)
    except ValueError as e:
        await bot.send_message(user_id, f"⚠️ {e}", reply_markup=kb_main())
        return False

    parts = build_report_parts(profile)
    try:
        for chunk in parts:
            await bot.send_message(user_id, chunk)
        await bot.send_message(user_id, "✅ Полный разбор ХВД готов.", reply_markup=kb_main())
    except Exception as e:
        logger.exception("deliver_hvd send %s: %s", user_id, e)
        return False

    db.clear_hvd_pending(user_id)
    return True
