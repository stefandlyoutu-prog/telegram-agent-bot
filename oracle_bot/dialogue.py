"""Уточняющие вопросы после чтения — ответ по сохранённому контексту."""

from __future__ import annotations

import re

from aiogram.types import Message

from oracle_bot import storage as db
from oracle_bot.access import has_full_access
from oracle_bot.llm_helpers import oracle_chat
from oracle_bot.mystic_data import zodiac_label
from oracle_bot.prompts import FULL_ONLY

_FOLLOWUP_PROMPT = """Пользователь уже получил мистическое чтение и задаёт уточнение.
Модуль: {module}
Профиль: имя {name}, дата {birth}, знак {sign}
Контекст последнего чтения:
{context}

Вопрос: {question}

{format}
Ответь по существу, опираясь на контекст и профиль. Не выдумывай факты вне контекста.
Если спрашивают про скрытую часть — напомни про 🔓 Продолжить или ⭐ Премиум.
Если вопрос совсем в другую тему — коротко ответь и предложи /menu."""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def build_reading_context(
    reading_text: str,
    cont_id: int | None,
    user_id: int,
) -> str:
    ctx = _strip_html(reading_text)
    if cont_id:
        cont = db.get_continuation(cont_id)
        if cont:
            if has_full_access(user_id) or cont.get("unlocked"):
                ctx += "\n\n" + _strip_html(cont["locked_text"])
            else:
                ctx += "\n\n[Полная часть скрыта — доступна через 🔓 Продолжить]"
    return ctx[:3500]


def has_context(user_id: int) -> bool:
    sess = db.get_session(user_id)
    return bool(sess.get("last_context"))


async def answer_followup(message: Message, question: str) -> bool:
    uid = message.from_user.id if message.from_user else 0
    sess = db.get_session(uid)
    context = sess.get("last_context") or ""
    if not context:
        return False

    profile = db.get_profile(uid)
    prompt = _FOLLOWUP_PROMPT.format(
        module=sess.get("last_module") or "—",
        name=profile.get("name") or "—",
        birth=profile.get("birth_date") or "—",
        sign=zodiac_label(profile["zodiac"]) if profile.get("zodiac") else "—",
        context=context,
        question=question.strip(),
        format=FULL_ONLY,
    )
    wait = await message.answer("💬 Уточняю…")
    try:
        text = await oracle_chat(prompt, temperature=0.72)
    except Exception as e:
        await wait.edit_text(f"Не удалось ответить: {e}")
        return True

    db.append_dialogue(uid, "user", question[:500])
    db.append_dialogue(uid, "assistant", text[:800])
    await wait.edit_text(text)
    return True
