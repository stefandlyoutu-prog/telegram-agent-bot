"""Groq API для Оракула (ключ GROK_API_KEY / gsk_…)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiohttp import ClientError

from bot.config import GROK_API_KEY
from bot.services.llm import LLMError

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_CHAT_MODEL = "llama-3.3-70b-versatile"
_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_TIMEOUT = aiohttp.ClientTimeout(total=90, connect=30)


def groq_configured() -> bool:
    return bool(GROK_API_KEY and GROK_API_KEY.startswith("gsk_"))


async def _post(payload: dict[str, Any]) -> dict[str, Any]:
    if not groq_configured():
        raise LLMError("Groq не настроен (GROK_API_KEY)")
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _GROQ_URL,
                json=payload,
                headers=headers,
                timeout=_TIMEOUT,
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    body = await resp.text()
                    raise LLMError(f"Groq ({resp.status}): {body[:200]}")
                if resp.status != 200:
                    err = data.get("error", {})
                    msg = err.get("message", str(data)) if isinstance(err, dict) else str(data)
                    raise LLMError(f"Groq ({resp.status}): {msg}")
                return data
    except asyncio.TimeoutError as e:
        raise LLMError("Таймаут Groq API") from e
    except ClientError as e:
        raise LLMError(f"Сеть Groq: {e}") from e


def _text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Groq: пустой ответ")
    text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise LLMError("Groq: пустой текст")
    return text.strip()


async def chat(
    user_prompt: str,
    *,
    system: str,
    temperature: float = 0.8,
    max_tokens: int = 1200,
) -> str:
    payload = {
        "model": _CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _text(await _post(payload))


async def vision(
    user_text: str,
    image_data_url: str,
    *,
    system: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> str:
    payload = {
        "model": _VISION_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _text(await _post(payload))
