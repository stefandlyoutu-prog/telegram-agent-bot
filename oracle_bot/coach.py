"""Коуч: короткий совет внутри чтения, без спама вторым сообщением."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from oracle_bot import storage as db
from oracle_bot.config import ORACLE_COACH_SEPARATE
from oracle_bot.groq_client import groq_configured, chat as groq_chat
from oracle_bot.revenue_bridge import load_catalog, notify_admins, register_gap, rule_match

logger = logging.getLogger(__name__)

_COACH_SYSTEM = """Ты — мягкий коуч m-Oracul. По контексту чтения дай короткую поддержку.
Ответ СТРОГО JSON без markdown:
{
  "micro_step": "1 конкретный шаг на сегодня (до 120 символов)",
  "pain": "краткая боль",
  "product_slugs": ["slug1"],
  "new_idea": null или {"title": "...", "why": "...", "can_auto": false}
}"""


def _parse_json(raw: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}", raw.strip())
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


async def _llm_coach(*, module: str, profile: dict, snippet: str, user_text: str) -> dict[str, Any]:
    if not groq_configured():
        return {}
    brief = [
        {"slug": c["slug"], "title": c["title"]}
        for c in load_catalog()
        if c.get("slug") not in ("oracle-deep",)
    ][:30]
    prompt = (
        f"Модуль: {module}\nПрофиль: {profile}\n"
        f"Фрагмент: {snippet[:400]}\n"
        f"Сообщение: {user_text or '—'}\n"
        f"Каталог: {json.dumps(brief, ensure_ascii=False)}"
    )
    try:
        raw = await groq_chat(prompt, system=_COACH_SYSTEM, temperature=0.35, max_tokens=400)
        return _parse_json(raw)
    except Exception as e:
        logger.warning("coach llm: %s", e)
        return {}


async def reading_footer(
    *,
    uid: int,
    module: str,
    reading_text: str,
    user_text: str = "",
) -> str:
    """1–2 строки в конце чтения — без второго сообщения."""
    snippet = re.sub(r"<[^>]+>", "", reading_text)[:500]
    llm = await _llm_coach(
        module=module,
        profile=db.get_profile(uid),
        snippet=snippet,
        user_text=user_text,
    )
    micro = (llm.get("micro_step") or "").strip()
    if not micro:
        return ""
    await _register_gaps(uid, module, snippet, user_text, llm)
    return f"\n\n<i>Шаг на сегодня:</i> {micro}"


async def _register_gaps(
    uid: int,
    module: str,
    snippet: str,
    user_text: str,
    llm: dict[str, Any],
) -> None:
    pain = llm.get("pain") or ""
    new_idea = llm.get("new_idea")
    if isinstance(new_idea, dict) and new_idea.get("title"):
        register_gap(
            user_id=uid,
            pain_summary=pain or new_idea["title"],
            proposal=f"{new_idea['title']}. {new_idea.get('why', '')}",
            module=module,
            automation="auto" if new_idea.get("can_auto") else "manual",
        )
        return
    products = rule_match(f"{user_text} {snippet}", module)
    if not products and pain:
        register_gap(
            user_id=uid,
            pain_summary=pain,
            proposal=snippet[:200],
            module=module,
            automation="manual",
        )


async def after_reading_coach(
    message: Message,
    *,
    uid: int,
    module: str,
    reading_text: str,
    user_text: str = "",
    cont_id: int | None = None,
) -> None:
    """Только если ORACLE_COACH_SEPARATE=1 — отдельное сообщение (legacy)."""
    if not ORACLE_COACH_SEPARATE:
        snippet = re.sub(r"<[^>]+>", "", reading_text)[:500]
        llm = await _llm_coach(
            module=module,
            profile=db.get_profile(uid),
            snippet=snippet,
            user_text=user_text,
        )
        await _register_gaps(uid, module, snippet, user_text, llm)
        db.save_session(uid, module=module, pain=llm.get("pain") or "", snippet=snippet)
        return

    # legacy separate message — сокращённый
    footer = await reading_footer(
        uid=uid, module=module, reading_text=reading_text, user_text=user_text
    )
    if footer:
        await message.answer(footer.strip())


async def coach_from_free_text(message: Message, text: str) -> None:
    uid = message.from_user.id if message.from_user else 0
    llm = await _llm_coach(
        module="free",
        profile=db.get_profile(uid),
        snippet="",
        user_text=text,
    )
    micro = llm.get("micro_step") or "Выбери раздел в меню или напиши свой вопрос."
    await message.answer(f"<i>{micro}</i>")
