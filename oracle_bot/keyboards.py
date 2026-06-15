"""Клавиатуры Оракула."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from oracle_bot.config import ORACLE_DEEP_STARS, ORACLE_PREMIUM_STARS, ORACLE_REFERRAL_BONUS, ORACLE_WEBAPP_URL
from oracle_bot.mystic_data import ZODIAC_SIGNS
from oracle_bot.prompts import CROSS_SELL


def _webapp_row() -> list[InlineKeyboardButton] | None:
    if not ORACLE_WEBAPP_URL:
        return None
    return [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=ORACLE_WEBAPP_URL))]


def kb_main() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    wa = _webapp_row()
    if wa:
        rows.append(wa)
    rows.extend([
        [
            InlineKeyboardButton(text="Сегодня", callback_data="mod:horo_today"),
            InlineKeyboardButton(text="Таро", callback_data="mod:tarot"),
        ],
        [
            InlineKeyboardButton(text="Карта дня", callback_data="mod:card_day"),
            InlineKeyboardButton(text="Натальная", callback_data="mod:natal"),
        ],
        [
            InlineKeyboardButton(text="Пара", callback_data="mod:compat"),
            InlineKeyboardButton(text="Ладонь", callback_data="mod:palm"),
        ],
        [
            InlineKeyboardButton(text="Ещё разделы", callback_data="nav:mystic"),
            InlineKeyboardButton(text="Профиль", callback_data="mod:profile"),
        ],
        [
            InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
            InlineKeyboardButton(text="Пригласить", callback_data="mod:referral"),
        ],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_referral(user_id: int) -> InlineKeyboardMarkup:
    from oracle_bot.referrals import share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поделиться ссылкой", url=share_url(user_id))],
            [
                InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
                InlineKeyboardButton(text="Меню", callback_data="nav:menu"),
            ],
        ]
    )


def kb_limit_reached(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Пригласить (+{ORACLE_REFERRAL_BONUS})", callback_data="mod:referral")],
            [
                InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
                InlineKeyboardButton(text="Меню", callback_data="nav:menu"),
            ],
        ]
    )


def kb_mystic() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Карма", callback_data="mod:karma"),
                InlineKeyboardButton(text="Акаши", callback_data="mod:akashic"),
            ],
            [
                InlineKeyboardButton(text="И-Цзин", callback_data="mod:iching"),
                InlineKeyboardButton(text="Ленорман", callback_data="mod:lenormand"),
            ],
            [
                InlineKeyboardButton(text="Чакры", callback_data="mod:chakra"),
                InlineKeyboardButton(text="Аура", callback_data="mod:aura"),
            ],
            [
                InlineKeyboardButton(text="Наставник", callback_data="mod:spirit_guide"),
                InlineKeyboardButton(text="Лунный", callback_data="mod:moon"),
            ],
            [
                InlineKeyboardButton(text="Кристалл", callback_data="mod:crystal"),
                InlineKeyboardButton(text="Тень", callback_data="mod:shadow"),
            ],
            [
                InlineKeyboardButton(text="Родств. душа", callback_data="mod:twin_flame"),
                InlineKeyboardButton(text="Биоритмы", callback_data="mod:biorhythm"),
            ],
            [
                InlineKeyboardButton(text="Транзиты", callback_data="mod:transit"),
                InlineKeyboardButton(text="Числа", callback_data="mod:numerology"),
            ],
            [
                InlineKeyboardButton(text="Китайский", callback_data="mod:chinese"),
                InlineKeyboardButton(text="Руна", callback_data="mod:rune"),
            ],
            [
                InlineKeyboardButton(text="Сонник", callback_data="mod:dream"),
                InlineKeyboardButton(text="Любовь", callback_data="mod:dating"),
            ],
            [
                InlineKeyboardButton(text="Карьера", callback_data="mod:career"),
                InlineKeyboardButton(text="Да/Нет", callback_data="mod:yesno"),
            ],
            [InlineKeyboardButton(text="Родовая карма", callback_data="mod:family_karma")],
            [InlineKeyboardButton(text="Главное меню", callback_data="nav:menu")],
        ]
    )


def kb_zodiac(prefix: str = "sign") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label, _ in ZODIAC_SIGNS:
        row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_after_reading(
    module: str,
    cont_id: int | None,
    user_id: int,
) -> InlineKeyboardMarkup:
    from oracle_bot import storage as db

    rows: list[list[InlineKeyboardButton]] = []
    if cont_id and not db.is_premium(user_id):
        rows.append([
            InlineKeyboardButton(
                text=f"Полная версия · {ORACLE_DEEP_STARS}⭐",
                callback_data=f"deep:{cont_id}",
            )
        ])
    cross = CROSS_SELL.get(module)
    if cross:
        label, data = cross
        clean = label.split(maxsplit=1)[-1] if label.startswith(("🖐", "➡️", "🌌", "🔮")) else label
        rows.append([InlineKeyboardButton(text=clean, callback_data=data)])
    rows.append([
        InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
        InlineKeyboardButton(text="Меню", callback_data="nav:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_profile(has_profile: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Дата рождения", callback_data="prof:birth")],
        [InlineKeyboardButton(text="Время и город", callback_data="prof:natal_data")],
        [InlineKeyboardButton(text="Имя", callback_data="prof:name")],
    ]
    if has_profile:
        rows.insert(0, [
            InlineKeyboardButton(text="Натальная", callback_data="prof:natal"),
            InlineKeyboardButton(text="Гороскоп", callback_data="prof:horo"),
        ])
    rows.append([InlineKeyboardButton(text="Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
