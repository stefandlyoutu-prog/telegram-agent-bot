"""Ответ голосом через Google Text-to-Speech."""

from __future__ import annotations

import logging
import re

from aiogram.types import BufferedInputFile, Message

logger = logging.getLogger(__name__)

_VOICE_REQUEST = re.compile(
    r"(?:"
    r"ответ(?:ь|ьте)?\s+(?:мне\s+)?голосом|"
    r"голосов(?:ым|ое)\s+(?:сообщени|ответ)|"
    r"озвуч(?:ь|и|ите)|"
    r"скажи\s+голосом|"
    r"пришли\s+голосом|"
    r"отправь\s+голосом|"
    r"tts|"
    r"text[\s-]?to[\s-]?speech"
    r")",
    re.I,
)

_TTS_WRAPPER = re.compile(
    r"^[\s*]*текст\s+для\s+озвучки\s*:?\s*",
    re.I,
)


def strip_voice_request_phrases(user_text: str) -> tuple[str, bool]:
    """Убрать просьбу «голосом» из запроса к модели; флаг — нужна озвучка."""
    raw = (user_text or "").strip()
    if not raw:
        return raw, False
    want = wants_voice_reply(raw)
    cleaned = _VOICE_REQUEST.sub(" ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;—-")
    if not cleaned:
        return raw, want
    return cleaned, want


def prepare_text_for_tts(reply: str) -> str:
    """Текст для Google TTS — без обёрток «текст для озвучки» от модели."""
    t = (reply or "").strip()
    t = _TTS_WRAPPER.sub("", t).strip()
    if (t.startswith("«") and t.endswith("»")) or (
        t.startswith('"') and t.endswith('"')
    ):
        t = t[1:-1].strip()
    return t


_VOICE_ONLY = re.compile(
    r"^(?:"
    r"(?:и\s+)?(?:тоже|ещё|еще)\s+)?"
    r"(?:ответ(?:ь|ьте)?\s+(?:мне\s+)?голосом|"
    r"озвуч(?:ь|и|ите)(?:\s+ответ)?|"
    r"голосов(?:ым|ое)\s+сообщени(?:е|ем)?|"
    r"пришли\s+голосом|"
    r"скажи\s+голосом)"
    r"[.!?\s]*$",
    re.I,
)


def wants_voice_reply(user_text: str) -> bool:
    return bool(_VOICE_REQUEST.search(user_text or ""))


def is_voice_only_request(user_text: str) -> bool:
    """Пользователь просит озвучить предыдущий ответ, без новой задачи."""
    t = (user_text or "").strip()
    if not t or len(t) > 120:
        return False
    return bool(_VOICE_ONLY.match(t))


async def send_voice_reply(
    message: Message,
    text: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """Отправить голосовое. force=True — без проверки настройки /voice."""
    if not message.from_user:
        return False, "нет пользователя"
    from bot.services.user_prefs import get_voice_reply

    if not force and not await get_voice_reply(message.from_user.id):
        return False, "ответ голосом выключен (/voice on)"

    clean = prepare_text_for_tts(text)
    if not clean:
        return False, "пустой текст для озвучки"

    try:
        from bot.services.google_cloud import gcp_tts_configured, synthesize_speech_ogg

        if not gcp_tts_configured():
            return False, "Google TTS не настроен (GCP_TTS_ENABLED, ADC)"
        ogg = await synthesize_speech_ogg(clean, user_id=message.from_user.id)
        await message.answer_voice(
            BufferedInputFile(ogg, filename="reply.ogg"),
        )
        return True, ""
    except Exception as e:
        logger.warning("Voice reply failed: %s", e)
        return False, str(e)[:400]


async def maybe_send_voice_reply(
    message: Message,
    text: str,
    *,
    force: bool = False,
) -> bool:
    ok, _ = await send_voice_reply(message, text, force=force)
    return ok


async def last_assistant_text(user_id: int) -> str:
    from bot.services import history

    past = await history.get_history(user_id)
    for msg in reversed(past):
        if msg.get("role") == "assistant":
            content = (msg.get("content") or "").strip()
            if content and not content.startswith("Отправлен "):
                return content
    return ""
