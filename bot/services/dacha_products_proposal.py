"""Коммерческое предложение: наборы 20×20 + печатные коннекторы."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class TubePack:
    sticks: int = 9
    length_cm: int = 200
    price_rub: float = 2500.0

    @property
    def total_m(self) -> float:
        return self.sticks * self.length_cm / 100.0

    @property
    def rub_per_m(self) -> float:
        return self.price_rub / self.total_m

    @property
    def rub_per_stick(self) -> float:
        return self.price_rub / self.sticks


TUBE = TubePack()

# Справочно: розница PETG, M5, упаковка (подставьте свои цифры)
PETG_RUB_PER_KG = 850.0
BOLT_M5_SET_RUB = 5.0  # болт+гайка
PACK_RUB = 120.0
CUT_PACK_LABOR_RUB = 200.0  # нарезка + комплектация ~30–40 мин


@dataclass(frozen=True)
class ProductOffer:
    id: str
    name: str
    demand: str  # текст «насколько сейчас»
    season: str
    in_box: str
    sticks_used: float
    profile_m: float
    connector_count: int
    plastic_g: float
    bolt_sets: int
    competitors: str
    competitor_avg_rub: Tuple[float, float]
    sell_rub: Tuple[float, float]
    photos_needed: str

    def profile_cost(self) -> float:
        return self.sticks_used * TUBE.rub_per_stick

    def plastic_cost(self) -> float:
        return (self.plastic_g / 1000.0) * PETG_RUB_PER_KG

    def cogs(self, *, with_labor: bool = True) -> float:
        total = (
            self.profile_cost()
            + self.plastic_cost()
            + self.bolt_sets * BOLT_M5_SET_RUB
            + PACK_RUB
        )
        if with_labor:
            total += CUT_PACK_LABOR_RUB
        return total

    def margin_at(self, price: float, *, with_labor: bool = True) -> float:
        return price - self.cogs(with_labor=with_labor)


PRODUCTS: List[ProductOffer] = [
    ProductOffer(
        id="shpalera-tomat-2",
        name="Шпалера «Томат-2» 60×200 см",
        demand="***** Сейчас пик: томаты/огурцы, май-июль",
        season="Апрель–август",
        in_box=(
            "2 стойки 200 см + 5 перемычек 60 см (маркировка), "
            "12 коннекторов, 24× M5, PDF+чертёж, QR сборки"
        ),
        sticks_used=3.5,
        profile_m=7.0,
        connector_count=12,
        plastic_g=280.0,
        bolt_sets=24,
        competitors=(
            "Пластик «лесенка» от ~360 ₽ (слабая); "
            "палки/шпагат DIY 500–1500 ₽; "
            "сварные/металл Ozon/Avito 2500–8000 ₽"
        ),
        competitor_avg_rub=(2500.0, 4500.0),
        sell_rub=(5900.0, 6900.0),
        photos_needed=(
            "1) на грядке с растениями 2) комплектация 3) узел крупно "
            "4) чертёж спереди 5) вид сбоку/изометрия"
        ),
    ),
    ProductOffer(
        id="gryadka-2x1",
        name="Каркас высокой грядки 200×100×25 см",
        demand="***** Тренд высокие грядки, апрель-июнь",
        season="Март–июнь",
        in_box=(
            "Профиль: 2×200 + 2×100 см (+ угловые стойки по желанию), "
            "8–10 коннекторов, M5, инструкция. "
            "Без земли/геотекстиля — только каркас"
        ),
        sticks_used=4.0,
        profile_m=8.0,
        connector_count=10,
        plastic_g=240.0,
        bolt_sets=20,
        competitors=(
            "Оцинковые готовые борта 2×1 м высота 20 см: "
            "1750–3700 ₽ (тонкий лист 0.7 мм, не 20×20×2)"
        ),
        competitor_avg_rub=(2200.0, 3200.0),
        sell_rub=(6900.0, 7900.0),
        photos_needed=(
            "1) грядка с землёй 2) человек сидит на борту (прочность) "
            "3) комплект 4) чертёж 3 вида 5) сравнение с тонкой оцинковкой"
        ),
    ),
    ProductOffer(
        id="drovnica-120",
        name="Дровница каркас 120×40×100 см (3 полки)",
        demand="**** Стабильный спрос на даче круглый год",
        season="Круглый год, пик осень",
        in_box=(
            "Профиль нарезанный под 3 яруса, 10–12 коннекторов, "
            "M5, схема сборки. Настил/крыша — опция (+цена)"
        ),
        sticks_used=5.0,
        profile_m=10.0,
        connector_count=12,
        plastic_g=320.0,
        bolt_sets=24,
        competitors=(
            "Каркас металл 1.2 м: GardenDreams ~5741 ₽, BARNAS ~8900 ₽; "
            "сварные дровники 15000–30000 ₽"
        ),
        competitor_avg_rub=(5500.0, 12000.0),
        sell_rub=(7900.0, 9900.0),
        photos_needed=(
            "1) с дровами 2) без дров (каркас) 3) комплект "
            "4) чертёж 3 вида 5) масштаб (рука/лопата)"
        ),
    ),
    ProductOffer(
        id="stoyka-invent",
        name="Стойка садового инвентаря 180 см",
        demand="*** Средний спрос, мало готовых на Avito",
        season="Апрель–сентябрь",
        in_box=(
            "2 стойки + перекладины, 6–8 коннекторов, крюки/держатели "
            "(печать), M5, инструкция"
        ),
        sticks_used=2.5,
        profile_m=5.0,
        connector_count=8,
        plastic_g=180.0,
        bolt_sets=12,
        competitors=(
            "Пластиковые стойки 800–2500 ₽; "
            "самоделки из дерева 1000–2000 ₽"
        ),
        competitor_avg_rub=(1200.0, 2500.0),
        sell_rub=(3900.0, 4900.0),
        photos_needed=(
            "1) лопата/грабли на стойке 2) у сарая 3) комплект "
            "4) чертёж 3 вида"
        ),
    ),
]


def build_proposal_pdf() -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)

    font_r = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_b = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    try:
        pdf.add_font("Ar", "", font_r)
        pdf.add_font("ArB", "", font_b)
        bf, bb = "Ar", "ArB"
        uni = True
    except Exception:
        bf, bb = "Helvetica", "Helvetica"
        uni = False

    w = pdf.w - 28

    def txt(s: str, size: int = 10, bold: bool = False) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "").replace("₽", " руб.")
        if uni:
            pdf.multi_cell(w, size * 0.4, t)
        else:
            pdf.multi_cell(w, size * 0.4, t.encode("latin-1", "replace").decode("latin-1"))
        pdf.ln(0.5)

    # Титул
    pdf.add_page()
    txt("Коммерческое предложение: дачные наборы 20×20 + 3D-коннекторы", 16, bold=True)
    txt("Солнечногорск / МО · Bambu P2S · без сертификации в расчёте", 9)
    pdf.ln(2)
    txt("База закупки трубы", 13, bold=True)
    txt(
        f"Сталь 20×20×2 мм, {TUBE.sticks} шт × {TUBE.length_cm} см = {TUBE.total_m:.0f} п.м. "
        f"за {TUBE.price_rub:.0f} ₽\n"
        f"→ {TUBE.rub_per_stick:.0f} ₽ / хлыст 2 м · {TUBE.rub_per_m:.0f} ₽ / п.м.",
        10,
    )
    pdf.ln(1)
    txt("Формула себестоимости (на 1 комплект)", 13, bold=True)
    txt(
        "Себестоимость = труба (хлысты × цена хлыста) + пластик (г × 850 ₽/кг) "
        "+ крепёж + упаковка + нарезка/сборка комплекта (200 ₽).\n"
        "Печать коннекторов: ~1–2 прогона P2S, PETG/ASA.",
        10,
    )
    pdf.ln(1)
    txt("Что продавать клиенту", 13, bold=True)
    txt(
        "Не «коннекторы», а готовое решение: нарезанный профиль + печатные узлы + "
        "инструкция + фото/чертёж. Опционально: доставка и сборка на участке (+15–25%).",
        10,
    )
    pdf.ln(2)
    txt("Приоритет запуска (сейчас, июнь)", 13, bold=True)
    txt("1. Шпалера → 2. Грядка 2×1 → 3. Дровница → 4. Стойка инвентаря", 11)

    # Сводная таблица
    pdf.add_page()
    txt("Сводка: 4 продукта", 15, bold=True)
    pdf.ln(1)
    headers = ["Продукт", "Себест.", "Цена", "Конкуренты", "Маржа"]
    col_w = [52, 22, 28, 38, 22]
    pdf.set_font(bb, size=8)
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    for i, h in enumerate(headers):
        pdf.set_xy(x0 + sum(col_w[:i]), y0)
        pdf.cell(col_w[i], 6, h, border=1)
    pdf.ln(6)
    pdf.set_font(bf, size=7)
    for p in PRODUCTS:
        cogs = p.cogs()
        sell_mid = sum(p.sell_rub) / 2
        comp_mid = sum(p.competitor_avg_rub) / 2
        margin = sell_mid - cogs
        row = [
            p.name[:28],
            f"{cogs:.0f}",
            f"{p.sell_rub[0]:.0f}-{p.sell_rub[1]:.0f}",
            f"{comp_mid:.0f}",
            f"{margin:.0f}",
        ]
        y0 = pdf.get_y()
        for i, cell in enumerate(row):
            pdf.set_xy(x0 + sum(col_w[:i]), y0)
            pdf.cell(col_w[i], 6, cell, border=1)
        pdf.ln(6)

    # Карточки продуктов
    for p in PRODUCTS:
        pdf.add_page()
        txt(p.name, 14, bold=True)
        txt(p.demand, 10)
        txt(f"Сезон: {p.season}", 9)
        pdf.ln(1)
        txt("Комплект", 12, bold=True)
        txt(p.in_box, 10)
        pdf.ln(1)
        txt("Расход трубы", 12, bold=True)
        txt(
            f"≈ {p.sticks_used:.1f} хлыстов из 9 ({p.profile_m:.0f} п.м.) → "
            f"{p.profile_cost():.0f} ₽ только профиль",
            10,
        )
        pdf.ln(1)
        cogs = p.cogs()
        cogs_no_lab = p.cogs(with_labor=False)
        sell_lo, sell_hi = p.sell_rub
        comp_lo, comp_hi = p.competitor_avg_rub
        txt("Себестоимость", 12, bold=True)
        txt(f"  Профиль: {p.profile_cost():.0f} ₽", 10)
        txt(f"  Пластик ({p.plastic_g:.0f} г): {p.plastic_cost():.0f} ₽", 10)
        txt(f"  Крепёж {p.bolt_sets} компл.: {p.bolt_sets * BOLT_M5_SET_RUB:.0f} ₽", 10)
        txt(f"  Упаковка: {PACK_RUB:.0f} ₽", 10)
        txt(f"  Нарезка/комплектация: {CUT_PACK_LABOR_RUB:.0f} ₽", 10)
        txt(f"  ИТОГО с работой: {cogs:.0f} ₽ · без работы: {cogs_no_lab:.0f} ₽", 11, bold=True)
        pdf.ln(1)
        txt("Продажная цена (рекомендация)", 12, bold=True)
        txt(
            f"  {sell_lo:.0f} – {sell_hi:.0f} ₽ · самовывоз Солнечногорск\n"
            f"  Доставка/сборка: +800–2500 ₽",
            10,
        )
        margin = (sell_lo + sell_hi) / 2 - cogs
        txt(f"  Маржа при средней цене: ≈ {margin:.0f} ₽ ({100*margin/((sell_lo+sell_hi)/2):.0f}%)", 10)
        pdf.ln(1)
        txt("Конкуренты (ориентир рынка)", 12, bold=True)
        txt(f"  Диапазон: {comp_lo:.0f} – {comp_hi:.0f} ₽", 10)
        txt(f"  {p.competitors}", 9)
        pdf.ln(1)
        txt("Фото / чертёж (обязательно для Avito)", 12, bold=True)
        txt(p.photos_needed, 9)
        pdf.ln(1)
        txt("Чертёж: вид спереди + сбоку + сверху (можно в PDF инструкции)", 10)

    # Экономика пачки труб
    pdf.add_page()
    txt("Как использовать пачку 9×2 м за 2500 ₽", 14, bold=True)
    txt(
        "Из одной пачки (18 п.м.) реально сделать:\n"
        "• 5 шпалер (7 п.м. каждая) — нет, не хватит\n"
        "• 2 шпалеры (7×2=14 п.м.) + стойка инвентаря (5 п.м.) — да\n"
        "• 1 дровница (10 п.м.) + 1 шпалера (7 п.м.) — да\n"
        "• 2 грядки 2×1 (8×2=16 п.м.) — впритык",
        10,
    )
    pdf.ln(2)
    txt("Варианты продажи", 13, bold=True)
    txt(
        "A) «Полный набор» — труба нарезанная + коннекторы + PDF (основной чек).\n"
        "B) «Только коннекторы» — 1200–1800 ₽ (низкий чек, для тех, у кого труба есть).\n"
        "C) «Пачка трубы + скидка на набор» — продать 9 хлыстов за 3200 ₽ "
        "с купоном −500 ₽ на первый набор.",
        10,
    )
    pdf.ln(2)
    txt("Что НЕ запускать сейчас (низкий ROI / перегрет рынок)", 13, bold=True)
    txt(
        "Детский домик, песочница (много готовых пластиковых), "
        "походный душ (узкая ниша), абстрактные «коннекторы без задачи».",
        10,
    )

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def write_proposal(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.write_bytes(build_proposal_pdf())
    return path
