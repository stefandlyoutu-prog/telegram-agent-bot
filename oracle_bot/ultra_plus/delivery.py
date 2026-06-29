"""Доставка PDF Ultra Plus в Telegram."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO

from aiogram.types import BufferedInputFile

from oracle_bot import storage as db
from oracle_bot.keyboards import kb_main
from oracle_bot.ultra_plus.assembler import build_book_sections
from oracle_bot.ultra_plus.calculator import calculate
from oracle_bot.ultra_plus.pdf_builder import build_book_pdf

logger = logging.getLogger(__name__)


async def deliver_ultra_plus_book(bot, user_id: int) -> bool:
    pending = db.get_ultra_plus_pending(user_id)
    if not pending:
        try:
            await bot.send_message(
                user_id,
                "⚠️ Данные для книги не найдены. Меню → <b>Ultra Plus</b> — введи имя и дату заново.",
                reply_markup=kb_main(),
            )
        except Exception as e:
            logger.warning("ultra_plus no pending %s: %s", user_id, e)
        return False

    try:
        birth = datetime.strptime(pending["birth_date"], "%Y-%m-%d").date()
    except ValueError:
        await bot.send_message(user_id, "⚠️ Некорректная дата. Запроси книгу заново.", reply_markup=kb_main())
        return False

    try:
        profile = calculate(pending["name"], birth)
    except ValueError as e:
        await bot.send_message(user_id, f"⚠️ {e}", reply_markup=kb_main())
        return False

    try:
        sections = build_book_sections(profile)
        pdf_bytes = build_book_pdf(profile.name, sections)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in profile.name)[:40]
        fname = f"Kniga_{safe_name}_{profile.birth.strftime('%d%m%Y')}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=fname)
        await bot.send_document(
            user_id,
            doc,
            caption=(
                f"📖 <b>Ultra Plus — Книга о тебе</b>\n"
                f"👤 {profile.name} · {profile.birth.strftime('%d.%m.%Y')}\n\n"
                f"Персональный PDF по Матрице Судьбы ({len(sections)} разделов)."
            ),
        )
        await bot.send_message(user_id, "✅ Книга готова. Храни файл — повтор бесплатно только через поддержку.", reply_markup=kb_main())
    except Exception as e:
        logger.exception("ultra_plus deliver %s: %s", user_id, e)
        await bot.send_message(user_id, "⚠️ Не удалось собрать PDF. Напиши администратору.", reply_markup=kb_main())
        return False

    db.clear_ultra_plus_pending(user_id)
    return True
