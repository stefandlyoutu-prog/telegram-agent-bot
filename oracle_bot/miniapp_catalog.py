"""Каталог разделов Mini App: порядок, описания, секции."""

from __future__ import annotations

from typing import Any

# section: top — самое популярное, popular — частое, deep — углубление
MINIAPP_MODULES: list[dict[str, str]] = [
    # Топ
    {"id": "psychology", "title": "Психолог", "desc": "Поддержка: тревога, отношения, выгорание", "section": "top", "emoji": "🧠"},
    {"id": "horo_today", "title": "Гороскоп", "desc": "Прогноз на сегодня по знаку", "section": "top", "emoji": "🌅"},
    {"id": "tarot", "title": "Таро", "desc": "3 карты: прошлое, настоящее, совет", "section": "top", "emoji": "🔮"},
    {"id": "card_day", "title": "Карта дня", "desc": "Бесплатный знак и подсказка", "section": "top", "emoji": "🃏"},
    {"id": "compat", "title": "Пара", "desc": "Совместимость по датам рождения", "section": "top", "emoji": "💕"},
    {"id": "palm", "title": "Ладонь", "desc": "Хиромантия по фото ладони", "section": "top", "emoji": "🖐"},
    {"id": "dating", "title": "Любовь", "desc": "Совет по отношениям и переписке", "section": "top", "emoji": "💬"},
    # Популярное
    {"id": "career", "title": "Карьера", "desc": "Работа, деньги, следующий шаг", "section": "popular", "emoji": "💼"},
    {"id": "dream", "title": "Сонник", "desc": "Смысл сна и подсказка наяву", "section": "popular", "emoji": "🌙"},
    {"id": "natal", "title": "Натальная", "desc": "Карта рождения: характер и судьба", "section": "popular", "emoji": "🌌"},
    {"id": "numerology", "title": "Числа", "desc": "Нумерология по имени и дате", "section": "popular", "emoji": "🔢"},
    {"id": "yesno", "title": "Да / Нет", "desc": "Быстрый ответ на один вопрос", "section": "popular", "emoji": "🎲"},
    {"id": "portrait", "title": "Портрет", "desc": "Психологический портрет личности", "section": "popular", "emoji": "🎂"},
    {"id": "destiny", "title": "Судьба дня", "desc": "Число, цвет и окно удачи", "section": "popular", "emoji": "✨"},
    {"id": "horo_week", "title": "Неделя", "desc": "Гороскоп на 7 дней", "section": "popular", "emoji": "📅"},
    {"id": "rune", "title": "Руна", "desc": "Скандинавский знак дня", "section": "popular", "emoji": "🪬"},
    # Углубление
    {"id": "karma", "title": "Карма", "desc": "Уроки души и что повторяется", "section": "deep", "emoji": "⚖️"},
    {"id": "akashic", "title": "Акаши", "desc": "Записи души: миссия и выбор жизни", "section": "deep", "emoji": "📜"},
    {"id": "iching", "title": "И-Цзин", "desc": "Китайский оракул перемен", "section": "deep", "emoji": "☯️"},
    {"id": "lenormand", "title": "Ленорман", "desc": "Карты на конкретный вопрос", "section": "deep", "emoji": "🦋"},
    {"id": "chakra", "title": "Чакры", "desc": "Энергетические центры тела", "section": "deep", "emoji": "🔴"},
    {"id": "aura", "title": "Аура", "desc": "Цвета энергии и притяжение", "section": "deep", "emoji": "🌈"},
    {"id": "spirit_guide", "title": "Наставник", "desc": "Послание духовного проводника", "section": "deep", "emoji": "👁"},
    {"id": "moon", "title": "Лунный", "desc": "Фаза Луны и дела по календарю", "section": "deep", "emoji": "🌑"},
    {"id": "crystal", "title": "Кристалл", "desc": "Камень дня и намерение", "section": "deep", "emoji": "💎"},
    {"id": "shadow", "title": "Тень", "desc": "Скрытый страх и интеграция", "section": "deep", "emoji": "🌑"},
    {"id": "twin_flame", "title": "Родств. душа", "desc": "Глубокая связь и этап пары", "section": "deep", "emoji": "🔥"},
    {"id": "biorhythm", "title": "Биоритмы", "desc": "Физика, эмоции, ум на неделю", "section": "deep", "emoji": "📈"},
    {"id": "transit", "title": "Транзиты", "desc": "Астро-влияния на сегодня", "section": "deep", "emoji": "🪐"},
    {"id": "chinese", "title": "Китайский", "desc": "Год животного и элемент", "section": "deep", "emoji": "🐉"},
    {"id": "past_life", "title": "Прошлые жизни", "desc": "Символическое прошлое воплощение", "section": "deep", "emoji": "🕰"},
    {"id": "family_karma", "title": "Родовая карма", "desc": "Сценарии семьи и освобождение", "section": "deep", "emoji": "🧬"},
]

SECTION_LABELS = {
    "top": "Популярное",
    "popular": "Ещё разборы",
    "deep": "Углубление",
}


def modules_for_api() -> list[dict[str, Any]]:
    return [
        {**m, "section_label": SECTION_LABELS.get(m["section"], m["section"])}
        for m in MINIAPP_MODULES
    ]
