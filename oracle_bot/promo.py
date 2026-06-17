"""Промо-посты для @MOracul_bot — каналы и рассылка."""

from __future__ import annotations

import random
from datetime import date

BOT = "MOracul_bot"
LINK = f"https://t.me/{BOT}"


def _cta() -> str:
    return f'👉 <a href="{LINK}">Открыть @{BOT}</a>'


def post_tarot_hook() -> str:
    return (
        "🔮 <b>Три карты — один честный ответ</b>\n\n"
        "Не «вас ждёт перемена», а конкретика: что мешает, куда смотреть, "
        "что делать дальше. Таро, совместимость, ладонь по фото — в боте.\n\n"
        "Первая часть бесплатно каждый день.\n\n"
        + _cta()
    )


def post_love_compat() -> str:
    return (
        "💞 <b>Совместимость по датам рождения</b>\n\n"
        "Без регистрации на сайтах — просто две даты в Telegram. "
        "Где вы совпадаете, где трёт, и что усилить в паре.\n\n"
        + _cta()
    )


def post_palm() -> str:
    return (
        "🖐 <b>Хиромантия по фото ладони</b>\n\n"
        "Сфотографируй ладонь — бот разберёт линии и даст персональный совет. "
        "Работает прямо в Telegram, без приложений.\n\n"
        + _cta()
    )


def post_horoscope_today() -> str:
    day = date.today().strftime("%d.%m")
    return (
        f"✨ <b>Гороскоп на {day}</b>\n\n"
        "Общий прогноз — скучно. В боте — <b>ваш</b> день: энергия, "
        "отношения, деньги, один совет на вечер.\n\n"
        + _cta()
    )


def post_referral() -> str:
    return (
        "🎁 <b>Бесплатные расклады за друзей</b>\n\n"
        "Пригласи подругу или друга — получи бонусные чтения, "
        "когда закончится дневной лимит. Без карты, оплата только если захочешь Premium.\n\n"
        + _cta()
    )


def post_launch_broadcast() -> str:
    """Рассылка существующим пользователям бота."""
    return (
        "🔮 <b>Оракул обновлён — загляни снова</b>\n\n"
        "• Таро и карта дня — бесплатно каждый день\n"
        "• Совместимость по датам\n"
        "• Ладонь по фото\n"
        "• 15+ разделов — Карма, И-Цзин, чакры…\n\n"
        "Нажми /start — меню уже ждёт.\n"
        "⭐ Premium — без лимитов через Telegram Stars."
    )


def post_for_channel(username: str) -> str:
    u = username.lstrip("@").lower()
    if u == "signsvishe":
        return (
            "✨ <b>Знаки свыше — не абстракция</b>\n\n"
            "Когда хочется не общий текст, а <b>личный</b> ответ: "
            "Таро, карта дня, совместимость, линии на ладони — "
            "всё в Telegram, первая часть бесплатно.\n\n"
            + _cta()
        )
    if u == "auragirlss":
        return (
            "💫 <b>Аура, энергия, отношения</b>\n\n"
            "Разбор чакр, совместимость по датам, «судьба дня» — "
            "для тех, кто чувствует тонко. Бот без приложений и регистраций.\n\n"
            + _cta()
        )
    return pick_channel_post()


def pick_channel_post() -> str:
    posts = [
        post_tarot_hook,
        post_love_compat,
        post_palm,
        post_horoscope_today,
        post_referral,
    ]
    return random.choice(posts)()


def all_channel_posts() -> list[str]:
    return [
        post_horoscope_today(),
        post_tarot_hook(),
        post_love_compat(),
        post_palm(),
        post_referral(),
    ]
