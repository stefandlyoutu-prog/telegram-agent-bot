"""Реклама @MOracul_bot: бриф, темы, источники-метки (UTM для Telegram), план на месяц.

Идея:
- каждый ролик получает уникальную deeplink-метку  t.me/MOracul_bot?start=src_<код>
- Оракул-бот уже умеет это: ?start=src_<код> → storage.set_signup_source
- по этим меткам команда /sources в боте показывает, какой канал качает трафик
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

# ───────────────────────── Бриф продукта для LLM-сценариста ─────────────────────────
ORACLE_BRIEF = """
Telegram-бот @MOracul_bot — личный AI-оракул и таро в кармане:
- мгновенный расклад таро на любовь, деньги, отношения, будущее
- персональный гороскоп и совместимость по знакам
- число судьбы, послание дня, ответ на «да/нет»
- глубокие разборы ситуации простым языком, без эзотерического тумана
- первый расклад бесплатно, премиум — безлимит всех разделов
- работает 24/7 прямо в Телеграме, ответ за секунды
Аудитория: интересуются гороскопами, таро, психологией, знаками судьбы.
Тон: тёплый, чуть мистический, поддерживающий — без запугивания и «порчи».
"""

# Темы-хуки (ротация по дням). Короткие, кликабельные, без латиницы.
ORACLE_TOPICS: list[str] = [
    "Что вселенная хочет тебе сказать сегодня",
    "Таро-расклад: что ждёт тебя в любви",
    "Один знак — и ты поймёшь, кто твой человек",
    "Послание дня для твоего знака зодиака",
    "Три карты, которые меняют решение",
    "Число судьбы: что зашито в твоей дате рождения",
    "Он думает о тебе? Спроси у карт",
    "Знаки, которым скоро крупно повезёт",
    "Что мешает деньгам прийти в твою жизнь",
    "Расклад на ближайшее будущее за 1 минуту",
    "Совместимость по знакам: правда без иллюзий",
    "Карта дня: на что обратить внимание прямо сейчас",
    "Вселенная отвечает да или нет на твой вопрос",
    "Почему один и тот же человек снова в твоей жизни",
    "Тайное послание твоего ангела-хранителя",
    "Что произойдёт через 3 дня — расклад таро",
    "Знаки зодиака, у которых меняется судьба этой осенью",
    "Как понять, что перемены уже начались",
    "Карты говорят, что ты упускаешь",
    "Расклад на отношения: вместе или порознь",
    "Кого ты встретишь до конца месяца",
    "Энергия дня: чего избегать прямо сейчас",
    "Что скрывает твой повторяющийся сон",
    "Знаки, которым пора отпустить прошлое",
    "Прогноз по картам на твою главную тревогу",
    "Чего по-настоящему хочет твоё сердце",
    "Карта-предупреждение на эту неделю",
    "Кто тайно желает тебе добра",
    "Лунный совет для твоего знака",
    "Что изменится, если ты решишься",
    "Расклад: стоит ли давать второй шанс",
    "Твоя сильная сторона по дате рождения",
    "Знак судьбы, который ты не замечаешь",
    "Деньги на подходе — для каких знаков",
    "Что карты говорят о твоём бывшем",
    "Ответ на вопрос, который ты боишься задать",
    "Три совета вселенной на сегодня",
    "Чакра, которая просит внимания",
    "Будет ли у вас общее будущее",
]

# Платформы → короткий код источника для метки
PLATFORMS: dict[str, str] = {
    "tiktok": "tt",
    "youtube": "yt",
    "instagram": "ig",
    "vk": "vk",
    "telegram": "tg",
    "shorts": "ys",
}


def oracle_username() -> str:
    try:
        from oracle_bot.config import ORACLE_BOT_USERNAME  # type: ignore

        return (ORACLE_BOT_USERNAME or "MOracul_bot").lstrip("@")
    except Exception:
        return "MOracul_bot"


def source_code(platform: str, day: date, slot: int) -> str:
    """Уникальная метка источника: tt_0628_1 (площадка_ддмм_слот)."""
    code = PLATFORMS.get(platform, platform[:2])
    return f"{code}_{day:%m%d}_{slot}"


def deeplink(src: str) -> str:
    """Ссылка для описания ролика. Оракул распарсит src_<код> в signup_source."""
    return f"https://t.me/{oracle_username()}?start=src_{src}"


@dataclass
class PromoItem:
    date: str  # YYYY-MM-DD
    platform: str
    slot: int
    topic: str
    source: str
    link: str
    status: str = "planned"  # planned | rendered | posted | failed
    file: str = ""
    note: str = ""


def build_month_plan(
    start: date,
    per_day: dict[str, int],
    *,
    days: int = 30,
) -> list[PromoItem]:
    """План на N дней: для каждой площадки per_day[platform] роликов в день.

    Каждому ролику — своя тема (ротация) и уникальная метка источника.
    """
    items: list[PromoItem] = []
    topic_i = 0
    for d in range(days):
        day = start + timedelta(days=d)
        for platform, n in per_day.items():
            for slot in range(1, n + 1):
                topic = ORACLE_TOPICS[topic_i % len(ORACLE_TOPICS)]
                topic_i += 1
                src = source_code(platform, day, slot)
                items.append(
                    PromoItem(
                        date=day.isoformat(),
                        platform=platform,
                        slot=slot,
                        topic=topic,
                        source=src,
                        link=deeplink(src),
                    )
                )
    return items


# ───────────────────────── Хранение плана ─────────────────────────
def _plan_path() -> Path:
    from video_bot.config import VIDEO_DATA_DIR

    p = VIDEO_DATA_DIR / "promo"
    p.mkdir(parents=True, exist_ok=True)
    return p / "oracle_plan.json"


def save_plan(items: Iterable[PromoItem]) -> Path:
    path = _plan_path()
    path.write_text(
        json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_plan() -> list[PromoItem]:
    path = _plan_path()
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PromoItem(**r) for r in raw]


def due_items(plan: list[PromoItem], on: date | None = None) -> list[PromoItem]:
    """Ролики, которые надо выпустить на дату `on` (по умолчанию сегодня) и ещё не выпущены."""
    target = (on or date.today()).isoformat()
    return [i for i in plan if i.date <= target and i.status in {"planned", "rendered"}]


# ───────────────────────── Рендер ролика ─────────────────────────
async def render_item(item: PromoItem, out_dir: Path, *, use_llm: bool = True) -> Path:
    """Генерирует сценарий под тему Оракула и собирает вертикальный ролик."""
    from video_bot.content_product.assembler import build_product_video
    from video_bot.content_product.script_engine import generate_script

    out_dir.mkdir(parents=True, exist_ok=True)
    seed = abs(hash(item.source)) % 997
    script = await generate_script(
        item.topic,
        product_brief=ORACLE_BRIEF,
        cta=item.link,
        use_llm=use_llm,
        seed=seed,
    )
    out = out_dir / f"{item.platform}_{item.date}_{item.slot}.mp4"
    work = out_dir / f"_tmp_{item.platform}_{item.date}_{item.slot}"
    return await build_product_video(script, out, work_dir=work, min_duration_sec=55.0)
