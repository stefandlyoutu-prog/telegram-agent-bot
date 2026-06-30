"""Рекламные тексты ХВД и Ultra Plus: личка (персонально) + каналы."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.config import (
    ORACLE_BOT_USERNAME,
    ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
    ORACLE_ULTRA_PLUS_PRICE_RUB,
)

logger = logging.getLogger(__name__)

BOT = ORACLE_BOT_USERNAME.lstrip("@")
HVD_PRICE = ORACLE_EXCLUSIVE_HVD_PRICE_RUB
ULTRA_PRICE = ORACLE_ULTRA_PLUS_PRICE_RUB

_MODULE_HOOK = {
    "tarot": "ты раскладывал Таро",
    "compat": "ты смотрел совместимость",
    "natal": "ты собирал натальную карту",
    "palm": "ты гадал по ладони",
    "numerology": "тебя интересовали числа судьбы",
    "destiny": "ты заглядывал в судьбу дня",
    "chakra": "ты проверял чакры",
    "horo_today": "ты читал свой гороскоп",
    "dream": "ты разбирал сны",
    "career": "тебя волновала карьера",
    "dating": "тебя волновали отношения",
    "family_karma": "тебя интересовала родовая карма",
}


def kb_books() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔮 ХВД-разбор · {HVD_PRICE}₽", url=f"https://t.me/{BOT}?start=hvd")],
            [InlineKeyboardButton(text=f"📖 Книга о тебе · {ULTRA_PRICE}₽", url=f"https://t.me/{BOT}?start=ultra_plus")],
        ]
    )


def _greeting(profile: dict, meta: dict) -> str:
    name = (profile.get("name") or meta.get("first_name") or "").strip()
    return f"{name}, " if name and name.lower() not in ("гость", "guest") else ""


def personal_intro(user_id: int) -> str:
    """Персональная зацепка по тому, чем человек интересовался."""
    profile = db.get_profile(user_id)
    meta = db.get_user_meta(user_id)
    greet = _greeting(profile, meta)
    last = (meta.get("last_module") or "").strip()
    hook = _MODULE_HOOK.get(last)
    if hook:
        return (
            f"{greet}помнишь, {hook} в Оракуле? "
            "Это была лишь верхушка. Под ней — вся карта твоей судьбы."
        )
    if profile.get("birth_date"):
        return (
            f"{greet}по твоей дате рождения можно собрать не просто гороскоп, "
            "а полную карту личности — характер, деньги, отношения, предназначение."
        )
    return f"{greet}у нас вышли два самых глубоких персональных разбора за всё время."


def hvd_dm(user_id: int) -> str:
    intro = personal_intro(user_id)
    return (
        f"🔮 <b>ХВД — Хронально-Векторная Диагностика</b>\n\n"
        f"{intro}\n\n"
        "Это полный разбор тебя по дате рождения:\n"
        "• твой <b>характер и темперамент</b> — почему ты реагируешь именно так;\n"
        "• <b>сильные стороны и таланты</b>, которые приносят деньги;\n"
        "• <b>задачи жизни</b> и код негатива — что тормозит и как это снять;\n"
        "• <b>чакры и энергия</b> + личная методичка реабилитации.\n\n"
        "Подходит, когда чувствуешь, что «ходишь по кругу», не понимаешь себя "
        "или близкого человека, выбираешь путь, профессию, партнёра.\n\n"
        f"💳 <b>{HVD_PRICE}₽</b> · разбор приходит прямо в чат + можно задать вопросы ассистенту."
    )


def ultra_dm(user_id: int) -> str:
    intro = personal_intro(user_id)
    return (
        f"📖 <b>Ultra Plus — «Книга о тебе»</b>\n\n"
        f"{intro}\n\n"
        "Персональная книга в PDF, которую можно сохранить, перечитывать и "
        "<b>подарить</b>. 30+ страниц только про одного человека:\n"
        "• личные качества в плюсе и в минусе;\n"
        "• таланты от рода — по линии матери и отца;\n"
        "• предназначение по возрастам, деньги и каналы реализации;\n"
        "• кармические программы, отношения, здоровье, прогноз на год.\n\n"
        "🎁 <b>Идеальный подарок</b> — маме, партнёру, подруге, ребёнку: "
        "такого о себе они ещё не читали.\n\n"
        f"💳 <b>{ULTRA_PRICE}₽</b> · готовый PDF в Telegram + ответы ассистента по книге."
    )


def combo_dm(user_id: int) -> str:
    """Главное рекламное сообщение в личку — персональное, с двумя продуктами."""
    intro = personal_intro(user_id)
    return (
        f"✨ <b>Узнай о себе то, что не покажет ни один гороскоп</b>\n\n"
        f"{intro}\n\n"
        f"🔮 <b>ХВД-разбор · {HVD_PRICE}₽</b>\n"
        "Характер, таланты, задачи жизни, чакры и что мешает — по дате рождения, "
        "прямо в чат. Когда хочешь наконец понять себя или близкого.\n\n"
        f"📖 <b>«Книга о тебе» · {ULTRA_PRICE}₽</b>\n"
        "Персональная книга-PDF на 30+ страниц: предназначение, деньги, род, "
        "отношения, прогноз. Себе — как опора, в подарок — как вау-эмоция.\n\n"
        "После покупки можно <b>задавать вопросы ассистенту</b> прямо по своему разбору.\n"
        "Тапни кнопку ниже 👇"
    )


# --- Каналы (без персонализации) ---

def hvd_channel(source: str = "") -> str:
    return (
        "🔮 <b>Кто ты на самом деле — по дате рождения</b>\n\n"
        "ХВД-разбор: характер, скрытые таланты, задачи жизни, код негатива и чакры. "
        "Не общие слова, а конкретно про тебя — что мешает и как это снять.\n\n"
        f"💳 {HVD_PRICE}₽ · приходит прямо в Telegram.\n\n"
        f'👉 <a href="https://t.me/{BOT}?start=hvd">Сделать разбор</a>'
    )


def ultra_channel(source: str = "") -> str:
    return (
        "📖 <b>«Книга о тебе» — персональная, в PDF</b>\n\n"
        "30+ страниц только про одного человека: предназначение, деньги, таланты "
        "рода, отношения, прогноз на год. Себе — опора, в подарок — вау-эмоция.\n\n"
        f"💳 {ULTRA_PRICE}₽ · готовый PDF в Telegram.\n\n"
        f'👉 <a href="https://t.me/{BOT}?start=ultra_plus">Заказать книгу</a>'
    )


async def push_books_ad_to_all(bot, *, variant: str = "combo") -> dict[str, Any]:
    """Персональная рассылка рекламы книг всем пользователям бота."""
    builder = {"combo": combo_dm, "hvd": hvd_dm, "ultra": ultra_dm}.get(variant, combo_dm)
    ids = db.all_user_ids()
    ok = fail = 0
    for user_id in ids:
        meta = db.get_user_meta(user_id)
        if meta.get("push_opt_out"):
            continue
        try:
            await bot.send_message(
                user_id, builder(user_id), parse_mode="HTML", reply_markup=kb_books()
            )
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            try:
                await bot.send_message(
                    user_id, builder(user_id), parse_mode="HTML", reply_markup=kb_books()
                )
                ok += 1
            except Exception:
                fail += 1
        except TelegramForbiddenError:
            fail += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("books ad %s: %s", user_id, e)
            fail += 1
        await asyncio.sleep(0.05)
    return {"total": len(ids), "ok": ok, "fail": fail}
