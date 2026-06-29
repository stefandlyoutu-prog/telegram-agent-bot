"""Форматирование полного отчёта ХВД для Telegram."""

from __future__ import annotations

from oracle_bot.exclusive_hvd.calculator import HVDProfile, Contour
from oracle_bot.exclusive_hvd.interpreter import (
    CHARACTER_NOTES,
    CHAKRA_MEANING,
    TEMPERAMENT_NOTES,
    THINKING_NOTES,
)
from oracle_bot.exclusive_hvd.knowledge import (
    chakras_course_text,
    contour_course_text,
    intuitive_course_text,
    intro_course_text,
    period_digit_course_text,
    reactivity_course_text,
    task_course_text,
    typology_course_text,
    yinyang_course_text,
)
from oracle_bot.exclusive_hvd.tables import CHAKRA_REHAB

_TG_LIMIT = 3900


def _chakra_bar(pct: int) -> str:
    filled = max(0, min(10, pct // 10))
    return "▰" * filled + "▱" * (10 - filled)


def _clip(text: str, limit: int = 900) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = cut.rfind(".")
    return cut[: last + 1] if last > limit // 2 else cut + "…"


def _contour_block(title: str, contour: Contour, cycle: int, notes: dict[str, str]) -> str:
    c1, c2 = contour.chakras
    note = notes.get(contour.label.split("(")[0].strip(), "")
    course = _clip(contour_course_text(contour.label), 350)
    extra = f"\n<i>{note}</i>" if note else ""
    course_block = f"\n<i>Из курса:</i> {course}" if course else ""
    return (
        f"<b>{title}</b> (маркер {contour.marker}, цикл {cycle})\n"
        f"Тип: {contour.label}\n"
        f"• {c1.name}: {c1.percent}% {_chakra_bar(c1.percent)} — {CHAKRA_MEANING.get(c1.name, '')}\n"
        f"• {c2.name}: {c2.percent}% {_chakra_bar(c2.percent)} — {CHAKRA_MEANING.get(c2.name, '')}"
        f"{extra}{course_block}"
    )


def _rehab_section(profile: HVDProfile) -> str:
    keys = [
        ("muladhara", profile.physical.chakras[0]),
        ("svadhisthana", profile.physical.chakras[1]),
        ("manipura", profile.emotional.chakras[0]),
        ("anahata", profile.emotional.chakras[1]),
        ("vishuddha", profile.intellectual.chakras[0]),
        ("ajna", profile.intellectual.chakras[1]),
    ]
    lines = ["<b>🔧 Реабилитация чакр</b> (методичка курса)"]
    chakras_note = _clip(chakras_course_text(), 400)
    if chakras_note:
        lines.append(f"\n<i>{chakras_note}</i>")
    for key, ch in keys:
        tips = CHAKRA_REHAB.get(key, [])
        level = "ниже нормы" if ch.percent < 35 else ("высокий потенциал" if ch.percent > 70 else "средний уровень")
        action = "развивать и раскручивать" if ch.percent < 35 else (
            "использовать, но не перегружать — разгрузка" if ch.percent > 70 else "поддерживать баланс"
        )
        lines.append(f"\n<b>{ch.name}</b> ({ch.percent}%, {level}) — {action}")
        for t in tips:
            lines.append(f"  · {t}")
    return "\n".join(lines)


def build_teaser(profile: HVDProfile) -> str:
    bd = profile.birth.strftime("%d.%m.%Y")
    return (
        f"✨ <b>Эксклюзив: полный курс ХВД</b>\n"
        f"👤 {profile.name} · {bd}\n\n"
        f"Кармическая типология: <b>{profile.typology}</b>\n"
        f"Маркеры: физ {profile.markers_raw[0]} · эмо {profile.markers_raw[1]} · инт {profile.markers_raw[2]}\n\n"
        f"Темперамент: {profile.physical.label}\n"
        f"Характер: {profile.emotional.label}\n"
        f"Мышление: {profile.intellectual.label}\n\n"
        f"<i>Отдельная оплата — не входит в Премиум. "
        f"После оплаты — полный разбор по всем параметрам курса.</i>"
    )


def build_report_parts(profile: HVDProfile) -> list[str]:
    bd = profile.birth.strftime("%d.%m.%Y")
    parts: list[str] = []

    intro = intro_course_text()
    typo_course = typology_course_text(profile.typology)
    parts.append(
        f"🔮 <b>ХВД — полный разбор курса</b>\n"
        f"👤 {profile.name} · 📅 {bd}\n\n"
        f"<b>Кармическая типология: {profile.typology}</b>\n"
        f"{profile.typology_hint}"
        + (f"\n\n<i>Из курса (уроки 2-x):</i> {_clip(typo_course, 800)}" if typo_course else "")
        + (f"\n\n<i>{_clip(intro, 300)}</i>" if intro else "")
    )

    parts.append(
        _contour_block("⚡ Физический контур · темперамент", profile.physical, 23, TEMPERAMENT_NOTES)
        + "\n\n"
        + _contour_block("💫 Эмоциональный контур · характер", profile.emotional, 28, CHARACTER_NOTES)
        + "\n\n"
        + _contour_block("🧠 Интеллектуальный контур · мышление", profile.intellectual, 33, THINKING_NOTES)
        + f"\n\n<i>{profile.sahasrara_hint}</i>"
    )

    react_text = reactivity_course_text(profile.reactivity) or profile.egoism_note
    yin_text = yinyang_course_text()
    intuit_text = intuitive_course_text()
    parts.append(
        f"<b>⚖️ Инь / Ян · Хочу / Могу</b>\n"
        f"Инь: <b>{profile.yin_pct}%</b> · Ян: <b>{profile.yang_pct}%</b>\n"
        f"Хочу: <b>{profile.want}%</b> · Могу (муладхара): <b>{profile.can_pct}%</b>\n"
        f"Сексуальный потенциал: <b>{profile.sexual_potential}</b>"
        + (f"\n\n<i>Из курса (урок 6):</i> {_clip(yin_text, 700)}" if yin_text else "")
        + "\n\n"
        f"<b>🎯 Интуитивный контур</b>\n"
        f"Вербальный: <b>{profile.verbal_intellect}%</b> · "
        f"Невербальный: <b>{profile.nonverbal_intellect}%</b>"
        + (f"\n<i>{_clip(intuit_text, 500)}</i>" if intuit_text else "")
        + "\n\n"
        f"<b>Эгоизм / альтруизм:</b> {profile.reactivity}\n"
        f"Я / Мы: <b>{profile.reactivity_ya}%</b> / <b>{profile.reactivity_my}%</b>\n"
        f"<i>{_clip(react_text, 900)}</i>"
    )

    period_lines = [
        "<b>📅 Периоды жизни</b>",
        f"Код негатива: <b>{profile.negative_code}</b> · цифры: "
        + " ".join(str(p.digit) for p in profile.life_periods),
    ]
    for p in profile.life_periods:
        course = period_digit_course_text(p.digit)
        period_lines.append(
            f"\n<b>{p.index}. {p.age_range}</b> · цифра <b>{p.digit}</b> · {p.theme}\n"
            f"Чакра: {p.chakra} · блок {p.group}\n"
            f"{p.description}"
            + (f"\n<i>Из курса:</i> {_clip(course, 650)}" if course else "")
        )
    parts.append("\n".join(period_lines))

    pos_digits = " · ".join(str(x) for x in profile.positive_digits)
    task_block = (
        f"<b>📜 Код жизни и задачи</b>\n"
        f"Код негатива: <b>{profile.negative_code}</b>\n"
        f"Код позитива (сумма): <b>{profile.positive_code}</b>\n"
        f"Код позитива по цифрам (+ типология {profile.typology}): <b>{pos_digits}</b>\n\n"
        f"Задача прошлого: <b>{profile.task_past}</b> — {profile.task_past_hint}\n"
        f"Задача настоящего: <b>{profile.task_present}</b> — {profile.task_present_hint}\n"
        f"Родовая: <b>{profile.task_lineage}</b> — {profile.task_lineage_hint}\n"
        f"От родителей: <b>{profile.task_parents}</b> — {profile.task_parents_hint}"
    )
    for label, num in (
        ("прошлого", profile.task_past),
        ("настоящего", profile.task_present),
        ("рода", profile.task_lineage),
        ("родителей", profile.task_parents),
    ):
        extra = task_course_text(num)
        if extra:
            task_block += f"\n\n<i>Урок 8-x — задача {label}:</i> {_clip(extra, 400)}"
    parts.append(task_block)

    parts.append(_rehab_section(profile))

    parts.append(
        "<i>ХВД по методике Жажкова–Солодкова (курс numerologyHVD). "
        "Продукт отдельный от Премиум. Не заменяет медицинскую консультацию.</i>"
    )

    # разбить слишком длинные части для Telegram
    final: list[str] = []
    for chunk in parts:
        if len(chunk) <= _TG_LIMIT:
            final.append(chunk)
            continue
        start = 0
        while start < len(chunk):
            final.append(chunk[start : start + _TG_LIMIT])
            start += _TG_LIMIT
    return final
