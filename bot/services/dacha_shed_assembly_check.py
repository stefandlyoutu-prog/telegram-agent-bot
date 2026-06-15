"""Проверка логики сборки сарая v3 — расход палок и коннекторов по шагам."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from bot.services.dacha_shed_parts_ru import PARTS_RU


@dataclass(frozen=True)
class AssemblyIssue:
    level: str  # error | warn
    message: str


def _step_stick_usage(steps, *, from_step: int = 3) -> Dict[int, int]:
    """Сколько палок 150 см списывается по шагам сборки (без шага «проверка комплекта»)."""
    out: Dict[int, int] = {}
    for st in steps:
        if st.number < from_step:
            continue
        n = 0
        for lbl, qty in st.parts:
            if "150 см" in lbl and "200" not in lbl:
                n += qty
        if n:
            out[st.number] = n
    return out


def validate_v3_assembly(spec, steps) -> List[AssemblyIssue]:
    issues: List[AssemblyIssue] = []
    sc = spec.stick_counts()
    cc = spec.connector_counts()

    p150_steps = _step_stick_usage(steps)
    p150_total = sum(p150_steps.values())
    if p150_total != sc[1500]:
        issues.append(
            AssemblyIssue(
                "error",
                f"Палки 150 см: в шагах {p150_total} шт., в спецификации {sc[1500]} шт. "
                f"(по шагам: {p150_steps}).",
            )
        )

    # inline_splice по шагам
    spl_steps = {}
    for st in steps:
        if st.number < 3:
            continue
        for lbl, qty in st.parts:
            if "Соединитель «в линию»" in lbl or "inline_splice" in lbl.lower():
                spl_steps[st.number] = spl_steps.get(st.number, 0) + qty
    spl_total = sum(spl_steps.values())
    need_spl = spec.inline_splice_count()
    if spl_total != need_spl:
        issues.append(
            AssemblyIssue(
                "error",
                f"Соединители «в линию»: в шагах {spl_total}, в спецификации {need_spl}.",
            )
        )

    # corner_post / corner_90 — не должны дублироваться на одних углах
    cp_steps = [st.number for st in steps if any("Уголок для стойки" in l for l, _ in st.parts)]
    c90_steps = [st.number for st in steps if any("Уголок 90°" in l for l, _ in st.parts)]
    if 3 in c90_steps and 3 in cp_steps:
        issues.append(
            AssemblyIssue(
                "error",
                "На шаге 3 и углах нельзя одновременно «Уголок 90°» и «Уголок для стойки» — "
                "на углах с стойками нужен только уголок для стойки.",
            )
        )

    # дверь
    left = spec.door_offset_left_mm
    right = left + spec.door_width_mm
    posts = spec.front_post_x()
    if right not in posts:
        issues.append(
            AssemblyIssue(
                "warn",
                f"Правый край двери {right} мм — нет стойки на фасаде {posts}.",
            )
        )
    if left not in posts and left > 0:
        issues.append(
            AssemblyIssue(
                "warn",
                f"Левый край двери {left} мм — отдельной стойки нет; проём держат уголки двери "
                f"и обвязки (стойка только в углу на 0 мм).",
            )
        )

    # геометрия фасада
    if posts[-1] != spec.length_mm:
        issues.append(AssemblyIssue("error", "Последняя стойка фасада не совпадает с длиной здания."))

    return issues


def format_assembly_report(spec, steps) -> str:
    issues = validate_v3_assembly(spec, steps)
    sc = spec.stick_counts()
    lines = [
        "Проверка сборки по инструкции",
        "=" * 40,
        "",
        f"Палки 150 см (спецификация): {sc[1500]}",
        f"Палки 150 см (сумма по шагам): {sum(_step_stick_usage(steps).values())}",
        "",
    ]
    for st in steps:
        parts = ", ".join(f"{q}×{n.split(' (')[0]}" for n, q in st.parts[:6])
        lines.append(f"Шаг {st.number}: {parts}")
    lines.append("")
    if not issues:
        lines.append("Ошибок не найдено.")
    else:
        lines.append("Замечания:")
        for i in issues:
            mark = "ОШИБКА" if i.level == "error" else "Внимание"
            lines.append(f"  [{mark}] {i.message}")
    lines.append("")
    return "\n".join(lines)
