"""Полный архив дачных наборов 20×20: 4 продукта, PDF 3 вида, 3MF, Avito, экономика."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Any

from bot.services.dacha_products_proposal import PRODUCTS, TUBE, ProductOffer
from bot.services.dacha_trellis_kit import (
    CONNECTOR_LABELS_RU,
    DEFAULT_SPEC,
    TrellisSpec,
    build_kit_pdf,
    export_connectors_3mf_split_counts,
    export_connector_stls_for_counts,
    _draw_node,
    _draw_trellis_front,
)


@dataclass(frozen=True)
class DachaKit:
    folder: str
    title: str
    profile_cuts: List[Tuple[str, float, int]]
    connector_counts: Dict[str, int]
    bolt_sets: int
    dimensions: str
    assembly_steps: List[Tuple[str, str]]
    avito_title: str
    avito_price: str
    avito_body: str
    draw_3views: Callable  # (pdf, uni, bf, bb) -> None
    offer_id: str
    extra_notes: str = ""


def _ladder_counts(width_rungs: int = 5) -> Dict[str, int]:
    return {
        "corner_90": 4,
        "bracket_rung": max(0, (width_rungs - 2) * 2),
        "foot_base": 2,
    }


SHPALERA = DachaKit(
    folder="01-shpalera-tomat-2",
    title="Шпалера «Томат-2» 60×200 см",
    profile_cuts=[("СТ-В", 2000, 2), ("ПР-Г", 600, 5)],
    connector_counts=_ladder_counts(5),
    bolt_sets=24,
    dimensions="60×200 см (ширина×высота)",
    assembly_steps=[
        ("Шаг 1", "Разложите 2 стойки 200 см и 5 перемычек 60 см по маркировке."),
        ("Шаг 2", "Низ: опора + нижняя перемычка на 10 см — углы 90°."),
        ("Шаг 3", "Верх на 190 см — углы 90°. Середина — кронштейны на 50/100/150 см."),
        ("Шаг 4", "Затяните M5, подвяжите шпагат зигзагом."),
    ],
    avito_title="Шпалера для томатов 2 м — набор 20×20, Солнечногорск",
    avito_price="5 900 – 6 900 руб.",
    avito_body=(
        "Готовый набор: профиль нарезан, 12 коннекторов PETG, болты M5, PDF с чертежами 3 вида.\n"
        "Сборка ~1 ч. Для томатов, огурцов, гороха."
    ),
    draw_3views=lambda pdf, uni, bf, bb: _draw_shpalera_3views(pdf, uni, bf, bb),
    offer_id="shpalera-tomat-2",
)

GRYADKA = DachaKit(
    folder="02-gryadka-2x1",
    title="Каркас высокой грядки 200×100×25 см",
    profile_cuts=[("ДЛ-2М", 2000, 2), ("КР-1М", 1000, 2), ("СТ-25", 250, 4)],
    connector_counts={"corner_post": 4, "bracket_rung": 4},
    bolt_sets=20,
    dimensions="200×100×25 см (длина×ширина×высота борта)",
    assembly_steps=[
        ("Шаг 1", "Соберите прямоугольник на земле: 2×200 см + 2×100 см в углах corner_post."),
        ("Шаг 2", "Вставьте 4 стойки 25 см в вертикальные гильзы углов."),
        ("Шаг 3", "По желанию — средние кронштейны для жёсткости длинных сторон."),
        ("Шаг 4", "Засыпьте землю внутри, утрамбуйте."),
    ],
    avito_title="Грядка металл 2×1 м каркас 20×20 — набор, Солнечногорск",
    avito_price="6 900 – 7 900 руб.",
    avito_body=(
        "Каркас из стали 20×20×2 — не гнётся как тонкая оцинковка. "
        "Нарезка + 8 коннекторов + PDF 3 вида. Без земли."
    ),
    draw_3views=lambda pdf, uni, bf, bb: _draw_gryadka_3views(pdf, uni, bf, bb),
    offer_id="gryadka-2x1",
    extra_notes="Не оцинкованный лист — массивный борт из профиля 2 мм.",
)

DROVNICA = DachaKit(
    folder="03-drovnica-120",
    title="Дровница каркас 120×100 см (3 полки)",
    profile_cuts=[("СТ-В", 1000, 2), ("ПР-Г", 1200, 5)],
    connector_counts=_ladder_counts(5),
    bolt_sets=24,
    dimensions="120×100 см, 3 яруса",
    assembly_steps=[
        ("Шаг 1", "Две стойки 100 см + 5 полок 120 см (как лестница)."),
        ("Шаг 2", "Низ/верх — углы 90°, три средних яруса — кронштейны."),
        ("Шаг 3", "Опоры внизу, выставить вертикально, затянуть болты."),
        ("Шаг 4", "Уложите дрова поперёк полок."),
    ],
    avito_title="Дровница каркас 1.2 м металл 20×20 — набор, Солнечногорск",
    avito_price="7 900 – 9 900 руб.",
    avito_body=(
        "Каркас под дрова: 2 стойки + 3 полки. "
        "Профиль нарезан, коннекторы PETG, инструкция 3 вида. Крыша/настил — опция."
    ),
    draw_3views=lambda pdf, uni, bf, bb: _draw_drovnica_3views(pdf, uni, bf, bb),
    offer_id="drovnica-120",
)

STOYKA = DachaKit(
    folder="04-stoyka-invent",
    title="Стойка садового инвентаря 180 см",
    profile_cuts=[("СТ-В", 1800, 2), ("ПР-Г", 800, 4)],
    connector_counts={
        "corner_90": 4,
        "bracket_rung": 4,
        "foot_base": 2,
        "hook": 4,
    },
    bolt_sets=20,
    dimensions="80×180 см, 4 крюка",
    assembly_steps=[
        ("Шаг 1", "2 стойки 180 см (из хлыста 200 см) + 4 перекладины 80 см."),
        ("Шаг 2", "Соберите как лестницу: углы наверху/внизу, кронштейны посередине."),
        ("Шаг 3", "Прикрутите 4 крюка к перекладинам (отверстие под шуруп)."),
        ("Шаг 4", "Поставьте у сарая, развесьте лопату/грабли."),
    ],
    avito_title="Стойка для лопаты/граблей 180 см — набор 20×20, Солнечногорск",
    avito_price="3 900 – 4 900 руб.",
    avito_body=(
        "Каркас + 4 печатных крюка. Профиль нарезан. "
        "Удобно у сарая. PDF с 3 видами."
    ),
    draw_3views=lambda pdf, uni, bf, bb: _draw_stoyka_3views(pdf, uni, bf, bb),
    offer_id="stoyka-invent",
)

ALL_KITS: List[DachaKit] = [SHPALERA, GRYADKA, DROVNICA, STOYKA]

DRAWING_ID = {
    "shpalera-tomat-2": "shpalera",
    "gryadka-2x1": "gryadka",
    "drovnica-120": "drovnica",
    "stoyka-invent": "stoyka",
}

FORMAT_TITLES = {
    "A": "Формат A — три отдельных вида (спереди / сбоку / сверху)",
    "B": "Формат B — одна 3D-схема (изометрия)",
    "C": "Формат C — схема IKEA (номера + таблица деталей)",
    "D": "Формат D — только вид спереди, крупно",
    "E": "Формат E — таблица деталей + ваши фото (без чертежа)",
}


def _pdf_fonts(pdf) -> Tuple[str, str, bool]:
    font_r = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_b = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    try:
        pdf.add_font("Ar", "", font_r)
        pdf.add_font("ArB", "", font_b)
        return "Ar", "ArB", True
    except Exception:
        return "Helvetica", "Helvetica", False


def _draw_box_frame(pdf, ox, oy, w, h, scale, *, color=(30, 80, 180)):
    pdf.set_draw_color(*color)
    pdf.set_line_width(2.0)
    W, H = w * scale, h * scale
    pdf.rect(ox, oy - H, W, H)


def _label(pdf, x, y, text, bf, bb, uni, size=8, bold=False):
    pdf.set_font(bb if bold else bf, size=size)
    if uni:
        pdf.text(x, y, text)
    else:
        pdf.text(x, y, text.encode("latin-1", "replace").decode("latin-1"))


def _draw_panel_title(pdf, x, y, title, bf, bb, uni):
    _label(pdf, x, y, title, bf, bb, uni, 10, True)


def _draw_shpalera_3views(pdf, uni, bf, bb) -> None:
    spec = DEFAULT_SPEC
    # Спереди
    _draw_panel_title(pdf, 12, 25, "A. Спереди", bf, bb, uni)
    pdf.set_xy(0, 0)
    _draw_trellis_front(pdf, spec, uni=uni, bf=bf, bb=bb)
    # Сбоку (глубина 60)
    ox, oy = 155.0, 175.0
    sc = 130.0 / spec.height_mm
    _draw_panel_title(pdf, 150, 25, "B. Сбоку", bf, bb, uni)
    _draw_box_frame(pdf, ox, oy, 60, spec.height_mm, sc, color=(60, 120, 60))
    _label(pdf, ox + 5, oy + 12, "60 mm", bf, bb, uni)
    # Сверху
    ox2, oy2 = 230.0, 120.0
    sc2 = 80.0 / spec.width_mm
    _draw_panel_title(pdf, 225, 25, "C. Сверху", bf, bb, uni)
    _draw_box_frame(pdf, ox2, oy2, spec.width_mm, 60, sc2, color=(100, 60, 140))
    _label(pdf, ox2 + 20, oy2 + 8, "600 mm", bf, bb, uni)


def _draw_gryadka_3views(pdf, uni, bf, bb) -> None:
    L, W, H = 2000.0, 1000.0, 250.0
    _draw_panel_title(pdf, 12, 25, "A. Спереди (2000)", bf, bb, uni)
    _draw_box_frame(pdf, 40, 175, L, H, 130 / H)
    _draw_panel_title(pdf, 150, 25, "B. Сбоку (1000)", bf, bb, uni)
    _draw_box_frame(pdf, 155, 175, W, H, 130 / H, color=(60, 120, 60))
    _draw_panel_title(pdf, 225, 25, "C. Сверху", bf, bb, uni)
    _draw_box_frame(pdf, 230, 120, L, W, 75 / L, color=(100, 60, 140))
    for px, py in ((40, 175), (40 + 2000 * 130 / H, 175)):
        _draw_node(pdf, px, py, "corner")
    _label(pdf, 12, 190, "Угол corner_post — 4 шт.", bf, bb, uni, 9)


def _draw_drovnica_3views(pdf, uni, bf, bb) -> None:
    spec = TrellisSpec(
        name="Дровница",
        width_mm=1200,
        height_mm=1000,
        horizontal_count=5,
        rung_heights_mm=(100.0, 300.0, 550.0, 800.0, 950.0),
    )
    _draw_panel_title(pdf, 12, 25, "A. Спереди (1200)", bf, bb, uni)
    _draw_trellis_front(pdf, spec, uni=uni, bf=bf, bb=bb)
    _draw_panel_title(pdf, 150, 25, "B. Сбоку (400)", bf, bb, uni)
    _draw_box_frame(pdf, 155, 175, 400, 1000, 130 / 1000, color=(60, 120, 60))
    _draw_panel_title(pdf, 225, 25, "C. Сверху", bf, bb, uni)
    _draw_box_frame(pdf, 230, 120, 1200, 400, 60 / 1200, color=(100, 60, 140))


def _draw_stoyka_3views(pdf, uni, bf, bb) -> None:
    spec = TrellisSpec(
        name="Стойка",
        width_mm=800,
        height_mm=1800,
        horizontal_count=5,
        rung_heights_mm=(200.0, 600.0, 1000.0, 1400.0, 1700.0),
    )
    _draw_panel_title(pdf, 12, 25, "A. Спереди (800)", bf, bb, uni)
    _draw_trellis_front(pdf, spec, uni=uni, bf=bf, bb=bb)
    _label(pdf, 12, 200, "Крюк hook — 4 шт. на перекладинах", bf, bb, uni, 9)
    _draw_panel_title(pdf, 150, 25, "B. Сбоку", bf, bb, uni)
    _draw_box_frame(pdf, 165, 175, 300, 1800, 130 / 1800, color=(60, 120, 60))
    _draw_panel_title(pdf, 225, 25, "C. Сверху", bf, bb, uni)
    _draw_box_frame(pdf, 240, 120, 800, 300, 70 / 800, color=(100, 60, 140))


def build_product_pdf(
    kit: DachaKit,
    offer: ProductOffer,
    fmt: str,
    drawing_png: Path,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    bf, bb, uni = _pdf_fonts(pdf)
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    w = pdf.w - 28

    def txt(s: str, size: int = 10, bold: bool = False) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "")
        if uni:
            pdf.multi_cell(w, size * 0.4, t)
        else:
            pdf.multi_cell(w, size * 0.4, t.encode("latin-1", "replace").decode("latin-1"))
        pdf.ln(0.5)

    txt(f"Инструкция {fmt} — {kit.title}", 16, bold=True)
    txt(FORMAT_TITLES[fmt], 11, bold=True)
    txt(f"Профиль: сталь 20×20×2 мм. {kit.dimensions}", 10)
    pdf.ln(2)

    txt("1. Состав комплекта", 13, bold=True)
    total_mm = sum(l * q for _, l, q in kit.profile_cuts)
    txt(f"Профиль нарезанный — {total_mm/1000:.1f} п.м.:", 10)
    for mark, length, qty in kit.profile_cuts:
        txt(f"  — {mark}: {qty} x {length/10:.0f} см", 10)
    txt("Коннекторы (PETG/ASA):", 10)
    for k, n in kit.connector_counts.items():
        txt(f"  — {CONNECTOR_LABELS_RU[k]}: {n} шт.", 10)
    txt(f"Болт M5 + гайка: {kit.bolt_sets} компл.", 10)
    if kit.extra_notes:
        txt(kit.extra_notes, 9)
    pdf.ln(2)

    txt("2. Экономика (ориентир)", 13, bold=True)
    cogs = offer.cogs()
    sell = sum(offer.sell_rub) / 2
    txt(
        f"Себестоимость: ~{cogs:.0f} руб. | Рекоменд. цена: {offer.sell_rub[0]:.0f}–{offer.sell_rub[1]:.0f} руб.\n"
        f"Конкуренты: {offer.competitor_avg_rub[0]:.0f}–{offer.competitor_avg_rub[1]:.0f} руб. | "
        f"Маржа ~{sell - cogs:.0f} руб.",
        10,
    )
    pdf.ln(2)

    txt("3. Сборка", 13, bold=True)
    for title, body in kit.assembly_steps:
        txt(title, 11, bold=True)
        txt(body, 10)

    use_landscape = fmt in ("A", "B") or kit.offer_id == "gryadka-2x1"
    if use_landscape:
        pdf.add_page(orientation="L")
        pdf.set_margins(8, 8, 8)
    else:
        pdf.add_page()
    _pdf_fonts(pdf)
    txt(f"4. Схема — формат {fmt}", 14, bold=True)
    img_w = pdf.w - 16
    pdf.image(str(drawing_png), x=8, y=32, w=img_w)

    pdf.add_page(orientation="P")
    pdf.set_margins(14, 14, 14)
    _pdf_fonts(pdf)
    txt("5. Печать коннекторов", 13, bold=True)
    txt(
        "Файлы connectors-plate-*-of-*.3mf в папке набора. PETG/ASA, 0.2 мм, 40–50 %, без поддержек. "
        "Bambu: при вопросе multi-part — NO.",
        10,
    )

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def _economics_txt(kit: DachaKit, offer: ProductOffer) -> str:
    cogs = offer.cogs()
    return f"""ЭКОНОМИКА — {kit.title}
========================

Закупка трубы: 9 x 200 см = {TUBE.price_rub:.0f} руб. ({TUBE.rub_per_stick:.0f} руб./хлыст)
Расход на изделие: ~{offer.sticks_used:.1f} хлыстов = {offer.profile_cost():.0f} руб. профиль

Себестоимость (полная):
  Профиль:     {offer.profile_cost():.0f} руб.
  Пластик:     {offer.plastic_cost():.0f} руб. ({offer.plastic_g:.0f} г)
  Крепёж:      {offer.bolt_sets * 5:.0f} руб.
  Упаковка:    120 руб.
  Нарезка:     200 руб.
  ИТОГО:       {cogs:.0f} руб.

Продажная цена:  {offer.sell_rub[0]:.0f} – {offer.sell_rub[1]:.0f} руб.
Конкуренты:      {offer.competitor_avg_rub[0]:.0f} – {offer.competitor_avg_rub[1]:.0f} руб.
Маржа (сред.):   ~{(sum(offer.sell_rub)/2) - cogs:.0f} руб.

{offer.competitors}
"""


def _avito_txt(kit: DachaKit, offer: ProductOffer) -> str:
    return f"""Заголовок Avito:
{kit.avito_title}

Цена: {kit.avito_price}
Доставка: Солнечногорск, Истра, Клин, Зеленоград — от 800 руб.

{kit.avito_body}

В комплекте:
{kit.dimensions}
Профиль 20×20×2 нарезан, коннекторы PETG, болты M5, PDF (3 вида + сборка).

Себестоимость ~{offer.cogs():.0f} руб. | На рынке аналоги ~{sum(offer.competitor_avg_rub)/2:.0f} руб.

Пишите «{kit.folder}» — уточню наличие и доставку.
"""


def _offer_by_id(oid: str) -> ProductOffer:
    for p in PRODUCTS:
        if p.id == oid:
            return p
    raise KeyError(oid)


def build_one_kit(out_root: Path, kit: DachaKit) -> Path:
    from bot.services.dacha_drawings import SPECS, render_format

    offer = _offer_by_id(kit.offer_id)
    dest = out_root / kit.folder
    dest.mkdir(parents=True, exist_ok=True)
    draw_spec = SPECS[DRAWING_ID[kit.offer_id]]
    chert_dir = dest / "chertezhi-png"
    chert_dir.mkdir(exist_ok=True)

    for fmt in ("A", "B", "C", "D", "E"):
        png = chert_dir / f"{fmt}.png"
        render_format(draw_spec, fmt, png)
        pdf_bytes = build_product_pdf(kit, offer, fmt, png)
        (dest / f"{fmt}.pdf").write_bytes(pdf_bytes)

    (dest / "ekonomika.txt").write_text(_economics_txt(kit, offer), encoding="utf-8")
    (dest / "avito.txt").write_text(_avito_txt(kit, offer), encoding="utf-8")
    (dest / "KAKOY-FORMAT.txt").write_text(
        "Инструкции по буквам:\n"
        "  A.pdf — три отдельных вида\n"
        "  B.pdf — 3D изометрия\n"
        "  C.pdf — IKEA (номера)\n"
        "  D.pdf — спереди крупно\n"
        "  E.pdf — таблица + фото\n"
        "В коробку кладите ОДНУ выбранную букву + connectors 3MF.\n"
        "chertezhi-png/ — картинки для Avito.\n",
        encoding="utf-8",
    )

    export_connectors_3mf_split_counts(
        dest, kit.connector_counts, per_plate=6, name_prefix="connectors-plate"
    )
    export_connector_stls_for_counts(dest / "stl", kit.connector_counts, title=kit.title)

    return dest


def build_full_archive(out_dir: Path) -> Path:
    from bot.services.dacha_products_proposal import write_proposal

    out_dir = out_dir.expanduser().resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    write_proposal(out_dir / "00-biznes-proposal.pdf")

    for kit in ALL_KITS:
        build_one_kit(out_dir, kit)

    avito_all = []
    for kit in ALL_KITS:
        avito_all.append((out_dir / kit.folder / "avito.txt").read_text(encoding="utf-8"))
    (out_dir / "avito-vse-tovary.txt").write_text(
        "\n\n" + ("=" * 60) + "\n\n".join(avito_all), encoding="utf-8"
    )

    (out_dir / "README.txt").write_text(
        "Дачные наборы 20×20 — полный комплект (5 форматов инструкций)\n"
        "========================================================\n\n"
        "00-biznes-proposal.pdf — экономика 4 продуктов\n\n"
        "Папки продуктов:\n"
        "  01-shpalera-tomat-2/\n"
        "  02-gryadka-2x1/\n"
        "  03-drovnica-120/\n"
        "  04-stoyka-invent/\n\n"
        "В каждой папке — 5 инструкций по буквам:\n"
        "  A.pdf — три вида (спереди/сбоку/сверху)\n"
        "  B.pdf — изометрия 3D\n"
        "  C.pdf — схема IKEA\n"
        "  D.pdf — вид спереди крупно\n"
        "  E.pdf — таблица + место под фото\n"
        "  chertezhi-png/ — те же схемы в PNG для Avito\n"
        "  connectors-plate-*.3mf, stl/, ekonomika.txt, avito.txt\n"
        "  KAKOY-FORMAT.txt — какую букву класть в коробку\n\n"
        f"Труба: {TUBE.sticks} x {TUBE.length_cm} см = {TUBE.price_rub:.0f} руб.\n",
        encoding="utf-8",
    )

    zip_path = out_dir.parent / f"{out_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir.parent))
    return zip_path
