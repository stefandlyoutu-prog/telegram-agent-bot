"""Мини-опрос «жизненный контекст» перед первым разбором — персонализация как у Selena."""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from oracle_bot import storage as db

logger = logging.getLogger(__name__)
router = Router()

RELATIONSHIP = {
    "pair": "В паре",
    "single": "Один/одна",
    "split": "Расстались / в разводе",
    "complicated": "Сложно / на паузе",
}
WORK = {
    "employed": "Работаю",
    "search": "Не работаю, в поиске",
    "business": "Свой бизнес / фриланс",
    "burnout": "Выгорел(а), на перерыве",
}
PAIN = {
    "money": "💰 Деньги",
    "love": "❤️ Отношения",
    "meaning": "🧭 Смысл / куда дальше",
    "health": "🌿 Энергия / здоровье",
}

_KV = "life_quiz:{uid}"
_AWAIT = "life_quiz_await_about:{uid}"


class _AwaitingAbout(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        uid = message.from_user.id if message.from_user else 0
        return db.kv_get(_AWAIT.format(uid=uid)) == "1"


def needs_quiz(user_id: int) -> bool:
    p = db.get_profile(user_id)
    if not p.get("birth_date"):
        return False
    return str(p.get("life_quiz_done") or "") not in ("1", "true", "yes")


def life_context_block(profile: dict) -> str:
    parts: list[str] = []
    if profile.get("relationship_status"):
        parts.append(f"Отношения: {profile['relationship_status']}")
    if profile.get("work_status"):
        parts.append(f"Работа: {profile['work_status']}")
    if profile.get("pain_focus"):
        parts.append(f"Сейчас больше всего болит: {profile['pain_focus']}")
    about = (profile.get("about_text") or "").strip()
    if about:
        parts.append(f"Своими словами: {about}")
    if not parts:
        return ""
    return (
        "\n\nКонтекст жизни человека (обязательно используй в разборе, называй по имени):\n"
        + "\n".join(f"• {x}" for x in parts)
    )


def _kb(prefix: str, options: dict[str, str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"lqz:{prefix}:{key}")]
        for key, label in options.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_pending(user_id: int, pending: dict) -> None:
    db.kv_set(_KV.format(uid=user_id), json.dumps(pending, ensure_ascii=False))


def peek_pending(user_id: int) -> dict | None:
    raw = db.kv_get(_KV.format(uid=user_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def pop_pending(user_id: int) -> dict | None:
    raw = db.kv_get(_KV.format(uid=user_id))
    db.kv_set(_KV.format(uid=user_id), "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def start_quiz(msg: Message, uid: int, *, pending: dict | None = None) -> None:
    if pending:
        set_pending(uid, pending)
    db.kv_set(_AWAIT.format(uid=uid), "")
    await msg.answer(
        "🎯 <b>Чтобы разбор был про тебя — 4 коротких вопроса</b>\n\n"
        "Не «для всех», а под твою ситуацию.\n\n"
        "<b>1/4.</b> Отношения сейчас?",
        reply_markup=_kb("rel", RELATIONSHIP),
    )


async def _finish_quiz(msg: Message, uid: int, state=None) -> None:
    db.save_profile(uid, life_quiz_done="1")
    db.kv_set(_AWAIT.format(uid=uid), "")
    p = db.get_profile(uid)
    name = p.get("name") or "друг"
    await msg.answer(
        f"✅ <b>{name}, принял.</b>\n\n"
        "Покажу <b>два сценария</b> на 2 месяца:\n"
        "🔴 если ничего не менять · 🟢 если работать с картой\n\n"
        "Собираю разбор…",
    )
    pending = pop_pending(uid)
    if pending:
        from oracle_bot.handlers import resume_after_life_quiz

        await resume_after_life_quiz(msg, uid, pending, state)
    else:
        await msg.answer("Выбери раздел в меню 👇")


@router.callback_query(F.data.startswith("lqz:rel:"))
async def cb_rel(call: CallbackQuery) -> None:
    uid = call.from_user.id if call.from_user else 0
    key = (call.data or "").split(":")[-1]
    db.save_profile(uid, relationship_status=RELATIONSHIP.get(key, key))
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🎯 <b>2/4.</b> Работа / доход сейчас?",
            reply_markup=_kb("work", WORK),
        )


@router.callback_query(F.data.startswith("lqz:work:"))
async def cb_work(call: CallbackQuery) -> None:
    uid = call.from_user.id if call.from_user else 0
    key = (call.data or "").split(":")[-1]
    db.save_profile(uid, work_status=WORK.get(key, key))
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🎯 <b>3/4.</b> Что сейчас болит сильнее всего?",
            reply_markup=_kb("pain", PAIN),
        )


@router.callback_query(F.data.startswith("lqz:pain:"))
async def cb_pain(call: CallbackQuery) -> None:
    uid = call.from_user.id if call.from_user else 0
    key = (call.data or "").split(":")[-1]
    db.save_profile(uid, pain_focus=PAIN.get(key, key))
    db.kv_set(_AWAIT.format(uid=uid), "1")
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🎯 <b>4/4.</b> Одной фразой — что сейчас в жизни?\n\n"
            "<i>Например: «уволился, жена ушла, деньги не идут»</i>\n\n"
            "Напиши сообщением или нажми «Пропустить»",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Пропустить →", callback_data="lqz:skip")]
                ]
            ),
        )


@router.callback_query(F.data == "lqz:skip")
async def cb_skip(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id if call.from_user else 0
    await call.answer()
    msg = call.message
    if msg:
        await _finish_quiz(msg, uid, state)


@router.message(_AwaitingAbout(), F.text)
async def msg_about_if_quiz(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = (message.text or "").strip()
    if text and text.lower() not in ("—", "-", "пропустить", "skip"):
        db.save_profile(uid, about_text=text[:500])
    await _finish_quiz(message, uid, state)
