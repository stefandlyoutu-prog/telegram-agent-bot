"""PDF «Книга о тебе» для Ultra Plus."""

from __future__ import annotations

from oracle_bot.ultra_plus.assembler import BookSection


def build_book_pdf(profile_name: str, sections: list[BookSection]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)

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

    w = pdf.w - pdf.l_margin - pdf.r_margin

    def write(text: str, size: int, *, bold: bool = False) -> None:
        pdf.set_font(bold_font if bold else body_font, size=size)
        safe = (text or " ").replace("\r", "").strip() or " "
        if use_unicode:
            pdf.multi_cell(w, size * 0.42, safe)
        else:
            pdf.multi_cell(w, size * 0.42, safe.encode("latin-1", "replace").decode("latin-1"))

    for i, sec in enumerate(sections):
        pdf.add_page()
        if i == 0:
            write(sec.title, 20, bold=True)
            pdf.ln(4)
            write(sec.body, 11)
        else:
            write(sec.title, 15, bold=True)
            pdf.ln(3)
            write(sec.body, 10)

    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")
