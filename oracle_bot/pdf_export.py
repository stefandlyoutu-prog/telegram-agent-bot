"""Выгрузка любого разбора Оракула в PDF (довыгрузка к продукту)."""

from __future__ import annotations

import logging
import re
from datetime import date
from io import BytesIO

from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

_FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
_FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
# Render (Linux) — DejaVu обычно есть; иначе fpdf core-шрифт (латиница)
_FONT_LINUX = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_LINUX_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def build_pdf(title: str, body: str, *, footer_note: str = "") -> bytes:
    """Собирает PDF из заголовка и текста (строки/абзацы)."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    use_unicode = False
    body_font = bold_font = "Helvetica"
    import os

    pairs = [
        (_FONT_REGULAR, _FONT_BOLD),
        (_FONT_LINUX, _FONT_LINUX_BOLD),
    ]
    for reg, bold in pairs:
        if os.path.exists(reg):
            try:
                pdf.add_font("Body", "", reg)
                pdf.add_font("BodyB", "", bold if os.path.exists(bold) else reg)
                body_font, bold_font = "Body", "BodyB"
                use_unicode = True
                break
            except Exception as e:  # noqa: BLE001
                logger.warning("pdf font %s: %s", reg, e)

    w = pdf.w - pdf.l_margin - pdf.r_margin

    def write(text: str, size: int, *, bold: bool = False) -> None:
        pdf.set_font(bold_font if bold else body_font, size=size)
        safe = (text or " ").replace("\r", "")
        if not safe.strip():
            safe = " "
        if not use_unicode:
            safe = safe.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(w, size * 0.5, safe)

    write(_strip_html(title), 18, bold=True)
    pdf.ln(2)
    write(f"m-Oracul · {date.today().strftime('%d.%m.%Y')}", 9)
    pdf.ln(4)

    for block in _strip_html(body).split("\n\n"):
        block = block.strip()
        if not block:
            continue
        # короткая строка-заголовок → жирным
        if len(block) <= 60 and not block.endswith((".", "!", "?", "…")):
            write(block, 13, bold=True)
            pdf.ln(1)
        else:
            write(block, 11)
            pdf.ln(2)

    if footer_note:
        pdf.ln(4)
        pdf.set_text_color(120, 120, 120)
        write(footer_note, 9)
        pdf.set_text_color(0, 0, 0)

    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")


async def deliver_pdf(bot, user_id: int, kind: str) -> bool:
    """Отправляет ранее сохранённый разбор как PDF-файл."""
    from oracle_bot import storage as db
    from oracle_bot.keyboards import kb_main

    src = db.get_pdf_source(user_id, kind)
    if not src or not (src.get("content") or "").strip():
        try:
            await bot.send_message(
                user_id,
                "⚠️ Не нашёл разбор для PDF. Сделай разбор заново и нажми «Сохранить в PDF».",
                reply_markup=kb_main(),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("deliver_pdf no source %s: %s", user_id, e)
        return False

    title = src.get("title") or "Разбор m-Oracul"
    footer = (
        "Документ сформирован персонально по вашему запросу в m-Oracul. "
        "Не является медицинской или юридической консультацией."
    )
    try:
        pdf_bytes = build_pdf(title, src["content"], footer_note=footer)
        safe = re.sub(r"[^0-9A-Za-zА-Яа-яЁё _-]", "_", title)[:40].strip() or "razbor"
        fname = f"{safe}_{date.today().strftime('%d%m%Y')}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=fname)
        await bot.send_document(
            user_id,
            doc,
            caption=f"📄 <b>{title}</b>\nТвой разбор в PDF — можно сохранить и перечитывать.",
        )
        await bot.send_message(user_id, "✅ Готово.", reply_markup=kb_main())
        return True
    except Exception as e:  # noqa: BLE001
        logger.exception("deliver_pdf build %s: %s", user_id, e)
        try:
            await bot.send_message(
                user_id,
                "⚠️ Не удалось собрать PDF. Напиши администратору.",
                reply_markup=kb_main(),
            )
        except Exception:  # noqa: BLE001
            pass
        return False
