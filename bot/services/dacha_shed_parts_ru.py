"""Русские названия деталей и «словарь» для инструкции сарая 3×3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# id → (название, простое описание, размер/материал)
PARTS_RU: Dict[str, Tuple[str, str, str]] = {
    "profil_200": (
        "Палка профиля 200 см",
        "Длинная металлическая труба. Стоит вертикально — это стойки стен.",
        "20×20 мм, длина 200 см",
    ),
    "profil_150": (
        "Палка профиля 150 см",
        "Средняя труба. Идёт горизонтально: пол, потолок, крыша, раскос.",
        "20×20 мм, длина 150 см",
    ),
    "profil_100": (
        "Палка профиля 100 см",
        "Короткая труба. Над дверью — держит верх проёма.",
        "20×20 мм, длина 100 см",
    ),
    "foot_base": (
        "Опора на блок",
        "Пластиковая подставка. Стойка вставляется сверху, снизу — болт в бетонный блок.",
        "пластик PETG",
    ),
    "corner_90": (
        "Уголок 90°",
        "Соединяет две палки под прямым углом (как буква Г). Ставится в углах нижней и верхней рамы.",
        "пластик PETG",
    ),
    "corner_post": (
        "Уголок для стойки",
        "Три гнезда: две горизонтали + одна вертикальная стойка. Только на 4 углах здания.",
        "пластик PETG",
    ),
    "tee_90": (
        "Т-образный уголок",
        "Три гнезда: стойка + две балки в стороны. На верхней раме и у средних стоек.",
        "пластик PETG",
    ),
    "inline_splice": (
        "Соединитель «в линию»",
        "Склеивает две палки в одну длинную (150+150=300 см). Концы вставляются в оба гнезда.",
        "пластик PETG",
    ),
    "brace_45": (
        "Крепление для раскоса",
        "Держит палку по диagonali. Одно гнездо — на стойку, второе — на наклонную палку 150 см.",
        "пластик PETG",
    ),
    "door_frame": (
        "Уголок двери",
        "Усиленный уголок у проёма двери. Соединяет стойку и ригель.",
        "пластик PETG",
    ),
    "lintel_splice": (
        "Соединитель над дверью",
        "Держит две короткие палки 100 см рядом — двойной ригель над дверью.",
        "пластик PETG",
    ),
    "rafter_seat": (
        "Держатель стропила",
        "Крепит наклонную палку (стропило) к передней или задней стене.",
        "пластик PETG",
    ),
    "girt_bracket": (
        "Кронштейн для полки на стене",
        "Горизонтальная палка для крепления металлического листа на стене.",
        "пластик PETG",
    ),
    "bolt_m5": (
        "Болт M5 с гайкой",
        "Закручивается сквозь пластик и профиль. Ключ на 8.",
        "нержавейка",
    ),
    "bolt_m8": (
        "Анкер M8",
        "Болт в бетонный блок через опору. Нужны перфоратор и ключ.",
        "в блок 40×40",
    ),
    "proflist": (
        "Лист металлический (профлист)",
        "Накрывает стены и крышу. Крепится саморезами.",
        "С10, ~25 м²",
    ),
    "samorez": (
        "Саморез для листа",
        "Прикручивает лист к палкам. Удобно шуруповёртом.",
        "5,5×25 мм",
    ),
    "blok": (
        "Бетонный блок",
        "Фундамент под опору. 6 штук на квадрат 3×3 м.",
        "40×40 см",
    ),
}


@dataclass(frozen=True)
class CatalogRow:
    qty: int
    part_id: str

    @property
    def name(self) -> str:
        return PARTS_RU[self.part_id][0]

    @property
    def desc(self) -> str:
        return PARTS_RU[self.part_id][1]

    @property
    def size(self) -> str:
        return PARTS_RU[self.part_id][2]


def full_kit_catalog(spec) -> List[CatalogRow]:
    """Полный список деталей комплекта для страницы «Словарь»."""
    sc = spec.stick_counts()
    cc = spec.connector_counts()
    rows: List[CatalogRow] = []
    rows.append(CatalogRow(sc[2000], "profil_200"))
    rows.append(CatalogRow(sc[1500], "profil_150"))
    rows.append(CatalogRow(sc[1000], "profil_100"))
    rows.append(CatalogRow(spec.post_count, "blok"))
    rows.append(CatalogRow(cc["foot_base"], "foot_base"))
    rows.append(CatalogRow(cc["corner_90"], "corner_90"))
    rows.append(CatalogRow(cc["corner_post"], "corner_post"))
    rows.append(CatalogRow(cc["tee_90"], "tee_90"))
    rows.append(CatalogRow(cc["inline_splice"], "inline_splice"))
    rows.append(CatalogRow(cc["brace_45"], "brace_45"))
    rows.append(CatalogRow(cc["door_frame"], "door_frame"))
    rows.append(CatalogRow(cc["lintel_splice"], "lintel_splice"))
    rows.append(CatalogRow(cc["rafter_seat"], "rafter_seat"))
    rows.append(CatalogRow(cc["girt_bracket"], "girt_bracket"))
    rows.append(CatalogRow(spec.post_count, "bolt_m8"))
    rows.append(CatalogRow(80, "bolt_m5"))
    rows.append(CatalogRow(1, "proflist"))
    rows.append(CatalogRow(180, "samorez"))
    return rows


def part_name(part_id: str) -> str:
    """Короткое русское название детали (видео, подписи)."""
    return PARTS_RU[part_id][0]


def part_label_ru(part_id: str, qty: int) -> str:
    name, _, size = PARTS_RU[part_id]
    return f"{name} ({size}) — {qty} шт."


def step_part(part_id: str, qty: int) -> Tuple[str, int]:
    """Подпись детали для списка на шаге: название + размер."""
    name, _, size = PARTS_RU[part_id]
    return (f"{name} ({size})", qty)


def catalog_pdf_lines(spec) -> List[str]:
    lines = ["СЛОВАРЬ ДЕТАЛЕЙ — всё, что в коробке", ""]
    for row in full_kit_catalog(spec):
        lines.append(f"• {row.name} — {row.qty} шт.")
        lines.append(f"   {row.desc}")
        lines.append(f"   Размер: {row.size}")
        lines.append("")
    return lines
