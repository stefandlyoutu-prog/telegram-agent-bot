"""Доставка PDF Ultra Plus в Telegram."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO

from aiogram.types import BufferedInputFile

from oracle_bot import storage as db
from oracle_bot.keyboards import kb_main
from oracle_bot.ultra_plus.calculator import calculate
from oracle_bot.ultra_plus.narrative import book_for_pdf, build_book_sections_async

logger = logging.getLogger(__name__)


def _render_ultra_pdf(profile, sections) -> tuple[bytes, str]:
    """Богатый PDF (обложка + оглавление + главы с эпиграфами). Возвращает (bytes, encoded)."""
    from oracle_bot.book_pdf import decode_book, render_book_pdf

    encoded = book_for_pdf(profile, sections)
    meta = decode_book(encoded)
    footer = (
        "Персональная книга по методике Матрицы Судьбы (22 аркана). "
        "Сформирована индивидуально по вашей дате рождения в m-Oracul. "
        "Не является медицинской или юридической консультацией."
    )
    if not meta["chapters"]:
        # запасной путь — старый компоновщик
        from oracle_bot.ultra_plus.pdf_builder import build_book_pdf

        return build_book_pdf(profile.name, sections), encoded
    pdf_bytes = render_book_pdf(
        title=meta["title"],
        subtitle=meta["subtitle"],
        author_line=meta["author"],
        chapters=meta["chapters"],
        footer_note=footer,
    )
    return pdf_bytes, encoded


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
        sections = await build_book_sections_async(profile)
        pdf_bytes, encoded = _render_ultra_pdf(profile, sections)
        chapters_n = encoded.count("@@CH@@")
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in profile.name)[:40]
        fname = f"Kniga_{safe_name}_{profile.birth.strftime('%d%m%Y')}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=fname)
        await bot.send_document(
            user_id,
            doc,
            caption=(
                f"📖 <b>Ultra Plus — Книга о тебе</b>\n"
                f"👤 {profile.name} · {profile.birth.strftime('%d.%m.%Y')}\n\n"
                f"Персональная книга по Матрице Судьбы · {chapters_n} глав с оглавлением."
            ),
        )
        _save_followup(user_id, profile.name, sections, encoded)
        from oracle_bot.keyboards import kb_book_done

        await bot.send_message(
            user_id,
            "✅ Книга готова. Храни файл — повтор бесплатно только через поддержку.\n\n"
            "💬 Что-то непонятно в книге? Напиши вопрос — отвечу по твоему разбору.",
            reply_markup=kb_book_done(),
        )
    except Exception as e:
        logger.exception("ultra_plus deliver %s: %s", user_id, e)
        await bot.send_message(user_id, "⚠️ Не удалось собрать PDF. Напиши администратору.", reply_markup=kb_main())
        return False

    db.clear_ultra_plus_pending(user_id)
    return True


def _save_followup(user_id: int, name: str, sections, encoded: str = "") -> None:
    parts = []
    for s in sections:
        parts.append(f"{getattr(s, 'title', '')}\n{getattr(s, 'body', '')}")
    full = "\n\n".join(parts).strip()
    try:
        db.save_session(
            user_id,
            module="ultra_plus",
            snippet=full[:500],
            last_context=full[:3500],
        )
        if encoded:
            db.save_pdf_source(user_id, "ultra_plus", f"Книга о тебе — {name}", encoded)
    except Exception as e:
        logger.warning("ultra followup save %s: %s", user_id, e)
