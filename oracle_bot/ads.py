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


def kb_entry() -> InlineKeyboardMarkup:
    """Лестница: главный CTA — бесплатный вопрос (дальше пейволл сам предложит 99₽)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔮 Задать вопрос бесплатно", url=f"https://t.me/{BOT}?start=mod_tarot")],
            [InlineKeyboardButton(text=f"Сразу полный разбор себя · {HVD_PRICE}₽", url=f"https://t.me/{BOT}?start=hvd")],
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
        "<b>подарить</b>. Целая книга с оглавлением и главами — только про одного человека:\n"
        "• личные качества в плюсе и в минусе;\n"
        "• таланты от рода — по линии матери и отца;\n"
        "• предназначение по возрастам, деньги и каналы реализации;\n"
        "• кармические программы, отношения, здоровье, прогноз на год.\n\n"
        "🎁 <b>Идеальный подарок</b> — маме, партнёру, подруге, ребёнку: "
        "такого о себе они ещё не читали.\n\n"
        f"💳 <b>{ULTRA_PRICE}₽</b> · готовый PDF в Telegram + ответы ассистента по книге."
    )


def entry_dm(user_id: int) -> str:
    """Вход за 99₽: сначала бесплатный вопрос, полный разбор — 99₽. Без большого чека в лоб."""
    intro = personal_intro(user_id)
    return (
        f"🔮 <b>Один вопрос — полный ответ за 99₽</b>\n\n"
        f"{intro}\n\n"
        "Работает просто:\n"
        "1️⃣ Задаёшь свой вопрос — <b>бесплатно</b>: любовь, деньги, решение, человек\n"
        "2️⃣ Получаешь первую часть разбора сразу\n"
        f"3️⃣ Полная версия — детали, прогноз, личный совет — всего <b>99₽</b>\n\n"
        "Дешевле чашки кофе. А ясности — на месяц вперёд.\n\n"
        "Начни с бесплатного вопроса 👇"
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
        "Целая персональная книга-PDF с оглавлением: предназначение, деньги, род, "
        "отношения, прогноз. Себе — как опора, в подарок — как вау-эмоция.\n\n"
        "После покупки можно <b>задавать вопросы ассистенту</b> прямо по своему разбору.\n"
        "Тапни кнопку ниже 👇"
    )


# --- Каналы (без персонализации) ---

def entry_channel(source: str = "") -> str:
    src = f"?start=src_{source.lstrip('@').lower()}" if source else "?start=mod_tarot"
    return (
        "🔮 <b>Один вопрос — честный разбор за 99₽</b>\n\n"
        "Не «вас ждут перемены», а конкретно по твоей ситуации: "
        "что происходит, что делать и чего ждать.\n\n"
        "1️⃣ Задай вопрос — <b>бесплатно</b>\n"
        "2️⃣ Первая часть ответа — сразу\n"
        "3️⃣ Полный разбор с прогнозом и советом — <b>99₽</b>\n\n"
        "Дешевле кофе. Работает прямо в Telegram, 30 секунд.\n\n"
        f'👉 <a href="https://t.me/{BOT}{src}">Задать вопрос бесплатно</a>'
    )


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
        "Целая книга только про одного человека: предназначение, деньги, таланты "
        "рода, отношения, прогноз на год. Себе — опора, в подарок — вау-эмоция.\n\n"
        f"💳 {ULTRA_PRICE}₽ · готовый PDF в Telegram.\n\n"
        f'👉 <a href="https://t.me/{BOT}?start=ultra_plus">Заказать книгу</a>'
    )


# --- Креативы для внешних каналов (можно копировать и постить руками) ---

def _link(start: str) -> str:
    return f"https://t.me/{BOT}?start={start}"


def hvd_creative_1(source: str = "ext") -> str:
    return (
        "🔮 <b>Ты до сих пор не знаешь о себе главного</b>\n\n"
        "Есть разбор, после которого люди пишут: «как будто меня прочитали насквозь». "
        "Это <b>ХВД</b> — диагностика личности по дате рождения.\n\n"
        "За пару минут ты получишь честную карту себя:\n"
        "🧬 характер и темперамент — почему ты реагируешь именно так;\n"
        "💎 скрытые таланты, на которых можно зарабатывать;\n"
        "⛓ что тормозит тебя годами — и как это снять;\n"
        "🌈 твои чакры и энергия + личные рекомендации.\n\n"
        "Это не гороскоп «для всех». Это книга про <b>тебя одного</b> — "
        "которую хочется перечитывать и показать близким.\n\n"
        f"👉 <a href=\"{_link('hvd')}\">Сделать разбор ХВД</a> · приходит прямо в Telegram"
    )


def hvd_creative_2(source: str = "ext") -> str:
    return (
        "✨ <b>«Почему я всё время наступаю на одни и те же грабли?»</b>\n\n"
        "Ответ зашит в твоей дате рождения. <b>ХВД-разбор</b> показывает твой "
        "повторяющийся сценарий — и как из него выйти.\n\n"
        "Подходит, когда ты:\n"
        "• чувствуешь, что ходишь по кругу и не понимаешь себя;\n"
        "• выбираешь профессию, партнёра, город — и боишься ошибиться;\n"
        "• хочешь понять близкого человека или ребёнка.\n\n"
        "Внутри: типология, сильные стороны, задачи жизни, код того, что мешает, "
        "и карта твоей энергии. Конкретно, по-человечески, без эзотерического тумана.\n\n"
        "💬 После разбора можно задать вопросы — бот ответит лично по твоей карте.\n\n"
        f"👉 <a href=\"{_link('hvd')}\">Узнать себя настоящего</a>"
    )


def ultra_creative_1(source: str = "ext") -> str:
    return (
        "📖 <b>Представь книгу, написанную лично про тебя</b>\n\n"
        "Не про знак зодиака. Про <b>тебя</b>: твоё имя на обложке, твоя дата, "
        "твоя судьба внутри. Это «Книга о тебе» — персональный разбор по Матрице Судьбы.\n\n"
        "Целая книга-PDF с оглавлением и главами:\n"
        "🌟 кто ты в плюсе и что включается в минусе;\n"
        "🎁 таланты, данные тебе родом — по линии матери и отца;\n"
        "🧭 предназначение, деньги и где твоя реализация;\n"
        "❤️ любовь, род, дети, здоровье и прогноз на год.\n\n"
        "🎁 <b>Лучший подарок</b> маме, партнёру, подруге: такого о себе они ещё не читали. "
        "Сохраняешь PDF навсегда и перечитываешь.\n\n"
        f"👉 <a href=\"{_link('ultra_plus')}\">Создать «Книгу о тебе»</a>"
    )


def ultra_creative_2(source: str = "ext") -> str:
    return (
        "🎁 <b>Что подарить тому, у кого всё есть?</b>\n\n"
        "Книгу про него самого. «Книга о тебе» — персональная книга-PDF по дате "
        "рождения, которую невозможно купить в магазине, потому что она существует "
        "в одном экземпляре — для одного человека.\n\n"
        "Внутри — целая история жизни: характер, таланты рода, предназначение, "
        "деньги, отношения, кармические программы и прогноз на год. С оглавлением, "
        "главами и эпиграфами — как настоящая книга.\n\n"
        "Себе — как опора и точка ясности. В подарок — как вау-эмоция, "
        "которую помнят.\n\n"
        f"👉 <a href=\"{_link('ultra_plus')}\">Заказать книгу</a> · готовый PDF в Telegram"
    )


def both_creative(source: str = "ext") -> str:
    return (
        "🌌 <b>Два разбора, после которых ты увидишь себя по-новому</b>\n\n"
        f"🔮 <b>ХВД</b> — диагностика личности по дате рождения: характер, таланты, "
        "что мешает и как это снять. Приходит прямо в чат.\n\n"
        f"📖 <b>«Книга о тебе»</b> — персональная книга-PDF: предназначение, деньги, "
        "род, отношения, прогноз. Себе — опора, в подарок — вау-эмоция.\n\n"
        "Не гороскоп для всех. Только про тебя — честно и глубоко.\n\n"
        f"🔮 <a href=\"{_link('hvd')}\">ХВД-разбор</a>   ·   "
        f"📖 <a href=\"{_link('ultra_plus')}\">Книга о тебе</a>"
    )


# --- Крючки по дате рождения (для видео-рекламы и коротких постов) ---
# Идея: «люди, рождённые N числа, обладают тем-то» — зацепка-крючок в бота.
# Возвращаемся к видео позже; здесь — готовый текстовый материал.

_BIRTH_DAY_TRAITS = {
    1: "прирождённые лидеры: воля, амбиция, умение начинать с нуля. Но риск — упрямство и одиночество на вершине.",
    2: "дипломаты и чувствующие: интуиция, мягкая сила, талант к партнёрству. Их слабое место — зависимость от чужого мнения.",
    3: "творцы и обаятельные коммуникаторы: лёгкость, юмор, харизма. Тень — разбрасываются и боятся глубины.",
    4: "опора и система: надёжность, труд, умение строить на годы. Ловушка — застревают в контроле и страхе перемен.",
    5: "свобода и драйв: лёгкие на подъём, обаятельные, многозадачные. Риск — бегут от рутины и обязательств.",
    6: "хранители любви и красоты: забота, ответственность за близких, вкус. Тень — гиперопека и жертвенность.",
    7: "мыслители и искатели смысла: глубина, интуиция, тяга к истине. Слабость — уход в себя и недоверие к миру.",
    8: "про деньги и власть: масштаб, хватка, умение управлять ресурсами. Ловушка — работа на износ ради статуса.",
    9: "гуманисты и завершители: мудрость, сострадание, широкий взгляд. Тень — груз прошлого и трудность отпускать.",
}


def birthday_hook(day: int, *, product: str = "hvd") -> str:
    """Короткий крючок «рождённые N числа …» со ссылкой в бота."""
    n = day if day in _BIRTH_DAY_TRAITS else (sum(int(c) for c in str(day)) or 1)
    while n > 9:
        n = sum(int(c) for c in str(n))
    trait = _BIRTH_DAY_TRAITS.get(n, _BIRTH_DAY_TRAITS[1])
    start = "ultra_plus" if product == "ultra" else "hvd"
    label = "📖 Книга о тебе" if product == "ultra" else "🔮 Разбор по дате рождения"
    return (
        f"✨ <b>Рождённые {n}-го числа</b> — {trait}\n\n"
        "Это только верхушка. Полная карта твоей личности — характер, таланты, "
        "деньги, отношения и предназначение — по точной дате рождения.\n\n"
        f"👉 <a href=\"{_link(start)}\">{label}</a>"
    )


def birthday_hooks_all(product: str = "hvd") -> list[str]:
    return [birthday_hook(n, product=product) for n in range(1, 10)]


# --- Осознанность через боль (воронка как Selena / ProAstro) ---

def kb_awareness() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔴 Узнать оба сценария бесплатно",
                    url=f"https://t.me/{BOT}?start=src_awareness",
                )
            ],
        ]
    )


def pain_awareness_channel(source: str = "") -> str:
    src = f"?start=src_{source.lstrip('@').lower()}" if source else "?start=src_awareness"
    return (
        "🔴 <b>Через 2 месяца ты будешь там же — или уже другой?</b>\n\n"
        "Большинство живёт «на автопилоте»: те же деньги, те же ссоры, "
        "те же решения — и удивляются, почему снова больно.\n\n"
        "В @MOracul_bot — <b>честный разбор по твоей дате</b>:\n"
        "• 🔴 <b>Сценарий 1</b> — что будет, если ничего не менять\n"
        "• 🟢 <b>Сценарий 2</b> — что изменится, если работать с картой\n\n"
        "4 коротких вопроса про твою жизнь → ответ <b>под тебя</b>, не «для всех».\n"
        "Первая часть бесплатно. Полный сценарий 2 — от <b>49₽</b> (первый раз).\n\n"
        "📋 <b>Скопируй и отправь боту</b> (или жми кнопку):\n"
        "<code>Разбор на 2 месяца: что будет если ничего не менять "
        "и что если работать с картой. Дата: ДД.ММ.ГГГГ. Ситуация: ...</code>\n\n"
        f'👉 <a href="https://t.me/{BOT}{src}">Открыть бота — 2 сценария</a>'
    )


def pain_awareness_channel_v2(source: str = "") -> str:
    """Короткий сильный вариант для платного посева: 1 крючок, 1 действие.

    Правки против v1: убран copy-paste блок (ломает конверсию — лишний шаг),
    один явный CTA-кнопка, боль в первой строке, цена-якорь ниже.
    """
    src = f"?start=src_{source.lstrip('@').lower()}" if source else "?start=src_awareness"
    link = f"https://t.me/{BOT}{src}"
    return (
        "🔮 <b>Бесплатный разбор: где ты будешь через 2 месяца?</b>\n\n"
        "Ты снова прокручиваешь в голове один и тот же разговор. "
        "Те же мысли, те же сомнения — и чувство, что топчешься на месте. 🌀\n\n"
        "Загляни на 2 месяца вперёд по своей дате рождения:\n"
        "🔴 что будет, <b>если оставить всё как есть</b>\n"
        "🟢 и что изменится, <b>если начать действовать</b>\n\n"
        "Это не гороскоп «для всех» — 4 вопроса про <b>твою</b> ситуацию и ответ лично тебе.\n"
        "Первый разбор — <b>бесплатно</b>, прямо в Telegram.\n\n"
        f'👉 <a href="{link}">Узнать свои 2 сценария бесплатно</a>'
    )


def pain_awareness_admin_report() -> str:
    return (
        "✅ <b>Внедрено: воронка «осознанность через боль»</b>\n\n"
        "• Мини-опрос (4 вопроса) перед первым разбором\n"
        "• Формат 🔴 Сценарий 1 / 🟢 Сценарий 2 в бесплатных чтениях\n"
        "• Paywall на Сценарий 2 (49₽ первый раз)\n"
        "• Deeplink: <code>?start=src_awareness</code>\n\n"
        "Рекламный пост отправлен в каналы. Можно лить трафик на "
        f"<code>t.me/{BOT}?start=src_awareness</code>"
    )


EXTERNAL_CREATIVES: dict[str, "callable"] = {
    "hvd_1": hvd_creative_1,
    "hvd_2": hvd_creative_2,
    "ultra_1": ultra_creative_1,
    "ultra_2": ultra_creative_2,
    "both": both_creative,
}


def _already_bought(user_id: int, variant: str) -> bool:
    """Не рекламируем то, что человек уже купил (combo — только если купил оба)."""
    hvd = db.has_paid(user_id, "exclusive_hvd")
    ultra = db.has_paid(user_id, "ultra_plus")
    if variant == "hvd":
        return hvd
    if variant == "ultra":
        return ultra
    return hvd and ultra


# После рассылки запускаем воронку возражений (час не купил → дожим).
# Лестница ultra_plus сама спускается до ХВД и Премиума, поэтому для combo — она.
# У entry дожима нет: вход за 99₽ не должен давить большим чеком.
_VARIANT_OBJECTION = {"combo": "ultra_plus", "hvd": "exclusive_hvd", "ultra": "ultra_plus", "entry": "none"}


async def push_books_ad_to_all(bot, *, variant: str = "entry") -> dict[str, Any]:
    """Персональная рассылка рекламы всем пользователям бота (по умолчанию — вход за 99₽)."""
    builder = {"combo": combo_dm, "hvd": hvd_dm, "ultra": ultra_dm, "entry": entry_dm}.get(variant, entry_dm)
    obj_kind = _VARIANT_OBJECTION.get(variant, "none")
    kb = kb_entry() if variant == "entry" else kb_books()
    ids = db.all_user_ids()
    ok = fail = skipped = 0
    for user_id in ids:
        meta = db.get_user_meta(user_id)
        if meta.get("push_opt_out") or _already_bought(user_id, variant):
            skipped += 1
            continue
        sent = False
        try:
            await bot.send_message(
                user_id, builder(user_id), parse_mode="HTML", reply_markup=kb
            )
            sent = True
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            try:
                await bot.send_message(
                    user_id, builder(user_id), parse_mode="HTML", reply_markup=kb
                )
                sent = True
            except Exception:
                fail += 1
        except TelegramForbiddenError:
            fail += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("books ad %s: %s", user_id, e)
            fail += 1
        if sent:
            ok += 1
            db.log_event(user_id, "books_ad_sent", variant)
            try:
                from oracle_bot.pushes import schedule_objection_flow

                schedule_objection_flow(user_id, obj_kind)
            except Exception as e:  # noqa: BLE001
                logger.warning("objection schedule %s: %s", user_id, e)
        await asyncio.sleep(0.05)
    return {"total": len(ids), "ok": ok, "fail": fail, "skipped": skipped}
