"""Генерация сценария: LLM (Gemini) + fallback воронка."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from video_bot.content_product.models import Scene, VideoScript
from video_bot.content_product.prompts import (
    PRODUCT_BRIEF_NOVA,
    PRODUCT_BRIEF_WORK_BOT,
    SCRIPT_JSON_PROMPT,
    SYSTEM_SALES_DIRECTOR,
)

logger = logging.getLogger(__name__)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _fallback_earn_2026() -> VideoScript:
    """Ручная воронка — без LLM, продающая структура."""
    return VideoScript(
        topic="Заработок в интернете 2026",
        cta="t.me/M_onetest_bot",
        scenes=[
            Scene(
                "hook",
                ["ПОКА ТЫ СКРОЛИШЬ", "ДРУГИЕ УЖЕ СЧИТАЮТ"],
                "СЧИТАЮТ",
                "Стоп. Пока ты залипаешь в ленте, другие уже закрывают задания и выводят деньги.",
                "hands scrolling smartphone screen close up",
                cut_sec=2.2,
            ),
            Scene(
                "problem",
                ["ДЕНЬГИ В СЕТИ", "КАЖУТСЯ СЛОЖНЫМИ"],
                "СЛОЖНЫМИ",
                "Кажется, что заработать в интернете — это хаос, схемы и вечный поиск, с чего начать.",
                "laptop keyboard typing top view",
                cut_sec=2.4,
            ),
            Scene(
                "agitate",
                ["БЕЗ СИСТЕМЫ", "ТЫ ТОНЕШЬ"],
                "ТОНЕШЬ",
                "Без системы ты тратишь недели на ролики, которые никто не оплачивает.",
                "messy desk papers overhead b roll",
                cut_sec=2.3,
            ),
            Scene(
                "solution",
                ["ОДИН БОТ", "ВСЕ ЗАДАНИЯ"],
                "БОТ",
                "Мы собрали всё в одном месте — один бот в Телеграме. Центр твоего заработка — один клик.",
                "smartphone app notifications screen",
                cut_sec=2.6,
            ),
            Scene(
                "proof",
                ["TikTok · YouTube · VK", "ПЛАТЯТ ЗА ПРОСМОТРЫ"],
                "ПЛАТЯТ",
                "ТикТок, Ютуб и ВКонтакте платят за просмотры. Берёшь задание, публикуешь, сдаёшь отчёт.",
                "content creator filming phone vertical",
                cut_sec=2.8,
            ),
            Scene(
                "proof",
                ["АВИТО И ПАРТНЁРКИ", "ЯНДЕКС · OZON"],
                "ПАРТНЁРКИ",
                "Авито даёт заявки и процент со сделки. Плюс партнёрские программы Яндекса, Озона и банков.",
                "online payment credit card shopping",
                cut_sec=2.8,
            ),
            Scene(
                "offer",
                ["ГОТОВЫЕ МАТЕРИАЛЫ", "БЕРИ И ПУБЛИКУЙ"],
                "МАТЕРИАЛЫ",
                "Внутри — готовые материалы. Не придумывай с нуля — бери и выкладывай.",
                "phone downloading files interface",
                cut_sec=2.5,
            ),
            Scene(
                "offer",
                ["БОНУСЫ · РЕФЕРАЛКА", "ВЫВОД ОТ 5000 ₽"],
                "5000",
                "Бонус за друзей, награды за серии и вывод от пяти тысяч рублей после проверки.",
                "counting cash money macro b roll",
                cut_sec=2.6,
            ),
            Scene(
                "urgency",
                ["СЕЙЧАС КОНКУРЕНЦИЯ", "НИЖЕ ЧЕМ ЗАВТРА"],
                "СЕЙЧАС",
                "Сейчас ниша ещё открыта. Чем раньше зайдёшь — тем проще набрать оборот.",
                "city night traffic timelapse aerial",
                cut_sec=2.3,
            ),
            Scene(
                "cta",
                ["ЖМИ ССЫЛКУ", "В ОПИСАНИИ"],
                "ЖМИ",
                "Жми ссылку в описании и забери первое задание уже сегодня.",
                "finger tapping smartphone screen close up",
                cut_sec=2.5,
            ),
        ],
    )


def _fallback_nova_potolki() -> VideoScript:
    """НОВА — натяжные потолки Москва. Оффер с potolki-nova.ru."""
    return VideoScript(
        topic="Натяжные потолки в Москве — NOVA",
        cta="https://potolki-nova.ru/",
        meta={"client": "nova", "site": "potolki-nova.ru", "topic_key": "stretch_ceiling", "music_profile": "corporate"},
        scenes=[
            Scene(
                "hook",
                ["ПОТОЛОК ПОРТИТ", "ВЕСЬ РЕМОНТ"],
                "РЕМОНТ",
                "Смотри наверх. Трещины, пятна, старый ремонт — один потолок портит всю квартиру.",
                "old ceiling cracks apartment interior",
                cut_sec=2.2,
            ),
            Scene(
                "problem",
                ["КУХНЯ · ЗАЛ", "ЖДУТ ИДЕАЛ"],
                "ИДЕАЛ",
                "Кухня и зал уже готовы, а потолок откладываешь снова и снова.",
                "modern kitchen interior renovation",
                cut_sec=2.3,
            ),
            Scene(
                "agitate",
                ["БЕЗ ПОТОЛКА", "РЕМОНТ НЕ ЗАКОНЧЕН"],
                "НЕ ЗАКОНЧЕН",
                "Без нового потолка ремонт так и останется недоделанным месяцами.",
                "unfinished room renovation interior",
                cut_sec=2.2,
            ),
            Scene(
                "solution",
                ["NOVA · МОСКВА", "ПОД КЛЮЧ"],
                "NOVA",
                "Компания Нова — натяжные потолки в Москве и области под ключ, с понятной ценой за метр.",
                "modern stretch ceiling living room lights",
                cut_sec=2.6,
            ),
            Scene(
                "proof",
                ["ОТ 299 ₽", "ЗА МЕТР КВАДРАТНЫЙ"],
                "299",
                "По акции — от двухсот девяноста девяти рублей за квадратный метр. Цена прозрачная, без сюрпризов.",
                "luxury apartment ceiling spotlights",
                cut_sec=2.7,
            ),
            Scene(
                "proof",
                ["14 ЛЕТ · СВОЁ", "ПРОИЗВОДСТВО"],
                "14 ЛЕТ",
                "Четырнадцать лет опыта и своё производство — вы платите без лишних посредников.",
                "factory production interior materials",
                cut_sec=2.5,
            ),
            Scene(
                "offer",
                ["ГАРАНТИЯ", "25 ЛЕТ"],
                "25 ЛЕТ",
                "Расширенная гарантия до двадцати пяти лет и только сертифицированные полотна.",
                "modern white ceiling interior design",
                cut_sec=2.5,
            ),
            Scene(
                "offer",
                ["ЗАМЕР БЕСПЛАТНО", "СВЕТ В ПОДАРОК"],
                "БЕСПЛАТНО",
                "Бесплатный замер в Москве и области плюс светильники в подарок при заказе.",
                "interior designer measuring room",
                cut_sec=2.6,
            ),
            Scene(
                "urgency",
                ["МОНТАЖ", "ЗА ОДИН ДЕНЬ"],
                "ОДИН ДЕНЬ",
                "Монтаж часто за один день — заходите утром, вечером уже новый потолок.",
                "home renovation completion happy interior",
                cut_sec=2.3,
            ),
            Scene(
                "cta",
                ["NOVA · МОСКВА", "ССЫЛКА В ОПИСАНИИ"],
                "NOVA",
                "Оставь заявку на сайте — ссылка в описании. Закажи бесплатный замер уже сегодня.",
                "smartphone booking online close up",
                cut_sec=2.5,
            ),
        ],
    )


_ORACLE_HINTS = ("оракул", "таро", "гороскоп", "расклад", "знак", "карт", "судьб", "вселенн", "зодиак")


def _is_oracle_topic(topic: str) -> bool:
    t = topic.lower()
    return any(h in t for h in _ORACLE_HINTS)


def _oracle_v_tarot(cta: str) -> VideoScript:
    return VideoScript(
        topic="Оракул: один расклад таро",
        cta=cta,
        meta={"client": "oracle", "topic_key": "tarot"},
        scenes=[
            Scene("hook", ["ОДНА КАРТА", "ВСЁ ОБЪЯСНИТ"], "КАРТА",
                  "Стоп. Загадай вопрос — и одна карта скажет то, что ты боишься признать.",
                  "tarot cards candle mystical dark", cut_sec=2.2),
            Scene("problem", ["МЫСЛИ ПО КРУГУ", "НЕТ ОТВЕТА"], "ОТВЕТА",
                  "Когда внутри тревога и мысли ходят по кругу, так хочется простого честного ответа.",
                  "woman thinking window rain night", cut_sec=2.4),
            Scene("agitate", ["СОМНЕНИЯ", "КРАДУТ ВРЕМЯ"], "ВРЕМЯ",
                  "Чем дольше тянешь с решением, тем больше сил забирают сомнения.",
                  "clock time lapse dark moody", cut_sec=2.3),
            Scene("solution", ["ОРАКУЛ", "В ТЕЛЕГРАМЕ"], "ОРАКУЛ",
                  "Твой личный оракул в Телеграме. Таро, гороскоп и совместимость — ответ за секунды.",
                  "smartphone glowing magic interface", cut_sec=2.6),
            Scene("proof", ["ТАРО · ГОРОСКОП", "ЧИСЛО СУДЬБЫ"], "ТАРО",
                  "Расклад на любовь и деньги, гороскоп на сегодня, число судьбы по дате рождения.",
                  "astrology zodiac stars cosmos", cut_sec=2.8),
            Scene("offer", ["ПЕРВЫЙ РАСКЛАД", "БЕСПЛАТНО"], "БЕСПЛАТНО",
                  "Первый расклад бесплатно. Просто открой бота и задай свой вопрос.",
                  "hands holding phone cozy candle", cut_sec=2.5),
            Scene("urgency", ["КАРТЫ ГОТОВЫ", "ОТВЕТИТЬ СЕЙЧАС"], "СЕЙЧАС",
                  "Карты уже готовы ответить. Не откладывай то, что можно узнать прямо сейчас.",
                  "tarot spread table candlelight", cut_sec=2.3),
            Scene("cta", ["ЖМИ ССЫЛКУ", "В ОПИСАНИИ"], "ЖМИ",
                  "Жми ссылку в описании и получи свой первый расклад бесплатно.",
                  "finger tapping phone screen glow", cut_sec=2.5),
        ],
    )


def _oracle_v_love(cta: str) -> VideoScript:
    return VideoScript(
        topic="Оракул: расклад на любовь",
        cta=cta,
        meta={"client": "oracle", "topic_key": "love"},
        scenes=[
            Scene("hook", ["ОН ДУМАЕТ", "О ТЕБЕ?"], "О ТЕБЕ",
                  "Хочешь знать, думает ли он о тебе прямо сейчас? Карты не умеют врать.",
                  "couple silhouette sunset romantic", cut_sec=2.2),
            Scene("problem", ["МОЛЧАНИЕ", "СВОДИТ С УМА"], "МОЛЧАНИЕ",
                  "Когда он молчит, голова придумывает худшее, а сердце ждёт хоть какого-то знака.",
                  "woman looking at phone waiting", cut_sec=2.4),
            Scene("agitate", ["ДОГАДКИ", "РАНЯТ СИЛЬНЕЕ"], "ДОГАДКИ",
                  "Бесконечные догадки ранят больнее правды. Пора получить ясность.",
                  "rainy window sad mood evening", cut_sec=2.3),
            Scene("solution", ["СПРОСИ", "У ОРАКУЛА"], "ОРАКУЛ",
                  "Спроси у оракула в Телеграме: что он чувствует, чего хочет, и есть ли будущее.",
                  "tarot reading love spread candle", cut_sec=2.6),
            Scene("proof", ["ЕГО ЧУВСТВА", "ВАШЕ БУДУЩЕЕ"], "ЧУВСТВА",
                  "Расклад на отношения, совместимость по датам и честный прогноз для пары.",
                  "two hands together heart light", cut_sec=2.8),
            Scene("offer", ["ПЕРВЫЙ ОТВЕТ", "БЕСПЛАТНО"], "БЕСПЛАТНО",
                  "Первый ответ бесплатно. Задай свой вопрос о нём прямо сейчас.",
                  "woman smiling phone cozy home", cut_sec=2.5),
            Scene("urgency", ["НЕ ГАДАЙ", "УЗНАЙ"], "УЗНАЙ",
                  "Хватит гадать на ромашке. Узнай, что между вами на самом деле.",
                  "rose petals candle soft focus", cut_sec=2.3),
            Scene("cta", ["ССЫЛКА", "В ОПИСАНИИ"], "ССЫЛКА",
                  "Жми ссылку в описании и получи расклад на любовь бесплатно.",
                  "finger tapping phone screen glow", cut_sec=2.5),
        ],
    )


def _oracle_v_horo(cta: str) -> VideoScript:
    return VideoScript(
        topic="Оракул: гороскоп и судьба знака",
        cta=cta,
        meta={"client": "oracle", "topic_key": "horoscope"},
        scenes=[
            Scene("hook", ["ТВОЙ ЗНАК", "НА ПОРОГЕ ПЕРЕМЕН"], "ПЕРЕМЕН",
                  "Если ты родилась под этим знаком, ближайшие дни изменят многое.",
                  "starry night sky zodiac cosmos", cut_sec=2.2),
            Scene("problem", ["ОБЩИЙ ГОРОСКОП", "НЕ ПРО ТЕБЯ"], "ОБЩИЙ",
                  "Гороскопы из ленты слишком общие и никогда не попадают в твою ситуацию.",
                  "newspaper horoscope blurry pages", cut_sec=2.4),
            Scene("agitate", ["ВАЖНЫЙ ДЕНЬ", "МОЖНО УПУСТИТЬ"], "УПУСТИТЬ",
                  "А ведь один правильный день можно упустить, если не знать, чего ждать.",
                  "sand hourglass time flowing", cut_sec=2.3),
            Scene("solution", ["ЛИЧНЫЙ", "ПРОГНОЗ"], "ЛИЧНЫЙ",
                  "Оракул в Телеграме составит личный прогноз: энергия, деньги, отношения на сегодня.",
                  "astrology chart wheel glowing", cut_sec=2.6),
            Scene("proof", ["ЛЮБОВЬ · ДЕНЬГИ", "СОВЕТ ДНЯ"], "СОВЕТ",
                  "Что усилить, чего избегать и один точный совет именно для твоего знака.",
                  "planets space stars motion", cut_sec=2.8),
            Scene("offer", ["ПРОГНОЗ", "БЕСПЛАТНО"], "БЕСПЛАТНО",
                  "Первый персональный прогноз бесплатно. Узнай свой день за минуту.",
                  "phone calendar morning sunrise", cut_sec=2.5),
            Scene("urgency", ["УЗНАЙ", "ПОКА ДЕНЬ НЕ НАЧАЛСЯ"], "СЕЙЧАС",
                  "Загляни до того, как начнётся день — так совет действительно сработает.",
                  "sunrise horizon golden hour", cut_sec=2.3),
            Scene("cta", ["ССЫЛКА", "В ОПИСАНИИ"], "ССЫЛКА",
                  "Жми ссылку в описании и забери свой гороскоп на сегодня бесплатно.",
                  "finger tapping phone screen glow", cut_sec=2.5),
        ],
    )


_ORACLE_VARIANTS = (_oracle_v_tarot, _oracle_v_love, _oracle_v_horo)


def _fallback_oracle(cta: str = "t.me/MOracul_bot", seed: int = 0) -> VideoScript:
    """Оракул @MOracul_bot — продающая воронка без LLM. seed выбирает один из вариантов."""
    return _ORACLE_VARIANTS[seed % len(_ORACLE_VARIANTS)](cta)


async def generate_script(
    topic: str,
    *,
    product_brief: str = PRODUCT_BRIEF_WORK_BOT,
    cta: str = "t.me/M_onetest_bot",
    use_llm: bool = True,
    script_id: str | None = None,
    seed: int = 0,
) -> VideoScript:
    if script_id == "nova_potolki" or "nova" in topic.lower() or "натяжн" in topic.lower() or "потолк" in topic.lower():
        return _fallback_nova_potolki()
    if use_llm:
        try:
            return await _generate_via_llm(topic, product_brief=product_brief, cta=cta)
        except Exception as e:
            logger.warning("LLM script failed, fallback: %s", e)
    if script_id == "oracle" or _is_oracle_topic(topic):
        return _fallback_oracle(cta, seed=seed)
    if "зарабат" in topic.lower() or "2026" in topic:
        return _fallback_earn_2026()
    return _fallback_earn_2026()


async def _generate_via_llm(topic: str, *, product_brief: str, cta: str) -> VideoScript:
    from bot.services.gemini_llm import gemini_chat_completion, gemini_llm_configured

    if not gemini_llm_configured():
        raise RuntimeError("GEMINI_API_KEY не настроен")

    prompt = SCRIPT_JSON_PROMPT.format(
        topic=topic,
        product_brief=product_brief.strip(),
        cta=cta,
    )
    raw = await gemini_chat_completion(
        [{"role": "user", "content": prompt}],
        system=SYSTEM_SALES_DIRECTOR,
        temperature=0.85,
        timeout_sec=90,
    )
    data = _parse_json(raw)
    scenes: list[Scene] = []
    for s in data.get("scenes") or []:
        scenes.append(
            Scene(
                stage=s.get("stage", "proof"),
                caption_lines=list(s.get("caption_lines") or ["..."])[:2],
                highlight=str(s.get("highlight") or "")[:24],
                voice=str(s.get("voice") or "").strip(),
                broll_search=str(s.get("broll_search") or "money phone").strip(),
                media_prefer=s.get("media_prefer", "video"),
                cut_sec=float(s.get("cut_sec") or 2.4),
            )
        )
    if len(scenes) < 5:
        raise ValueError("слишком мало сцен от LLM")
    return VideoScript(
        topic=str(data.get("topic") or topic),
        cta=str(data.get("cta") or cta),
        scenes=scenes,
        meta={"source": "llm"},
    )
