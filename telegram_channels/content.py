"""Шаблоны постов: воронка на бота / реф. ссылки."""

from __future__ import annotations


def funnel_post(
    *,
    bot_username: str = "MOracul_bot",
    hook: str = "Персональный расклад, совместимость и ладонь",
) -> str:
    bot = bot_username.lstrip("@")
    return (
        f"🔮 <b>Хотите глубже, чем общий гороскоп?</b>\n\n"
        f"{hook} — в боте <a href=\"https://t.me/{bot}\">@{bot}</a>\n\n"
        f"⭐ Премиум без лимитов — Telegram Stars"
    )


def yandex_browser_post(referral_url: str) -> str:
    return (
        "🌐 <b>Яндекс Браузер</b> — быстрый, с Алисой и защитой\n\n"
        f"Скачать: {referral_url}\n\n"
        "<i>Партнёрская ссылка</i>"
    )


def daily_horoscope_teaser(sign_hint: str = "") -> str:
    extra = f" ({sign_hint})" if sign_hint else ""
    return (
        f"✨ <b>Гороскоп на сегодня</b>{extra}\n\n"
        "Подробнее — в закрепе и в нашем боте для персональных раскладов."
    )
