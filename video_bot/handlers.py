"""@M_twotest_bot — генератор видео под песню или статью."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from video_bot.config import VIDEO_DATA_DIR
from video_bot.batch_factory import build_batch_from_brief
from video_bot.generate import build_article_video, build_lyrics_video

logger = logging.getLogger(__name__)
router = Router()


class Flow(StatesGroup):
    lyrics_title = State()
    lyrics_body = State()
    article_title = State()
    article_body = State()
    audio_wait = State()
    batch_brief = State()


def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Песня + слова", callback_data="vid:song"),
                InlineKeyboardButton(text="📚 Статья / факт", callback_data="vid:article"),
            ],
            [InlineKeyboardButton(text="🏭 Batch контент-завод", callback_data="vid:batch")],
            [InlineKeyboardButton(text="❓ Как это работает", callback_data="vid:help")],
        ]
    )


def _welcome() -> str:
    return (
        "🎬 <b>Video Maker</b>\n\n"
        "Сделаю вертикальное видео 9:16:\n"
        "• <b>Песня</b> — текст на экране (karaoke-стиль)\n"
        "• <b>Статья</b> — слайды с фактами (например: почему птицы летают)\n"
        "• <b>Batch</b> — «делай batch контент-завод» + бриф → серия faceless-роликов\n\n"
        "Озвучка нейросеть Dmitry + B-roll кадры + субтитры (стиль TikTok).\n"
        "Выбери режим ниже 👇"
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_welcome(), reply_markup=_kb_main())


@router.callback_query(F.data == "vid:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.message.answer(
        "📖 <b>Инструкция</b>\n\n"
        "<b>Песня:</b> название → текст по строкам (каждая строка = кадр ~3 сек)\n"
        "<b>Статья:</b> заголовок → текст абзацами\n\n"
        "Пример статьи:\n"
        "<i>Почему птицы летают</i>\n"
        "Птицы летают благодаря крыльям с аэродинамическим профилем…",
        reply_markup=_kb_main(),
    )
    await call.answer()


@router.callback_query(F.data == "vid:song")
async def cb_song(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.lyrics_title)
    await call.message.answer("🎵 Напиши <b>название</b> песни / трека")
    await call.answer()


@router.message(Flow.lyrics_title, F.text)
async def song_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:120])
    await state.set_state(Flow.lyrics_body)
    await message.answer(
        "Теперь пришли <b>текст песни</b> — каждая строка отдельно (Enter между строками)"
    )


@router.message(Flow.lyrics_body, F.text)
async def song_body(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data.get("title", "Без названия")
    lyrics = (message.text or "").strip()
    if len(lyrics) < 10:
        await message.answer("Текст слишком короткий")
        return
    await message.answer("⏳ Рендер видео… 30–90 сек")
    out = VIDEO_DATA_DIR / f"lyrics_{message.from_user.id}.mp4"
    try:
        build_lyrics_video(title=title, lyrics=lyrics, out_path=out)
        await message.answer_video(FSInputFile(out), caption=f"🎵 {title}")
    except Exception as e:
        logger.exception("lyrics video")
        await message.answer(f"Ошибка рендера: {e}")
    await state.clear()
    await message.answer("Готово! Ещё видео?", reply_markup=_kb_main())


@router.callback_query(F.data == "vid:article")
async def cb_article(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.article_title)
    await call.message.answer("📚 Напиши <b>заголовок</b> (например: Почему птицы летают)")
    await call.answer()


@router.message(Flow.article_title, F.text)
async def article_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:200])
    await state.set_state(Flow.article_body)
    await message.answer(
        "Пришли <b>текст статьи</b> — абзацы через пустую строку"
    )


@router.message(Flow.article_body, F.text)
async def article_body(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data.get("title", "Статья")
    body = (message.text or "").strip()
    if len(body) < 30:
        await message.answer("Нужен текст подлиннее (минимум ~30 символов)")
        return
    await message.answer("⏳ Рендер видео…")
    out = VIDEO_DATA_DIR / f"article_{message.from_user.id}.mp4"
    try:
        build_article_video(title=title, body=body, out_path=out)
        await message.answer_video(FSInputFile(out), caption=f"📚 {title}")
    except Exception as e:
        logger.exception("article video")
        await message.answer(f"Ошибка: {e}")
    await state.clear()
    await message.answer("Ещё?", reply_markup=_kb_main())


@router.message(Command("batch"))
@router.message(F.text.regexp(r"(?i)делай\s+batch\s+контент-?завод"))
async def cmd_batch_hint(message: Message, state: FSMContext) -> None:
    await state.set_state(Flow.batch_brief)
    await message.answer(
        "🏭 <b>Batch контент-завод</b>\n\n"
        "Пришли <b>бриф</b> — каждая строка = смысловой блок ролика.\n"
        "Соберу <b>3 варианта</b> с озвучкой и текстом на экране (демо; "
        "полный конвейер 50+ — <code>scripts/build_batch_content.py</code>).\n\n"
        "Пример брифа:\n"
        "<i>TikTok — просмотры\n"
        "Авито — лиды\n"
        "Партнёрки банков\n"
        "Вывод от 5000 ₽</i>"
    )


@router.message(Flow.batch_brief, F.text)
async def batch_brief(message: Message, state: FSMContext) -> None:
    brief = (message.text or "").strip()
    if len(brief) < 20:
        await message.answer("Бриф короче 20 символов — добавь деталей")
        return
    await message.answer("⏳ Batch: 3 ролика с озвучкой… это 3–8 минут")
    out_dir = VIDEO_DATA_DIR / f"batch_{message.from_user.id}"
    try:
        paths = build_batch_from_brief(brief, out_dir, count=3)
        for i, p in enumerate(paths, 1):
            await message.answer_video(
                FSInputFile(p),
                caption=f"🏭 Batch {i}/3 · контент-завод",
            )
    except Exception as e:
        logger.exception("batch factory")
        await message.answer(f"Ошибка batch: {e}")
    await state.clear()
    await message.answer("Готово! Полный конвейер 50+: scripts/build_batch_content.py", reply_markup=_kb_main())


@router.callback_query(F.data == "vid:batch")
async def cb_batch(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.batch_brief)
    await call.message.answer(
        "🏭 Пришли <b>бриф</b> (строки через Enter).\n"
        "Или напиши: <code>делай batch контент-завод</code>"
    )
    await call.answer()
