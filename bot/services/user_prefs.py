"""Настройки пользователя: автопилот без опросников, ответ голосом."""

from __future__ import annotations

from bot.config import DEFAULT_AUTO_PROCEED


async def get_auto_proceed(user_id: int) -> bool:
    from bot.services.history import get_user_pref

    val = await get_user_pref(user_id, "auto_proceed")
    if val is None:
        return DEFAULT_AUTO_PROCEED
    return val in (1, "1", True, "true")


async def set_auto_proceed(user_id: int, enabled: bool) -> None:
    from bot.services.history import set_user_pref

    await set_user_pref(user_id, "auto_proceed", 1 if enabled else 0)


async def get_voice_reply(user_id: int) -> bool:
    from bot.config import GCP_TTS_ENABLED
    from bot.services.history import get_user_pref

    if not GCP_TTS_ENABLED:
        return False
    val = await get_user_pref(user_id, "voice_reply")
    if val is None:
        return True
    return val in (1, "1", True, "true")


async def set_voice_reply(user_id: int, enabled: bool) -> None:
    from bot.services.history import set_user_pref

    await set_user_pref(user_id, "voice_reply", 1 if enabled else 0)


async def get_tts_voice(user_id: int) -> str:
    from bot.config import GCP_TTS_VOICE
    from bot.services.history import get_user_pref

    val = await get_user_pref(user_id, "tts_voice")
    if val and isinstance(val, str) and val.strip():
        return val.strip()
    return GCP_TTS_VOICE


async def set_tts_voice(user_id: int, voice_name: str) -> None:
    from bot.services.history import set_user_pref

    await set_user_pref(user_id, "tts_voice", voice_name.strip())


async def should_skip_questionnaire(user_id: int) -> bool:
    """Не показывать анкету принтера — сразу делать задачу."""
    return await get_auto_proceed(user_id)
