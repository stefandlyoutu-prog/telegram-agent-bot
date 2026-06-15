"""SEO-текст для Авито в PDF."""

import io
import re
from typing import List


def build_seo_pdf(
    title: str,
    sections: List[tuple[str, str]],
    *,
    method_note: str = "",
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    font_regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    use_unicode = False
    try:
        pdf.add_font("Arial", "", font_regular)
        pdf.add_font("ArialB", "", font_bold)
        body_font, bold_font = "Arial", "ArialB"
        use_unicode = True
    except Exception:
        body_font, bold_font = "Helvetica", "Helvetica"

    def write_block(text: str, size: int, bold: bool = False) -> None:
        font = bold_font if bold else body_font
        pdf.set_font(font, size=size)
        safe = _safe(text)
        if use_unicode:
            pdf.multi_cell(w, size * 0.45, safe)
        else:
            pdf.multi_cell(w, size * 0.45, safe.encode("latin-1", "replace").decode("latin-1"))

    write_block(title, 18, bold=True)
    pdf.ln(3)

    if method_note:
        pdf.set_text_color(110, 110, 110)
        write_block(method_note, 9)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    for heading, body in sections:
        write_block(heading, 13, bold=True)
        write_block(body, 11)
        pdf.ln(3)

    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")


def _safe(text: str) -> str:
    return text.replace("\r", "").strip() or " "


def parse_sections_from_markdown(text: str) -> List[tuple[str, str]]:
    """Разбивает ответ LLM на секции по заголовкам ## или **."""
    sections: List[tuple[str, str]] = []
    chunks = re.split(r"\n(?=##\s+|\*\*[^*]+\*\*\s*\n)", text.strip())
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split("\n", 1)
        head = lines[0].strip().strip("#").strip("*").strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if not body and len(head) > 80:
            sections.append(("Описание", head))
        elif head:
            sections.append((head[:80], body or head))
    if not sections:
        sections.append(("SEO-текст для Авито", text[:8000]))
    return sections
