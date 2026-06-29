"""Знания курса ХВД: выборка из транскриптов по параметрам профиля."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"
COURSE_SRC = Path.home() / "Downloads" / "numerologyHVD"

_FILE_BY_PREFIX: dict[str, tuple[str, ...]] = {
    "intro": ("01 - Введение", "01-"),
    "typology": ("2-1", "2-2", "2-3"),
    "chakras": ("3-1", "3-2", "3-3"),
    "contours": ("4-1", "4-2", "4-3", "4-4"),
    "egoism": ("5-Эгоизм",),
    "yinyang": ("6-Инь",),
    "periods_intro": ("7-1",),
    "periods_04": ("7-2",),
    "periods_59": ("7-3",),
    "task_present": ("8-1",),
    "task_past": ("8-2",),
    "task_lineage": ("8-3",),
    "task_parents": ("8-4",),
}

_TYPOLOGY_FILES = {
    1: "2-1", 2: "2-1", 3: "2-1",
    4: "2-2", 5: "2-2", 6: "2-2",
    7: "2-3", 8: "2-3", 9: "2-3",
}

_PERIOD_KEYWORDS: dict[int, tuple[str, ...]] = {
    0: ("период нуля", "нулев", "нулё", "ноль", "цифра 0", "ноля"),
    1: ("первый период", "период один", "период 1", "единиц", "муладхар"),
    2: ("второй период", "период дв", "период 2", "двойк", "свадхистан"),
    3: ("третий период", "период три", "период 3", "тройк", "манипур"),
    4: ("четверт", "четвёрт", "период 4", "анахат", "четыр"),
    5: ("пятый период", "период 5", "пятер", "вишудх"),
    6: ("шестой период", "период 6", "шестер", "аджн"),
    7: ("седьмой период", "период 7", "семер", "духовн"),
    8: ("восьмой период", "период 8", "восьмер", "смысл"),
    9: ("девятый период", "период 9", "девят", "предназнач", "карм"),
}

_TYPOLOGY_KEYWORDS: dict[int, tuple[str, ...]] = {
    1: ("типолог", "единиц", "тип 1", "первый тип", "лидер"),
    2: ("типолог", "двоек", "тип 2", "второй тип", "партнер"),
    3: ("типолог", "троек", "тип 3", "творч"),
    4: ("типолог", "четвер", "тип 4", "труд", "систем"),
    5: ("типолог", "пятер", "тип 5", "свобод"),
    6: ("типолог", "шестер", "тип 6", "семь"),
    7: ("типолог", "семер", "тип 7", "духов"),
    8: ("типолог", "восьмер", "тип 8", "власт"),
    9: ("типолог", "девят", "тип 9", "мудр", "философ", "отшельник", "девятк"),
}

_REACTIVITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Холодный": ("холодный", "холодн"),
    "Самоотверженный": ("самоотвержен", "самоотверж"),
    "Среднереактивный": ("среднереактив", "средний реактив", "золотой серед"),
    "Энергичный": ("энергичн", "энергичный тип"),
    "Эгоистический": ("эгоистическ", "эгоистич"),
    "Сверхэнергичный": ("сверхэнергич", "сверх энергич"),
}


def _load_text(stem_prefix: str) -> str:
    if not TRANSCRIPT_DIR.is_dir():
        return ""
    for path in sorted(TRANSCRIPT_DIR.glob("*.txt")):
        if path.name.startswith(stem_prefix):
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
    return ""


def _load_topic(topic: str) -> str:
    parts = []
    for prefix in _FILE_BY_PREFIX.get(topic, ()):
        text = _load_text(prefix)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [s.strip() for s in raw if len(s.strip()) >= 35]


def _pick_sentences(text: str, keywords: tuple[str, ...], limit: int = 10) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    picked: list[str] = []
    for sent in _sentences(text):
        low = sent.lower()
        if not any(k in low for k in keywords):
            continue
        key = low[:80]
        if key in seen:
            continue
        seen.add(key)
        picked.append(sent)
        if len(picked) >= limit:
            break
    return picked


def _join(sents: list[str], max_chars: int = 1400) -> str:
    if not sents:
        return ""
    out: list[str] = []
    total = 0
    for s in sents:
        if total + len(s) > max_chars:
            break
        out.append(s)
        total += len(s) + 1
    return " ".join(out)


@lru_cache(maxsize=32)
def topic_snippet(topic: str, max_chars: int = 500) -> str:
    text = _load_topic(topic)
    if len(text) < 80:
        return ""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    last = cut.rfind(".")
    if last > max_chars // 2:
        cut = cut[: last + 1]
    return cut


def typology_course_text(n: int) -> str:
    prefix = _TYPOLOGY_FILES.get(n, "2-1")
    text = _load_text(prefix)
    sents = _pick_sentences(text, _TYPOLOGY_KEYWORDS.get(n, (str(n),)), limit=12)
    return _join(sents, 1200)


def period_digit_course_text(digit: int) -> str:
    source = _load_topic("periods_04") if digit <= 4 else _load_topic("periods_59")
    if not source:
        source = _load_topic("periods_intro")
    sents = _pick_sentences(source, _PERIOD_KEYWORDS.get(digit, (str(digit),)), limit=14)
    return _join(sents, 1500)


def reactivity_course_text(reactivity: str) -> str:
    text = _load_topic("egoism")
    keys = _REACTIVITY_KEYWORDS.get(reactivity, (reactivity.lower(),))
    sents = _pick_sentences(text, keys, limit=8)
    return _join(sents, 1000)


def task_course_text(task_num: int) -> str:
    mapping = {
        1: "task_present", 2: "task_present", 3: "task_present", 4: "task_present",
        5: "task_present", 6: "task_present", 7: "task_present", 8: "task_present", 9: "task_present",
    }
    # also search all task files for the number
    parts: list[str] = []
    for topic in ("task_past", "task_present", "task_lineage", "task_parents"):
        sents = _pick_sentences(_load_topic(topic), (f"задач", str(task_num), f" {task_num} "), limit=4)
        parts.extend(sents)
    return _join(parts, 900)


def contour_course_text(label: str) -> str:
    text = _load_topic("contours")
    # first word of temperament/character type
    token = label.split("(")[0].split("-")[0].strip().lower()[:12]
    sents = _pick_sentences(text, (token,), limit=5) if token else []
    return _join(sents, 600)


def yinyang_course_text() -> str:
    return topic_snippet("yinyang", 800)


def intuitive_course_text() -> str:
    return topic_snippet("contours", 400) or _join(
        _pick_sentences(_load_text("4-2"), ("интуитив", "вербал", "невербал"), 6), 700
    )


def intro_course_text() -> str:
    return topic_snippet("intro", 400)


def chakras_course_text() -> str:
    return topic_snippet("chakras", 500)


def transcripts_ready() -> int:
    if not TRANSCRIPT_DIR.is_dir():
        return 0
    return len(list(TRANSCRIPT_DIR.glob("*.txt")))


def missing_course_videos() -> list[str]:
    if not COURSE_SRC.is_dir():
        return []
    done = {p.stem for p in TRANSCRIPT_DIR.glob("*.txt")} if TRANSCRIPT_DIR.is_dir() else set()
    return [p.name for p in sorted(COURSE_SRC.glob("*.mp4")) if p.stem not in done]
