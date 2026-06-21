"""Промо-посты для @MOracul_bot — каналы, прогрев, очередь и A/B."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

BOT = "MOracul_bot"
MSK = ZoneInfo("Europe/Moscow")

# 5 слотов в день (МСК): утро → вечер, слот 3 — реклама оракула
SLOT_HOURS_MSK = (7, 10, 13, 16, 20)
PROMO_SLOT_INDEX = 3


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


def _cta(source: str = "", *, module: str = "tarot", label: str = "Получить расклад бесплатно") -> str:
    link = bot_link(source, module=module)
    return f'👉 <a href="{link}">{label}</a>'


# --- Рекламные варианты (A/B) ---

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
        + _cta(source, module="horo_today", label="Мой гороскоп на сегодня")
    )


def post_dream(source: str = "") -> str:
    return (
        "🌙 <b>Сонник утром — пока сон свежий</b>\n\n"
        "Опиши сон текстом или <b>голосовым</b> — бот разберёт символы "
        "и даст подсказку на день. Особенно хорошо сразу после пробуждения.\n\n"
        + _cta(source, module="dream", label="Разобрать сон бесплатно")
    )


def post_voice(source: str = "") -> str:
    return (
        "🎤 <b>Голосом — как подруге</b>\n\n"
        "Не хочешь печатать? Запиши голосовое: сон, вопрос к Таро, "
        "ситуация в отношениях — бот поймёт и ответит развёрнуто.\n\n"
        + _cta(source, module="tarot", label="Открыть бота и записать голос")
    )


def post_natal(source: str = "") -> str:
    return (
        "🌌 <b>Натальная карта в Telegram</b>\n\n"
        "Дата, время и город рождения — и персональный разбор характера, "
        "сильных сторон и повторяющихся сценариев.\n\n"
        + _cta(source, module="natal", label="Собрать натальную")
    )


def post_yesno(source: str = "") -> str:
    return (
        "🎲 <b>Да или нет — без воды</b>\n\n"
        "Один чёткий вопрос — быстрый ответ оракула. "
        "Когда голова кругом и нужно решение сегодня.\n\n"
        + _cta(source, module="yesno", label="Задать вопрос")
    )


def post_chakra(source: str = "") -> str:
    return (
        "🔴 <b>Чакры и энергия дня</b>\n\n"
        "Какой центр просит внимания, что блокирует поток и "
        "простая практика на вечер — в боте за минуту.\n\n"
        + _cta(source, module="chakra", label="Проверить чакры")
    )


def post_moon(source: str = "") -> str:
    return (
        "🌑 <b>Лунный календарь</b>\n\n"
        "Фаза Луны сегодня: что усиливать, от чего отложить. "
        "Плюс «судьба дня» по знаку.\n\n"
        + _cta(source, module="moon", label="Лунный разбор")
    )


def post_referral(source: str = "") -> str:
    return (
        "🎁 <b>Бесплатные расклады за друзей</b>\n\n"
        "Пригласи подругу — получи бонусные чтения, "
        "когда закончится дневной лимит. Оплата только если захочешь Premium.\n\n"
        + _cta(source)
    )


PROMO_VARIANTS: list[tuple[str, Callable[[str], str]]] = [
    ("tarot", post_tarot_hook),
    ("dream", post_dream),
    ("voice", post_voice),
    ("compat", post_love_compat),
    ("palm", post_palm),
    ("horo", post_horoscope_today),
    ("natal", post_natal),
    ("yesno", post_yesno),
    ("chakra", post_chakra),
    ("moon", post_moon),
    ("referral", post_referral),
]


def promo_variant(variant_id: str, source: str = "") -> str:
    for vid, fn in PROMO_VARIANTS:
        if vid == variant_id:
            return fn(source)
    return post_tarot_hook(source)


def pick_promo_variant(day_index: int, channel: str) -> tuple[str, str]:
    """Детерминированная ротация A/B по дню и каналу."""
    u = channel.lstrip("@").lower()
    order = [v[0] for v in PROMO_VARIANTS]
    if u == "auragirlss":
        order = ["chakra", "dream", "voice", "compat", "moon", "tarot", "palm", "natal"]
    elif u == "signsvishe":
        order = ["horo", "tarot", "dream", "yesno", "compat", "natal", "voice", "moon"]
    idx = (day_index * 3 + hash(u) % 3) % len(order)
    vid = order[idx]
    return vid, promo_variant(vid, u)


def post_launch_broadcast() -> str:
    return (
        "🔮 <b>Оракул обновлён — загляни снова</b>\n\n"
        "• Таро и карта дня — бесплатно каждый день\n"
        "• Сонник утром — текстом или голосом\n"
        "• Совместимость по датам · ладонь по фото\n"
        "• 25+ разделов — Карма, И-Цзин, чакры…\n\n"
        "Нажми /start — меню уже ждёт.\n"
        "⭐ Premium — без лимитов через Telegram Stars."
    )


# --- Прогрев без ссылки ---

def warmup_post_for_channel(username: str, *, day: int = 1) -> str:
    u = username.lstrip("@").lower()
    day = max(1, min(day, 7))
    if u == "signsvishe":
        posts = [
            "✨ <b>Карта дня</b>\n\nСегодня многие Овны и Рыбы чувствуют «знак» — не случайная мысль, а подсказка. Запиши первое, что пришло в голову утром.",
            "💞 <b>Совместимость</b>\n\nПара из разных стихий часто сильнее «идеальной» по гороскопу. Где у вас трёт — там и рост.",
            "🔮 <b>Три карты</b>\n\nСитуация · препятствие · совет — классика, которая реально помогает когда голова кругом.",
            "🌙 <b>Сны и знаки</b>\n\nПовторяющийся сюжет во сне — не случайность. Утром память ярче: запиши три детали, пока не забылось.",
            "🎲 <b>Решение «да/нет»</b>\n\nЕсли крутишь мысль третий день — отложи до вечера. Луна сменит угол, и ответ станет очевиднее.",
            "🌌 <b>Натальная</b>\n\nДата рождения — не приговор, а карта. Где твоя сила, а где привычка сдаваться?",
            "✨ <b>Ретроградный Меркурий</b>\n\nНе паникуй: перепроверяй договорённости, не рви связи на эмоциях.",
        ]
        return posts[(day - 1) % len(posts)]
    if u == "auragirlss":
        posts = [
            "🌈 <b>Аура сегодня</b>\n\nЕсли чувствуешь чужую усталость — три вдоха и «это не моё». Граница — не эгоизм.",
            "💫 <b>Энергия пары</b>\n\nСовпадение дат не гарантия, но ритм отношений часто виден по циклам. Замечали?",
            "🖐 <b>Линии на ладони</b>\n\nСердце, голова, судьба — три линии, которые меняются. Сфоткай при дневном свете.",
            "🔴 <b>Корневая чакра</b>\n\nТревога в теле? Заземлись: босиком по полу 2 минуты или тёплая еда.",
            "🌙 <b>Луна и сны</b>\n\nПеред сном положи телефон подальше — сны станут ярче, а утром легче вспомнить.",
            "🔥 <b>Родственная душа</b>\n\nНе всегда «навсегда». Иногда встреча — урок, а не пункт назначения.",
            "💎 <b>Кристалл дня</b>\n\nАметист — ясность, розовый кварц — мягкость к себе. Выбери один на неделю.",
        ]
        return posts[(day - 1) % len(posts)]
    posts = [
        f"✨ <b>Гороскоп на {date.today().strftime('%d.%m')}</b>\n\nСегодня у многих знаков — день «да/нет». Если сомневаешься — отложи решение до вечера.",
        "🔮 <b>Один вопрос — три карты</b>\n\nНе «что будет», а «что мешает» и «куда смотреть». Работает лучше общих предсказаний.",
        "💞 <b>Две даты — одна картина</b>\n\nСовместимость не про «подходит/нет», а про где беречь, а где отпускать.",
        "🌙 <b>Утренний сон</b>\n\nСтранный сон — не мусор мозга. Три образа из сна часто объясняют, что крутится днём.",
        "💼 <b>Карьера и деньги</b>\n\nНе всё решает «удачный день». Иногда звёзды говорят: сначала договорись, потом действуй.",
        "🪬 <b>Руна дня</b>\n\nОдин символ — один фокус. Не ищи в интернете чужую — прислушайся к своей реакции на знак.",
        "📅 <b>Неделя впереди</b>\n\nСреда — для переговоров, пятница — для личного. Планируй с запасом, не в ноль.",
    ]
    return posts[(day - 1) % len(posts)]


def _content_slot(channel: str, day_index: int, slot_index: int) -> tuple[str, str, str]:
    """Контент без рекламы: kind, variant_id, text."""
    u = channel.lstrip("@").lower()
    d = day_index + 1
    if slot_index == 0:
        # Утро — сонник / гороскоп
        if u == "auragirlss":
            return "warmup", "morning_aura", warmup_post_for_channel(u, day=max(1, (d % 5) + 1))
        if u == "signsvishe":
            return "warmup", "morning_sign", warmup_post_for_channel(u, day=d)
        return "warmup", "morning_horo", warmup_post_for_channel(u, day=d)
    if slot_index == 1:
        tips = [
            ("tip_compat", "💞 <b>Мини-практика</b>\n\nНапиши партнёру одну вещь, за которую благодарна сегодня — без «но»."),
            ("tip_money", "💰 <b>Деньги</b>\n\nНе принимай крупных решений до обеда — утро для ясности, не для импульса."),
            ("tip_self", "🪞 <b>К себе</b>\n\nЕсли раздражает чужая мелочь — часто это зеркало своего напряжения."),
        ]
        vid, text = tips[(d + slot_index) % len(tips)]
        return "content", vid, text
    if slot_index == 2:
        pool = [
            ("tip_tarot", "🔮 <b>Таро-мысль</b>\n\nКарта «Повешенный» — не про застой. Про паузу, чтобы увидеть иначе."),
            ("tip_palm", "🖐 <b>Ладонь</b>\n\nЛиния сердца не про «сколько браков». Про то, как ты любишь и отпускаешь."),
            ("tip_dream", "🌙 <b>Сны</b>\n\nВода во сне — эмоции. Пресная — покой, бурная — то, что давно не проговорили."),
        ]
        if u == "auragirlss":
            pool.append(("tip_chakra", "🔴 <b>Сердечная чакра</b>\n\nБоль в груди без причины? Спроси: кому я сейчас не сказала правду?"))
        vid, text = pool[(d + hash(u)) % len(pool)]
        return "content", vid, text
    # slot 4 — вечер
    evening = [
        ("eve_moon", "🌑 <b>Вечер</b>\n\nЛуна просит замедлиться. Завтрашние дела — на бумагу, голова отпустит."),
        ("eve_love", "💫 <b>Отношения</b>\n\nНе выясняй важное перед сном. Утро — для честного разговора."),
        ("eve_rune", "🪬 <b>Знак</b>\n\nТретье совпадение за день — не паранойя. Вселенная любит троекратность."),
    ]
    vid, text = evening[(d + slot_index) % len(evening)]
    return "content", vid, text


def slot_post(channel: str, day_index: int, slot_index: int) -> tuple[str, str, str]:
    """Текст поста: kind, variant_id, body."""
    if slot_index == PROMO_SLOT_INDEX:
        vid, body = pick_promo_variant(day_index, channel)
        return "promo", vid, body
    return _content_slot(channel, day_index, slot_index)


def post_for_channel(username: str) -> str:
    u = username.lstrip("@").lower()
    if u == "signsvishe":
        return (
            "✨ <b>Знаки свыше — не абстракция</b>\n\n"
            "Когда хочется не общий текст, а <b>личный</b> ответ: "
            "Таро, сонник, совместимость, линии на ладони — "
            "всё в Telegram, первая часть бесплатно.\n\n"
            + _cta(u)
        )
    if u == "auragirlss":
        return (
            "💫 <b>Аура, энергия, отношения</b>\n\n"
            "Разбор чакр, совместимость по датам, сонник, голосовые — "
            "для тех, кто чувствует тонко. Бот без приложений.\n\n"
            + _cta(u, module="chakra")
        )
    return post_tarot_hook(u)


def pick_channel_post() -> str:
    return random.choice([fn() for _, fn in PROMO_VARIANTS])


def all_channel_posts() -> list[str]:
    return [fn("") for _, fn in PROMO_VARIANTS[:6]]


def schedule_dt_msk(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, 0, tzinfo=MSK)


def build_week_plan(
    *,
    start_day: date | None = None,
    channels: tuple[str, ...] | None = None,
    days: int = 7,
) -> list[dict]:
    """План постов: channels × days × 5 слотов."""
    from oracle_bot.config import ORACLE_PROMO_CHANNELS

    start = start_day or date.today()
    chs = channels or ORACLE_PROMO_CHANNELS
    rows: list[dict] = []
    for day_offset in range(days):
        d = start + timedelta(days=day_offset)
        for ch in chs:
            u = ch.strip().lstrip("@")
            if not u:
                continue
            for slot_i, hour in enumerate(SLOT_HOURS_MSK):
                kind, vid, body = slot_post(u, day_offset, slot_i)
                at = schedule_dt_msk(d, hour)
                rows.append(
                    {
                        "channel": u,
                        "scheduled_at": at.astimezone(timezone.utc).isoformat(),
                        "kind": kind,
                        "variant_id": vid,
                        "body": body,
                    }
                )
    return rows
