"""PDF «Книга о тебе» для Ultra Plus."""

from __future__ import annotations

from oracle_bot.fonts import register_pdf_font
from oracle_bot.ultra_plus.assembler import BookSection


def build_book_pdf(profile_name: str, sections: list[BookSection]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)

    body_font, bold_font, use_unicode = register_pdf_font(pdf)
    w = pdf.w - pdf.l_margin - pdf.r_margin

    def write(text: str, size: int, *, bold: bool = False, lh: float = 0.52) -> None:
        pdf.set_font(bold_font if bold else body_font, size=size)
        safe = (text or " ").replace("\r", "").strip() or " "
        if not use_unicode:
            safe = safe.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(w, size * lh, safe)

    for i, sec in enumerate(sections):
        pdf.add_page()
        if i == 0:
            pdf.ln(60)
            write(sec.title, 26, bold=True)
            pdf.ln(6)
            write(sec.body, 12)
            continue
        write(sec.title, 17, bold=True)
        pdf.ln(3)
        for block in (sec.body or "").split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if block.startswith("## "):
                pdf.ln(1)
                write(block[3:].strip(), 13, bold=True)
                pdf.ln(1)
            elif len(block) <= 48 and not block.endswith((".", "!", "?", "…", ":", ")")):
                pdf.ln(1)
                write(block, 13, bold=True)
            else:
                write(block, 11)
                pdf.ln(2)

    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")
