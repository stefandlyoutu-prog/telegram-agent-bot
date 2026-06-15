"""Gemini API fallback when KupiAPI (OpenAI-compatible proxy) is unavailable."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from bot.config import (
    GEMINI_API_KEY,
    GEMINI_CHAT_MODEL,
    GEMINI_VISION_MODEL,
    LLM_GEMINI_FALLBACK,
)

logger = logging.getLogger(__name__)


def gemini_llm_configured() -> bool:
    return bool(LLM_GEMINI_FALLBACK and GEMINI_API_KEY)


def _chat_models() -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for model in (
        GEMINI_CHAT_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
    ):
        if model and model not in seen:
            seen.add(model)
            out.append(model)
    return tuple(out)


def _vision_models() -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for model in (
        GEMINI_VISION_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
    ):
        if model and model not in seen:
            seen.add(model)
            out.append(model)
    return tuple(out)


def _session() -> aiohttp.ClientSession:
    from bot.services.google_cloud import _external_aiohttp_session

    return _external_aiohttp_session()


def _parse_data_url(url: str) -> Tuple[str, str]:
    match = re.match(r"data:([^;]+);base64,(.+)", url or "", re.I | re.S)
    if not match:
        return "image/jpeg", ""
    return match.group(1), match.group(2)


def openai_messages_to_gemini(
    messages: List[Dict[str, Any]],
    *,
    system: str = "",
) -> Tuple[Optional[dict], List[dict]]:
    """Convert OpenAI-style chat messages to Gemini systemInstruction + contents."""
    contents: list[dict] = []
    sys_parts = [system.strip()] if system and system.strip() else []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        if role == "system":
            if isinstance(content, str) and content.strip():
                sys_parts.append(content.strip())
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts: list[dict] = []
        if isinstance(content, str):
            if content.strip():
                parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    text = (block.get("text") or "").strip()
                    if text:
                        parts.append({"text": text})
                elif block.get("type") == "image_url":
                    url = (block.get("image_url") or {}).get("url", "")
                    mime, b64 = _parse_data_url(url)
                    if b64:
                        parts.append({"inline_data": {"mime_type": mime, "data": b64}})

        if not parts:
            continue
        if contents and contents[-1]["role"] == gemini_role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": gemini_role, "parts": parts})

    system_instruction = None
    if sys_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(sys_parts)}]}
    return system_instruction, contents


async def gemini_generate(
    *,
    system_instruction: Optional[dict],
    contents: List[dict],
    temperature: float = 0.7,
    models: Optional[tuple[str, ...]] = None,
    timeout_sec: int = 120,
) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY не задан")

    last_err = ""
    payload_base: dict = {"generationConfig": {"temperature": temperature}}
    if system_instruction:
        payload_base["systemInstruction"] = system_instruction

    async with _session() as session:
        for model in models or _chat_models():
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )
            payload = {**payload_base, "contents": contents}
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-goog-api-key": GEMINI_API_KEY,
                    },
                    timeout=aiohttp.ClientTimeout(total=timeout_sec),
                ) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        last_err = str(data)[:300]
                        logger.warning("Gemini %s HTTP %s: %s", model, resp.status, last_err)
                        continue
                    for cand in data.get("candidates") or []:
                        for part in (cand.get("content") or {}).get("parts") or []:
                            text = (part.get("text") or "").strip()
                            if text:
                                logger.info("Gemini fallback OK (%s)", model)
                                return text
                    last_err = "пустой ответ"
            except Exception as e:
                last_err = str(e)
                logger.warning("Gemini %s error: %s", model, e)

    raise RuntimeError(last_err or "Gemini не ответил")


async def gemini_chat_completion(
    messages: List[Dict[str, Any]],
    *,
    system: str = "",
    temperature: float = 0.7,
    timeout_sec: int = 120,
) -> str:
    system_instruction, contents = openai_messages_to_gemini(messages, system=system)
    if not contents:
        raise RuntimeError("Gemini: пустые сообщения")
    return await gemini_generate(
        system_instruction=system_instruction,
        contents=contents,
        temperature=temperature,
        models=_chat_models(),
        timeout_sec=timeout_sec,
    )


async def gemini_vision_completion(
    user_text: str,
    image_data_url: str,
    *,
    system: str = "",
    temperature: float = 0.5,
    timeout_sec: int = 75,
) -> str:
    mime, b64 = _parse_data_url(image_data_url)
    if not b64:
        raise RuntimeError("Gemini vision: некорректный data URL")

    parts = [{"text": user_text}, {"inline_data": {"mime_type": mime, "data": b64}}]
    system_instruction = {"parts": [{"text": system}]} if system else None
    return await gemini_generate(
        system_instruction=system_instruction,
        contents=[{"role": "user", "parts": parts}],
        temperature=temperature,
        models=_vision_models(),
        timeout_sec=timeout_sec,
    )


async def check_gemini_api() -> tuple[bool, str]:
    if not GEMINI_API_KEY:
        return False, "ключ не задан"
    try:
        text = await gemini_chat_completion(
            [{"role": "user", "content": "Ответь одним словом: OK"}],
            system="Короткий ответ.",
            temperature=0.0,
            timeout_sec=25,
        )
        if text.strip():
            return True, f"API отвечает ({GEMINI_CHAT_MODEL})"
        return False, "пустой ответ"
    except Exception as e:
        return False, str(e)[:120]
