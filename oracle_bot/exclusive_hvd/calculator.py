"""Расчёт показателей ХВД по дате рождения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from oracle_bot.exclusive_hvd.interpreter import (
    EGOISM_ALTRUISM,
    LIFE_PERIOD,
    life_code_digits,
    period_age_range,
)
from oracle_bot.exclusive_hvd.tables import (
    CYCLES,
    LIFE_TASK_HINTS,
    REACTIVITY,
    TABLE3,
    TYPOLOGY_HINTS,
    YEAR_MARKERS,
    days_in_month,
    month_markers,
    reduce_marker,
)

@dataclass
class ChakraLevel:
    name: str
    percent: int


@dataclass
class Contour:
    marker: int
    label: str
    chakras: tuple[ChakraLevel, ChakraLevel]


@dataclass
class LifePeriod:
    index: int
    digit: int
    age_range: str
    theme: str
    chakra: str
    description: str
    group: str


@dataclass
class HVDProfile:
    name: str
    birth: date
    typology: int
    typology_hint: str
    markers_raw: tuple[int, int, int]
    physical: Contour
    emotional: Contour
    intellectual: Contour
    reactivity: str
    reactivity_ya: int
    reactivity_my: int
    yin_pct: float
    yang_pct: float
    want: float
    can_pct: int
    sexual_potential: float
    verbal_intellect: float
    nonverbal_intellect: float
    negative_code: int
    positive_code: int
    positive_digits: tuple[int, ...]
    task_past: int
    task_present: int
    task_lineage: int
    task_parents: int
    task_past_hint: str
    task_present_hint: str
    task_lineage_hint: str
    task_parents_hint: str
    sahasrara_hint: str
    life_periods: tuple[LifePeriod, ...]
    egoism_note: str


def _negative_code(birth: date) -> int:
    """Код негатива по курсу: DDMM × год (пример 11.12.1931 → 1112×1931)."""
    ddmm = birth.day * 100 + birth.month
    return ddmm * birth.year


def _digit_root(n: int) -> int:
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n if n else 9


def typology(birth: date) -> int:
    digits = f"{birth.day:02d}{birth.month:02d}{birth.year}"
    return _digit_root(sum(int(c) for c in digits))


def _contour_from_row(marker: int, row_idx: int) -> Contour:
    phys_row, emo_row, intel_row = TABLE3[marker]
    if row_idx == 0:
        row = phys_row
        names = ("Муладхара", "Свадхистана")
    elif row_idx == 1:
        row = emo_row
        names = ("Манипура", "Анахата")
    else:
        row = intel_row
        names = ("Вишудха", "Аджна")
    if row is None:
        raise ValueError(f"Нет физического контура для маркера {marker}")
    c1, c2, label = row
    return Contour(
        marker=marker,
        label=label,
        chakras=(
            ChakraLevel(names[0], c1),
            ChakraLevel(names[1], c2),
        ),
    )


def _reactivity(emo_marker: int) -> tuple[str, int, int]:
    for name, data in REACTIVITY.items():
        if emo_marker in data["markers"]:
            return name, int(data["ya"]), int(data["my"])
    return "Среднереактивный", 56, 41


def _sahasrara_hint(vishuddha: int, ajna: int) -> str:
    diff = abs(vishuddha - ajna)
    if diff <= 10:
        return "Разница вишудхи и аджны небольшая — склонность к медитативному, цельному мышлению."
    if diff >= 50:
        return (
            "Сильный разрыв вишудхи и аджны — неординарное мышление, "
            "но возможна повышенная чувствительность психики."
        )
    return "Умеренный баланс вишудхи и аджны — гибкое сочетание логики и интуиции."


def calculate(name: str, birth: date) -> HVDProfile:
    if birth.year not in YEAR_MARKERS:
        raise ValueError(f"Год {birth.year} вне диапазона таблицы (1900–2099)")

    year_m = YEAR_MARKERS[birth.year]
    month_m = month_markers(birth.month, birth.year)
    dim = days_in_month(birth.month, birth.year)
    day_m = dim - birth.day

    totals = []
    markers = []
    for i, cycle in enumerate(CYCLES):
        total = year_m[i] + month_m[i] + day_m
        markers.append(reduce_marker(total, cycle))
        totals.append(total)

    phys = _contour_from_row(markers[0], 0)
    emo = _contour_from_row(markers[1], 1)
    intel = _contour_from_row(markers[2], 2)

    mula = phys.chakras[0].percent
    svad = phys.chakras[1].percent
    manip = emo.chakras[0].percent
    anah = emo.chakras[1].percent
    vish = intel.chakras[0].percent
    ajna = intel.chakras[1].percent

    yin_raw = svad + anah + ajna
    yang_raw = mula + manip + vish
    yin_pct = round(yin_raw / 297 * 100, 1)
    yang_pct = round(yang_raw / 297 * 100, 1)
    want = round(abs(yin_pct - yang_pct), 1)
    can_pct = mula
    sexual = round(want * can_pct / 100, 1)

    verbal = round((manip + vish) / 198 * 100, 1)
    nonverbal = round((anah + ajna) / 198 * 100, 1)

    typ = typology(birth)
    neg = _negative_code(birth)
    neg_digits = life_code_digits(neg)
    task_past = neg_digits[0] if neg_digits else typ
    task_present = _digit_root(task_past + neg_digits[-1]) if neg_digits else typ
    lineage_raw = birth.day + birth.month
    task_lineage = _digit_root(lineage_raw)
    task_parents = _digit_root(task_lineage + task_present)

    pos = _digit_root(sum(neg_digits) + typ) if neg_digits else typ
    pos_digits = tuple(_digit_root(d + typ) for d in neg_digits) if neg_digits else (typ,)

    react_name, react_ya, react_my = _reactivity(markers[1])

    periods: list[LifePeriod] = []
    for i, digit in enumerate(neg_digits):
        info = LIFE_PERIOD.get(digit, LIFE_PERIOD[0])
        group = "0–4" if digit <= 4 else "5–9"
        periods.append(
            LifePeriod(
                index=i + 1,
                digit=digit,
                age_range=period_age_range(i),
                theme=info["theme"],
                chakra=info["chakra"],
                description=info["desc"],
                group=group,
            )
        )

    return HVDProfile(
        name=name,
        birth=birth,
        typology=typ,
        typology_hint=TYPOLOGY_HINTS.get(typ, ""),
        markers_raw=tuple(markers),
        physical=phys,
        emotional=emo,
        intellectual=intel,
        reactivity=react_name,
        reactivity_ya=react_ya,
        reactivity_my=react_my,
        yin_pct=yin_pct,
        yang_pct=yang_pct,
        want=want,
        can_pct=can_pct,
        sexual_potential=sexual,
        verbal_intellect=verbal,
        nonverbal_intellect=nonverbal,
        negative_code=neg,
        positive_code=pos,
        positive_digits=pos_digits,
        task_past=task_past,
        task_present=task_present,
        task_lineage=task_lineage,
        task_parents=task_parents,
        task_past_hint=LIFE_TASK_HINTS.get(task_past, ""),
        task_present_hint=LIFE_TASK_HINTS.get(task_present, ""),
        task_lineage_hint=LIFE_TASK_HINTS.get(task_lineage, ""),
        task_parents_hint=LIFE_TASK_HINTS.get(task_parents, ""),
        sahasrara_hint=_sahasrara_hint(vish, ajna),
        life_periods=tuple(periods),
        egoism_note=EGOISM_ALTRUISM.get(react_name, ""),
    )
