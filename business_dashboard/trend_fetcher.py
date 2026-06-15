"""Подсказки поиска (Google + Yandex) — бесплатно, без API-ключа."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

USER_AGENT = "Mozilla/5.0 (compatible; MoneyHub/1.0)"


def _get_json(url: str, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def google_suggest(query: str, lang: str = "ru") -> List[str]:
    q = urllib.parse.quote(query)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&hl={lang}&q={q}"
    try:
        data = _get_json(url)
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            return [str(s).strip() for s in data[1] if s and len(str(s)) > 3][:8]
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        pass
    return []


def yandex_suggest(query: str) -> List[str]:
    q = urllib.parse.quote(query)
    url = f"https://yandex.ru/suggest/suggest-ya.cgi?v=4&part={q}&uil=ru"
    try:
        data = _get_json(url)
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            return [str(s).strip() for s in data[1] if s and len(str(s)) > 3][:8]
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        pass
    return []


def _guess_solution(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("бот", "telegram", "тг ", " tg")):
        return "bot"
    if any(w in q for w in ("сайт", "онлайн", "сравнить", "калькулятор")):
        return "site"
    if any(w in q for w in ("реферал", "партнёр", "cpa", "осаго")):
        return "referral"
    return "bot"


def _guess_daily_rub(query: str) -> float:
    q = query.lower()
    if "осаго" in q or "кредит" in q:
        return 500.0
    if "ozon" in q or "wildberries" in q or "wb " in q:
        return 400.0
    if "бот" in q or "telegram" in q:
        return 300.0
    return 200.0


def _slugify_trend(query: str) -> str:
    import hashlib
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return f"scout-live-{digest}"


def fetch_live_trends(seed_queries: List[str]) -> List[Dict[str, Any]]:
    """Собирает подсказки из Google и Yandex по базовым запросам."""
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []

    for seed in seed_queries:
        for source, suggestions in (
            ("google", google_suggest(seed)),
            ("yandex", yandex_suggest(seed)),
        ):
            for text in suggestions:
                key = text.lower()
                if key in seen or len(key) < 6:
                    continue
                seen.add(key)
                sol = _guess_solution(text)
                daily = _guess_daily_rub(text)
                out.append(
                    {
                        "slug": _slugify_trend(text),
                        "query": text,
                        "source": source,
                        "volume": 55,
                        "solution_type": sol,
                        "monetization": f"авто-оценка ({sol})",
                        "expected_daily_rub": daily,
                    }
                )
    return out
