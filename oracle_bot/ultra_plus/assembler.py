"""Сборка персональной «Книги о тебе» из матрицы и корпуса текстов."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from oracle_bot.ultra_plus.calculator import MatrixProfile, program_channels, section_numbers

CORPUS_PATH = Path(__file__).resolve().parent / "corpus.json"

INTRO_STATIC = (
    "Человек может находиться в позитивном и негативном состоянии. В позитивном "
    "у человека всё хорошо — он чувствует лёгкость и гармонию. Когда проявляется "
    "негативное состояние, человек «сбивается с пути»: возникают трудности. "
    "Как только возвращается в позитив, жизнь налаживается."
)

PURPOSE_STATIC = (
    "До 40 лет важно понять, кто вы и чем хотите заниматься — судьба даёт испытания, "
    "через которые открываются ответы. С 20 до 40 — время семьи и близких связей. "
    "После 40 — делиться опытом: тогда приходит материальное благополучие. "
    "На протяжении пути важно духовное развитие."
)

SOURCE_NOTE = (
    "Персональная книга по методике Матрицы Судьбы (22 аркана Таро). "
    "Тексты интерпретаций — по классической системе самопознания; "
    "расчёт выполнен индивидуально по вашей дате рождения."
)


@dataclass
class BookSection:
    title: str
    body: str


def _load_corpus() -> dict:
    if not CORPUS_PATH.is_file():
        return {"sections": {}, "programs": {}, "talent_titles": {}, "static": {}, "arcana_names": {}}
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _arcana_name(corpus: dict, n: int) -> str:
    return corpus.get("arcana_names", {}).get(str(n), f"Аркан {n}")


def _text(corpus: dict, section: str, n: int, fallback_section: str | None = None) -> str:
    sec = corpus.get("sections", {}).get(section, {})
    t = sec.get(str(n), "")
    if t:
        return t
    if fallback_section:
        return corpus.get("sections", {}).get(fallback_section, {}).get(str(n), "")
    return ""


def _talent_block(corpus: dict, nums: tuple[int, ...], section: str) -> str:
    titles = corpus.get("talent_titles", {})
    parts: list[str] = []
    for n in nums:
        title = titles.get(str(n)) or _arcana_name(corpus, n)
        body = _text(corpus, section, n)
        if body:
            parts.append(f"{title} ({n})\n\n{body}")
    return "\n\n".join(parts)


def _numbered_blocks(corpus: dict, section: str, nums: tuple[int, ...]) -> str:
    parts: list[str] = []
    for n in nums:
        body = _text(corpus, section, n)
        if body:
            parts.append(f"({n}) {body}")
    return "\n\n".join(parts)


def _programs_block(corpus: dict, profile: MatrixProfile) -> str:
    known = corpus.get("programs", {})
    if not known:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for key, _triple in program_channels(profile):
        if key in seen or key not in known:
            continue
        seen.add(key)
        prog = known[key]
        block = [f"{prog.get('name', key)} ({key})"]
        if prog.get("strengths"):
            block.append("Сильные стороны:\n" + prog["strengths"])
        if prog.get("problems"):
            block.append("Возможные проблемы:\n" + prog["problems"])
        if prog.get("recommendations"):
            block.append("Рекомендации:\n" + prog["recommendations"])
        lines.append("\n\n".join(block))
    return "\n\n---\n\n".join(lines)


def _hvd_enrichment(profile: MatrixProfile) -> str:
    """Дополнение из курса ХВД (если транскрипты на месте)."""
    try:
        from oracle_bot.exclusive_hvd import calculate as hvd_calc
        from oracle_bot.exclusive_hvd.knowledge import (
            intro_course_text,
            typology_course_text,
            yinyang_course_text,
        )

        hvd = hvd_calc(profile.name, profile.birth)
        chunks = [
            f"Кармическая типология ХВД: {hvd.typology}. {hvd.typology_hint}",
            typology_course_text(hvd.typology),
            yinyang_course_text(),
            intro_course_text(),
        ]
        merged = " ".join(c for c in chunks if c).strip()
        if len(merged) > 1200:
            merged = merged[:1199].rsplit(".", 1)[0] + "."
        return merged
    except Exception:
        return ""


def build_teaser(profile: MatrixProfile) -> str:
    bd = profile.birth.strftime("%d.%m.%Y")
    nums = section_numbers(profile)
    a, b = nums["personal"]
    return (
        f"📖 <b>Ultra Plus — Книга о тебе</b>\n"
        f"👤 {profile.name} · {bd}\n\n"
        f"Матрица Судьбы: день <b>{a}</b> · месяц <b>{b}</b> · центр <b>{profile.E}</b>\n\n"
        f"Целая персональная книга-PDF: обложка, оглавление и отдельные главы с "
        f"эпиграфами — качества, таланты, предназначение, деньги, кармические "
        f"программы, отношения, здоровье, прогноз на год.\n\n"
        f"<i>Уникальная книга создаётся под вас. Отдельная оплата — не входит в Премиум.</i>"
    )


def build_book_sections(profile: MatrixProfile) -> list[BookSection]:
    corpus = _load_corpus()
    nums = section_numbers(profile)
    bd = profile.birth.strftime("%d.%m.%Y")
    sections: list[BookSection] = []

    sections.append(
        BookSection(
            title=f"{profile.name} ({bd})",
            body="Персональная книга · Ultra Plus\n\n" + SOURCE_NOTE,
        )
    )

    pa, pb = nums["personal"]
    pos_a = _text(corpus, "personal_positive", pa)
    pos_b = _text(corpus, "personal_positive", pb)
    neg_a = _text(corpus, "personal_negative", pa)
    neg_b = _text(corpus, "personal_negative", pb)
    comm = _text(corpus, "communication", nums["communication"])

    personal = INTRO_STATIC + "\n\n"
    if pos_a or pos_b:
        personal += "В позитиве\n\n"
        if pos_a:
            personal += f"({pa}) {pos_a}\n\n"
        if pos_b:
            personal += f"({pb}) {pos_b}\n\n"
    if neg_a or neg_b:
        personal += "В негативе\n\n"
        if neg_a:
            personal += f"({pa}) {neg_a}\n\n"
        if neg_b:
            personal += f"({pb}) {neg_b}\n\n"
    if comm:
        personal += f"В общении\n\n({nums['communication']}) {comm}"
    sections.append(BookSection(title="Личные качества", body=personal.strip()))

    for title, key in (
        ("Таланты от Бога", "talents_god"),
        ("Таланты по линии матери", "talents_mother"),
        ("Таланты по линии отца", "talents_father"),
    ):
        body = _talent_block(corpus, tuple(nums[key]), key)
        if body:
            sections.append(BookSection(title=title, body=body))

    purpose = PURPOSE_STATIC + "\n\n"
    purpose += _numbered_blocks(corpus, "purpose_20_40", tuple(nums["purpose_20_40"]))
    purpose += "\n\n" + _numbered_blocks(corpus, "purpose_40_60", tuple(nums["purpose_40_60"]))
    pg = nums["purpose_general"]
    pt = _text(corpus, "purpose_general", pg if isinstance(pg, int) else pg)
    if pt:
        purpose += f"\n\nПредназначение общее\n\n({pg}) {pt}"
    sections.append(BookSection(title="Предназначение", body=purpose.strip()))

    money = ""
    md = nums["money_direction"]
    mt = _text(corpus, "money_direction", md if isinstance(md, int) else md)
    if mt:
        money += f"Направление деятельности ({md})\n\n{mt}\n\n"
    money += _numbered_blocks(corpus, "money_success", tuple(nums["money_success"]))
    if money.strip():
        sections.append(BookSection(title="Деньги", body=money.strip()))

    prog = _programs_block(corpus, profile)
    if prog:
        sections.append(BookSection(title="Программы (кармические каналы)", body=prog))

    for title, key, sec in (
        ("Сексуальность", "sexuality", "sexuality"),
        ("Прошлая жизнь", "past_life", "past_life"),
        ("Родители", "parents", "parents"),
        ("Родовые программы (мужская линия)", "lineage_male", "lineage_male"),
        ("Родовые программы (женская линия)", "lineage_female", "lineage_female"),
        ("Обиды на родителей", "parent_wounds", "parent_wounds"),
        ("Дети", "children", "children"),
        ("Отношения", "relationships", "relationships"),
    ):
        body = _numbered_blocks(corpus, sec, tuple(nums[key]))
        if body:
            sections.append(BookSection(title=title, body=body))

    health = _numbered_blocks(corpus, "health_recommend", tuple(nums["health_recommend"]))
    if health:
        sections.append(BookSection(title="Здоровье — личные рекомендации", body=health))

    guide = _numbered_blocks(corpus, "life_guide", tuple(nums["life_guide"]))
    if guide:
        sections.append(BookSection(title="Руководство по жизни", body=guide))

    forecast = _numbered_blocks(corpus, "year_forecast", tuple(nums["year_forecast"]))
    if forecast:
        sections.append(BookSection(title="Прогноз на год", body=forecast))

    hvd = _hvd_enrichment(profile)
    if hvd:
        sections.append(
            BookSection(
                title="Дополнение: Хронально-Векторная Диагностика",
                body=hvd,
            )
        )

    matrix_summary = (
        f"Ключевые точки матрицы: A={profile.A} B={profile.B} C={profile.C} "
        f"D={profile.D} E={profile.E} · AB={profile.AB} AC={profile.AC} "
        f"BD={profile.BD} CD={profile.CD}"
    )
    sections.append(
        BookSection(
            title="Справка: ваши числа матрицы",
            body=matrix_summary + "\n\n" + SOURCE_NOTE,
        )
    )
    return sections
