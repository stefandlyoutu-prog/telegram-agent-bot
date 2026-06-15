"""KupiAPI для Оракула: прокси → напрямую, длинные таймауты."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiohttp import ClientConnectorError, ClientError

from bot.config import LLM_API_KEY, LLM_CHAT_URL, VISION_MODEL
from bot.services.http_client import (
    format_client_error,
    llm_connection_modes,
    proxy_for_request,
    session_kwargs,
)
from bot.services.llm import LLMError, _normalize_model

_VISION_TIMEOUT = 90
_CHAT_TIMEOUT = 120


def _timeout(total: int) -> aiohttp.ClientTimeout:
    connect = min(45, total)
    return aiohttp.ClientTimeout(total=total, connect=connect, sock_connect=connect)


async def _post(payload: dict[str, Any], *, timeout_sec: int) -> dict[str, Any]:
    if not LLM_API_KEY:
        raise LLMError("Не задан LLM_API_KEY")
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    modes = list(llm_connection_modes())
    last_err: Exception | None = None

    for use_proxy in modes:
        try:
            async with aiohttp.ClientSession(**session_kwargs(use_proxy)) as session:
                async with session.post(
                    LLM_CHAT_URL,
                    json=payload,
                    headers=headers,
                    timeout=_timeout(timeout_sec),
                    proxy=proxy_for_request(use_proxy),
                ) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        body = await resp.text()
                        raise LLMError(f"Kupi ({resp.status}): {body[:200]}")
                    if resp.status != 200:
                        err = data.get("error", {})
                        msg = err.get("message", str(data)) if isinstance(err, dict) else str(data)
                        raise LLMError(f"Kupi ({resp.status}): {msg}")
                    return data
        except LLMError:
            raise
        except asyncio.TimeoutError as e:
            last_err = e
        except ClientConnectorError as e:
            last_err = e
        except ClientError as e:
            last_err = e

    if isinstance(last_err, asyncio.TimeoutError):
        raise LLMError(f"Таймаут KupiAPI ({timeout_sec} сек)") from last_err
    if last_err:
        raise LLMError(f"KupiAPI: {format_client_error(last_err)}") from last_err
    raise LLMError("KupiAPI недоступен")


def _text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Kupi: пустой ответ")
    text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise LLMError("Kupi: пустой текст")
    return text.strip()


async def chat(
    user_prompt: str,
    *,
    system: str,
    model: str,
    temperature: float = 0.8,
) -> str:
    payload = {
        "model": _normalize_model(model),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    return _text(await _post(payload, timeout_sec=_CHAT_TIMEOUT))


async def vision(
    user_text: str,
    image_data_url: str,
    *,
    system: str,
    temperature: float = 0.3,
) -> str:
    payload = {
        "model": _normalize_model(VISION_MODEL),
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
    }
    return _text(await _post(payload, timeout_sec=_VISION_TIMEOUT))
