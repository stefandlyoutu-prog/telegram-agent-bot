"""Google Cloud (ADC): Speech, TTS, Vision, Translation."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def gcp_configured() -> bool:
    from bot.config import GCP_PROJECT_ID, GCP_SPEECH_ENABLED

    if not GCP_SPEECH_ENABLED or not GCP_PROJECT_ID:
        return False
    return adc_available()


def gcp_tts_configured() -> bool:
    from bot.config import GCP_TTS_ENABLED

    return GCP_TTS_ENABLED and gcp_configured()


def adc_available() -> bool:
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if creds_path and Path(creds_path).is_file():
        return True
    adc_default = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc_default.is_file()


def setup_hint() -> str:
    return (
        "Google Cloud (ADC) не настроен.\n\n"
        "1. Установите Google Cloud SDK (gcloud).\n"
        "2. На Mac, где запущен бот:\n"
        "   gcloud auth application-default login\n"
        "3. Включите API:\n"
        "   gcloud services enable speech.googleapis.com texttospeech.googleapis.com "
        "vision.googleapis.com translate.googleapis.com\n"
        "4. В .env:\n"
        "   GCP_PROJECT_ID=ваш-project-id\n"
        "   GCP_SPEECH_ENABLED=1\n"
        "   GCP_TTS_ENABLED=1\n"
    )


async def check_gcp_speech() -> Tuple[bool, str]:
    if not gcp_configured():
        if not adc_available():
            return False, "ADC не найден (gcloud auth application-default login)"
        from bot.config import GCP_PROJECT_ID

        if not GCP_PROJECT_ID:
            return False, "GCP_PROJECT_ID не задан в .env"
        return False, "GCP_SPEECH_ENABLED=0"

    try:
        await asyncio.get_event_loop().run_in_executor(None, _ping_speech_recognize)
        return True, "Speech-to-Text API включён"
    except ImportError:
        return False, "pip install google-cloud-speech"
    except Exception as e:
        if _service_disabled(e):
            await asyncio.get_event_loop().run_in_executor(None, ensure_gcp_apis_enabled)
            return False, "Speech API выключен — включение запрошено, повторите через 2–5 мин"
        return False, str(e)[:120]


async def check_gcp_tts() -> Tuple[bool, str]:
    if not gcp_tts_configured():
        return False, "GCP TTS выключен или нет ADC"
    try:
        await asyncio.get_event_loop().run_in_executor(None, _ping_tts_client)
        return True, "Text-to-Speech готов"
    except ImportError:
        return False, "pip install google-cloud-texttospeech"
    except Exception as e:
        return False, str(e)[:120]


def _speech_client():
    from google.cloud import speech

    return speech.SpeechClient(transport="rest")


def _ping_speech_client() -> None:
    _ping_speech_recognize()


def _ping_speech_recognize() -> None:
    """Проверка, что Speech API включён (не только создание клиента)."""
    from google.cloud import speech

    client = _speech_client()
    audio = speech.RecognitionAudio(content=b"\x00" * 64)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        sample_rate_hertz=48000,
        language_code="ru-RU",
    )
    client.recognize(config=config, audio=audio, timeout=12)


def _service_disabled(err: Exception) -> bool:
    text = str(err).lower()
    return "service_disabled" in text or "has not been used" in text or "it is disabled" in text


def ensure_gcp_apis_enabled() -> None:
    """Включить Speech/TTS API в проекте (один раз при ADC)."""
    import subprocess

    from bot.config import GCP_PROJECT_ID

    if not GCP_PROJECT_ID or not adc_available():
        return
    apis = ("speech.googleapis.com", "texttospeech.googleapis.com")
    try:
        from google.cloud import serviceusage_v1

        client = serviceusage_v1.ServiceUsageClient()
        parent = f"projects/{GCP_PROJECT_ID}"
        for api in apis:
            name = f"{parent}/services/{api}"
            try:
                client.enable_service(request={"name": name})
                logger.info("GCP API enable requested: %s", api)
            except Exception as e:
                if "already enabled" not in str(e).lower():
                    logger.debug("enable %s: %s", api, e)
        return
    except ImportError:
        pass
    except Exception as e:
        logger.debug("serviceusage client: %s", e)

    try:
        subprocess.run(
            [
                "gcloud",
                "services",
                "enable",
                *apis,
                f"--project={GCP_PROJECT_ID}",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        logger.info("gcloud services enable requested for %s", ", ".join(apis))
    except FileNotFoundError:
        logger.debug("gcloud не найден — включите Speech API вручную в консоли GCP")
    except Exception as e:
        logger.warning("ensure_gcp_apis_enabled: %s", e)


def _tts_client():
    from google.cloud import texttospeech

    return texttospeech.TextToSpeechClient(transport="rest")


def _ping_tts_client() -> None:
    _tts_client()


def stt_available() -> bool:
    """Есть хотя бы один канал распознавания голоса."""
    from bot.config import (
        GCP_STT_GEMINI_FALLBACK,
        GCP_STT_KUPI_FALLBACK,
        GEMINI_API_KEY,
        LLM_API_KEY,
    )

    if gcp_configured():
        return True
    if GCP_STT_KUPI_FALLBACK and LLM_API_KEY:
        return True
    return bool(GCP_STT_GEMINI_FALLBACK and GEMINI_API_KEY)


async def transcribe_telegram_audio(
    audio_bytes: bytes,
    *,
    mime_hint: str = "audio/ogg",
    language_code: str | None = None,
) -> str:
    from bot.config import GCP_SPEECH_LANGUAGE, GCP_SPEECH_TIMEOUT_SEC

    if not stt_available():
        raise RuntimeError(setup_hint())

    lang = language_code or GCP_SPEECH_LANGUAGE
    loop = asyncio.get_event_loop()
    deadline = GCP_SPEECH_TIMEOUT_SEC + 15
    errors: list[str] = []

    if gcp_configured():
        await loop.run_in_executor(None, ensure_gcp_apis_enabled)
        try:
            text = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _transcribe_sync(
                        audio_bytes, mime_hint=mime_hint, language_code=lang
                    ),
                ),
                timeout=deadline,
            )
            if text:
                return text
            errors.append("Google Speech: пустой результат")
        except asyncio.TimeoutError:
            logger.warning("Google Speech timeout (%ss)", deadline)
            errors.append("Google Speech: таймаут")
        except Exception as e:
            logger.warning("Google Speech failed: %s", e)
            errors.append(f"Google Speech: {e}")
            if _service_disabled(e):
                await loop.run_in_executor(None, ensure_gcp_apis_enabled)
                errors.append("Speech API включается — повторите через 2–5 мин")

    text = await _transcribe_kupiapi_whisper(audio_bytes, mime_hint)
    if text:
        return text
    errors.append("KupiAPI Whisper: не распознано")

    text = await _transcribe_gemini_fallback(audio_bytes, mime_hint)
    if text:
        return text
    errors.append("Gemini STT: недоступен")

    detail = errors[-1] if errors else "неизвестная ошибка"
    raise RuntimeError(
        f"Не удалось распознать голос ({detail}). "
        "Попробуйте ещё раз или напишите текстом."
    )


def _transcribe_sync(
    audio_bytes: bytes,
    *,
    mime_hint: str,
    language_code: str,
) -> str:
    from google.cloud import speech
    from bot.config import GCP_SPEECH_TIMEOUT_SEC

    client = _speech_client()
    audio = speech.RecognitionAudio(content=audio_bytes)
    req_timeout = float(GCP_SPEECH_TIMEOUT_SEC)

    configs = []
    for rate in (48000, 24000, 16000, 12000):
        configs.append(
            speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=rate,
                audio_channel_count=1,
                language_code=language_code,
                alternative_language_codes=["en-US"],
                enable_automatic_punctuation=True,
                model="latest_short",
            )
        )

    last_err: Optional[Exception] = None
    for config in configs:
        try:
            response = client.recognize(
                config=config, audio=audio, timeout=req_timeout
            )
            parts = []
            for result in response.results:
                if result.alternatives:
                    parts.append(result.alternatives[0].transcript.strip())
            text = " ".join(p for p in parts if p).strip()
            if text:
                logger.info(
                    "Speech OK (%s Hz): %s",
                    config.sample_rate_hertz,
                    text[:80],
                )
                return text
        except Exception as e:
            last_err = e
            logger.warning("Speech %s Hz: %s", config.sample_rate_hertz, e)

    if last_err:
        if _service_disabled(last_err):
            ensure_gcp_apis_enabled()
        raise RuntimeError(f"Google Speech: {last_err}") from last_err
    raise RuntimeError("Google Speech: пустой результат")


def _external_aiohttp_session():
    import aiohttp

    from bot.config import TELEGRAM_PROXY

    if TELEGRAM_PROXY and str(TELEGRAM_PROXY).startswith(("socks4", "socks5")):
        from aiohttp_socks import ProxyConnector

        return aiohttp.ClientSession(
            connector=ProxyConnector.from_url(TELEGRAM_PROXY, rdns=True)
        )
    return aiohttp.ClientSession()


async def _transcribe_kupiapi_whisper(audio_bytes: bytes, mime_hint: str) -> str:
    from bot.config import (
        GCP_STT_KUPI_FALLBACK,
        GCP_STT_KUPI_MODEL,
        GCP_SPEECH_LANGUAGE,
        LLM_API_KEY,
        LLM_BASE_URL,
    )
    from bot.services.http_client import llm_connection_modes, session_kwargs

    if not GCP_STT_KUPI_FALLBACK or not LLM_API_KEY:
        return ""

    import aiohttp

    ext = "ogg" if "ogg" in mime_hint else "mp3"
    lang = (GCP_SPEECH_LANGUAGE or "ru-RU").split("-")[0]
    url = f"{LLM_BASE_URL}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}

    for use_proxy in llm_connection_modes():
        data = aiohttp.FormData()
        data.add_field(
            "file",
            audio_bytes,
            filename=f"voice.{ext}",
            content_type=mime_hint if mime_hint.startswith("audio/") else "audio/ogg",
        )
        data.add_field("model", GCP_STT_KUPI_MODEL)
        data.add_field("language", lang)
        try:
            async with aiohttp.ClientSession(**session_kwargs(use_proxy)) as session:
                async with session.post(
                    url,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.warning(
                            "Kupi Whisper (%s): %s %s",
                            "proxy" if use_proxy else "direct",
                            resp.status,
                            body[:200],
                        )
                        continue
                    try:
                        import json

                        parsed = json.loads(body)
                        text = (parsed.get("text") or "").strip()
                    except Exception:
                        text = body.strip()
                    if text:
                        logger.info("STT Kupi Whisper: %s", text[:80])
                        return text
        except Exception as e:
            logger.warning("Kupi Whisper: %s", e)
    return ""


async def _transcribe_gemini_fallback(audio_bytes: bytes, mime_hint: str) -> str:
    from bot.config import GCP_STT_GEMINI_FALLBACK, GEMINI_API_KEY

    if not GCP_STT_GEMINI_FALLBACK or not GEMINI_API_KEY:
        return ""

    import base64

    import aiohttp

    mime = mime_hint if mime_hint.startswith("audio/") else "audio/ogg"
    b64 = base64.standard_b64encode(audio_bytes).decode("ascii")
    prompt = (
        "Распознай речь на этом голосовом. Верни только текст на русском, без пояснений."
    )
    last_err = ""
    async with _external_aiohttp_session() as session:
        for model in ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"):
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                }]
            }
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-goog-api-key": GEMINI_API_KEY,
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        last_err = str(data)[:200]
                        continue
                    for cand in data.get("candidates") or []:
                        for part in (cand.get("content") or {}).get("parts") or []:
                            t = (part.get("text") or "").strip()
                            if t:
                                logger.info("STT Gemini (%s): %s", model, t[:80])
                                return t
            except Exception as e:
                last_err = str(e)
                logger.warning("Gemini STT %s: %s", model, e)
    if last_err:
        logger.warning("Gemini STT failed: %s", last_err)
    return ""


def _strip_for_tts(text: str, *, max_len: int = 1200) -> str:
    t = re.sub(r"```[\s\S]*?```", "", text)
    t = re.sub(r"\[.*?\]\(.*?\)", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[#*_`]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        cut = t[:max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        t = cut + "…"
    return t


RUSSIAN_TTS_VOICES: list[tuple[str, str]] = [
    ("ru-RU-Chirp3-HD-Charon", "мужской, HD — по умолчанию в боте"),
    ("ru-RU-Chirp3-HD-Orus", "мужской, HD"),
    ("ru-RU-Chirp3-HD-Fenrir", "мужской, HD"),
    ("ru-RU-Chirp3-HD-Puck", "нейтральный, HD"),
    ("ru-RU-Chirp3-HD-Kore", "женский, HD"),
    ("ru-RU-Chirp3-HD-Leda", "женский, HD"),
    ("ru-RU-Chirp3-HD-Aoede", "женский, HD"),
    ("ru-RU-Chirp3-HD-Zephyr", "нейтральный, HD"),
    ("ru-RU-Wavenet-A", "женский, Wavenet (старый)"),
    ("ru-RU-Wavenet-B", "мужской, Wavenet"),
    ("ru-RU-Wavenet-C", "женский, Wavenet"),
    ("ru-RU-Wavenet-D", "мужской, Wavenet"),
    ("ru-RU-Wavenet-E", "женский, Wavenet"),
    ("ru-RU-Standard-A", "женский, базовый"),
    ("ru-RU-Standard-B", "мужской, базовый"),
    ("ru-RU-Standard-C", "женский, базовый"),
    ("ru-RU-Standard-D", "мужской, базовый"),
]


def format_tts_voice_list() -> str:
    lines = ["<b>Голоса озвучки (ru-RU)</b>", ""]
    for name, hint in RUSSIAN_TTS_VOICES:
        lines.append(f"• <code>{name}</code> — {hint}")
    lines.append("")
    lines.append(
        "Сменить: <code>/voice set ru-RU-Wavenet-A</code>\n"
        "Или в .env: <code>GCP_TTS_VOICE=…</code> (для всех, если не задан /voice set)"
    )
    return "\n".join(lines)


async def synthesize_speech_ogg(text: str, *, user_id: int | None = None) -> bytes:
    """Текст → OGG Opus для Telegram voice."""
    from bot.config import GCP_TTS_LANGUAGE, GCP_TTS_VOICE

    if not gcp_tts_configured():
        raise RuntimeError("GCP Text-to-Speech не настроен")

    voice = GCP_TTS_VOICE
    if user_id is not None:
        from bot.services.user_prefs import get_tts_voice

        voice = await get_tts_voice(user_id)

    clean = _strip_for_tts(text)
    if not clean:
        raise RuntimeError("Пустой текст для озвучки")

    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(
            None,
            lambda: _synthesize_sync(clean, voice=voice, language=GCP_TTS_LANGUAGE),
        ),
        timeout=90,
    )


def _synthesize_sync(text: str, *, voice: str, language: str) -> bytes:
    from google.cloud import texttospeech

    client = _tts_client()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code=language,
        name=voice,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
        speaking_rate=1.0,
        pitch=0.0,
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )
    if not response.audio_content:
        raise RuntimeError("TTS: пустой ответ")
    return response.audio_content


async def vision_ocr_image(image_bytes: bytes) -> str:
    """OCR через Cloud Vision (запасной канал)."""
    from bot.config import GCP_VISION_ENABLED

    if not GCP_VISION_ENABLED or not adc_available():
        raise RuntimeError("GCP Vision выключен")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _vision_ocr_sync(image_bytes))


def _vision_ocr_sync(image_bytes: bytes) -> str:
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)
    texts = response.text_annotations
    if not texts:
        return ""
    return (texts[0].description or "").strip()


async def translate_text(text: str, *, target: str | None = None) -> str:
    from bot.config import GCP_TRANSLATE_ENABLED, GCP_TRANSLATE_TARGET

    if not GCP_TRANSLATE_ENABLED or not adc_available():
        return text
    tgt = target or GCP_TRANSLATE_TARGET
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: _translate_sync(text, target_language=tgt)
    )


def _translate_sync(text: str, *, target_language: str) -> str:
    from google.cloud import translate_v2 as translate

    client = translate.Client()
    result = client.translate(text, target_language=target_language)
    if isinstance(result, dict):
        return result.get("translatedText") or text
    return text


async def check_gcp_all() -> list[tuple[str, bool, str]]:
    rows = []
    ok, d = await check_gcp_speech()
    rows.append(("Speech-to-Text", ok, d))
    ok, d = await check_gcp_tts()
    rows.append(("Text-to-Speech", ok, d))
    try:
        from bot.config import GCP_VISION_ENABLED

        if GCP_VISION_ENABLED and adc_available():
            from google.cloud import vision

            vision.ImageAnnotatorClient()
            rows.append(("Cloud Vision", True, "готов"))
        else:
            rows.append(("Cloud Vision", False, "выключен"))
    except ImportError:
        rows.append(("Cloud Vision", False, "pip install google-cloud-vision"))
    except Exception as e:
        rows.append(("Cloud Vision", False, str(e)[:80]))
    try:
        from bot.config import GCP_TRANSLATE_ENABLED

        if GCP_TRANSLATE_ENABLED and adc_available():
            from google.cloud import translate_v2 as translate

            translate.Client()
            rows.append(("Translation", True, "готов"))
        else:
            rows.append(("Translation", False, "выключен"))
    except ImportError:
        rows.append(("Translation", False, "pip install google-cloud-translate"))
    except Exception as e:
        rows.append(("Translation", False, str(e)[:80]))
    return rows


def gcp_services_overview() -> str:
    return (
        "<b>Google Cloud в боте</b>\n\n"
        "✅ <b>Голосовые вход</b> — Speech-to-Text (🎤 → текст)\n"
        "✅ <b>Голосовые ответы</b> — Text-to-Speech (текст → 🎤)\n"
        "✅ <b>Vision OCR</b> — текст с фото (запасной канал)\n"
        "✅ <b>Translation</b> — перевод при необходимости\n\n"
        "/autopilot — не спрашивать принтер, сразу делать задачи\n"
        "/voice — вкл/выкл ответ голосом"
    )
