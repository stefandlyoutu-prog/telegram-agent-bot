#!/usr/bin/env python3
"""Извлечение текстов арканов из образца PDF «Книга о тебе» → ultra_plus/corpus.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "oracle_bot" / "ultra_plus" / "_source_stepan_sample.txt"
OUT = ROOT / "oracle_bot" / "ultra_plus" / "corpus.json"

ARCANA_NAMES: dict[int, str] = {
    1: "Маг",
    2: "Жрица",
    3: "Императрица",
    4: "Император",
    5: "Иерофант",
    6: "Влюблённые",
    7: "Колесница",
    8: "Справедливость",
    9: "Отшельник",
    10: "Колесо Фортуны",
    11: "Сила",
    12: "Повешенный",
    13: "Смерть",
    14: "Умеренность",
    15: "Дьявол",
    16: "Башня",
    17: "Звезда",
    18: "Луна",
    19: "Солнце",
    20: "Суд",
    21: "Мир",
    22: "Шут",
}

SECTION_MARKERS: list[tuple[str, str]] = [
    ("intro", r"^Информация о вас"),
    ("personal_positive", r"^В позитиве"),
    ("personal_negative", r"^В негативе"),
    ("communication", r"^В общении"),
    ("talents_god", r"^Таланты от Бога"),
    ("talents_mother", r"^Таланты по линии матери"),
    ("talents_father", r"^Таланты по линии отца"),
    ("purpose_intro", r"^Предназначение$"),
    ("purpose_20_40", r"^Предназначение 20-40"),
    ("purpose_40_60", r"^Предназначение 40-60"),
    ("purpose_general", r"^Предназначение общее"),
    ("money_direction", r"^Направление деятельности"),
    ("money_success", r"^Для достижения успеха важно"),
    ("programs", r"^Программы"),
    ("sexuality", r"^Сексуальность"),
    ("past_life", r"^Прошлая жизнь"),
    ("parents", r"^Родители"),
    ("lineage_male", r"^Родовые программы по мужской"),
    ("lineage_female", r"^Родовые программы по женской"),
    ("parent_wounds", r"^Обиды на родителей"),
    ("children", r"^Дети"),
    ("relationships", r"^Отношения"),
    ("health_recommend", r"^Личные рекомендации"),
    ("life_guide", r"^Руководство по жизни"),
    ("year_forecast", r"^Прогноз на год"),
]

TALENT_TITLE = re.compile(
    r"^([А-ЯA-ZЁ][^\n(]{2,50}?)\s*\((\d{1,2})\)\s*$",
    re.MULTILINE,
)
ARCANA_BLOCK = re.compile(r"^\((\d{1,2})\)\s*(.+)", re.MULTILINE | re.DOTALL)
PROGRAM_HEAD = re.compile(r"^(.+?)\s*\((\d{1,2}-\d{1,2}-\d{1,2})\)\s*$", re.MULTILINE)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def parse_arcana_blocks(text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in ARCANA_BLOCK.finditer(text):
        n = int(m.group(1))
        body = _clean(m.group(2))
        if body and (n not in out or len(body) > len(out[n])):
            out[n] = body
    return out


def parse_programs(text: str) -> dict[str, dict[str, str]]:
    programs: dict[str, dict[str, str]] = {}
    chunks = re.split(r"\n(?=[^\n]+\(\d{1,2}-\d{1,2}-\d{1,2}\)\s*\n)", text)
    for chunk in chunks:
        head = PROGRAM_HEAD.search(chunk)
        if not head:
            continue
        key = head.group(2)
        body = chunk[head.end() :]
        strengths = ""
        problems = ""
        rec = ""
        if "Ваши сильные стороны" in body:
            parts = re.split(r"Возможные проблемы:|Рекомендации:", body)
            strengths = _clean(parts[0].split("Ваши сильные стороны", 1)[-1])
            if len(parts) > 1:
                problems = _clean(parts[1])
            if len(parts) > 2:
                rec = _clean(parts[2])
        else:
            strengths = _clean(body)
        programs[key] = {
            "name": _clean(head.group(1)),
            "strengths": strengths,
            "problems": problems,
            "recommendations": rec,
        }
    return programs


def parse_talent_titles(text: str) -> dict[int, str]:
    titles: dict[int, str] = {}
    for m in TALENT_TITLE.finditer(text):
        titles[int(m.group(2))] = _clean(m.group(1))
    return titles


def main() -> int:
    src = SAMPLE
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    if not src.is_file():
        print(f"Нет файла: {src}", file=sys.stderr)
        return 1

    raw = src.read_text(encoding="utf-8")
    pages = [p.strip() for p in raw.split("---PAGE---") if p.strip()]
    full = "\n\n".join(pages)

    corpus: dict = {
        "meta": {
            "source": "Matrix of Destiny (Матрица Судьбы, 22 аркана)",
            "sample": "Степан 21.06.1994",
        },
        "arcana_names": {str(k): v for k, v in ARCANA_NAMES.items()},
        "sections": {},
        "talent_titles": {},
        "programs": {},
        "static": {},
    }

    current = "misc"
    buffer: list[str] = []

    def flush(section: str) -> None:
        nonlocal buffer
        if not buffer:
            return
        text = "\n".join(buffer)
        if section == "programs":
            corpus["programs"].update(parse_programs(text))
        elif section in ("talents_god", "talents_mother", "talents_father"):
            corpus["talent_titles"].update(parse_talent_titles(text))
            corpus["sections"][section] = {str(k): v for k, v in parse_arcana_blocks(text).items()}
        else:
            blocks = parse_arcana_blocks(text)
            if blocks:
                corpus["sections"][section] = {str(k): v for k, v in blocks.items()}
            elif len(_clean(text)) > 120:
                corpus["static"][section] = _clean(text)

    for line in full.splitlines():
        matched = False
        for sec, pat in SECTION_MARKERS:
            if re.match(pat, line.strip()):
                flush(current)
                current = sec
                buffer = []
                matched = True
                break
        if not matched:
            buffer.append(line)

    flush(current)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sections: {len(corpus['sections'])}, programs: {len(corpus['programs'])}, → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
