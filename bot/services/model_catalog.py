"""Каталог моделей KupiAPI + авто-выбор под задачу."""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Кнопки /model — основные (не перегружать клавиатуру)
PRIMARY_MODEL_IDS: List[str] = [
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.5",
    "gpt-5.4-nano",
    "claude-haiku-4.5",
    "claude-sonnet-4.6",
    "claude-opus-4.7",
    "deepseek-chat",
]

MODEL_LABELS: Dict[str, str] = {
    "gpt-5.5": "GPT-5.5 (сложные задачи)",
    "gpt-5.5-codex": "GPT-5.5 Codex (код)",
    "gpt-5.5-high": "GPT-5.5 High",
    "gpt-5.5-medium": "GPT-5.5 Medium",
    "gpt-5.4": "GPT-5.4 (инженерия)",
    "gpt-5.4-medium": "GPT-5.4 Medium",
    "gpt-5.4-mini": "GPT-5.4 mini (быстро, по умолчанию)",
    "gpt-5.4-mini-medium": "GPT-5.4 mini Medium",
    "gpt-5.4-nano": "GPT-5.4 nano (черновики)",
    "claude-opus-4.7": "Claude Opus 4.7 (максимум)",
    "claude-sonnet-4.6": "Claude Sonnet 4.6 (баланс)",
    "claude-haiku-4.5": "Claude Haiku 4.5 (коротко/SEO)",
    "deepseek-chat": "DeepSeek Chat",
    "deepseek-reasoner": "DeepSeek Reasoner (рассуждения)",
    "gpt-4o-mini": "GPT-5.4 mini (алиас)",
    "gpt-4o": "GPT-5.4 (алиас)",
    "claude-haiku": "Claude Haiku 4.5 (алиас)",
    "claude-sonnet": "Claude Sonnet 4.6 (алиас)",
    "claude-opus": "Claude Opus 4.7 (алиас)",
    "deepseek-r1": "DeepSeek Reasoner (алиас)",
}

TEXT_ONLY_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner", "deepseek-r1"})

_CACHE: Dict[str, object] = {"at": 0.0, "ids": set()}


def model_label(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


def merged_available_models() -> Dict[str, str]:
    from bot.config import AVAILABLE_MODELS

    out = dict(AVAILABLE_MODELS)
    for mid, label in MODEL_LABELS.items():
        out.setdefault(mid, label)
    return out


async def refresh_from_api() -> List[str]:
    """Подтянуть ID моделей с KupiAPI (кэш 10 мин)."""
    from bot.config import LLM_API_KEY, LLM_BASE_URL

    now = time.time()
    if now - float(_CACHE.get("at") or 0) < 600 and _CACHE.get("ids"):
        return sorted(_CACHE["ids"])  # type: ignore[arg-type]

    if not LLM_API_KEY:
        return []

    import aiohttp

    from bot.services.http_client import llm_connection_modes, proxy_for_request, session_kwargs

    ids: set[str] = set()
    url = f"{LLM_BASE_URL}/models"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    for use_proxy in llm_connection_modes():
        try:
            async with aiohttp.ClientSession(**session_kwargs(use_proxy)) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                    proxy=proxy_for_request(use_proxy),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    for item in data.get("data") or []:
                        mid = item.get("id")
                        if mid:
                            ids.add(str(mid))
                    break
        except Exception as e:
            logger.debug("models list: %s", e)
            continue

    if ids:
        _CACHE["at"] = now
        _CACHE["ids"] = ids
    return sorted(ids)


def infer_capability(user_text: str, *, base: str = "chat") -> str:
    """Уточнить capability для авто-модели."""
    t = (user_text or "").lower()
    if base != "chat":
        return base
    if re.search(r"\b(код|python|javascript|sql|openscad|\.scad|script|regex|api)\b", t):
        return "code"
    if re.search(
        r"сложн|подробн|глубок|стратег|анализ|исслед|сравни|обосну|архитект|"
        r"оптимиз|proof|доказ|рассужд",
        t,
    ):
        return "complex_chat"
    if re.search(r"кратко|коротко|seo|авито|заголов|описан|реклам", t):
        return "seo_copy"
    return "chat"


def pick_model_for_capability(capability: str, user_model: Optional[str] = None) -> Tuple[str, str]:
    from bot.config import AUTO_SWITCH_MODEL, DEFAULT_MODEL
    from bot.services.model_router import model_for_capability

    user_model = user_model or DEFAULT_MODEL
    chosen = model_for_capability(capability, user_model)
    user_label = model_label(user_model)
    chosen_label = model_label(chosen)

    if chosen == user_model:
        reason = f"Модель: {chosen_label}."
    elif AUTO_SWITCH_MODEL:
        reason = f"Авто-модель: {chosen_label} (в /model: {user_label})."
    else:
        reason = f"Для задачи — {chosen_label} (в /model: {user_label})."
    return chosen, reason
