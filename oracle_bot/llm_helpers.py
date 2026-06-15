"""LLM для Оракула: Groq → Kupi → Gemini."""

from __future__ import annotations

import asyncio
import logging
import os

from bot.config import DEFAULT_MODEL, VISION_DESCRIBE_PROMPT, VISION_SYSTEM_PROMPT
from bot.services.gemini_llm import (
    gemini_chat_completion,
    gemini_llm_configured,
    gemini_vision_completion,
)
from bot.services.llm import LLMError
from bot.services.vision import detect_mime, to_data_url
from oracle_bot.config import ORACLE_LLM_MODEL
from oracle_bot.groq_client import chat as groq_chat
from oracle_bot.groq_client import groq_configured
from oracle_bot.groq_client import vision as groq_vision
from oracle_bot.kupi_direct import chat as kupi_chat
from oracle_bot.kupi_direct import vision as kupi_vision
from oracle_bot.prompts import ORACLE_SYSTEM, PALM_USER, FULL_ONLY, SPLIT_INSTRUCTION

logger = logging.getLogger(__name__)

_LLM_SEM = asyncio.Semaphore(int(os.getenv("ORACLE_LLM_CONCURRENCY", "20")))

_PALM_VISION_PROMPT = (
    "Опиши ладонь на фото для хироманта: форма ладони, основные линии "
    "(жизни, сердца, ума, судьбы), холмы, особые знаки. Только наблюдаемое."
)


async def oracle_chat(user_prompt: str, *, temperature: float = 0.8) -> str:
    async with _LLM_SEM:
        return await _oracle_chat_inner(user_prompt, temperature=temperature)


async def _oracle_chat_inner(user_prompt: str, *, temperature: float = 0.8) -> str:
    errors: list[str] = []

    if groq_configured():
        try:
            return await groq_chat(
                user_prompt,
                system=ORACLE_SYSTEM,
                temperature=temperature,
            )
        except Exception as e:
            errors.append(f"Groq: {e}")
            logger.warning("oracle groq chat: %s", e)

    try:
        return await kupi_chat(
            user_prompt,
            system=ORACLE_SYSTEM,
            model=ORACLE_LLM_MODEL or DEFAULT_MODEL,
            temperature=temperature,
        )
    except Exception as e:
        errors.append(f"Kupi: {e}")
        logger.warning("oracle kupi chat: %s", e)

    if gemini_llm_configured():
        try:
            return await gemini_chat_completion(
                [{"role": "user", "content": user_prompt}],
                system=ORACLE_SYSTEM,
                temperature=temperature,
                timeout_sec=90,
            )
        except Exception as e:
            errors.append(f"Gemini: {e}")

    hint = errors[-1] if errors else "нет провайдеров"
    raise LLMError(f"Оракул временно недоступен. {hint}")


async def oracle_reading(
    user_prompt: str,
    *,
    premium: bool,
    temperature: float = 0.8,
) -> str:
    fmt = FULL_ONLY if premium else SPLIT_INSTRUCTION
    return await oracle_chat(f"{user_prompt}\n\n{fmt}", temperature=temperature)


async def _vision_facts(image_data: bytes) -> str:
    data_url = to_data_url(image_data, detect_mime(image_data))
    errors: list[str] = []

    if groq_configured():
        try:
            text = await groq_vision(
                _PALM_VISION_PROMPT,
                data_url,
                system=VISION_SYSTEM_PROMPT,
                temperature=0.3,
            )
            if text.strip():
                return text
        except Exception as e:
            errors.append(f"Groq: {e}")
            logger.warning("oracle groq vision: %s", e)

    try:
        text = await kupi_vision(
            VISION_DESCRIBE_PROMPT,
            data_url,
            system=VISION_SYSTEM_PROMPT,
            temperature=0.3,
        )
        if text.strip():
            return text
    except Exception as e:
        errors.append(f"Kupi: {e}")
        logger.warning("oracle kupi vision: %s", e)

    if gemini_llm_configured():
        try:
            text = await gemini_vision_completion(
                VISION_DESCRIBE_PROMPT,
                data_url,
                system=VISION_SYSTEM_PROMPT,
                temperature=0.3,
                timeout_sec=90,
            )
            if text.strip():
                return text
        except Exception as e:
            errors.append(f"Gemini: {e}")

    hint = errors[-1] if errors else "нет vision"
    raise LLMError(f"Не разобрал фото ладони. {hint}")


async def oracle_palm_reading(
    image_data: bytes,
    comment: str = "",
    *,
    premium: bool = False,
) -> str:
    facts = await _vision_facts(image_data)
    return await oracle_reading(
        PALM_USER.format(facts=facts, comment=comment or "—"),
        premium=premium,
        temperature=0.75,
    )
