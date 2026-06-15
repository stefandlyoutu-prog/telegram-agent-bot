"""Знаки зодиака, китайский календарь, нумерология, руны."""

from __future__ import annotations

from datetime import date

ZODIAC_SIGNS: list[tuple[str, str, str]] = [
    ("oven", "♈ Овен", "21.03–19.04"),
    ("telec", "♉ Телец", "20.04–20.05"),
    ("bliz", "♊ Близнецы", "21.05–20.06"),
    ("rak", "♋ Рак", "21.06–22.07"),
    ("lev", "♌ Лев", "23.07–22.08"),
    ("deva", "♍ Дева", "23.08–22.09"),
    ("vesy", "♎ Весы", "23.09–22.10"),
    ("skorp", "♏ Скорпион", "23.10–21.11"),
    ("strelec", "♐ Стрелец", "22.11–21.12"),
    ("kozer", "♑ Козерог", "22.12–19.01"),
    ("vodol", "♒ Водолей", "20.01–18.02"),
    ("ryby", "♓ Рыбы", "19.02–20.03"),
]

ZODIAC_BY_KEY = {k: (label, period) for k, label, period in ZODIAC_SIGNS}

CHINESE_ANIMALS = [
    "Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
    "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья",
]

RUNES = [
    "Феху", "Уruz", "Тurisaz", "Ansuz", "Raidho", "Kenaz",
    "Gebo", "Wunjo", "Hagalaz", "Nauthiz", "Isa", "Jera",
    "Eihwaz", "Perthro", "Algiz", "Sowilo", "Tiwaz", "Berkano",
    "Ehwaz", "Mannaz", "Laguz", "Ingwaz", "Dagaz", "Othala",
]

ICHING = [
    "Цянь — Творчество", "Кунь — Исполнение", "Чжунь — Начало", "Мэн — Неопытность",
    "Сюй — Ожидание", "Сун — Спор", "Би — Воинство", "Би — Единство",
    "Сяо Чху — Укрощение", "Лü — Поступь", "Тай — Мир", "Пи — Застой",
    "Тун Жэнь — Содружество", "Да Ю — Обладание", "Цянь — Смирение", "Юй — Восторг",
    "Суй — Следование", "Гу — Расчистка", "Лин — Приближение", "Гуань — Наблюдение",
    "Ши Хэ — Стиснутость", "Би — Грация", "Бо — Разрушение", "Фу — Возврат",
    "Ву Ван — Невинность", "Да Чжу — Накопление", "И — Питание", "Да Го — Перелом",
    "Кань — Бездна", "Ли — Огонь", "Сянь — Прикосновение", "Хэн — Постоянство",
    "Дунь — Отступление", "Да Чжуан — Мощь", "Цзинь — Расцвет", "Мин И — Потемнение",
    "Цзя Жэнь — Дом", "Куй — Разлад", "Цзянь — Преграда", "Се — Освобождение",
    "Сунь — Убыль", "И — Прибыль", "Гуай — Прорыв", "Гоу — Встреча",
    "Цуй — Собрание", "Шэн — Подъём", "Кунь — Истощение", "Цзин — Источник",
    "Гэ — Переворот", "Дин — Котёл", "Чжэн — Гром", "Гэн — Гора",
    "Гуй Мэй — Союз", "Фэн — Изобилие", "Лü — Странник", "Сюнь — Проникновение",
    "Цуй — Радость", "Дуй — Благость", "Хуань — Рассеяние", "Цзянь — Мера",
    "Чжун Фу — Вера", "Сяо Гuo — Малые дела", "Цзи Цзи — Уже", "Вэй Цзи — Ещё нет",
]

LENORMAND = [
    "Всадник", "Клевер", "Корабль", "Дом", "Дерево", "Облака", "Змея", "Гроб",
    "Букет", "Коса", "Метла", "Сова", "Ребёнок", "Лиса", "Медведь", "Звёзды",
    "Аист", "Собака", "Башня", "Сад", "Гора", "Развилка", "Крысы", "Сердце",
    "Кольцо", "Книга", "Письмо", "Мужчина", "Женщина", "Лилия", "Солнце", "Луна",
    "Ключ", "Рыбы", "Якорь", "Крест",
]

CRYSTALS = [
    "Аметист", "Горный хрусталь", "Розовый кварц", "Лабрадорит",
    "Обсидиан", "Цитрин", "Лазурит", "Бирюза",
    "Лунный камень", "Карнеол", "Чёрный турмалин", "Селенит",
]

CHAKRAS = [
    "Муладхара", "Свадхистана", "Манипура", "Анахата",
    "Вишудха", "Аджна", "Сахасрара",
]

MOON_PHASES = [
    "Новолуние", "Растущий серп", "Первая четверть", "Растущая Луна",
    "Полнолуние", "Убывающая Луна", "Последняя четверть", "Убывающий серп",
]


def moon_phase_today(d: date | None = None) -> str:
    d = d or date.today()
    ref = date(2000, 1, 6)
    days = (d - ref).days % 29.53
    idx = int((days / 29.53) * 8) % 8
    return MOON_PHASES[idx]


def parse_birth_time(text: str) -> str | None:
    import re

    m = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi}"
    return None


def extract_place(text: str) -> str | None:
    import re

    cleaned = re.sub(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", "", text)
    cleaned = re.sub(r"\d{1,2}[:.]\d{2}", "", cleaned)
    place = cleaned.strip(" ,;—–-")
    return place if len(place) >= 2 else None


def zodiac_from_date(d: date) -> str:
    m, day = d.month, d.day
    if (m == 3 and day >= 21) or (m == 4 and day <= 19):
        return "oven"
    if (m == 4 and day >= 20) or (m == 5 and day <= 20):
        return "telec"
    if (m == 5 and day >= 21) or (m == 6 and day <= 20):
        return "bliz"
    if (m == 6 and day >= 21) or (m == 7 and day <= 22):
        return "rak"
    if (m == 7 and day >= 23) or (m == 8 and day <= 22):
        return "lev"
    if (m == 8 and day >= 23) or (m == 9 and day <= 22):
        return "deva"
    if (m == 9 and day >= 23) or (m == 10 and day <= 22):
        return "vesy"
    if (m == 10 and day >= 23) or (m == 11 and day <= 21):
        return "skorp"
    if (m == 11 and day >= 22) or (m == 12 and day <= 21):
        return "strelec"
    if (m == 12 and day >= 22) or (m == 1 and day <= 19):
        return "kozer"
    if (m == 1 and day >= 20) or (m == 2 and day <= 18):
        return "vodol"
    return "ryby"


def zodiac_label(key: str) -> str:
    return ZODIAC_BY_KEY.get(key, (key, ""))[0]


def chinese_animal(year: int) -> str:
    return CHINESE_ANIMALS[(year - 4) % 12]


def life_path_number(birth: date) -> int:
    digits = f"{birth.day:02d}{birth.month:02d}{birth.year}"
    total = sum(int(c) for c in digits if c.isdigit())
    while total > 9 and total not in (11, 22, 33):
        total = sum(int(c) for c in str(total))
    return total


def parse_birth_date(text: str) -> date | None:
    import re

    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", text.strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 1900 if y > 30 else 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None
