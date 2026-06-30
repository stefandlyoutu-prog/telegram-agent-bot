"""Премиальная вёрстка персональной книги в PDF (обложка, главы, акцент)."""

from __future__ import annotations

import logging
import re

from oracle_bot.fonts import unicode_font_paths

logger = logging.getLogger(__name__)

# Эмодзи/пиктограммы отсутствуют в DejaVu — убираем, чтобы не было «?»/предупреждений.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\u2190-\u21ff\u2b00-\u2bff\u2300-\u23ff\u2700-\u27bf\ufe0f\u20e3]"
)


def _strip_emoji(s: str) -> str:
    return _EMOJI.sub("", s or "")

ACCENT = (74, 47, 109)      # глубокий фиолетовый
GOLD = (164, 132, 67)       # тёплое золото
INK = (38, 34, 46)          # почти чёрный — основной текст
GREY = (150, 150, 150)


def _new_pdf():
    from fpdf import FPDF

    class _BookPDF(FPDF):
        body = bold = "Helvetica"
        uni = False
        accent = ACCENT

        def setup(self) -> None:
            reg, bld = unicode_font_paths()
            if reg:
                try:
                    self.add_font("Body", "", reg)
                    self.add_font("BodyB", "", bld)
                    self.body, self.bold, self.uni = "Body", "BodyB", True
                except Exception as e:  # noqa: BLE001
                    logger.warning("book pdf font: %s", e)

        def footer(self) -> None:  # номер страницы (кроме обложки)
            if self.page_no() <= 1:
                return
            self.set_y(-14)
            self.set_font(self.body, size=8)
            self.set_text_color(*GREY)
            self.cell(0, 8, str(self.page_no() - 1), align="C")

    return _BookPDF(orientation="P", unit="mm", format="A4")


def _build_book(
    *,
    title: str,
    subtitle: str,
    author_line: str,
    chapters: list[tuple[str, str, str]],
    accent: tuple[int, int, int],
    footer_note: str,
    toc_entries: list[tuple[str, int]] | None,
):
    """Собирает документ. Возвращает (pdf, chapter_start_pages).

    Если toc_entries=None — страница содержания не вставляется (проход 1, замер
    номеров страниц). Иначе вставляется готовое оглавление (проход 2).
    """
    pdf = _new_pdf()
    pdf.accent = accent
    pdf.set_margins(24, 24, 24)
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.setup()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    cx = pdf.w / 2

    def txt(s: str) -> str:
        s = _strip_emoji((s or "").replace("\r", ""))
        return s if pdf.uni else s.encode("latin-1", "replace").decode("latin-1")

    def para(s: str, size: float, *, bold: bool = False, color=INK, align: str = "J", lh: float = 1.6) -> None:
        pdf.set_font(pdf.bold if bold else pdf.body, size=size)
        pdf.set_text_color(*color)
        pdf.multi_cell(w, size * lh * 0.35, txt(s.strip() or " "), align=align)

    def rule(width_mm: float, color=accent, thick: float = 0.6) -> None:
        pdf.set_draw_color(*color)
        pdf.set_line_width(thick)
        x0 = cx - width_mm / 2
        pdf.line(x0, pdf.get_y(), x0 + width_mm, pdf.get_y())

    # --- Обложка ---
    pdf.add_page()
    pdf.ln(52)
    rule(34, color=GOLD, thick=0.8)
    pdf.ln(10)
    pdf.set_font(pdf.bold, size=30)
    pdf.set_text_color(*accent)
    pdf.multi_cell(w, 13, txt(title), align="C")
    pdf.ln(4)
    if subtitle:
        pdf.set_font(pdf.body, size=13)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(w, 7, txt(subtitle), align="C")
    pdf.ln(8)
    rule(18, color=GOLD, thick=0.6)
    pdf.ln(10)
    if author_line:
        pdf.set_font(pdf.bold, size=14)
        pdf.set_text_color(*INK)
        pdf.multi_cell(w, 8, txt(author_line), align="C")
    pdf.set_y(-32)
    pdf.set_font(pdf.body, size=9)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(w, 5, txt("m-Oracul · персональная книга-разбор"), align="C")

    # --- Содержание (проход 2) ---
    if toc_entries is not None:
        pdf.add_page()
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        pdf.set_font(pdf.bold, size=10)
        pdf.set_text_color(*GOLD)
        pdf.cell(0, 6, txt("СОДЕРЖАНИЕ"))
        pdf.ln(11)
        pdf.set_font(pdf.bold, size=22)
        pdf.set_text_color(*accent)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w, 10, txt("Оглавление"), align="L")
        pdf.ln(1)
        pdf.set_draw_color(*accent)
        pdf.set_line_width(0.5)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + w, pdf.get_y())
        pdf.ln(8)
        for i, (ename, epage) in enumerate(toc_entries, start=1):
            pdf.set_x(pdf.l_margin)
            y = pdf.get_y()
            pdf.set_font(pdf.bold, size=12)
            pdf.set_text_color(*GOLD)
            pdf.cell(10, 8, txt(f"{i}"))
            pdf.set_font(pdf.body, size=12)
            pdf.set_text_color(*INK)
            pdf.cell(w - 10 - 12, 8, txt(ename))
            pdf.set_text_color(*GREY)
            pdf.cell(12, 8, str(epage), align="R")
            pdf.set_xy(pdf.l_margin, y + 9)

    # --- Главы ---
    total = len(chapters)
    chapter_pages: list[int] = []
    for i, (ctitle, body, epigraph) in enumerate(chapters, start=1):
        pdf.add_page()
        chapter_pages.append(pdf.page_no())
        pdf.set_font(pdf.bold, size=10)
        pdf.set_text_color(*GOLD)
        pdf.cell(0, 6, txt(f"ГЛАВА {i} ИЗ {total}"))
        pdf.ln(9)
        pdf.set_font(pdf.bold, size=21)
        pdf.set_text_color(*accent)
        pdf.multi_cell(w, 10, txt(ctitle), align="L")
        pdf.ln(2)
        rule(w, color=accent, thick=0.5)
        pdf.set_x(pdf.l_margin)
        pdf.ln(6)

        if epigraph:
            inset = 14
            pdf.set_left_margin(pdf.l_margin + inset)
            pdf.set_x(pdf.l_margin + inset)
            pdf.set_font(pdf.body, size=11.5)
            pdf.set_text_color(*GOLD)
            pdf.multi_cell(w - inset * 2, 6.2, txt("« " + epigraph.strip(" «»\"") + " »"), align="C")
            pdf.set_left_margin(pdf.l_margin)
            pdf.set_x(pdf.l_margin)
            pdf.ln(4)
            rule(20, color=GOLD, thick=0.4)
            pdf.set_x(pdf.l_margin)
            pdf.ln(6)

        for block in (body or "").split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if block.startswith("## "):
                pdf.ln(2)
                para(block[3:].strip(), 13, bold=True, color=accent, align="L", lh=1.4)
                pdf.ln(1)
            else:
                para(block, 11.5, color=INK, align="J", lh=1.65)
                pdf.ln(2.4)

    if footer_note:
        pdf.add_page()
        pdf.ln(4)
        para(footer_note, 9, color=GREY, align="L")

    return pdf, chapter_pages


def render_book_pdf(
    *,
    title: str,
    subtitle: str,
    author_line: str,
    chapters,  # list[tuple[str, str]] | list[tuple[str, str, str]] (title, body[, epigraph])
    accent: tuple[int, int, int] = ACCENT,
    footer_note: str = "",
) -> bytes:
    # нормализуем главы к (title, body, epigraph)
    norm: list[tuple[str, str, str]] = []
    for ch in chapters:
        if len(ch) >= 3:
            norm.append((ch[0], ch[1], ch[2] or ""))
        else:
            norm.append((ch[0], ch[1], ""))
    chapters = norm

    common = dict(
        title=title, subtitle=subtitle, author_line=author_line,
        chapters=chapters, accent=accent, footer_note=footer_note,
    )

    # Проход 1 — без оглавления, чтобы узнать страницы глав.
    _, pages1 = _build_book(**common, toc_entries=None)
    # В проходе 2 добавляется страница содержания после обложки → все главы +1.
    # Видимый номер в подвале = page_no() - 1, поэтому видимая страница главы = pages1[i].
    toc_entries = [(ctitle, pages1[i]) for i, (ctitle, _b, _e) in enumerate(chapters)]

    # Проход 2 — финальный документ с оглавлением.
    pdf, _ = _build_book(**common, toc_entries=toc_entries)

    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")


# --- Кодирование/разбор глав для хранения в pdf_source ---

_T, _S, _A, _C, _E = "@@TITLE@@", "@@SUB@@", "@@AUTHOR@@", "@@CH@@", "@@EP@@"


def encode_book(title: str, subtitle: str, author_line: str, chapters) -> str:
    """chapters: list[(title, body)] или list[(title, body, epigraph)]."""
    out = [f"{_T}{title}", f"{_S}{subtitle}", f"{_A}{author_line}"]
    for ch in chapters:
        ctitle, body = ch[0], ch[1]
        epigraph = ch[2] if len(ch) >= 3 else ""
        out.append(f"{_C}{ctitle}")
        if epigraph:
            out.append(f"{_E}{epigraph.strip()}")
        out.append(body.strip())
    return "\n".join(out)


def is_encoded_book(content: str) -> bool:
    return _C in (content or "")


def decode_book(content: str) -> dict:
    title = subtitle = author = ""
    chapters: list[tuple[str, str, str]] = []
    cur_title: str | None = None
    cur_ep = ""
    cur_body: list[str] = []

    def flush() -> None:
        if cur_title is not None:
            chapters.append((cur_title, "\n".join(cur_body).strip(), cur_ep))

    for line in (content or "").splitlines():
        if line.startswith(_T):
            title = line[len(_T):].strip()
        elif line.startswith(_S):
            subtitle = line[len(_S):].strip()
        elif line.startswith(_A):
            author = line[len(_A):].strip()
        elif line.startswith(_C):
            flush()
            cur_title = line[len(_C):].strip()
            cur_ep = ""
            cur_body = []
        elif line.startswith(_E):
            cur_ep = line[len(_E):].strip()
        else:
            if cur_title is not None:
                cur_body.append(line)
    flush()
    return {"title": title, "subtitle": subtitle, "author": author, "chapters": chapters}
