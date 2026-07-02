"""Персональные пуши для конверсии в оплату и возврата."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from oracle_bot import storage as db
from oracle_bot.access import has_full_access
from oracle_bot.config import (
    ORACLE_DEEP_STARS,
    ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
    ORACLE_PREMIUM_PRICE_RUB,
    ORACLE_REFERRAL_BONUS,
    ORACLE_ULTRA_PLUS_PRICE_RUB,
)
from oracle_bot.mystic_data import zodiac_label

logger = logging.getLogger(__name__)

# --- Воронка отработки возражений (HVD / Ultra Plus) -----------------------
# Если после показа оффера человек за час не оплатил — считаем, что его что-то
# смущает (обычно цена), и ведём по лестнице: вопрос → скидка -20% → скидка
# -50% → более доступный продукт → подписка Премиум. На каждом шаге, если
# оплата уже прошла, пуш тихо помечается отправленным и ничего не шлём.
_OBJ_STAGES = ("obj_ask", "obj_50", "obj_pivot", "obj_final")
_OBJ_DELAY_HOURS = {"obj_ask": 1, "obj_50": 21, "obj_pivot": 31, "obj_final": 55}
_OBJ_PRICE = {"exclusive_hvd": ORACLE_EXCLUSIVE_HVD_PRICE_RUB, "ultra_plus": ORACLE_ULTRA_PLUS_PRICE_RUB}
_OBJ_LABEL = {"exclusive_hvd": "🔮 Эксклюзив ХВД", "ultra_plus": "📖 Ultra Plus — Книга о тебе"}
_OBJ_DOWNSELL = {"ultra_plus": "exclusive_hvd", "exclusive_hvd": "premium_30d"}


def _discount_price(base: int, pct: int) -> int:
    return max(int(base * (100 - pct) / 100), 99)


def schedule_objection_flow(user_id: int, kind: str) -> None:
    """Запускает воронку отработки возражений после показа оффера HVD/Ultra Plus."""
    if kind not in _OBJ_PRICE:
        return
    if db.get_user_meta(user_id).get("push_opt_out"):
        return
    db.cancel_pushes(user_id, [f"{stage}:{kind}" for stage in _OBJ_STAGES])
    ctx = json.dumps({"kind": kind}, ensure_ascii=False)
    for stage in _OBJ_STAGES:
        db.schedule_push(user_id, f"{stage}:{kind}", delay_hours=_OBJ_DELAY_HOURS[stage], context=ctx)


def cancel_objection_flow(user_id: int, kind: str) -> None:
    """Оплата прошла (или юзер сказал «уже купил») — гасим всю оставшуюся лестницу."""
    db.cancel_pushes(user_id, [f"{stage}:{kind}" for stage in _OBJ_STAGES])


def _obj_should_skip(uid: int, kind: str) -> bool:
    """Продажа уже случилась (этот продукт, даунсейл или подписка) — дальше не давим."""
    if db.has_paid(uid, kind):
        return True
    alt = _OBJ_DOWNSELL.get(kind)
    if alt and db.has_paid(uid, alt):
        return True
    return kind != "premium_30d" and db.has_paid(uid, "premium_30d")


def _obj_payment_url(uid: int, kind: str, amount: int) -> str | None:
    from oracle_bot.config import robokassa_configured

    if not robokassa_configured() or uid <= 0:
        return None
    from oracle_bot.robokassa import build_payment_url

    descs = {
        "exclusive_hvd": "Оракул — Эксклюзив HVD (спецпредложение)",
        "ultra_plus": "Оракул — Ultra Plus, Книга о тебе (спецпредложение)",
        "premium_30d": "Оракул — Премиум 30 дней (спецпредложение)",
    }
    inv_id = db.create_invoice(uid, kind, amount)
    return build_payment_url(
        inv_id=inv_id,
        out_sum=amount,
        description=descs.get(kind, "Оракул — спецпредложение"),
        shp={"Shp_uid": str(uid), "Shp_kind": kind},
    )


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
    "psychology": "🧠 Психолог",
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


def schedule_premium_renewal(user_id: int, days: int = 30) -> None:
    """Напоминание о продлении за 3 дня до конца премиума (рекуррентный доход)."""
    db.cancel_pushes(user_id, ["premium_expiring"])
    delay = max(1.0, (days - 3) * 24.0)
    db.schedule_push(user_id, "premium_expiring", delay_hours=delay, context="{}")


def schedule_reengagement(user_id: int) -> None:
    """При каждом возврате — планируем напоминание через 72ч если снова пропадёт."""
    if has_full_access(user_id):
        return
    meta = db.get_user_meta(user_id)
    if meta.get("push_opt_out"):
        return
    db.cancel_pushes(user_id, ["inactive"])
    db.schedule_push(user_id, "inactive", delay_hours=72, context='{"reason":"return"}')


def _obj_kb(user_id: int, push_type: str, ctx: dict[str, Any]) -> InlineKeyboardMarkup:
    stage, _, kind = push_type.partition(":")
    kind = kind or ctx.get("kind", "")
    base = _OBJ_PRICE.get(kind, 0)

    if stage == "obj_ask":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💸 Дороговато", callback_data=f"obj:price:{kind}")],
            [InlineKeyboardButton(text="🤷 Не уверен(а), что это моё", callback_data=f"obj:fit:{kind}")],
            [InlineKeyboardButton(text="⏳ Пока думаю", callback_data=f"obj:later:{kind}")],
            [InlineKeyboardButton(text="✅ Уже купил(а)", callback_data=f"obj:bought:{kind}")],
        ])
    if stage == "obj_50":
        price = _discount_price(base, 50)
        url = _obj_payment_url(user_id, kind, price)
        rows = []
        if url:
            rows.append([InlineKeyboardButton(text=f"💳 Забрать за {price}₽ (−50%)", url=url)])
        rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if stage == "obj_pivot":
        alt = _OBJ_DOWNSELL.get(kind, "premium_30d")
        alt_price = ORACLE_PREMIUM_PRICE_RUB if alt == "premium_30d" else _OBJ_PRICE.get(alt, 0)
        url = _obj_payment_url(user_id, alt, alt_price)
        rows = []
        if url:
            label = "⭐ Премиум за" if alt == "premium_30d" else f"{_OBJ_LABEL.get(alt, alt)} за"
            rows.append([InlineKeyboardButton(text=f"💳 {label} {alt_price}₽", url=url)])
        rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if stage == "obj_final":
        price = _discount_price(ORACLE_PREMIUM_PRICE_RUB, 20)
        url = _obj_payment_url(user_id, "premium_30d", price)
        rows = []
        if url:
            rows.append([InlineKeyboardButton(text=f"⭐ Премиум за {price}₽ (−20%, первый месяц)", url=url)])
        rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")]])


def _kb_push(
    user_id: int,
    push_type: str,
    ctx: dict[str, Any],
) -> InlineKeyboardMarkup:
    if push_type.startswith("obj_"):
        return _obj_kb(user_id, push_type, ctx)
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
    elif push_type == "premium_expiring":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Продлить Премиум", callback_data="mod:premium")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")],
        ])
    elif push_type == "inactive":
        rows.append([InlineKeyboardButton(text="Судьба дня", callback_data="mod:destiny")])
    elif push_type.startswith("morning_"):
        rows.append([InlineKeyboardButton(text="Гороскоп", callback_data="mod:horo_today")])
    elif module:
        rows.append([
            InlineKeyboardButton(text=f"Ещё {_mod_label(module)}", callback_data=f"mod:{module}")
        ])

    if push_type != "referral_nudge":
        from oracle_bot.paywall import stars_enabled

        if stars_enabled():
            rows.append([
                InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="mod:referral"),
                InlineKeyboardButton(text="⭐ Премиум", callback_data="mod:premium"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="mod:referral"),
            ])
    else:
        rows.append([InlineKeyboardButton(text="🎁 Получить бесплатные расклады", callback_data="mod:referral")])

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _obj_message(push_type: str, ctx: dict[str, Any]) -> str:
    stage, _, kind = push_type.partition(":")
    kind = kind or ctx.get("kind", "")
    label = _OBJ_LABEL.get(kind, "продукт")
    base = _OBJ_PRICE.get(kind, 0)

    if stage == "obj_ask":
        return (
            f"🤔 Ты смотрел(а) «{label}», но пока не оформил(а).\n\n"
            "Что смущает — сама книга или цена? Скажи честно, помогу решить 👇"
        )
    if stage == "obj_50":
        price = _discount_price(base, 50)
        return (
            f"🎁 Специально для тебя — «{label}» по цене <b>−50%</b>: "
            f"<s>{base}₽</s> → <b>{price}₽</b>.\n\n"
            "Дальше эта скидка не повторится — предложение разовое, лично для тебя."
        )
    if stage == "obj_pivot":
        alt = _OBJ_DOWNSELL.get(kind, "premium_30d")
        if alt == "premium_30d":
            return (
                "💭 Понимаю, если сейчас не готов(а) к полному разбору.\n\n"
                "Есть более доступный вариант — <b>Премиум на 30 дней</b>: "
                "все разделы без лимита и продолжения без 🔒. Так тоже можно "
                "получить много ценного, не переплачивая сразу за большую книгу."
            )
        alt_label = _OBJ_LABEL.get(alt, alt)
        alt_price = _OBJ_PRICE.get(alt, 0)
        return (
            f"💭 Если «{label}» пока дороговато — начни с малого: "
            f"«{alt_label}» всего за {alt_price}₽. Тоже про тебя, тоже подробно, "
            "просто компактнее. Можно всегда доплатить и открыть остальное позже."
        )
    if stage == "obj_final":
        price = _discount_price(ORACLE_PREMIUM_PRICE_RUB, 20)
        return (
            "✨ Последнее предложение от меня на эту тему.\n\n"
            f"Если ни одна из книг пока не откликнулась — попробуй <b>Премиум</b> "
            f"со скидкой −20% на первый месяц: <b>{price}₽</b>. Это весь бот без "
            "ограничений — и время понять, что подходит именно тебе."
        )
    return f"🔮 «{label}» всё ещё ждёт тебя."


def build_push_message(user_id: int, push_type: str, ctx: dict[str, Any]) -> str:
    if push_type.startswith("obj_"):
        return _obj_message(push_type, ctx)
    module = ctx.get("module", "")
    label = _mod_label(module)
    profile = db.get_profile(user_id)
    sign = zodiac_label(profile["zodiac"]) if profile.get("zodiac") else ""

    if push_type == "unlock_tease":
        from oracle_bot.paywall import referral_primary

        if referral_primary():
            return (
                f"🔮 <b>{label}</b> — карты ещё шепчут…\n\n"
                "Ты видел(а) только начало. В скрытой части — конкретика и совет.\n\n"
                f"🎁 Пригласи друга — +{ORACLE_REFERRAL_BONUS} бонуса и можно открыть 🔓."
            )
        return (
            f"🔮 <b>{label}</b> — карты ещё шепчут…\n\n"
            "Ты видел(а) только начало. В скрытой части — конкретные даты, "
            "совет и то, что звёзды не договаривают в бесплатном фрагменте.\n\n"
            f"🔓 Открыть за {ORACLE_DEEP_STARS}⭐ или ⭐ Премиум — безлимит на 30 дней."
        )
    if push_type == "limit_hit":
        from oracle_bot.paywall import referral_primary

        if referral_primary():
            return (
                f"🌙 Лимит на сегодня в «{label}» исчерпан — но судьба не ставит пауз.\n\n"
                f"🎁 Пригласи друга — +{ORACLE_REFERRAL_BONUS} расклада и 🔓 продолжения\n"
                "/ref — твоя ссылка"
            )
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
    if push_type == "premium_expiring":
        return (
            "⭐ <b>Твой Премиум скоро закончится</b> (через ~3 дня).\n\n"
            "Чтобы не потерять безлимит всех разделов и продолжения без 🔒 — "
            "продли заранее. Один тап 👇"
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
        push_type = row["push_type"]
        is_obj = push_type.startswith("obj_")
        # premium_expiring — действующим премиум-юзерам; obj_* — отдельные платные
        # продукты (HVD/Ultra), Премиум их не заменяет, поэтому не гасим по has_full_access
        if push_type != "premium_expiring" and not is_obj and has_full_access(uid):
            db.mark_push_sent(int(row["id"]))
            continue
        meta = db.get_user_meta(uid)
        if meta.get("push_opt_out"):
            db.mark_push_sent(int(row["id"]))
            continue
        if is_obj:
            _, _, obj_kind = push_type.partition(":")
            if _obj_should_skip(uid, obj_kind):
                db.mark_push_sent(int(row["id"]))
                cancel_objection_flow(uid, obj_kind)
                continue
        ctx = _ctx(row.get("context"))
        text = build_push_message(uid, push_type, ctx)
        kb = _kb_push(uid, push_type, ctx)
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
