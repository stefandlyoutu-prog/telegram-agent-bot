"""Голосовые сообщения в @MOracul_bot → STT → текущий сценарий."""

from __future__ import annotations

import asyncio
import io
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()


async def _download_voice(bot: Bot, message: Message) -> tuple[bytes, str]:
    from bot.services.telegram_net import telegram_retry

    if message.voice:
        fid = message.voice.file_id
        mime = "audio/ogg"
    elif message.audio:
        fid = message.audio.file_id
        mime = message.audio.mime_type or "audio/mpeg"
    else:
        raise RuntimeError("Нет аудио")

    tg_file = await telegram_retry("get_file", lambda: bot.get_file(fid))
    if not tg_file.file_path:
        raise RuntimeError("Нет пути к файлу")
    buf = io.BytesIO()
    await telegram_retry(
        "download_file",
        lambda: bot.download_file(tg_file.file_path, buf),
    )
    data = buf.getvalue()
    if not data:
        raise RuntimeError("Пустой файл")
    return data, mime


async def transcribe_message(message: Message) -> str | None:
    from bot.services.google_cloud import stt_available, transcribe_telegram_audio

    if not stt_available():
        return None
    audio, mime = await _download_voice(message.bot, message)
    text = await asyncio.wait_for(
        transcribe_telegram_audio(audio, mime_hint=mime),
        timeout=90,
    )
    cap = (message.caption or "").strip()
    return f"{cap}\n{text}".strip() if cap else (text or "").strip()


@router.message(F.voice | F.audio)
async def on_voice(message: Message, state: FSMContext) -> None:
    from bot.services.google_cloud import setup_hint, stt_available
    from oracle_bot.coach import coach_from_free_text
    from oracle_bot.handlers import dispatch_voice_text

    if not stt_available():
        await message.answer(
            "🎤 Голос пока недоступен (нет Speech API).\n"
            "Напиши текстом или настрой GCP в .env.\n\n" + setup_hint()[:400]
        )
        return

    wait = await message.answer("🎤 Слушаю…")
    try:
        text = await transcribe_message(message)
    except asyncio.TimeoutError:
        await wait.edit_text("Таймаут распознавания. Напиши текстом ✍️")
        return
    except Exception as e:
        logger.exception("oracle voice")
        await wait.edit_text(
            f"Не разобрал голос: {escape(str(e)[:200])}\n\nНапиши текстом или /menu"
        )
        return

    if not text:
        await wait.edit_text("Речь не распознана. Повтори или напиши текстом.")
        return

    preview = escape(text[:400])
    await wait.edit_text(f"🎤 <i>{preview}</i>", parse_mode="HTML")

    if await dispatch_voice_text(message, state, text):
        return

    from oracle_bot.dialogue import answer_followup, has_context

    uid = message.from_user.id if message.from_user else 0
    if has_context(uid) and await answer_followup(message, text):
        return

    await coach_from_free_text(message, text)
