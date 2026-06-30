"""ХВД как живая персональная книга: данные расчёта → тёплый личный текст."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass

from oracle_bot.book_writer import SectionSpec, write_sections
from oracle_bot.exclusive_hvd.calculator import HVDProfile
from oracle_bot.exclusive_hvd.interpreter import CHAKRA_MEANING
from oracle_bot.exclusive_hvd.report import build_report_parts  # шаблонный фолбэк

logger = logging.getLogger(__name__)

_TG_LIMIT = 3900


@dataclass
class Section:
    title: str
    body: str


def _lvl(pct: int) -> str:
    if pct >= 75:
        return "очень сильно выражена — это твоя природная мощь и одновременно то, что легко перегружается"
    if pct >= 60:
        return "хорошо развита, на неё можно опираться"
    if pct >= 40:
        return "в рабочем балансе"
    if pct >= 25:
        return "приглушена, включается не сразу"
    return "почти спит — её стоит бережно пробуждать"


def _ch(profile: HVDProfile):
    return {
        "Муладхара": profile.physical.chakras[0].percent,
        "Свадхистана": profile.physical.chakras[1].percent,
        "Манипура": profile.emotional.chakras[0].percent,
        "Анахата": profile.emotional.chakras[1].percent,
        "Вишудха": profile.intellectual.chakras[0].percent,
        "Аджна": profile.intellectual.chakras[1].percent,
    }


def _chakra_facts(profile: HVDProfile, names: tuple[str, ...]) -> str:
    ch = _ch(profile)
    out = []
    for n in names:
        out.append(f"- {n} ({CHAKRA_MEANING.get(n, '')}): {_lvl(ch[n])}")
    return "\n".join(out)


def _specs(profile: HVDProfile) -> list[SectionSpec]:
    fb = {}
    try:
        parts = build_report_parts(profile)
        # сопоставление фолбэков по индексам частей шаблона
        fb = {i: p for i, p in enumerate(parts)}
    except Exception as e:  # noqa: BLE001
        logger.warning("hvd fallback parts: %s", e)

    ya, my = profile.reactivity_ya, profile.reactivity_my
    leadership = (
        "ярко выраженное «Я», лидер, который вовлекает других в свои задачи"
        if ya >= 80
        else "сбалансированное «Я и Мы» — умеет и вести, и быть в команде"
        if ya >= 55
        else "мягкое «Я», человек команды, которому важно «мы»"
    )

    return [
        SectionSpec(
            title="Кто ты на самом деле",
            brief=(
                "Вступление-портрет. Тёплое узнавание: какой это человек по сути, "
                "его главный внутренний стержень и противоречие, как он выглядит со "
                "стороны и какой он внутри. Задай тон всей книге."
            ),
            facts=(
                f"Кармическая типология: {profile.typology_hint}\n"
                f"Темперамент: {profile.physical.label}\n"
                f"Характер: {profile.emotional.label}\n"
                f"Мышление: {profile.intellectual.label}\n"
                f"Позиция «Я/Мы»: {leadership}"
            ),
            words="240–320",
            fallback=fb.get(0, ""),
        ),
        SectionSpec(
            title="Твоё тело и темперамент",
            brief=(
                "Физический контур: природная энергия, выносливость, чувственность, "
                "как тело реагирует на стресс, какой ритм жизни ему подходит."
            ),
            facts=(
                f"Тип темперамента: {profile.physical.label}\n"
                + _chakra_facts(profile, ("Муладхара", "Свадхистана"))
                + f"\nВнутренняя устойчивость («могу»): {_lvl(profile.can_pct)}"
            ),
            fallback=fb.get(1, ""),
        ),
        SectionSpec(
            title="Твой характер и сердце",
            brief=(
                "Эмоциональный контур: воля и самооценка, отношение к деньгам и власти, "
                "способность любить и принимать, как ведёт себя в близких отношениях и "
                "в конфликте. Бережно про теневую сторону."
            ),
            facts=(
                f"Тип характера: {profile.emotional.label}\n"
                + _chakra_facts(profile, ("Манипура", "Анахата"))
                + f"\nЭгоизм/альтруизм: {profile.reactivity}. {profile.egoism_note}\n"
                f"Позиция: {leadership}"
            ),
            fallback=fb.get(2, ""),
        ),
        SectionSpec(
            title="Как ты думаешь",
            brief=(
                "Интеллектуальный контур: стиль мышления, речь и самовыражение, "
                "интуиция и анализ, как принимает решения, где сила ума, где ловушки."
            ),
            facts=(
                f"Тип мышления: {profile.intellectual.label}\n"
                + _chakra_facts(profile, ("Вишудха", "Аджна"))
                + f"\n{profile.sahasrara_hint}\n"
                f"Вербальный интеллект {_lvl(int(profile.verbal_intellect))}; "
                f"невербальный {_lvl(int(profile.nonverbal_intellect))}."
            ),
            fallback=fb.get(2, ""),
        ),
        SectionSpec(
            title="Чего ты хочешь и что можешь",
            brief=(
                "Энергия желаний и воплощения: баланс «инь/ян» (восприятие и действие), "
                "разрыв между «хочу» и «могу», как наполнять себя энергией, чтобы "
                "желания доходили до результата. Про чувственность — тактично, по-взрослому."
            ),
            facts=(
                f"Инь (восприятие, накопление): {'преобладает' if profile.yin_pct>profile.yang_pct else 'в меру'}; "
                f"Ян (действие, отдача): {'преобладает' if profile.yang_pct>=profile.yin_pct else 'в меру'}.\n"
                f"Разрыв «хочу/могу»: {'заметный — желания крупнее, чем текущий ресурс' if profile.want>20 else 'небольшой — желания и возможности близки'}.\n"
                f"Опора на действие («могу»): {_lvl(profile.can_pct)}."
            ),
            fallback=fb.get(3, ""),
        ),
        SectionSpec(
            title="Твой путь по возрастам",
            brief=(
                "Периоды жизни как глава-история: какие уроки и темы человек проходит "
                "в каждом возрастном отрезке, что важно прожить и не пропустить. "
                "Свяжи периоды в единую линию судьбы."
            ),
            facts="\n".join(
                f"- {p.age_range}: тема «{p.theme}» — {p.description}"
                for p in profile.life_periods
            ),
            words="260–360",
            fallback=fb.get(4, ""),
        ),
        SectionSpec(
            title="Твои задачи и предназначение",
            brief=(
                "Главные задачи души: что важно освоить (из прошлого опыта, в настоящем, "
                "по линии рода и от родителей). Сведи в понятное предназначение — куда "
                "ведёт эта жизнь и в чём её смысл именно для него."
            ),
            facts=(
                f"Задача из прошлого: {profile.task_past_hint}\n"
                f"Задача настоящего: {profile.task_present_hint}\n"
                f"Родовая задача: {profile.task_lineage_hint}\n"
                f"Задача от родителей: {profile.task_parents_hint}"
            ),
            fallback=fb.get(4, ""),
        ),
        SectionSpec(
            title="Как жить в своём плюсе",
            brief=(
                "Практичная тёплая глава-напутствие: как этому человеку наполнять "
                "энергию там, где она проседает, и не перегорать там, где её через край. "
                "Конкретные, выполнимые привычки и опоры на каждый день. Заверши книгу "
                "поддерживающим, вдохновляющим абзацем лично к нему."
            ),
            facts=(
                "Энергия по центрам (что развивать, что разгружать):\n"
                + "\n".join(f"- {n}: {_lvl(p)}" for n, p in _ch(profile).items())
            ),
            words="260–340",
            fallback=fb.get(5, ""),
        ),
    ]


def _passport(profile: HVDProfile) -> str:
    ch = _ch(profile)
    bars = " · ".join(f"{n} {p}%" for n, p in ch.items())
    return (
        "<b>📋 Твой паспорт ХВД</b> (для тех, кто любит точные данные)\n\n"
        f"Кармическая типология: <b>{profile.typology}</b>\n"
        f"Темперамент: {profile.physical.label}\n"
        f"Характер: {profile.emotional.label}\n"
        f"Мышление: {profile.intellectual.label}\n"
        f"Энергия центров: {bars}\n"
        f"Инь {profile.yin_pct}% · Ян {profile.yang_pct}% · "
        f"Я/Мы {profile.reactivity_ya}%/{profile.reactivity_my}%\n\n"
        "<i>ХВД по методике Жажкова–Солодкова. Продукт отдельный от Премиум. "
        "Не заменяет медицинскую консультацию.</i>"
    )


_TITLE_EMOJI = {
    "Кто ты на самом деле": "✨",
    "Твоё тело и темперамент": "⚡",
    "Твой характер и сердце": "💗",
    "Как ты думаешь": "🧠",
    "Чего ты хочешь и что можешь": "⚖️",
    "Твой путь по возрастам": "📅",
    "Твои задачи и предназначение": "🎯",
    "Как жить в своём плюсе": "🌿",
}


def _to_html(body: str) -> str:
    out = []
    for ln in body.splitlines():
        s = ln.rstrip()
        if s.startswith("## "):
            out.append(f"<b>{html.escape(s[3:].strip())}</b>")
        else:
            out.append(html.escape(s))
    return "\n".join(out)


async def build_hvd_book(profile: HVDProfile) -> list[Section]:
    specs = _specs(profile)
    bodies = await write_sections(profile.name, specs, concurrency=2)
    sections: list[Section] = []
    for spec, body in zip(specs, bodies):
        body = (body or spec.fallback or "").strip()
        if not body:
            continue
        sections.append(Section(title=spec.title, body=body))
    return sections


def render_tg_parts(profile: HVDProfile, sections: list[Section]) -> list[str]:
    """Telegram-части из готовых разделов книги (+ паспорт). Фолбэк — шаблон."""
    if not sections:
        return build_report_parts(profile)

    bd = profile.birth.strftime("%d.%m.%Y")
    parts: list[str] = [
        f"📖 <b>ХВД — твоя личная книга</b>\n"
        f"👤 {html.escape(profile.name)} · {bd}\n\n"
        f"<i>Это написано лично про тебя — читай не спеша.</i>"
    ]
    for sec in sections:
        emoji = _TITLE_EMOJI.get(sec.title, "•")
        header = f"{emoji} <b>{html.escape(sec.title)}</b>\n\n"
        body_html = _to_html(sec.body)
        chunk = header + body_html
        if len(chunk) <= _TG_LIMIT:
            parts.append(chunk)
        else:
            start = 0
            first = True
            while start < len(body_html):
                piece = body_html[start : start + _TG_LIMIT - len(header)]
                parts.append((header if first else "") + piece)
                first = False
                start += _TG_LIMIT - len(header)
    parts.append(_passport(profile))
    return parts


async def build_report_parts_async(profile: HVDProfile) -> list[str]:
    """Совместимость: сгенерировать книгу и отрендерить Telegram-части."""
    try:
        sections = await build_hvd_book(profile)
    except Exception as e:  # noqa: BLE001
        logger.warning("hvd book failed, fallback to template: %s", e)
        sections = []
    return render_tg_parts(profile, sections)


def book_plain_text(profile: HVDProfile, sections: list[Section]) -> str:
    """Полный текст книги для PDF/follow-up (с маркерами ## для подзаголовков)."""
    out = [f"ХВД — твоя личная книга\n{profile.name} · {profile.birth.strftime('%d.%m.%Y')}"]
    for sec in sections:
        out.append(f"## {sec.title}\n\n{sec.body}")
    ch = _ch(profile)
    out.append(
        "## Паспорт ХВД\n\n"
        f"Типология {profile.typology}. Темперамент: {profile.physical.label}. "
        f"Характер: {profile.emotional.label}. Мышление: {profile.intellectual.label}.\n"
        + ", ".join(f"{n} {p}%" for n, p in ch.items())
    )
    return "\n\n".join(out)
