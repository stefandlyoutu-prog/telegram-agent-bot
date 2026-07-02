"""Движок персональных книг-разборов: сухие данные → живая личная книга."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from oracle_bot.llm_helpers import oracle_chat_with_system

logger = logging.getLogger(__name__)

# Иероглифы CJK, хангыль, тайский, арабский, иврит — недопустимы в русской книге
_FOREIGN = re.compile(r"[\u0590-\u05ff\u0600-\u06ff\u0e00-\u0e7f\u3000-\u9fff\uac00-\ud7af]")
# Латиница (английские слова) — тоже брак для русской книги
_LATIN = re.compile(r"[A-Za-z]{2,}")
# Эмодзи/пиктограммы — убираем из тела книги (нет в шрифте PDF, лишние в премиум-тексте)
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u2190-\u21ff\u2b00-\u2bff\ufe0f]"
)

BOOK_SYSTEM = (
    "Ты — автор персональных книг о человеке мирового уровня. Твоя книга должна "
    "читаться как самый тёплый, точный и глубокий текст, который человек когда-либо "
    "читал о себе: в каждом абзаце он узнаёт свои черты и думает «это про меня».\n\n"
    "Правила письма:\n"
    "• Живой литературный русский язык. Обращайся на «ты» — тепло, по-человечески, "
    "как мудрый близкий человек, который видит тебя насквозь и любит таким, какой есть.\n"
    "• Превращай сухие данные диагностики в смысл, характер и узнаваемые сцены из жизни "
    "(как человек ведёт себя в работе, в любви, в конфликте, наедине с собой).\n"
    "• НИКОГДА не показывай проценты, коды, номера арканов, проценты чакр и "
    "термины метода как сырые данные. Только их человеческий смысл. ИСКЛЮЧЕНИЕ — "
    "возрасты и календарные годы: их называй явно и точно («с 24 до 36 лет, то есть "
    "примерно с 2018 по 2030 год»), человеку важна эта конкретика.\n"
    "• Без воды. Каждый абзац обязан содержать конкретное узнаваемое утверждение о "
    "человеке, пример из жизни или практический вывод. Вычёркивай фразы, которые "
    "подошли бы кому угодно («жизнь полна перемен», «важно верить в себя», «у каждого "
    "свой путь»). Меньше красивых обобщений — больше точных наблюдений и советов.\n"
    "• Без эзотерических клише, гадального тумана, общих гороскопных фраз и обещаний "
    "богатства/судьбоносных встреч. Конкретно, образно, честно — и с теплом.\n"
    "• Показывай и сильные стороны, и теневые — но тень подавай бережно, как зону роста.\n"
    "• Не задавай вопросов читателю. Не выдумывай факты биографии (имена, события).\n"
    "• Пиши абзацами. Без буллет-списков, без Markdown-звёздочек, без эмодзи.\n"
    "• Пиши ИСКЛЮЧИТЕЛЬНО на русском языке. Ни одного английского или иностранного "
    "слова, ни одного иероглифа или латинской буквы — только грамотный живой русский. "
    "Если просится иностранное слово — подбери русское.\n"
    "• Если нужен подзаголовок внутри раздела — начинай строку с «## » (двойная решётка и пробел)."
)


@dataclass
class SectionSpec:
    title: str
    brief: str          # что осветить в разделе
    facts: str          # человеко-читаемые вводные о человеке
    words: str = "230–320"
    fallback: str = ""  # шаблонный текст, если LLM недоступен


def _build_prompt(person: str, spec: SectionSpec) -> str:
    return (
        f"Имя человека: {person}\n"
        f"Раздел книги: «{spec.title}»\n\n"
        f"Что нужно раскрыть в этом разделе:\n{spec.brief}\n\n"
        f"Индивидуальные вводные об этом человеке (используй как смысл, не цитируй цифры):\n"
        f"{spec.facts}\n\n"
        f"Напиши этот раздел книги объёмом {spec.words} слов. Только текст раздела, "
        f"без заголовка раздела в начале и без служебных пометок."
    )


def _clean(text: str) -> str:
    text = (text or "").strip()
    # убрать markdown-жирный и лишние решётки заголовков (## оставляем как маркер)
    for ch in ("**", "__", "`"):
        text = text.replace(ch, "")
    text = _EMOJI.sub("", text)
    lines = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if s.startswith("#") and not s.startswith("## "):
            s = "## " + s.lstrip("#").strip()
        lines.append(s)
    return "\n".join(lines).strip()


def _has_foreign(text: str) -> bool:
    return bool(_FOREIGN.search(text) or _LATIN.search(text))


def _sanitize_foreign(text: str) -> str:
    """Убирает залётные иероглифы/латиницу и приводит пробелы/пунктуацию в порядок."""
    text = _FOREIGN.sub("", text)
    text = _LATIN.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?»)])", r"\1", text)
    text = re.sub(r"([«(])\s+", r"\1", text)
    text = re.sub(r"\bа\s+,", "а,", text)
    return text.strip()


async def write_section(person: str, spec: SectionSpec, *, timeout: float = 75.0) -> str:
    try:
        raw = await asyncio.wait_for(
            oracle_chat_with_system(_build_prompt(person, spec), system=BOOK_SYSTEM),
            timeout=timeout,
        )
        body = _clean(raw)
        # премиум-качество: при залётных иероглифах/латинице — один аккуратный ретрай
        if _has_foreign(body):
            try:
                raw2 = await asyncio.wait_for(
                    oracle_chat_with_system(
                        _build_prompt(person, spec)
                        + "\n\nВАЖНО: пиши строго на русском, без единого иностранного символа.",
                        system=BOOK_SYSTEM,
                        temperature=0.6,
                    ),
                    timeout=timeout,
                )
                body2 = _clean(raw2)
                if body2 and not _has_foreign(body2):
                    body = body2
                else:
                    body = _sanitize_foreign(body2 or body)
            except Exception:  # noqa: BLE001
                body = _sanitize_foreign(body)
        if len(body) < 120:  # слишком коротко/пусто → шаблон
            return spec.fallback or body
        return body
    except Exception as e:  # noqa: BLE001
        logger.warning("book section «%s»: %s", spec.title, e)
        return spec.fallback


async def write_sections(person: str, specs: list[SectionSpec], *, concurrency: int = 2) -> list[str]:
    """Генерит все разделы (с ограничением параллельности). Возвращает тела разделов."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(spec: SectionSpec) -> str:
        async with sem:
            return await write_section(person, spec)

    return await asyncio.gather(*[_one(s) for s in specs])
