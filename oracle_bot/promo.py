"""Промо-посты для @MOracul_bot — каналы, прогрев и рассылка."""

from __future__ import annotations

import random
from datetime import date

BOT = "MOracul_bot"


def bot_link(source: str = "", *, module: str = "") -> str:
    """Deep-link: ?start=src_<канал> или mod_<раздел>."""
    start = ""
    if module:
        start = f"mod_{module}"
    elif source:
        start = f"src_{source.lstrip('@').lower()}"
    if start:
        return f"https://t.me/{BOT}?start={start}"
    return f"https://t.me/{BOT}"


def _cta(source: str = "", *, module: str = "tarot") -> str:
    link = bot_link(source, module=module)
    return f'👉 <a href="{link}">Получить расклад бесплатно</a>'


def post_tarot_hook(source: str = "") -> str:
    return (
        "🔮 <b>Три карты — один честный ответ</b>\n\n"
        "Не «вас ждёт перемена», а конкретика: что мешает, куда смотреть, "
        "что делать дальше. Таро, совместимость, ладонь по фото — в боте.\n\n"
        "Первая часть <b>бесплатно</b> каждый день. 30 секунд.\n\n"
        + _cta(source)
    )


def post_love_compat(source: str = "") -> str:
    return (
        "💞 <b>Совместимость по датам рождения</b>\n\n"
        "Без регистрации — две даты в Telegram. "
        "Где вы совпадаете, где трёт, и что усилить в паре.\n\n"
        + _cta(source, module="compat")
    )


def post_palm(source: str = "") -> str:
    return (
        "🖐 <b>Хиромантия по фото ладони</b>\n\n"
        "Сфотографируй ладонь — бот разберёт линии и даст персональный совет. "
        "Прямо в Telegram, без приложений.\n\n"
        + _cta(source, module="palm")
    )


def post_horoscope_today(source: str = "") -> str:
    day = date.today().strftime("%d.%m")
    return (
        f"✨ <b>Гороскоп на {day}</b>\n\n"
        "Общий прогноз — скучно. В боте — <b>ваш</b> день: энергия, "
        "отношения, деньги, один совет на вечер.\n\n"
        + _cta(source, module="horo_today")
    )


def post_referral(source: str = "") -> str:
    return (
        "🎁 <b>Бесплатные расклады за друзей</b>\n\n"
        "Пригласи подругу — получи бонусные чтения, "
        "когда закончится дневной лимит. Оплата только если захочешь Premium.\n\n"
        + _cta(source)
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


def warmup_post_for_channel(username: str, *, day: int = 1) -> str:
    """Прогрев без ссылки на бота — интрига перед рекламой."""
    u = username.lstrip("@").lower()
    day = max(1, min(day, 3))
    if u == "signsvishe":
        posts = [
            (
                "✨ <b>Карта дня</b>\n\n"
                "Сегодня многие Овны и Рыбы чувствуют «знак» — "
                "не случайная мысль, а подсказка. Запиши первое, что пришло в голову утром."
            ),
            (
                "💞 <b>Совместимость</b>\n\n"
                "Пара из разных стихий часто сильнее «идеальной» по гороскопу. "
                "Где у вас трёт — там и рост. Согласны?"
            ),
            (
                "🔮 <b>Три карты</b>\n\n"
                "Ситуация · препятствие · совет — классика, которая реально помогает "
                "когда голова кругом. Кто пробовал — напишите в комментариях."
            ),
        ]
        return posts[day - 1]
    if u == "auragirlss":
        posts = [
            (
                "🌈 <b>Аура сегодня</b>\n\n"
                "Если чувствуешь чужую усталость в метро или на работе — "
                "это не выдумка. Поставь границу: три глубоких вдоха и «это не моё»."
            ),
            (
                "💫 <b>Энергия пары</b>\n\n"
                "Совпадение дат рождения не гарантия, но <b>ритм</b> отношений "
                "часто виден по циклам. Замечали?"
            ),
            (
                "🖐 <b>Линии на ладони</b>\n\n"
                "Сердце, голова, судьба — три линии, которые меняются со временем. "
                "Сфоткай ладонь при дневном свете — интересно сравнить через год."
            ),
        ]
        return posts[day - 1]
    posts = [
        (
            f"✨ <b>Гороскоп на {date.today().strftime('%d.%m')}</b>\n\n"
            "Сегодня у многих знаков — день «да/нет». "
            "Если сомневаешься — отложи решение до вечера."
        ),
        (
            "🔮 <b>Один вопрос — три карты</b>\n\n"
            "Не «что будет», а «что мешает» и «куда смотреть». "
            "Работает лучше общих предсказаний."
        ),
        (
            "💞 <b>Две даты — одна картина</b>\n\n"
            "Совместимость не про «подходит/нет», а про где беречь, а где отпускать."
        ),
    ]
    return posts[day - 1]


def post_for_channel(username: str) -> str:
    u = username.lstrip("@").lower()
    if u == "signsvishe":
        return (
            "✨ <b>Знаки свыше — не абстракция</b>\n\n"
            "Когда хочется не общий текст, а <b>личный</b> ответ: "
            "Таро, карта дня, совместимость, линии на ладони — "
            "всё в Telegram, первая часть бесплатно.\n\n"
            + _cta(u)
        )
    if u == "auragirlss":
        return (
            "💫 <b>Аура, энергия, отношения</b>\n\n"
            "Разбор чакр, совместимость по датам, «судьба дня» — "
            "для тех, кто чувствует тонко. Бот без приложений.\n\n"
            + _cta(u, module="chakra")
        )
    return post_tarot_hook(u)


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
