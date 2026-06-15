"""Голосовые сообщения → Google Speech-to-Text → ответ бота."""

from __future__ import annotations

import io
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router()


async def _download_voice(bot: Bot, message: Message) -> tuple[bytes, str]:
    from bot.services.telegram_net import format_telegram_error, telegram_retry

    if message.voice:
        fid = message.voice.file_id
        mime = "audio/ogg"
    elif message.audio:
        fid = message.audio.file_id
        mime = message.audio.mime_type or "audio/mpeg"
    else:
        raise RuntimeError("Нет аудио в сообщении")

    tg_file = await telegram_retry("get_file", lambda: bot.get_file(fid))
    if not tg_file.file_path:
        raise RuntimeError("Telegram не вернул путь к файлу")

    buf = io.BytesIO()
    await telegram_retry(
        "download_file",
        lambda: bot.download_file(tg_file.file_path, buf),
    )
    data = buf.getvalue()
    if not data:
        raise RuntimeError("Пустой аудиофайл")
    return data, mime


@router.message(F.voice | F.audio)
async def on_voice(message: Message, bot: Bot) -> None:
    import asyncio

    from bot.handlers.chat_logic import reply_with_llm
    from bot.services.google_cloud import (
        setup_hint,
        stt_available,
        transcribe_telegram_audio,
    )
    from bot.services.processing import clear_busy, is_user_busy, set_busy

    user_id = message.from_user.id if message.from_user else 0
    logger.info("Voice message from user %s", user_id)

    if is_user_busy(user_id):
        await message.answer("⏳ Подождите — ещё обрабатываю предыдущий запрос.")
        return

    if not stt_available():
        await message.answer(setup_hint())
        return

    set_busy(user_id, "голос")
    status = await message.answer("🎤 Распознаю речь…")
    try:
        try:
            audio_bytes, mime = await _download_voice(bot, message)
            logger.info("Voice downloaded: %s bytes, mime=%s", len(audio_bytes), mime)
            text = await asyncio.wait_for(
                transcribe_telegram_audio(audio_bytes, mime_hint=mime),
                timeout=90,
            )
        except asyncio.TimeoutError:
            await status.edit_text(
                "🔴 Распознавание заняло слишком долго. Напишите текстом или повторите 🎤."
            )
            return
        except Exception as e:
            logger.exception("Voice STT failed: %s", e)
            err = str(e)[:900]
            try:
                await status.edit_text(f"🔴 Голос: {escape(err)}", parse_mode="HTML")
            except Exception:
                await message.answer(f"🔴 Голос: {err}")
            return

        if not (text or "").strip():
            await status.edit_text("🔴 Речь не распознана. Повторите громче или напишите текстом.")
            return

        cap = (message.caption or "").strip()
        combined = f"{cap}\n{text}".strip() if cap else text
        preview = escape(combined[:900])
        try:
            await status.edit_text(
                f"🎤 Распознано:\n<i>{preview}</i>\n\n⏳ Отвечаю…",
                parse_mode="HTML",
            )
        except Exception:
            await message.answer("🎤 Распознано. Отвечаю…")

        try:
            await reply_with_llm(message, combined, phase="голос")
        except Exception as e:
            logger.exception("Voice reply failed: %s", e)
            await message.answer(
                f"🔴 Не удалось ответить после распознавания: {escape(str(e)[:500])}"
            )
    finally:
        clear_busy(user_id)
