"""Клавиатуры VPN-бота."""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from vpn_bot.config import (
    VPN_HELP_CONTACT,
    VPN_NEWS_CHANNEL,
    VPN_TRIAL_ENABLED,
    VPN_TARIFFS,
)


def kb_main() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔑 Мой ключ", callback_data="my_key")],
        [InlineKeyboardButton(text="💳 Купить / продлить", callback_data="buy")],
    ]
    if VPN_TRIAL_ENABLED:
        rows.append(
            [InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial")]
        )
    rows.append([InlineKeyboardButton(text="❓ Как подключить", callback_data="howto")])
    news_help: list[InlineKeyboardButton] = []
    if VPN_NEWS_CHANNEL:
        news_help.append(
            InlineKeyboardButton(text="✨ Новости", url=f"https://t.me/{VPN_NEWS_CHANNEL}")
        )
    if VPN_HELP_CONTACT:
        news_help.append(
            InlineKeyboardButton(text="⚙️ Помощь", url=f"https://t.me/{VPN_HELP_CONTACT}")
        )
    if news_help:
        rows.append(news_help)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_tariffs() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in VPN_TARIFFS:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{t['title']} — {t['price_rub']}₽",
                    callback_data=f"tariff:{t['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_pay(pay_url: str, inv_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
            [InlineKeyboardButton(text="Я оплатил — проверить", callback_data=f"check:{inv_id}")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_main")],
        ]
    )


def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« В меню", callback_data="back_main")]]
    )


def kb_key(subscription_url: str) -> InlineKeyboardMarkup:
    """Ключ: кнопка copy_text + инструкция + меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Скопировать ключ",
                    copy_text=CopyTextButton(text=subscription_url),
                )
            ],
            [InlineKeyboardButton(text="❓ Как подключить", callback_data="howto")],
            [InlineKeyboardButton(text="« В меню", callback_data="back_main")],
        ]
    )
