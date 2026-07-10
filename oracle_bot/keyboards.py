"""Клавиатуры Оракула."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from oracle_bot.config import (
    ORACLE_DEEP_PRICE_RUB,
    ORACLE_DEEP_STARS,
    ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
    ORACLE_PDF_HVD_PRICE_RUB,
    ORACLE_PDF_READING_PRICE_RUB,
    ORACLE_PREMIUM_STARS,
    ORACLE_REFERRAL_BONUS,
    ORACLE_ULTRA_PLUS_PRICE_RUB,
    miniapp_entry_url,
)
from oracle_bot.mystic_data import ZODIAC_SIGNS
from oracle_bot.paywall import referral_primary, stars_enabled
from oracle_bot.prompts import CROSS_SELL


def _webapp_row() -> list[InlineKeyboardButton] | None:
    url = miniapp_entry_url()
    if not url:
        return None
    return [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))]


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
            InlineKeyboardButton(
                text=f"🔮 ХВД курс — {ORACLE_EXCLUSIVE_HVD_PRICE_RUB}₽",
                callback_data="mod:exclusive_hvd",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📖 Ultra Plus — {ORACLE_ULTRA_PLUS_PRICE_RUB}₽",
                callback_data="mod:ultra_plus",
            ),
        ],
    ])
    if referral_primary():
        rows.append([
            InlineKeyboardButton(
                text=f"🎁 Пригласить (+{ORACLE_REFERRAL_BONUS})",
                callback_data="mod:referral",
            ),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
            InlineKeyboardButton(text="Пригласить", callback_data="mod:referral"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_referral(user_id: int) -> InlineKeyboardMarkup:
    from oracle_bot.referrals import share_url

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Поделиться ссылкой", url=share_url(user_id))],
    ]
    if stars_enabled():
        rows.append([
            InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
            InlineKeyboardButton(text="Меню", callback_data="nav:menu"),
        ])
    else:
        rows.append([InlineKeyboardButton(text="Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_limit_reached(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🎁 Пригласить друга (+{ORACLE_REFERRAL_BONUS})",
                callback_data="mod:referral",
            )
        ],
    ]
    if stars_enabled():
        rows.append([
            InlineKeyboardButton(text="Премиум", callback_data="mod:premium"),
            InlineKeyboardButton(text="Меню", callback_data="nav:menu"),
        ])
    else:
        rows.append([InlineKeyboardButton(text="Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def kb_hvd_done() -> InlineKeyboardMarkup:
    """После полного разбора ХВД: вопрос ассистенту + PDF-книга."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Спросить по разбору", callback_data="ask:start")],
            [
                InlineKeyboardButton(
                    text=f"📖 Получить в книге PDF · {ORACLE_PDF_HVD_PRICE_RUB}₽",
                    callback_data="pdf:hvd",
                )
            ],
            [InlineKeyboardButton(text="Меню", callback_data="nav:menu")],
        ]
    )


def kb_book_done() -> InlineKeyboardMarkup:
    """После Ultra Plus (книга уже PDF) — только вопрос ассистенту."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Спросить по книге", callback_data="ask:start")],
            [InlineKeyboardButton(text="Меню", callback_data="nav:menu")],
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
    from oracle_bot.access import has_full_access

    rows: list[list[InlineKeyboardButton]] = []
    if cont_id and not has_full_access(user_id):
        if stars_enabled():
            rows.append([
                InlineKeyboardButton(
                    text=f"🔓 Полная версия · {ORACLE_DEEP_PRICE_RUB}₽",
                    callback_data=f"deep:{cont_id}",
                )
            ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text="🔓 Полная версия · бонус или друг",
                    callback_data=f"deep:{cont_id}",
                )
            ])
    rows.append([
        InlineKeyboardButton(text="💬 Спросить по разбору", callback_data="ask:start"),
    ])
    if module not in ("exclusive_hvd", "ultra_plus"):
        rows.append([
            InlineKeyboardButton(
                text=f"📄 Сохранить в PDF · {ORACLE_PDF_READING_PRICE_RUB}₽",
                callback_data="pdf:reading",
            ),
        ])
    cross = CROSS_SELL.get(module)
    if cross:
        label, data = cross
        clean = label.split(maxsplit=1)[-1] if label.startswith(("🖐", "➡️", "🌌", "🔮")) else label
        rows.append([InlineKeyboardButton(text=clean, callback_data=data)])
    tail = [InlineKeyboardButton(text="Меню", callback_data="nav:menu")]
    if stars_enabled():
        tail.insert(0, InlineKeyboardButton(text="Премиум", callback_data="mod:premium"))
    else:
        tail.insert(
            0,
            InlineKeyboardButton(
                text=f"🎁 Пригласить (+{ORACLE_REFERRAL_BONUS})",
                callback_data="mod:referral",
            ),
        )
    rows.append(tail)
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
