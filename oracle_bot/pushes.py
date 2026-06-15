"""Персональные пуши для конверсии в оплату и возврата."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.access import has_full_access
from oracle_bot.mystic_data import zodiac_label

logger = logging.getLogger(__name__)

MODULE_LABELS: dict[str, str] = {
    "tarot": "🔮 Таро",
    "palm": "🖐 Ладонь",
    "natal": "🌌 Натальная",
    "horo_today": "🌅 Гороскоп",
    "horo_week": "📅 Неделя",
    "compat": "💕 Пара",
    "past_life": "🕰 Прошлые жизни",
    "karma": "⚖️ Карма",
    "dream": "🌙 Сонник",
    "dating": "💬 Любовь",
    "career": "💼 Карьера",
}


def _mod_label(module: str) -> str:
    return MODULE_LABELS.get(module, module or "расклад")


def _ctx(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"module": raw}


def schedule_topic_morning(user_id: int) -> None:
    meta = db.get_user_meta(user_id)
    topic = meta.get("topic")
    if not topic:
        return
    import json

    db.schedule_push(
        user_id,
        f"morning_{topic}",
        delay_hours=18,
        context=json.dumps({"topic": topic}, ensure_ascii=False),
    )


def schedule_after_limit(user_id: int, module: str) -> None:
    if has_full_access(user_id):
        return
    ctx = json.dumps({"module": module}, ensure_ascii=False)
    db.schedule_push(user_id, "limit_hit", delay_hours=3, context=ctx)
    st = db.referral_stats(user_id)
    if st["credits"] == 0 and st["invited"] == 0:
        db.schedule_push(user_id, "referral_nudge", delay_hours=6, context=ctx)


def schedule_after_teaser(user_id: int, module: str, cont_id: int) -> None:
    if has_full_access(user_id):
        return
    ctx = json.dumps({"module": module, "cont_id": cont_id}, ensure_ascii=False)
    db.schedule_push(user_id, "unlock_tease", delay_hours=2, context=ctx)


def schedule_welcome_series(user_id: int) -> None:
    if has_full_access(user_id):
        return
    db.schedule_push(user_id, "welcome_day1", delay_hours=4, context="{}")
    db.schedule_push(user_id, "welcome_day2", delay_hours=26, context="{}")


def schedule_inactive(user_id: int) -> None:
    if has_full_access(user_id):
        return
    db.schedule_push(user_id, "inactive", delay_hours=48, context="{}")


def _kb_push(
    push_type: str,
    ctx: dict[str, Any],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    cont_id = ctx.get("cont_id")
    module = ctx.get("module", "")

    if push_type in ("unlock_tease", "limit_hit") and cont_id:
        rows.append([
            InlineKeyboardButton(
                text=f"🔓 Продолжить ({ORACLE_DEEP_STARS}⭐)",
                callback_data=f"deep:{cont_id}",
            )
        ])
    elif push_type == "welcome_day1":
        rows.append([InlineKeyboardButton(text="Гороскоп на сегодня", callback_data="mod:horo_today")])
    elif push_type == "welcome_day2":
        rows.append([InlineKeyboardButton(text="Бесплатный расклад", callback_data="mod:tarot")])
    elif push_type == "inactive":
        rows.append([InlineKeyboardButton(text="Судьба дня", callback_data="mod:destiny")])
    elif push_type.startswith("morning_"):
        rows.append([InlineKeyboardButton(text="Гороскоп", callback_data="mod:horo_today")])
    elif module:
        rows.append([
            InlineKeyboardButton(text=f"Ещё {_mod_label(module)}", callback_data=f"mod:{module}")
        ])

    if push_type != "referral_nudge":
        rows.append([
            InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="mod:referral"),
            InlineKeyboardButton(text="⭐ Премиум", callback_data="mod:premium"),
        ])
    else:
        rows.append([InlineKeyboardButton(text="🎁 Получить бесплатные расклады", callback_data="mod:referral")])

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_push_message(user_id: int, push_type: str, ctx: dict[str, Any]) -> str:
    module = ctx.get("module", "")
    label = _mod_label(module)
    profile = db.get_profile(user_id)
    sign = zodiac_label(profile["zodiac"]) if profile.get("zodiac") else ""

    if push_type == "unlock_tease":
        return (
            f"🔮 <b>{label}</b> — карты ещё шепчут…\n\n"
            "Ты видел(а) только начало. В скрытой части — конкретные даты, "
            "совет и то, что звёзды не договаривают в бесплатном фрагменте.\n\n"
            f"🔓 Открыть за {ORACLE_DEEP_STARS}⭐ или ⭐ Премиум — безлимит на 30 дней."
        )
    if push_type == "limit_hit":
        return (
            f"🌙 Лимит на сегодня в «{label}» исчерпан — но судьба не ставит пауз.\n\n"
            f"⭐ Премиум — все разделы без 🔒\n"
            f"🎁 Или пригласи друга — +{ORACLE_REFERRAL_BONUS} расклада бесплатно\n"
            f"🔓 Или продолжи последнее чтение за {ORACLE_DEEP_STARS}⭐"
        )
    if push_type == "referral_nudge":
        return (
            "💫 Не хочешь платить — приведи друга.\n\n"
            f"За каждого нового пользователя по твоей ссылке — "
            f"<b>+{ORACLE_REFERRAL_BONUS}</b> бонусных чтений.\n"
            "Это работает, когда дневной лимит закончился."
        )
    if push_type == "welcome_day1":
        extra = f" для {sign}" if sign else ""
        return (
            f"🌅 Привет! Звёзды сегодня особенно ясны{extra}.\n\n"
            "Бесплатный гороскоп на день — один тап. "
            "Потом можно уточнить голосом или текстом."
        )
    if push_type == "welcome_day2":
        return (
            "🔮 Вчера ты заглянул(а) в Оракул — карты ещё ждут.\n\n"
            "Попробуй <b>Таро</b>: три карты, конкретный ответ. "
            "Первая часть бесплатно — продолжение по желанию."
        )
    if push_type == "inactive":
        extra = f" ({sign})" if sign else ""
        return (
            f"✨ Давно не виделись{extra}.\n\n"
            "«Судьба дня» — быстрый знак без лимита на размышления. "
            "Или загляни в меню — 25+ практик."
        )
    if push_type.startswith("morning_"):
        topic = ctx.get("topic") or push_type.replace("morning_", "")
        titles = {"love": "любовь", "money": "деньги", "career": "карьера"}
        t = titles.get(topic, topic)
        sign_part = f" для {sign}" if sign else ""
        return (
            f"🌅 Доброе утро{sign_part}.\n\n"
            f"Короткий фокус на <b>{t}</b>: загляни в гороскоп или выбери "
            f"раздел в приложении — бесплатная часть уже с советом."
        )
    return "🔮 m-Oracul ждёт тебя — загляни в меню."


async def process_due_pushes(bot: Bot) -> int:
    sent = 0
    for row in db.fetch_due_pushes():
        uid = int(row["user_id"])
        if has_full_access(uid):
            db.mark_push_sent(int(row["id"]))
            continue
        meta = db.get_user_meta(uid)
        if meta.get("push_opt_out"):
            db.mark_push_sent(int(row["id"]))
            continue
        push_type = row["push_type"]
        ctx = _ctx(row.get("context"))
        text = build_push_message(uid, push_type, ctx)
        kb = _kb_push(push_type, ctx)
        try:
            await bot.send_message(uid, text, reply_markup=kb)
            db.mark_push_sent(int(row["id"]))
            db.log_event(uid, "push_sent", push_type)
            sent += 1
        except Exception as e:
            logger.warning("push %s to %s: %s", push_type, uid, e)
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "chat not found" in err:
                db.mark_push_sent(int(row["id"]))
    return sent


async def push_worker(bot: Bot, interval_sec: int) -> None:
    import asyncio

    while True:
        try:
            n = await process_due_pushes(bot)
            if n:
                logger.info("pushes sent: %d", n)
        except Exception:
            logger.exception("push_worker")
        await asyncio.sleep(interval_sec)
