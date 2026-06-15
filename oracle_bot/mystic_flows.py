"""Запуски глубоких мистических модулей."""

from __future__ import annotations

import random
import re
from datetime import date

from aiogram.types import Message

from oracle_bot import storage as db
from oracle_bot.mystic_data import (
    CHAKRAS,
    CRYSTALS,
    ICHING as ICHING_HEXES,
    LENORMAND as LENORMAND_CARDS,
    extract_place,
    moon_phase_today,
    parse_birth_date,
    parse_birth_time,
    zodiac_from_date,
    zodiac_label,
)
from oracle_bot.formatting import reading_header
from oracle_bot.prompts import (
    AKASHIC,
    AURA,
    BIORHYTHM,
    CHAKRA,
    CRYSTAL,
    FAMILY_KARMA,
    ICHING,
    KARMA,
    LENORMAND,
    MOON,
    NATAL,
    PAST_LIFE,
    SHADOW,
    SPIRIT_GUIDE,
    TRANSIT,
    TWIN_FLAME,
)


def profile_ctx(uid: int) -> dict:
    p = db.get_profile(uid)
    sign_key = p.get("zodiac")
    return {
        "name": p.get("name") or "Путник",
        "birth": p.get("birth_date") or "не указана",
        "birth_time": p.get("birth_time") or "неизвестно",
        "birth_place": p.get("birth_place") or "не указано",
        "sign": zodiac_label(sign_key) if sign_key else "не определён",
        "sign_key": sign_key,
    }


def save_birth_from_text(uid: int, text: str) -> date | None:
    bd = parse_birth_date(text)
    if not bd:
        return None
    bt = parse_birth_time(text)
    place = extract_place(text)
    sign = zodiac_from_date(bd)
    db.save_profile(
        uid,
        birth_date=bd.strftime("%d.%m.%Y"),
        zodiac=sign,
        birth_time=bt,
        birth_place=place,
    )
    return bd


def natal_prompt(uid: int, raw: str) -> tuple[str, str] | None:
    bd = save_birth_from_text(uid, raw) or (
        parse_birth_date(db.get_profile(uid).get("birth_date") or "")
    )
    if not bd:
        return None
    ctx = profile_ctx(uid)
    name = re.sub(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", "", raw).strip() or ctx["name"]
    if name and name != ctx["name"]:
        db.save_profile(uid, name=name[:40])
        ctx = profile_ctx(uid)
    prompt = NATAL.format(
        name=ctx["name"],
        birth=bd.strftime("%d.%m.%Y"),
        birth_time=ctx["birth_time"],
        birth_place=ctx["birth_place"],
        sign=ctx["sign"],
    )
    return prompt, reading_header("Натальная карта", ctx["name"])


def past_life_prompt(uid: int, focus: str) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    prompt = PAST_LIFE.format(
        name=ctx["name"],
        birth=ctx["birth"],
        sign=ctx["sign"],
        focus=focus or "общий поиск души",
    )
    return prompt, reading_header("Прошлые жизни", ctx["name"])


def karma_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    return (
        KARMA.format(name=ctx["name"], birth=ctx["birth"], sign=ctx["sign"]),
        reading_header("Карма", ctx["name"]),
    )


def akashic_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    return (
        AKASHIC.format(name=ctx["name"], birth=ctx["birth"], sign=ctx["sign"]),
        reading_header("Записи Акаши", ctx["name"]),
    )


def iching_prompt(uid: int, question: str = "") -> tuple[str, str]:
    hexagram = random.choice(ICHING_HEXES)
    ctx = profile_ctx(uid)
    q = question or f"день {date.today()}, знак {ctx['sign']}"
    return (
        ICHING.format(hex=hexagram, context=q),
        reading_header("И-Цзин", hexagram.split("—")[0].strip()),
    )


def chakra_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    weak, strong = random.sample(CHAKRAS, 2)
    return (
        CHAKRA.format(name=ctx["name"], sign=ctx["sign"], weak=weak, strong=strong),
        reading_header("Чакры", f"фокус {weak}"),
    )


def aura_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    return (
        AURA.format(name=ctx["name"], sign=ctx["sign"], birth=ctx["birth"]),
        reading_header("Аура", ctx["name"]),
    )


def spirit_guide_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    symbols = ["Сова", "Волк", "Белый олень", "Змея", "Орёл", "Лиса", "Медведь", "Бабочка"]
    sym = random.choice(symbols)
    return (
        SPIRIT_GUIDE.format(name=ctx["name"], sign=ctx["sign"], symbol=sym),
        reading_header("Наставник", sym),
    )


def moon_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    phase = moon_phase_today()
    return (
        MOON.format(
            today=date.today().strftime("%d.%m.%Y"),
            phase=phase,
            sign=ctx["sign"],
            name=ctx["name"],
        ),
        reading_header("Лунный день", phase),
    )


def crystal_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    c = random.choice(CRYSTALS)
    return (
        CRYSTAL.format(crystal=c, name=ctx["name"], sign=ctx["sign"]),
        reading_header("Кристалл дня", c),
    )


def shadow_prompt(uid: int) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    return (
        SHADOW.format(name=ctx["name"], birth=ctx["birth"], sign=ctx["sign"]),
        reading_header("Теневая сторона", ctx["name"]),
    )


def twin_flame_prompt(uid: int, text: str) -> tuple[str, str]:
    ctx = profile_ctx(uid)
    return (
        TWIN_FLAME.format(text=text, name=ctx["name"], sign=ctx["sign"]),
        reading_header("Родственная душа"),
    )


def biorhythm_prompt(uid: int) -> tuple[str, str] | None:
    ctx = profile_ctx(uid)
    bd = parse_birth_date(ctx["birth"])
    if not bd:
        return None
    return (
        BIORHYTHM.format(birth=ctx["birth"], today=date.today().strftime("%d.%m.%Y")),
        reading_header("Биоритмы", ctx["birth"]),
    )


def transit_prompt(uid: int) -> tuple[str, str] | None:
    ctx = profile_ctx(uid)
    if not ctx["sign_key"]:
        return None
    return (
        TRANSIT.format(
            today=date.today().strftime("%d.%m.%Y"),
            sign=ctx["sign"],
            name=ctx["name"],
        ),
        reading_header("Транзиты", ctx["sign"]),
    )


def lenormand_prompt(question: str) -> tuple[str, str]:
    cards = random.sample(LENORMAND_CARDS, 3)
    q = question or "общий вектор"
    return (
        LENORMAND.format(cards=", ".join(cards), question=q),
        reading_header("Ленорман", ", ".join(cards)),
    )


def family_karma_prompt(text: str) -> tuple[str, str]:
    return (
        FAMILY_KARMA.format(text=text),
        reading_header("Родовая карма"),
    )
