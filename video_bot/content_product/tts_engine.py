"""Озвучка: polish через Gemini + Google TTS / edge-tts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path

from video_bot.tts import DEFAULT_VOICE, synthesize_speech

from video_bot.content_product.voice_rules import normalize_voice_text

logger = logging.getLogger(__name__)

FFMPEG = None


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _basic_clean(text: str) -> str:
    return normalize_voice_text(text)


_POLISH_DISABLED = False


async def polish_voice_text(text: str) -> str:
    """LLM-правка под TTS (числа словами, без англицизмов, омографы)."""
    global _POLISH_DISABLED
    clean = _basic_clean(text)
    if _POLISH_DISABLED or os.getenv("VIDEO_TTS_POLISH", "1") in ("0", "false"):
        return clean
    try:
        from oracle_bot.llm_helpers import oracle_chat_with_system
        from video_bot.content_product.prompts import TTS_POLISH_PROMPT

        out = await oracle_chat_with_system(
            TTS_POLISH_PROMPT.format(text=clean),
            system="Ты редактор озвучки. Верни только исправленный текст, без пояснений.",
            temperature=0.3,
            max_tokens=800,
        )
        polished = out.strip().strip('"').strip("'")
        if len(polished) > 10:
            return polished
    except Exception as e:
        logger.debug("TTS polish off: %s", e)
        _POLISH_DISABLED = True
    return clean


def _ogg_to_mp3(ogg: Path, mp3: Path) -> Path:
    subprocess.run(
        [_ffmpeg(), "-y", "-i", str(ogg), "-ac", "1", "-ar", "44100", str(mp3)],
        check=True,
        capture_output=True,
    )
    return mp3


_TTS_INSTRUCTIONS = (
    "Говори по-русски с идеально чистым произношением, спокойно и уверенно, "
    "как рассказчик мистических историй: тёплый, чуть загадочный тон, "
    "выразительные паузы на точках, без спешки и без театральности."
)


def _openai_tts(text: str, out_mp3: Path) -> bool:
    """Основной голос: OpenAI TTS (платный ключ, самое чистое произношение)."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key or "openai.com" not in base:
        return False
    import time

    import requests

    last_err: Exception | None = None
    for attempt in range(3):  # urllib3+LibreSSL иногда рвёт соединение — ретраим
        try:
            r = requests.post(
                f"{base}/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("VIDEO_TTS_MODEL", "gpt-4o-mini-tts"),
                    "voice": os.getenv("VIDEO_TTS_VOICE", "onyx"),
                    "input": text,
                    "instructions": _TTS_INSTRUCTIONS,
                    "response_format": "mp3",
                    "speed": 1.0,
                },
                timeout=120,
            )
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI TTS {r.status_code}: {r.text[:200]}")
            out_mp3.write_bytes(r.content)
            return True
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"OpenAI TTS после ретраев: {last_err}")


async def synthesize_voice_mp3(text: str, out_mp3: Path) -> Path:
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    polished = await polish_voice_text(text)

    # OpenAI TTS — приоритет: самое естественное и чистое русское произношение
    try:
        if await asyncio.to_thread(_openai_tts, polished, out_mp3):
            return out_mp3
    except Exception as e:
        logger.warning("OpenAI TTS fallback to GCP/edge: %s", e)

    # Google Cloud TTS (лучшие ударения)
    try:
        from bot.services.google_cloud import gcp_tts_configured, synthesize_speech_ogg

        if gcp_tts_configured():
            ogg_bytes = await synthesize_speech_ogg(polished)
            ogg = out_mp3.with_suffix(".ogg")
            ogg.write_bytes(ogg_bytes)
            _ogg_to_mp3(ogg, out_mp3)
            ogg.unlink(missing_ok=True)
            return out_mp3
    except Exception as e:
        logger.info("GCP TTS fallback to edge: %s", e)

    # edge-tts — Svetlana часто естественнее для продающих Shorts
    synthesize_speech(
        polished,
        out_mp3,
        voice="ru-RU-SvetlanaNeural",
        rate="+2%",
        pitch="-1Hz",
    )
    return out_mp3


def synthesize_voice_mp3_sync(text: str, out_mp3: Path) -> Path:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(synthesize_voice_mp3(text, out_mp3))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(synthesize_voice_mp3(text, out_mp3))).result()
