from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.enums import ChatAction

from oracle_bot import storage as db
from oracle_bot.config import (
    ORACLE_DEEP_PRICE_RUB,
    ORACLE_DEEP_STARS,
    ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
    ORACLE_FREE_PER_DAY,
    ORACLE_PDF_HVD_PRICE_RUB,
    ORACLE_PDF_READING_PRICE_RUB,
    ORACLE_PREMIUM_PRICE_RUB,
    ORACLE_ULTRA_PLUS_PRICE_RUB,
    ORACLE_PREMIUM_STARS,
    ORACLE_REFERRAL_BONUS,
    ORACLE_REFERRAL_WELCOME,
    robokassa_configured,
)
from oracle_bot.access import has_full_access, is_admin_user
from oracle_bot.formatting import reading_header
from oracle_bot import analytics as analytics_mod
from oracle_bot import funnel
from oracle_bot.keyboards import (
    kb_after_reading,
    kb_limit_reached,
    kb_main,
    kb_mystic,
    kb_profile,
    kb_referral,
    kb_zodiac,
)
from oracle_bot import mystic_flows as mf
from oracle_bot.llm_helpers import oracle_palm_reading, oracle_reading
from oracle_bot.mystic_data import (
    RUNES,
    ZODIAC_BY_KEY,
    chinese_animal,
    extract_place,
    life_path_number,
    parse_birth_date,
    parse_birth_time,
    zodiac_from_date,
    zodiac_label,
)
from oracle_bot.prompts import (
    CAREER,
    CHINESE,
    COMPAT_USER,
    DATING_USER,
    DESTINY_DAY,
    DREAM,
    HORO_TODAY,
    HORO_WEEK,
    MAJOR_ARCANA,
    NUMEROLOGY,
    PORTRAIT,
    PSYCHOLOGY_USER,
    RUNE,
    TAROT_USER,
    YESNO,
)

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int | None) -> bool:
    if not user_id:
        return False
    from oracle_bot.config import ORACLE_ADMIN_IDS

    return not ORACLE_ADMIN_IDS or user_id in ORACLE_ADMIN_IDS


class _ActivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            # ensure_user до touch_user: иначе /start никогда не узнает,
            # что пользователь новый (touch_user сам создаёт запись).
            data["is_new_user"] = db.ensure_user(user.id)
            db.touch_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
            )
            try:
                from oracle_bot.streak import record_visit

                record_visit(user.id)
            except Exception as e:
                logger.warning("record_visit uid=%s: %s", user.id, e)
        return await handler(event, data)


router.message.middleware(_ActivityMiddleware())
router.callback_query.middleware(_ActivityMiddleware())

_DATE_RE = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")
_WAIT = {
    "horo_today": "🌅 Смотрю звёзды…",
    "horo_week": "📅 Раскладываю неделю…",
    "portrait": "🎂 Составляю портрет…",
    "numerology": "🔢 Считаю код судьбы…",
    "chinese": "🐉 Читаю древние знаки…",
    "dream": "🌙 Погружаюсь в символы…",
    "yesno": "🎲 Бросаю жребий…",
    "rune": "🪬 Руна открывается…",
    "career": "💼 Смотрю путь…",
    "destiny": "✨ Судьба дня…",
    "tarot": "🔮 Тасую карты…",
    "compat": "💕 Смотрю связь…",
    "palm": "🖐 Читаю линии…",
    "dating": "💬 Думаю…",
    "psychology": "🧠 Слушаю…",
    "natal": "🌌 Строю натальную…",
    "past_life": "🕰 Погружаюсь в прошлое…",
    "karma": "⚖️ Смотрю карму…",
    "akashic": "📜 Открываю Акаши…",
    "iching": "☯️ Бросаю гексаграмму…",
    "chakra": "🔴 Сканирую чакры…",
    "aura": "🌈 Читаю ауру…",
    "spirit_guide": "👁 Зову наставника…",
    "moon": "🌑 Сверяюсь с Луной…",
    "crystal": "💎 Выбираю камень…",
    "shadow": "🌑 Встреча с Тенью…",
    "twin_flame": "🔥 Ищу связь душ…",
    "biorhythm": "📈 Считаю циклы…",
    "transit": "🪐 Транзиты…",
    "lenormand": "🦋 Расклад…",
    "family_karma": "🧬 Родовые узлы…",
}


class Flow(StatesGroup):
    tarot_question = State()
    compat_dates = State()
    palm_wait = State()
    dating_text = State()
    psychology_text = State()
    portrait_birth = State()
    numerology_input = State()
    chinese_birth = State()
    dream_text = State()
    yesno_question = State()
    career_text = State()
    prof_birth = State()
    prof_name = State()
    prof_natal_data = State()
    natal_input = State()
    past_life_focus = State()
    lenormand_question = State()
    twin_flame_text = State()
    family_karma_text = State()
    iching_question = State()
    hvd_input = State()
    ultra_plus_input = State()


def _premium_line(user_id: int) -> str:
    from oracle_bot.paywall import referral_primary

    if is_admin_user(user_id):
        return "\n\n👑 <b>Полный доступ</b> — все разделы без лимита"
    if db.is_premium(user_id):
        until = db.premium_until(user_id) or ""
        return f"\n\n⭐ <b>Премиум</b> до {until[:10]}\nВсе чтения без 🔒"
    used = db.total_usage_today(user_id)
    credits = db.get_referral_credits(user_id)
    invited = db.referral_stats(user_id)["invited"]
    bonus = f"\n🎁 Бонусов: {credits}" if credits else ""
    refs = f"\n👥 Друзей: {invited}" if invited else ""
    if referral_primary():
        return (
            f"\n\n🆓 Сегодня: {used} чтений"
            f"{bonus}{refs}\n"
            f"Бесплатно до {ORACLE_FREE_PER_DAY} на раздел\n"
            f"🎁 Пригласи друга — +{ORACLE_REFERRAL_BONUS} расклада и 🔓 продолжения\n"
            f"/ref — твоя ссылка"
        )
    return (
        f"\n\n🆓 Сегодня: {used} чтений"
        f"{bonus}{refs}\n"
        f"Бесплатно до {ORACLE_FREE_PER_DAY} на раздел\n"
        f"🔓 Продолжение — {ORACLE_DEEP_STARS}⭐\n"
        f"⭐ Премиум — безлимит\n"
        f"🎁 /ref — пригласи друга (+{ORACLE_REFERRAL_BONUS})"
    )


def _limit_text() -> str:
    from oracle_bot.paywall import referral_primary

    if referral_primary():
        return (
            "Лимит бесплатных чтений в этом разделе на сегодня исчерпан.\n\n"
            f"🎁 <b>Пригласи друга</b> — +{ORACLE_REFERRAL_BONUS} бонусных расклада "
            "и можно открыть 🔓 продолжение.\n"
            "Команда /ref — ссылка для отправки."
        )
    return (
        "Лимит бесплатных чтений в этом разделе на сегодня исчерпан.\n\n"
        f"🎁 <b>Пригласи друга</b> — +{ORACLE_REFERRAL_BONUS} бонусных расклада за каждого "
        "(команда /ref).\n"
        f"🔓 Или открой продолжение за {ORACLE_DEEP_STARS}⭐ · ⭐ Премиум — безлимит на 30 дней."
    )


async def _prompt_referral(
    message: Message,
    uid: int,
    source: str,
    *,
    extra: str = "",
) -> None:
    from oracle_bot.paywall import experiment_label
    from oracle_bot.referrals import stats_text

    if uid:
        analytics_mod.track_referral_prompt(uid, source)
    head = experiment_label()
    if extra:
        head += extra + "\n\n"
    await message.answer(head + stats_text(uid), reply_markup=kb_referral(uid))


def _start_text(user_id: int) -> str:
    from oracle_bot.config import (
        ORACLE_DEEP_FIRST_PRICE_RUB,
        ORACLE_FREE_PER_DAY,
        ORACLE_PREMIUM_PRICE_RUB,
        ORACLE_REFERRAL_UNLIMITED_AT,
        oferta_url,
        site_public_url,
    )
    from oracle_bot.free_day import is_free_day_active
    from oracle_bot.streak import get_streak

    p = db.get_profile(user_id)
    streak = get_streak(user_id)
    name = (p.get("name") or "").strip()
    greet = f", {name}" if name else ""
    lines = [
        f"<b>Оракул</b> — разборы под тебя{greet}",
        "",
        "🔴🟢 <b>2 сценария на 2 месяца</b> — что будет, если ничего не менять, "
        "и что изменится, если действовать.",
        "",
        "Популярное: Таро · гороскоп · совместимость · число судьбы.",
        "Первая часть — бесплатно, с конкретикой. Углубление от "
        f"<b>{ORACLE_DEEP_FIRST_PRICE_RUB}₽</b> (первый раз).",
    ]
    if is_free_day_active():
        lines.insert(2, "🎁 <b>Сегодня до конца дня — все разделы бесплатно!</b>")
        lines.insert(3, "")
    site = site_public_url()
    if site:
        lines.extend(["", f"🌐 Сайт: <a href=\"{site}\">{site.replace('https://', '')}</a>"])
    lines.extend([
        "",
        f"📋 <a href=\"{oferta_url()}\">Оферта</a> · "
        f"{ORACLE_FREE_PER_DAY} бесплатно/день · Премиум {ORACLE_PREMIUM_PRICE_RUB}₽/мес",
    ])
    if p.get("zodiac"):
        lines.append(f"Знак: {zodiac_label(p['zodiac'])}")
    if streak > 1:
        lines.append(f"Серия: {streak} дн. подряд 🔥")
    lines.append(_premium_line(user_id))
    return "\n".join(lines)


async def _guard(user_id: int, module: str) -> Optional[str]:
    if db.can_use(user_id, module, ORACLE_FREE_PER_DAY):
        return None
    analytics_mod.track_limit_hit(user_id, module)
    from oracle_bot.pushes import schedule_after_limit

    schedule_after_limit(user_id, module)
    return _limit_text()


async def _callback_chat(call: CallbackQuery) -> Optional[Message]:
    """Сообщение для ответа на inline-кнопку (fallback в личку)."""
    if call.message:
        return call.message
    if not call.bot or not call.from_user:
        return None
    try:
        return await call.bot.send_message(call.from_user.id, "🔮…")
    except Exception:
        logger.exception("callback_chat fallback")
        return None


async def _send_reading(
    message: Message,
    *,
    uid: int,
    module: str,
    prompt: str,
    header: str = "",
    temperature: float = 0.82,
    wait_msg: Message | None = None,
    user_text: str = "",
) -> None:
    from oracle_bot.life_quiz import life_context_block

    premium = has_full_access(uid)
    profile = db.get_profile(uid)
    prompt = f"{prompt}{life_context_block(profile)}"
    wait = wait_msg or await message.answer(_WAIT.get(module, "🔮…"))
    try:
        if message.bot:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        raw = await oracle_reading(prompt, premium=premium, temperature=temperature)
        text, cont_id = funnel.deliver(
            user_id=uid,
            module=module,
            raw_text=raw,
            header=header,
        )
    except Exception as e:
        logger.exception("%s llm", module)
        msg = str(e).replace("LLMError: ", "")
        await wait.edit_text(f"Сбой оракула: {msg}")
        return

    db.bump_usage(uid, module)
    analytics_mod.track_reading(uid, module, has_lock=bool(cont_id and not premium))
    if cont_id and not premium:
        from oracle_bot.pushes import schedule_after_teaser

        schedule_after_teaser(uid, module, cont_id)
    db.touch_user(uid, module=module)
    await wait.edit_text(
        text,
        reply_markup=kb_after_reading(module, cont_id, uid),
    )
    try:
        from oracle_bot.coach import reading_footer

        footer = await asyncio.wait_for(
            reading_footer(
                uid=uid,
                module=module,
                reading_text=text,
                user_text=user_text or (message.text or message.caption or ""),
            ),
            timeout=20,
        )
        if footer:
            await wait.edit_text(
                text + footer,
                reply_markup=kb_after_reading(module, cont_id, uid),
            )
    except asyncio.TimeoutError:
        logger.warning("footer timeout %s", module)
    except Exception as e:
        logger.warning("footer: %s", e)
    from oracle_bot.dialogue import build_reading_context

    reading_ctx = build_reading_context(text, cont_id, uid)
    db.save_session(
        uid,
        module=module,
        snippet=text[:500],
        last_context=reading_ctx,
    )
    try:
        db.save_pdf_source(uid, "pdf_reading", header or module, reading_ctx or text)
    except Exception as e:
        logger.warning("pdf source save: %s", e)
    try:
        from oracle_bot.coach import after_reading_coach

        ut = user_text or (message.text or message.caption or "")
        await after_reading_coach(
            message,
            uid=uid,
            module=module,
            reading_text=text,
            user_text=ut,
            cont_id=cont_id,
        )
    except Exception as e:
        logger.warning("coach: %s", e)


async def _instant(
    msg: Message,
    uid: int,
    module: str,
    builder,
    *,
    need_profile: bool = False,
    skip_quiz: bool = False,
) -> None:
    blocked = await _guard(uid, module)
    if blocked:
        await msg.answer(blocked, reply_markup=kb_limit_reached(uid))
        return
    if need_profile and not db.get_profile(uid).get("birth_date"):
        await msg.answer(
            "Нужна дата рождения — укажи в 👤 Профиль",
            reply_markup=kb_profile(False),
        )
        return
    if not skip_quiz:
        from oracle_bot import life_quiz as lq

        if lq.needs_quiz(uid):
            lq.set_pending(
                uid,
                {"type": "instant", "module": module, "need_profile": need_profile},
            )
            await lq.start_quiz(msg, uid)
            return
    result = builder(uid)
    if result is None:
        await msg.answer(
            "Не хватает данных — заполни 👤 Профиль",
            reply_markup=kb_profile(bool(db.get_profile(uid).get("birth_date"))),
        )
        return
    prompt, header = result
    await _send_reading(msg, uid=uid, module=module, prompt=prompt, header=header)


_INSTANT_BUILDERS: dict[str, tuple] = {}


async def resume_after_life_quiz(
    msg: Message,
    uid: int,
    pending: dict,
    state: FSMContext | None = None,
) -> None:
    """Продолжить чтение после мини-опроса."""
    t = pending.get("type")
    if t == "instant":
        mod = pending.get("module", "")
        spec = _INSTANT_BUILDERS.get(mod)
        if spec:
            builder, need_profile = spec
            await _instant(
                msg, uid, mod, builder, need_profile=need_profile, skip_quiz=True
            )
            return
    if t == "awareness_scenario":
        p = db.get_profile(uid)
        birth = p.get("birth_date") or ""
        name = (p.get("name") or "").strip()
        pain = (p.get("pain_focus") or "").strip()
        about = (p.get("about_text") or "").strip()
        prompt = (
            "Персональный разбор на ближайшие 2 месяца по дате рождения.\n"
            f"Имя: {name or 'не указано'}\n"
            f"Дата рождения: {birth}\n"
            f"Главный фокус: {pain or 'из опроса'}\n"
            f"Ситуация: {about or 'контекст из мини-опроса'}\n\n"
            "Покажи два честных сценария: что будет если ничего не менять, "
            "и что изменится если работать с картой осознанно. "
            "Конкретика по деньгам, отношениям и энергии."
        )
        await _send_reading(
            msg,
            uid=uid,
            module="tarot",
            prompt=prompt,
            header=reading_header("Два сценария", "2 месяца"),
            temperature=0.85,
        )
        return
    if t == "open_module":
        mod = pending.get("mod", "tarot")
        if state is None:
            await msg.answer(
                "🔮 Нажми <b>Таро</b> в меню — разбор уже будет персональным.",
                reply_markup=kb_main(),
            )
            return
        await _open_module(msg, state, uid, mod, skip_quiz=True)
        return
    await msg.answer("Выбери раздел в меню — разбор будет с учётом твоей ситуации.")


_INSTANT_BUILDERS.update(
    {
        "karma": (mf.karma_prompt, True),
        "akashic": (mf.akashic_prompt, True),
        "chakra": (mf.chakra_prompt, False),
        "aura": (mf.aura_prompt, True),
        "spirit_guide": (mf.spirit_guide_prompt, False),
        "moon": (mf.moon_prompt, False),
        "crystal": (mf.crystal_prompt, False),
        "shadow": (mf.shadow_prompt, True),
        "biorhythm": (mf.biorhythm_prompt, True),
        "transit": (mf.transit_prompt, True),
    }
)


async def _send_premium_invoice(message: Message) -> None:
    from oracle_bot.paywall import stars_enabled

    uid = message.from_user.id if message.from_user else 0
    if not stars_enabled():
        await _prompt_referral(
            message,
            uid,
            "premium",
            extra="⭐ Сейчас безлимит — через приглашение друзей, не через Stars.",
        )
        return
    if uid:
        analytics_mod.track_payment_intent(uid, "premium_30d")
    await message.answer_invoice(
        title="Оракул — Премиум 30 дней",
        description="Безлимит + все продолжения без 🔒. Все 15+ разделов.",
        payload="premium_30d",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=ORACLE_PREMIUM_STARS)],
    )


async def _send_deep_invoice(message: Message, cont_id: int) -> None:
    from oracle_bot.paywall import stars_enabled

    cont = db.get_continuation(cont_id)
    if not cont:
        await message.answer("Чтение устарело — запроси новое из меню.", reply_markup=kb_main())
        return
    uid = message.from_user.id if message.from_user else 0
    if not stars_enabled():
        if uid and db.get_referral_credits(uid) > 0 and db.spend_referral_credit(uid):
            analytics_mod.track_reading(uid, cont["module"], has_lock=False)
            await message.answer(
                funnel.format_full(cont["teaser_text"], cont["locked_text"]),
                reply_markup=kb_after_reading(cont["module"], None, uid),
            )
            return
        await _prompt_referral(
            message,
            uid,
            f"deep:{cont_id}",
            extra=(
                "🔓 <b>Полная версия</b> — пригласи друга (+бонус) "
                "или потрать уже накопленный бонус при следующем нажатии."
            ),
        )
        return
    if uid:
        analytics_mod.track_payment_intent(uid, f"deep:{cont_id}")
    await message.answer_invoice(
        title="🔓 Продолжение чтения",
        description="Скрытая часть: детали, прогноз, личный совет",
        payload=f"deep:{cont_id}",
        currency="XTR",
        prices=[LabeledPrice(label="Продолжение", amount=ORACLE_DEEP_STARS)],
    )


def _robokassa_url(
    uid: int,
    kind: str,
    cont_id: int | None = None,
    *,
    override_amount: int | None = None,
) -> str | None:
    """Создаёт инвойс и возвращает ссылку Робокассы (или None если не настроена).

    override_amount — для скидочных предложений в воронке отработки возражений:
    сумма другая, но kind тот же, поэтому выдача доступа при оплате работает как обычно.
    """
    if not robokassa_configured() or uid <= 0:
        return None
    from oracle_bot.robokassa import build_payment_url

    if kind == "premium_30d":
        amount = ORACLE_PREMIUM_PRICE_RUB
        desc = "Оракул — Премиум 30 дней"
    elif kind == "exclusive_hvd":
        amount = ORACLE_EXCLUSIVE_HVD_PRICE_RUB
        desc = "Оракул — Эксклюзив HVD"
    elif kind == "ultra_plus":
        amount = ORACLE_ULTRA_PLUS_PRICE_RUB
        desc = "Оракул — Ultra Plus, Книга о тебе"
    elif kind == "pdf_hvd":
        amount = ORACLE_PDF_HVD_PRICE_RUB
        desc = "Оракул — ХВД в книге PDF"
    elif kind == "pdf_reading":
        amount = ORACLE_PDF_READING_PRICE_RUB
        desc = "Оракул — разбор в PDF"
    else:
        amount = ORACLE_DEEP_PRICE_RUB
        desc = "Оракул — продолжение чтения"
    if override_amount is not None and override_amount > 0:
        amount = override_amount
        desc = f"{desc} (спецпредложение)"
    inv_id = db.create_invoice(uid, kind, amount, cont_id=cont_id)
    return build_payment_url(
        inv_id=inv_id,
        out_sum=amount,
        description=desc,
        shp={"Shp_uid": str(uid), "Shp_kind": kind},
    )


async def _offer_premium(message: Message, uid: int) -> None:
    """Премиум: оплата картой/СБП (Робокасса) + Telegram Stars (если включены)."""
    from oracle_bot.paywall import stars_enabled

    url = _robokassa_url(uid, "premium_30d")
    if not url:
        await _send_premium_invoice(message)
        return
    if uid:
        analytics_mod.track_payment_intent(uid, "premium_30d")
    rows = [[InlineKeyboardButton(text=f"💳 Картой/СБП — {ORACLE_PREMIUM_PRICE_RUB}₽", url=url)]]
    if stars_enabled():
        rows.append(
            [InlineKeyboardButton(text=f"⭐ Telegram Stars — {ORACLE_PREMIUM_STARS}", callback_data="stars:premium")]
        )
    rows.append([InlineKeyboardButton(text="📄 Оферта", url=_oferta_link())])
    await message.answer(
        "⭐ <b>Премиум на 30 дней</b>\n"
        "Безлимит всех разделов · все продолжения без 🔒\n\n"
        "Выбери способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _offer_exclusive_hvd(message: Message, uid: int) -> None:
    url = _robokassa_url(uid, "exclusive_hvd")
    if not url:
        await message.answer(
            "Оплата картой временно недоступна. Напиши администратору.",
            reply_markup=kb_main(),
        )
        return
    if uid:
        analytics_mod.track_payment_intent(uid, "exclusive_hvd")
        from oracle_bot.pushes import schedule_objection_flow

        schedule_objection_flow(uid, "exclusive_hvd")
    rows = [
        [InlineKeyboardButton(text=f"💳 Картой/СБП — {ORACLE_EXCLUSIVE_HVD_PRICE_RUB}₽", url=url)],
        [InlineKeyboardButton(text="📄 Оферта", url=_oferta_link())],
    ]
    await message.answer(
        "🔮 <b>Эксклюзив: Хронально-Векторная Диагностика</b>\n\n"
        "Полный персональный разбор по методике ХВД:\n"
        "чакры, контуры, инь/ян, задачи жизни, код негатива, реабилитация.\n\n"
        "Выбери способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _offer_ultra_plus(message: Message, uid: int) -> None:
    url = _robokassa_url(uid, "ultra_plus")
    if not url:
        await message.answer(
            "Оплата картой временно недоступна. Напиши администратору.",
            reply_markup=kb_main(),
        )
        return
    if uid:
        analytics_mod.track_payment_intent(uid, "ultra_plus")
        from oracle_bot.pushes import schedule_objection_flow

        schedule_objection_flow(uid, "ultra_plus")
    rows = [
        [InlineKeyboardButton(text=f"💳 Картой/СБП — {ORACLE_ULTRA_PLUS_PRICE_RUB}₽", url=url)],
        [InlineKeyboardButton(text="📄 Оферта", url=_oferta_link())],
    ]
    await message.answer(
        "📖 <b>Ultra Plus — Книга о тебе</b>\n\n"
        "Персональный PDF по Матрице Судьбы:\n"
        "качества, таланты, предназначение, деньги, программы, "
        "отношения, здоровье, прогноз + дополнение ХВД.\n\n"
        "Выбери способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _offer_deep(message: Message, uid: int, cont_id: int) -> None:
    from oracle_bot.paywall import stars_enabled
    from oracle_bot.config import ORACLE_DEEP_FIRST_PRICE_RUB

    cont = db.get_continuation(cont_id)
    if not cont:
        await message.answer("Чтение устарело — запроси новое из меню.", reply_markup=kb_main())
        return
    # Первая покупка — «разбить печать»: холодному юзеру спеццена на первую разблокировку.
    first_buy = uid > 0 and not db.has_paid(uid, "deep_unlock")
    price = ORACLE_DEEP_FIRST_PRICE_RUB if first_buy else ORACLE_DEEP_PRICE_RUB
    override = ORACLE_DEEP_FIRST_PRICE_RUB if first_buy else None
    url = _robokassa_url(uid, "deep_unlock", cont_id=cont_id, override_amount=override)
    if not url:
        await _send_deep_invoice(message, cont_id)
        return
    if uid:
        analytics_mod.track_payment_intent(uid, f"deep:{cont_id}")
        from oracle_bot.pushes import schedule_payment_recovery

        schedule_payment_recovery(uid, cont_id)
    btn = (
        f"💳 Открыть за {price}₽ (первый раз −50%)" if first_buy
        else f"💳 Картой/СБП — {price}₽"
    )
    rows = [[InlineKeyboardButton(text=btn, url=url)]]
    if stars_enabled():
        rows.append(
            [InlineKeyboardButton(text=f"⭐ Telegram Stars — {ORACLE_DEEP_STARS}", callback_data=f"stars:deep:{cont_id}")]
        )
    rows.append([InlineKeyboardButton(text="📄 Оферта", url=_oferta_link())])
    head = (
        "🔓 <b>Продолжение чтения</b>\n"
        "Скрытая часть: детали, прогноз, личный совет\n\n"
    )
    if first_buy:
        head += (
            f"🎁 <b>Только первая разблокировка — {price}₽ вместо {ORACLE_DEEP_PRICE_RUB}₽.</b>\n"
            "Попробуй, как это работает 👇\n\n"
        )
    else:
        head += "Выбери способ оплаты:"
    await message.answer(
        head.rstrip(),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _oferta_link() -> str:
    from oracle_bot.config import oferta_url

    return oferta_url()


def _profile_ctx(uid: int) -> dict:
    p = db.get_profile(uid)
    name = p.get("name") or "не указано"
    birth = p.get("birth_date") or "не указана"
    sign = p.get("zodiac")
    sign_label = zodiac_label(sign) if sign else "не определён"
    return {"name": name, "birth": birth, "sign": sign_label, "sign_key": sign}


_AWARENESS_ALIASES = frozenset({"awareness", "pain", "scenario", "razbor"})


def _is_awareness_start(args: str) -> bool:
    """Рекламные deeplink → воронка «2 сценария + 4 вопроса» (как в посте)."""
    a = (args or "").strip().lower()
    if a in _AWARENESS_ALIASES:
        return True
    return a.startswith("src_")


async def _enter_awareness_funnel(
    message: Message,
    state: FSMContext,
    uid: int,
) -> None:
    """Обещание рекламы: дата рождения → 4 вопроса → 🔴/🟢 сценарии на 2 месяца."""
    from oracle_bot import life_quiz as lq

    await message.answer(
        "🔴 <b>Два сценария на 2 месяца</b>\n\n"
        "Покажу честно: что будет, если ничего не менять — "
        "и что изменится, если работать с картой.\n\n"
        "Сначала 4 коротких вопроса про твою ситуацию 👇"
    )
    lq.set_pending(uid, {"type": "awareness_scenario"})
    if not db.get_profile(uid).get("birth_date"):
        await state.set_state(Flow.prof_birth)
        await message.answer(
            "📅 Для разбора по <b>дате рождения</b> напиши одним сообщением:\n"
            "<i>ДД.ММ.ГГГГ</i> (можно с именем: <i>15.03.1990 Анна</i>)"
        )
        return
    if lq.needs_quiz(uid):
        await lq.start_quiz(message, uid)
        return
    await resume_after_life_quiz(
        message, uid, {"type": "awareness_scenario"}, state
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
    is_new_user: bool = False,
) -> None:
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    is_new = db.ensure_user(uid) or is_new_user
    welcome_bonus = False
    notify_referrer: int | None = None

    args = (command.args or "").strip()
    # Атрибуция first-touch для любого src_* — независимо от is_new
    # (set_signup_source не перезаписывает уже существующую метку).
    if args.lower().startswith("src_"):
        db.set_signup_source(uid, args[4:].lower())
    try:
        from oracle_bot.free_day import is_free_day_active, track_visit

        if is_free_day_active():
            track_visit(uid, args)
    except Exception as e:
        logger.warning("free_day track: %s", e)

    await message.answer(_start_text(uid), reply_markup=kb_main())

    if is_new:
        from oracle_bot.referrals import process_new_user
        from oracle_bot.pushes import schedule_inactive, schedule_welcome_series

        ok, notify_referrer = process_new_user(uid, command.args)
        welcome_bonus = ok and ORACLE_REFERRAL_WELCOME > 0
        ref_id = None
        start_args = (command.args or "").strip()
        source = None
        if start_args.lower().startswith("ref"):
            try:
                ref_id = int(start_args[3:])
            except ValueError:
                ref_id = None
        elif start_args.lower().startswith("src_"):
            source = start_args[4:].lower()
            db.set_signup_source(uid, source)
        analytics_mod.track_signup(uid, referred_by=ref_id if ok else None, source=source)
        schedule_welcome_series(uid)
        schedule_inactive(uid)
        try:
            from oracle_bot.admin_notify import notify_new_user

            await notify_new_user(message.bot, uid, message.from_user, start_args=command.args)
        except Exception as e:
            logger.warning("admin new user notify: %s", e)
    else:
        from oracle_bot.pushes import schedule_reengagement

        schedule_reengagement(uid)
        try:
            from oracle_bot.admin_notify import notify_return_visit

            await notify_return_visit(message.bot, uid, message.from_user, start_args=command.args)
        except Exception as e:
            logger.warning("admin return notify: %s", e)

    args = (command.args or "").strip()
    if args.lower().startswith("p_"):
        from oracle_bot.partners import handle_start_arg

        handle_start_arg(uid, args)
        if is_new:
            await message.answer(
                "👇 Сейчас открою <b>Таро</b> — задай один вопрос, первая часть бесплатно."
            )
            await _open_module(message, state, uid, "tarot")
        return
    if args == "free_day":
        await message.answer(
            "🎁 <b>Бесплатный день активен!</b>\n\n"
            "Все разделы без лимитов до конца дня. Выбери в /menu что протестировать."
        )
        return
    if args in {"premium", "buy", "pay"} or args.startswith("pay_"):
        # переход с сайта/лендинга на оплату премиума (касса открыта под бота)
        if args.startswith("pay_"):
            db.set_signup_source(uid, args[4:] or "site")
        await _offer_premium(message, uid)
        return
    if args in {"hvd", "exclusive", "exclusive_hvd"}:
        await _open_module(message, state, uid, "exclusive_hvd")
        return
    if args in {"ultra", "ultra_plus", "book"}:
        await _open_module(message, state, uid, "ultra_plus")
        return
    if args == "ref":
        await cmd_ref(message)
        return
    if args == "voice":
        await message.answer(
            "🎤 <b>Голосом — удобно с утра</b>\n\n"
            "Запиши голосовое: сон, вопрос к Таро, ситуация в отношениях — "
            "я распознаю и отвечу.\n\n"
            "Или выбери раздел в /menu и уточни голосом после расклада."
        )
        return
    if args.startswith("mod_"):
        await _open_module(message, state, uid, args[4:])
        return
    if _is_awareness_start(args):
        await _enter_awareness_funnel(message, state, uid)
        return

    if welcome_bonus:
        await message.answer(
            f"🎁 Добро пожаловать! +{ORACLE_REFERRAL_WELCOME} бонусный расклад за переход по ссылке друга."
        )

    if notify_referrer:
        try:
            from oracle_bot.referrals import apply_referral_milestone

            st = db.referral_stats(notify_referrer)
            await message.bot.send_message(
                notify_referrer,
                f"🎁 <b>Новый друг в Оракуле!</b>\n"
                f"+{ORACLE_REFERRAL_BONUS} бонусных расклада.\n"
                f"Всего приглашено: {st['invited']} · бонусов: {st['credits']}\n"
                f"/ref — твоя ссылка",
            )
            milestone = apply_referral_milestone(notify_referrer)
            if milestone:
                await message.bot.send_message(notify_referrer, milestone)
        except Exception as e:
            logger.warning("referral notify %s: %s", notify_referrer, e)


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await message.answer(
        f"🏓 pong — бот на связи\nuid: {uid}\n"
        f"https://moracul.onrender.com/health"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    await message.answer(analytics_mod.format_stats_report())


@router.message(Command("daily"))
async def cmd_daily(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    await message.answer(analytics_mod.format_daily_report())


@router.message(Command("funnel"))
async def cmd_funnel(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    await message.answer(analytics_mod.format_funnel_report())
    from oracle_bot.config import cloud_webapp_url

    base = cloud_webapp_url() or "https://moracul.onrender.com"
    await message.answer(
        f"📊 CRM-дашборд:\n<a href=\"{base}/admin?uid={uid}\">открыть воронку</a>",
        disable_web_page_preview=False,
    )


@router.message(Command("sources"))
async def cmd_sources(message: Message, command: CommandObject) -> None:
    """Атрибуция трафика: какой канал/ролик качает подписчиков и оплаты (метки src_*)."""
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    arg = (command.args or "").strip()
    days = int(arg) if arg.isdigit() else 30
    rows = db.signups_by_source(days)
    if not rows:
        await message.answer("Пока нет данных по источникам.")
        return
    lines = [f"📡 <b>Откуда трафик</b> (за {days} дн.)\n"]
    for r in rows[:25]:
        rub = int(r.get("rub") or 0)
        rub_part = f" · <b>{rub}₽</b>" if rub else ""
        lines.append(
            f"• <code>{r['source']}</code> — {r['users']} чел., "
            f"оплат {r['payers']}{rub_part}"
        )
    lines.append("\nМетки задаются в ссылке: <code>?start=src_КОД</code>")
    await message.answer("\n".join(lines))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    text = (command.args or "").strip()
    if len(text) < 2:
        await message.answer(
            "Рассылка всем пользователям бота:\n"
            "<code>/broadcast текст сообщения</code>\n\n"
            "Поддерживается HTML. Пример:\n"
            "<code>/broadcast 🌅 Доброе утро! Новый раздел — Карма дня.</code>"
        )
        return
    await _run_broadcast(message, text)


async def _run_broadcast(message: Message, text: str) -> None:
    import asyncio

    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    ids = db.all_user_ids()
    if not ids:
        await message.answer("Нет пользователей для рассылки.")
        return
    status = await message.answer(f"📤 Рассылка {len(ids)} пользователям…")
    ok = fail = 0
    for user_id in ids:
        try:
            await message.bot.send_message(user_id, text, parse_mode="HTML")
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            try:
                await message.bot.send_message(user_id, text, parse_mode="HTML")
                ok += 1
            except Exception:
                fail += 1
        except TelegramForbiddenError:
            fail += 1
        except Exception as e:
            logger.warning("broadcast %s: %s", user_id, e)
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Рассылка готова: доставлено {ok}, ошибок {fail}.")


@router.message(Command("promo_books"))
async def cmd_promo_books(message: Message, command: CommandObject) -> None:
    """Персональная рассылка рекламы ХВД + Ultra Plus в личку всем."""
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    variant = (command.args or "entry").strip().lower()
    if variant not in ("combo", "hvd", "ultra", "entry"):
        variant = "entry"
    from oracle_bot.ads import push_books_ad_to_all

    status = await message.answer(f"📤 Рассылаю рекламу книг ({variant}) в личку…")
    try:
        res = await push_books_ad_to_all(message.bot, variant=variant)
        await status.edit_text(
            f"✅ Реклама книг ({variant}): доставлено <b>{res['ok']}</b> из "
            f"{res['total']} (ошибок {res['fail']}, пропущено {res.get('skipped', 0)} — "
            "уже купили или отписались).\n"
            "⏱ Через час тем, кто не купил, автоматически включится отработка возражений."
        )
    except Exception as e:
        await status.edit_text(f"⚠️ Ошибка рассылки: {e}")


@router.message(Command("creatives"))
async def cmd_creatives(message: Message) -> None:
    """Готовые рекламные креативы для внешних каналов (копируй и постируй)."""
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    from oracle_bot.ads import EXTERNAL_CREATIVES

    await message.answer("📣 <b>Рекламные креативы для внешних каналов</b>\nНиже — по одному сообщению, можно пересылать/копировать:")
    for key, fn in EXTERNAL_CREATIVES.items():
        try:
            await message.answer(fn("ext"), disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001
            await message.answer(f"⚠️ {key}: {e}")


@router.message(Command("seed_week"))
async def cmd_seed_week(message: Message, command: CommandObject) -> None:
    """Пересобрать недельную очередь постов по каналам (ХВД/Ultra включены)."""
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    from datetime import date, timedelta

    from oracle_bot.channel_queue import seed_week_queue

    arg = (command.args or "").strip().lower()
    start = date.today() + timedelta(days=1) if arg in ("tomorrow", "завтра", "") else date.today()
    try:
        res = seed_week_queue(start_day=start, days=7, replace_pending=True)
        await message.answer(
            f"✅ Очередь каналов пересобрана с {res['start']} на {res['days']} дн.\n"
            f"Поставлено постов: <b>{res['enqueued']}</b> · в ожидании: {res['pending']}.\n"
            "Реклама ХВД и Ultra Plus включена в ротацию."
        )
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")


@router.message(Command("free_day"))
async def cmd_free_day(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        await message.answer("Нет доступа.")
        return
    from oracle_bot.free_day import format_campaign_report, msk_today, run_broadcast

    status = await message.answer("🎁 Запускаю бесплатный день и рассылку…")
    try:
        result = await run_broadcast(message.bot)
        day = result.get("day") or msk_today()
        await status.edit_text(
            f"✅ <b>Бесплатный день {day}</b>\n\n"
            f"📤 Рассылка: доставлено <b>{result.get('ok', 0)}</b> из {result.get('total', 0)} "
            f"(ошибок: {result.get('fail', 0)})\n\n"
            f"В полночь МСК придёт отчёт по акции.\n\n"
            f"<i>Превью метрик:</i>\n{format_campaign_report(day)[:400]}…"
        )
    except Exception as e:
        logger.exception("free_day")
        await status.edit_text(f"❌ Ошибка: {e}")


@router.message(Command("ref"))
async def cmd_ref(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    db.ensure_user(uid)
    from oracle_bot.referrals import stats_text

    await message.answer(stats_text(uid), reply_markup=kb_referral(uid))


@router.message(Command("partner"))
async def cmd_partner(message: Message) -> None:
    """Партнёрка 25% для админов пабликов: ссылка, статистика, выплата."""
    uid = message.from_user.id if message.from_user else 0
    db.ensure_user(uid)
    from oracle_bot.partners import partner_text

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💸 Запросить выплату", callback_data="partner:payout")]
        ]
    )
    await message.answer(partner_text(uid), reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data == "partner:payout")
async def cb_partner_payout(callback: CallbackQuery) -> None:
    uid = callback.from_user.id if callback.from_user else 0
    from oracle_bot.partners import MIN_PAYOUT_RUB

    st = db.partner_stats(uid)
    balance = st["balance_rub"]
    if balance < MIN_PAYOUT_RUB:
        await callback.answer(
            f"Минимальная выплата {MIN_PAYOUT_RUB}₽. Сейчас к выплате {balance}₽.",
            show_alert=True,
        )
        return
    db.create_partner_payout(uid, balance)
    await callback.answer("Заявка принята ✅")
    if callback.message:
        await callback.message.answer(
            f"💸 <b>Заявка на выплату {balance}₽ принята.</b>\n"
            "Напиши сюда номер телефона для СБП и название банка — "
            "переведём в течение 24 часов."
        )
    try:
        from oracle_bot.admin_notify import notify_admins

        await notify_admins(
            callback.bot,
            f"💸 <b>Заявка на выплату партнёру</b>\n"
            f"Партнёр <a href=\"tg://user?id={uid}\">{uid}</a> · <b>{balance}₽</b>\n"
            "Свяжись и переведи, затем отметь в БД partner_payouts → paid.",
        )
    except Exception as e:
        logger.warning("partner payout notify: %s", e)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    await message.answer(_start_text(uid), reply_markup=kb_main())


@router.message(Command("premium"))
async def cmd_premium(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await _offer_premium(message, uid)


@router.callback_query(F.data == "nav:menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    uid = call.from_user.id
    if call.message:
        await call.message.answer(_start_text(uid), reply_markup=kb_main())


@router.callback_query(F.data == "nav:awareness")
async def cb_nav_awareness(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    msg = call.message
    if not msg:
        return
    await msg.answer(
        "🔴 <b>Два сценария на 2 месяца</b>\n\n"
        "Покажу честно: что будет, если ничего не менять — "
        "и что изменится, если работать с картой.\n\n"
        "Сначала 4 коротких вопроса про твою ситуацию 👇"
    )
    from oracle_bot import life_quiz as lq

    lq.set_pending(uid, {"type": "awareness_scenario"})
    if not db.get_profile(uid).get("birth_date"):
        await state.set_state(Flow.prof_birth)
        await msg.answer(
            "📅 Напиши дату рождения:\n<i>ДД.ММ.ГГГГ</i> (можно с именем)"
        )
        return
    if lq.needs_quiz(uid):
        await lq.start_quiz(msg, uid)
        return
    await resume_after_life_quiz(msg, uid, {"type": "awareness_scenario"}, state)


@router.callback_query(F.data == "nav:mystic")
async def cb_mystic_menu(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        await call.message.answer(
            "🔯 Дополнительные разделы — карма, чакры, лунные циклы и др.",
            reply_markup=kb_mystic(),
        )


@router.callback_query(F.data == "mod:premium")
async def cb_premium(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    if uid:
        analytics_mod.track_click(uid, "mod:premium")
    if call.message:
        await _offer_premium(call.message, uid)


@router.callback_query(F.data == "stars:premium")
async def cb_stars_premium(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        await _send_premium_invoice(call.message)


@router.callback_query(F.data.startswith("stars:deep:"))
async def cb_stars_deep(call: CallbackQuery) -> None:
    await call.answer()
    try:
        cont_id = int((call.data or "").split(":")[2])
    except (IndexError, ValueError):
        return
    if call.message:
        await _send_deep_invoice(call.message, cont_id)


@router.callback_query(F.data == "mod:referral")
async def cb_referral(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    db.ensure_user(uid)
    from oracle_bot.referrals import stats_text

    if call.message:
        await call.message.answer(stats_text(uid), reply_markup=kb_referral(uid))


@router.callback_query(F.data.startswith("deep:"))
async def cb_deep(call: CallbackQuery) -> None:
    await call.answer()
    cont_id = int((call.data or "").split(":", 1)[1])
    uid = call.from_user.id
    analytics_mod.track_click(uid, f"deep:{cont_id}")
    if db.is_premium(uid) or is_admin_user(uid):
        cont = db.get_continuation(cont_id)
        if cont and call.message:
            await call.message.answer(
                funnel.format_full(cont["teaser_text"], cont["locked_text"]),
                reply_markup=kb_after_reading(cont["module"], None, uid),
            )
        return
    if call.message:
        await _offer_deep(call.message, uid, cont_id)


@router.callback_query(F.data == "ask:start")
async def cb_ask_start(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    if uid:
        analytics_mod.track_click(uid, "ask:start")
    from oracle_bot.dialogue import has_context

    if call.message:
        if has_context(uid):
            await call.message.answer(
                "💬 Напиши свой вопрос по разбору — отвечу как личный ассистент, "
                "опираясь на твои данные. Например: «что это значит для отношений?», "
                "«с чего начать?», «как это в деньгах?»"
            )
        else:
            await call.message.answer(
                "Сначала сделай любой разбор в /menu — потом сможешь задавать "
                "уточняющие вопросы по нему."
            )


async def _offer_pdf(message: Message, uid: int, kind: str, price: int, title: str) -> None:
    url = _robokassa_url(uid, kind)
    if not url:
        await message.answer("Оплата картой временно недоступна. Напиши администратору.")
        return
    if uid:
        analytics_mod.track_payment_intent(uid, kind)
    rows = [
        [InlineKeyboardButton(text=f"💳 Картой/СБП — {price}₽", url=url)],
        [InlineKeyboardButton(text="📄 Оферта", url=_oferta_link())],
    ]
    await message.answer(
        f"📄 <b>{title}</b>\n\n"
        "Аккуратный PDF-файл с твоим разбором — можно сохранить, распечатать "
        "или подарить. Оформляется отдельно.\n\nВыбери способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "pdf:reading")
async def cb_pdf_reading(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    if uid:
        analytics_mod.track_click(uid, "pdf:reading")
    if not db.get_pdf_source(uid, "pdf_reading"):
        if call.message:
            await call.message.answer("Сначала сделай разбор — потом сохраню его в PDF.")
        return
    if not call.message:
        return
    if is_admin_user(uid):
        from oracle_bot.pdf_export import deliver_pdf

        await call.message.answer("👑 Админ — отправляю PDF без оплаты…")
        await deliver_pdf(call.message.bot, uid, "pdf_reading")
        return
    await _offer_pdf(call.message, uid, "pdf_reading", ORACLE_PDF_READING_PRICE_RUB, "Разбор в PDF")


@router.callback_query(F.data == "pdf:hvd")
async def cb_pdf_hvd(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    if uid:
        analytics_mod.track_click(uid, "pdf:hvd")
    if not db.get_pdf_source(uid, "pdf_hvd"):
        if call.message:
            await call.message.answer("Сначала получи разбор ХВД — потом соберу книгу PDF.")
        return
    if not call.message:
        return
    if is_admin_user(uid):
        from oracle_bot.pdf_export import deliver_pdf

        await call.message.answer("👑 Админ — отправляю книгу PDF без оплаты…")
        await deliver_pdf(call.message.bot, uid, "pdf_hvd")
        return
    await _offer_pdf(call.message, uid, "pdf_hvd", ORACLE_PDF_HVD_PRICE_RUB, "ХВД — книга PDF")


_OBJ_LABEL = {"exclusive_hvd": "Эксклюзив ХВД", "ultra_plus": "Ultra Plus — Книга о тебе"}
_OBJ_BASE_PRICE = {"exclusive_hvd": ORACLE_EXCLUSIVE_HVD_PRICE_RUB, "ultra_plus": ORACLE_ULTRA_PLUS_PRICE_RUB}


@router.callback_query(F.data.startswith("obj:"))
async def cb_objection(call: CallbackQuery) -> None:
    """Ответ на вопрос воронки отработки возражений (obj_ask): почему не купил(а)."""
    await call.answer()
    if not call.message:
        return
    uid = call.from_user.id if call.from_user else 0
    parts = (call.data or "").split(":")
    reason = parts[1] if len(parts) > 1 else ""
    kind = parts[2] if len(parts) > 2 else ""
    label = _OBJ_LABEL.get(kind, "продукт")
    base = _OBJ_BASE_PRICE.get(kind, 0)
    if uid:
        analytics_mod.track_click(uid, f"obj:{reason}:{kind}")

    if reason == "bought":
        from oracle_bot.pushes import cancel_objection_flow

        cancel_objection_flow(uid, kind)
        await call.message.answer("🙏 Отлично, спасибо! Если что-то ещё понадобится — я рядом.")
        return

    price20 = max(int(base * 0.8), 99)
    url = _robokassa_url(uid, kind, override_amount=price20) if uid else None
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        rows.append([InlineKeyboardButton(text=f"💳 Забрать за {price20}₽ (−20%, лично тебе)", url=url)])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if reason == "price":
        text = (
            f"Понимаю 🙏 Тогда держи персональную скидку на «{label}»: "
            f"<s>{base}₽</s> → <b>{price20}₽</b> (−20%). Предложение только для тебя "
            "и только сейчас — потом такой цены не будет."
        )
    elif reason == "fit":
        text = (
            f"«{label}» — это не общие фразы, а разбор именно ТВОИХ данных: даты рождения "
            "и уникального кода. Люди обычно находят там то, что интуитивно чувствовали, "
            "но не могли сформулировать про себя. Заодно — скидка, чтобы решиться проще: "
            f"<s>{base}₽</s> → <b>{price20}₽</b>."
        )
    else:  # later / неизвестная причина
        text = (
            "Хорошо, не тороплю 🙏 Просто чтобы не забыть: держи персональную скидку "
            f"на «{label}» — <s>{base}₽</s> → <b>{price20}₽</b>. Она сгорит, если отложить надолго."
        )
    await call.message.answer(text, reply_markup=kb)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    payload = query.invoice_payload or ""
    uid = query.from_user.id if query.from_user else 0
    if payload == "premium_30d":
        if uid:
            analytics_mod.track_checkout(uid, "premium_30d")
        await query.answer(ok=True)
        return
    if payload.startswith("deep:"):
        try:
            cid = int(payload.split(":", 1)[1])
        except ValueError:
            await query.answer(ok=False, error_message="Неверный платёж")
            return
        cont = db.get_continuation(cid)
        if cont and cont["user_id"] == query.from_user.id:
            if uid:
                analytics_mod.track_checkout(uid, f"deep:{cid}")
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="Чтение не найдено")
        return
    await query.answer(ok=False, error_message="Неизвестный платёж")


@router.message(F.successful_payment)
async def paid(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    payload = message.successful_payment.invoice_payload if message.successful_payment else ""

    if payload == "premium_30d":
        db.grant_premium(uid, days=30)
        analytics_mod.track_payment(uid, "premium_30d", ORACLE_PREMIUM_STARS, payload)
        db.cancel_pushes(uid, ["unlock_tease", "limit_hit", "welcome_day1", "welcome_day2", "inactive", "referral_nudge"])
        from oracle_bot.pushes import schedule_premium_renewal

        schedule_premium_renewal(uid, days=30)
        try:
            from oracle_bot.revenue_bridge import notify_admins

            await notify_admins(
                message.bot,
                f"💰 <b>Оракул: Премиум</b>\n"
                f"User {uid} · {ORACLE_PREMIUM_STARS}⭐\n\n"
                + analytics_mod.format_stats_report(),
            )
        except Exception as e:
            logger.warning("admin pay notify: %s", e)
        await message.answer(
            "✅ <b>Премиум 30 дней!</b>\n"
            "Все разделы без лимита · продолжения без 🔒\n"
            "Выбирай что угодно 👇",
            reply_markup=kb_main(),
        )
        return

    if payload.startswith("deep:"):
        cid = int(payload.split(":", 1)[1])
        cont = db.unlock_continuation(cid, uid)
        if not cont:
            await message.answer("Чтение не найдено.", reply_markup=kb_main())
            return
        analytics_mod.track_payment(uid, "deep_unlock", ORACLE_DEEP_STARS, payload)
        db.cancel_pushes(uid, ["unlock_tease", "limit_hit"])
        try:
            from oracle_bot.revenue_bridge import notify_admins

            await notify_admins(
                message.bot,
                f"💰 <b>Оракул: 🔓 Продолжение</b>\n"
                f"User {uid} · {ORACLE_DEEP_STARS}⭐ · cont {cid}",
            )
        except Exception as e:
            logger.warning("admin pay notify: %s", e)
        await message.answer(
            "🔓 <b>Продолжение открыто:</b>\n\n" + cont["locked_text"],
            reply_markup=kb_after_reading(cont["module"], None, uid),
        )


@router.callback_query(F.data.startswith("mod:"))
async def pick_module(call: CallbackQuery, state: FSMContext) -> None:
    mod = (call.data or "").split(":", 1)[-1]
    await call.answer()
    uid = call.from_user.id if call.from_user else 0
    if uid and mod not in ("premium", "referral"):
        analytics_mod.track_click(uid, f"mod:{mod}")
        analytics_mod.track_push_open(uid, mod)
    if mod in ("premium", "referral") or not call.message:
        return
    await _open_module(call.message, state, call.from_user.id, mod)


async def _open_module(
    msg: Message,
    state: FSMContext | None,
    uid: int,
    mod: str,
    *,
    skip_quiz: bool = False,
) -> None:
    if not mod:
        await msg.answer("Выбери раздел в меню 👇", reply_markup=kb_main())
        return
    blocked = await _guard(uid, mod)
    if blocked:
        await msg.answer(blocked, reply_markup=kb_limit_reached(uid))
        return
    if not skip_quiz and mod not in (
        "profile", "premium", "referral", "exclusive_hvd", "ultra_plus",
    ):
        from oracle_bot import life_quiz as lq

        if lq.needs_quiz(uid):
            lq.set_pending(uid, {"type": "open_module", "mod": mod})
            await lq.start_quiz(msg, uid)
            return

    if mod == "horo_today":
        await msg.answer("🌅 Выбери знак для гороскопа на сегодня:", reply_markup=kb_zodiac("htoday"))
    elif mod == "horo_week":
        await msg.answer("📅 Знак для прогноза на неделю:", reply_markup=kb_zodiac("hweek"))
    elif mod == "card_day":
        from oracle_bot.card_of_day import format_card_message

        await msg.answer(format_card_message(uid), reply_markup=kb_main())
    elif mod == "destiny":
        await _destiny_pick(msg, uid, state)
    elif mod == "portrait":
        await state.set_state(Flow.portrait_birth)
        await msg.answer("🎂 Дата рождения (ДД.ММ.ГГГГ), можно с именем:\n<i>15.03.1990 Анна</i>")
    elif mod == "numerology":
        await state.set_state(Flow.numerology_input)
        await msg.answer("🔢 Имя и дата рождения:\n<i>Анна 15.03.1990</i>")
    elif mod == "chinese":
        await state.set_state(Flow.chinese_birth)
        await msg.answer("🐉 Дата рождения (ДД.ММ.ГГГГ):")
    elif mod == "tarot":
        await state.set_state(Flow.tarot_question)
        await msg.answer("🔮 Вопрос для расклада (или «без вопроса»):")
    elif mod == "compat":
        await state.set_state(Flow.compat_dates)
        await msg.answer("💕 Две даты рождения:\n<i>15.03.1990 22.07.1992</i>")
    elif mod == "palm":
        await state.set_state(Flow.palm_wait)
        await msg.answer("🖐 Фото ладони (можно с подписью) 📷")
    elif mod == "dream":
        await state.set_state(Flow.dream_text)
        await msg.answer("🌙 Опиши сон — даже обрывками:")
    elif mod == "dating":
        await state.set_state(Flow.dating_text)
        await msg.answer("💬 Ситуация: с кем, что случилось, чего хочешь:")
    elif mod == "psychology":
        await state.set_state(Flow.psychology_text)
        await msg.answer(
            "🧠 <b>Психолог онлайн</b>\n\n"
            "Опиши, что беспокоит: тревога, выгорание, отношения, самооценка.\n"
            "<i>Не заменяет очного врача при кризисе.</i>"
        )
    elif mod == "career":
        await state.set_state(Flow.career_text)
        await msg.answer("💼 Работа/деньги: чем занят, что болит, чего хочешь:")
    elif mod == "yesno":
        await state.set_state(Flow.yesno_question)
        await msg.answer("🎲 Задай чёткий вопрос (Да/Нет):")
    elif mod == "rune":
        await _rune_now(msg, uid)
    elif mod == "profile":
        await _profile_show(msg, uid)
    elif mod == "natal":
        await state.set_state(Flow.natal_input)
        await msg.answer(
            "🌌 <b>Натальная карта</b>\n\n"
            "Дата, время (если знаешь), город:\n"
            "<i>15.03.1990 14:30 Москва</i>\n\n"
            "Или заполни 👤 Профиль и нажми «Натальная по профилю»."
        )
    elif mod == "past_life":
        await state.set_state(Flow.past_life_focus)
        await msg.answer(
            "🕰 <b>Прошлые жизни</b>\n\n"
            "Напиши фокус (или «общий поиск»):\n"
            "<i>почему боюсь воды · кем был в прошлом · кармический партнёр</i>"
        )
    elif mod == "karma":
        await _instant(msg, uid, "karma", mf.karma_prompt, need_profile=True)
    elif mod == "akashic":
        await _instant(msg, uid, "akashic", mf.akashic_prompt, need_profile=True)
    elif mod == "iching":
        await state.set_state(Flow.iching_question)
        await msg.answer("☯️ Вопрос для И-Цзин (или «сегодня»):")
    elif mod == "lenormand":
        await state.set_state(Flow.lenormand_question)
        await msg.answer("🦋 Вопрос для Ленорман (или «без вопроса»):")
    elif mod == "chakra":
        await _instant(msg, uid, "chakra", mf.chakra_prompt)
    elif mod == "aura":
        await _instant(msg, uid, "aura", mf.aura_prompt, need_profile=True)
    elif mod == "spirit_guide":
        await _instant(msg, uid, "spirit_guide", mf.spirit_guide_prompt)
    elif mod == "moon":
        await _instant(msg, uid, "moon", mf.moon_prompt)
    elif mod == "crystal":
        await _instant(msg, uid, "crystal", mf.crystal_prompt)
    elif mod == "shadow":
        await _instant(msg, uid, "shadow", mf.shadow_prompt, need_profile=True)
    elif mod == "twin_flame":
        await state.set_state(Flow.twin_flame_text)
        await msg.answer("🔥 Опиши связь / человека / ощущение родственной души:")
    elif mod == "biorhythm":
        await _instant(msg, uid, "biorhythm", mf.biorhythm_prompt, need_profile=True)
    elif mod == "transit":
        await _instant(msg, uid, "transit", mf.transit_prompt, need_profile=True)
    elif mod == "family_karma":
        await state.set_state(Flow.family_karma_text)
        await msg.answer("🧬 Что повторяется в роду / семье? Страхи, сценарии, отношения:")
    elif mod == "exclusive_hvd":
        await _prompt_book_input(
            msg, uid, state, "hvd",
            "🔮 <b>Эксклюзив: полный курс ХВД</b>\n\n"
            "Хронально-Векторная Диагностика — весь обучающий курс в одном отчёте:\n"
            "типология, чакры, контуры, инь/ян, периоды жизни, код негатива/позитива, "
            "задачи, эгоизм/альтруизм, реабилитация.\n\n"
            f"💳 <b>{ORACLE_EXCLUSIVE_HVD_PRICE_RUB}₽</b> — отдельно от Премиум",
            "<i>Анна 15.03.1990</i>",
        )
    elif mod == "ultra_plus":
        await _prompt_book_input(
            msg, uid, state, "ultra",
            "📖 <b>Ultra Plus — Книга о тебе</b>\n\n"
            "Персональная книга в PDF по Матрице Судьбы (22 аркана):\n"
            "личные качества, таланты, предназначение, деньги, кармические программы, "
            "отношения, здоровье, прогноз на год.\n\n"
            f"💳 <b>{ORACLE_ULTRA_PLUS_PRICE_RUB}₽</b> — отдельно от Премиум",
            "<i>Степан 21.06.1994</i>",
        )


async def _destiny_pick(msg: Message, uid: int, state: FSMContext) -> None:
    p = db.get_profile(uid)
    if p.get("zodiac"):
        await _destiny_run(msg, uid, p["zodiac"])
        return
    await msg.answer("✨ Выбери знак для судьбы дня:", reply_markup=kb_zodiac("dest"))


async def _destiny_run(msg: Message, uid: int, sign_key: str) -> None:
    ctx = _profile_ctx(uid)
    label, period = ZODIAC_BY_KEY.get(sign_key, (sign_key, ""))
    prompt = DESTINY_DAY.format(
        sign=f"{label} ({period})",
        name=ctx["name"],
        today=date.today().strftime("%d.%m.%Y"),
    )
    await _send_reading(
        msg,
        uid=uid,
        module="destiny",
        prompt=prompt,
        header=reading_header("Судьба дня", label),
    )


async def _rune_now(msg: Message, uid: int) -> None:
    rune = random.choice(RUNES)
    ctx = _profile_ctx(uid)
    prompt = RUNE.format(
        rune=rune,
        context=f"Знак: {ctx['sign']}, дата: {date.today().isoformat()}",
    )
    await _send_reading(
        msg,
        uid=uid,
        module="rune",
        prompt=prompt,
        header=reading_header("Руна дня", rune),
    )


async def _profile_show(msg: Message, uid: int) -> None:
    p = db.get_profile(uid)
    text = (
        "👤 <b>Твой профиль</b>\n\n"
        f"Имя: {p.get('name') or '—'}\n"
        f"Дата: {p.get('birth_date') or '—'}\n"
        f"Время: {p.get('birth_time') or '—'}\n"
        f"Место: {p.get('birth_place') or '—'}\n"
        f"Знак: {zodiac_label(p['zodiac']) if p.get('zodiac') else '—'}\n"
    )
    if p.get("relationship_status"):
        text += f"Отношения: {p['relationship_status']}\n"
    if p.get("work_status"):
        text += f"Работа: {p['work_status']}\n"
    if p.get("pain_focus"):
        text += f"Болит: {p['pain_focus']}\n"
    if p.get("about_text"):
        text += f"О себе: {p['about_text'][:120]}\n"
    text += "\n<i>Профиль усиляет все разборы — чем точнее, тем персональнее ответ.</i>"
    await msg.answer(
        text,
        reply_markup=kb_profile(bool(p.get("birth_date"))),
    )


@router.callback_query(F.data.startswith("htoday:"))
async def cb_horo_today(call: CallbackQuery) -> None:
    sign = (call.data or "").split(":", 1)[1]
    await call.answer("Читаю…")
    uid = call.from_user.id if call.from_user else 0
    msg = await _callback_chat(call)
    if not msg:
        return
    blocked = await _guard(uid, "horo_today")
    if blocked:
        await msg.answer(blocked, reply_markup=kb_limit_reached(uid))
        return
    label, period = ZODIAC_BY_KEY[sign]
    db.save_profile(uid, zodiac=sign)
    wait = await msg.answer(_WAIT.get("horo_today", "🌅 Смотрю звёзды…"))
    await _send_reading(
        msg,
        uid=uid,
        module="horo_today",
        prompt=HORO_TODAY.format(sign=label, sign_period=period),
        header=reading_header("Сегодня", label),
        wait_msg=wait,
    )


@router.callback_query(F.data.startswith("hweek:"))
async def cb_horo_week(call: CallbackQuery) -> None:
    sign = (call.data or "").split(":", 1)[1]
    await call.answer("Читаю…")
    uid = call.from_user.id if call.from_user else 0
    msg = await _callback_chat(call)
    if not msg:
        return
    blocked = await _guard(uid, "horo_week")
    if blocked:
        await msg.answer(blocked, reply_markup=kb_limit_reached(uid))
        return
    label, _ = ZODIAC_BY_KEY[sign]
    wait = await msg.answer(_WAIT.get("horo_week", "📅 Раскладываю неделю…"))
    await _send_reading(
        msg,
        uid=uid,
        module="horo_week",
        prompt=HORO_WEEK.format(sign=label),
        header=reading_header("Неделя", label),
        wait_msg=wait,
    )


@router.callback_query(F.data.startswith("dest:"))
async def cb_destiny(call: CallbackQuery) -> None:
    sign = (call.data or "").split(":", 1)[1]
    await call.answer("Читаю…")
    uid = call.from_user.id if call.from_user else 0
    msg = await _callback_chat(call)
    if not msg:
        return
    blocked = await _guard(uid, "destiny")
    if blocked:
        await msg.answer(blocked, reply_markup=kb_limit_reached(uid))
        return
    db.save_profile(uid, zodiac=sign)
    await _destiny_run(msg, uid, sign)


@router.callback_query(F.data == "prof:natal_data")
async def cb_prof_natal_data(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Flow.prof_natal_data)
    if call.message:
        await call.message.answer("🕐 Время и город рождения:\n<i>14:30 Москва</i>")


@router.callback_query(F.data == "prof:natal")
async def cb_prof_natal(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    p = db.get_profile(uid)
    if not p.get("birth_date") and call.message:
        await call.message.answer("Сначала укажи дату рождения.", reply_markup=kb_profile(False))
        return
    if call.message:
        raw = f"{p.get('birth_date', '')} {p.get('birth_time') or ''} {p.get('birth_place') or ''}"
        built = mf.natal_prompt(uid, raw)
        if not built:
            await call.message.answer("Не хватает даты.", reply_markup=kb_profile(True))
            return
        prompt, header = built
        await _send_reading(call.message, uid=uid, module="natal", prompt=prompt, header=header)


@router.callback_query(F.data == "prof:birth")
async def cb_prof_birth(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Flow.prof_birth)
    if call.message:
        await call.message.answer("📅 Дата рождения (ДД.ММ.ГГГГ):")


@router.callback_query(F.data == "prof:name")
async def cb_prof_name(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Flow.prof_name)
    if call.message:
        await call.message.answer("✏️ Как тебя звать?")


@router.callback_query(F.data == "prof:horo")
async def cb_prof_horo(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    p = db.get_profile(uid)
    if not p.get("zodiac") and call.message:
        await call.message.answer("Сначала укажи дату рождения.", reply_markup=kb_profile(True))
        return
    if call.message:
        sign = p["zodiac"]
        label, period = ZODIAC_BY_KEY[sign]
        await _send_reading(
            call.message,
            uid=uid,
            module="horo_today",
            prompt=HORO_TODAY.format(sign=label, sign_period=period),
            header=reading_header("Гороскоп", label),
        )


async def _continue_awareness_after_birth(
    message: Message,
    uid: int,
    state: FSMContext,
) -> bool:
    """После ввода даты — продолжить рекламную воронку, если ждали её."""
    from oracle_bot import life_quiz as lq

    pending = lq.peek_pending(uid)
    if not pending or pending.get("type") != "awareness_scenario":
        return False
    if lq.needs_quiz(uid):
        await lq.start_quiz(message, uid)
    else:
        await resume_after_life_quiz(
            message, uid, {"type": "awareness_scenario"}, state
        )
    return True


@router.message(Flow.prof_birth)
async def prof_birth_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = (message.text or "").strip()
    bd = parse_birth_date(text)
    if not bd:
        await message.answer("Формат: 15.03.1990")
        return
    sign = zodiac_from_date(bd)
    name = text.replace(bd.strftime("%d.%m.%Y"), "").replace(
        bd.strftime("%d.%m.%y"), ""
    ).strip()[:40]
    db.save_profile(
        uid,
        birth_date=bd.strftime("%d.%m.%Y"),
        zodiac=sign,
        name=name if len(name) >= 2 else None,
    )
    await state.clear()
    if await _continue_awareness_after_birth(message, uid, state):
        return
    await message.answer(
        f"✅ Сохранено: {bd.strftime('%d.%m.%Y')} · {zodiac_label(sign)}",
        reply_markup=kb_profile(True),
    )


@router.message(Flow.prof_name)
async def prof_name_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    name = (message.text or "").strip()[:40]
    if len(name) < 2:
        await message.answer("Имя покороче 🙂")
        return
    db.save_profile(uid, name=name)
    await state.clear()
    await message.answer(f"✅ Имя: {name}", reply_markup=kb_profile(True))


@router.message(Flow.portrait_birth)
async def portrait_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "portrait")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    text = message.text or ""
    bd = parse_birth_date(text)
    if not bd:
        await message.answer("Нужна дата: 15.03.1990")
        return
    sign = zodiac_from_date(bd)
    name = re.sub(_DATE_RE, "", text).strip() or _profile_ctx(uid)["name"]
    db.save_profile(uid, birth_date=bd.strftime("%d.%m.%Y"), zodiac=sign, name=name if name != "не указано" else None)
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="portrait",
        prompt=PORTRAIT.format(
            birth=bd.strftime("%d.%m.%Y"),
            sign=zodiac_label(sign),
            name=name,
        ),
        header=reading_header("Портрет", name),
    )


@router.message(Flow.numerology_input)
async def numerology_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "numerology")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    text = message.text or ""
    bd = parse_birth_date(text)
    if not bd:
        await message.answer("Нужны имя и дата: Анна 15.03.1990")
        return
    name = re.sub(_DATE_RE, "", text).strip() or "Гость"
    lp = life_path_number(bd)
    day_n = sum(int(c) for c in date.today().strftime("%d%m%Y"))
    while day_n > 9:
        day_n = sum(int(c) for c in str(day_n))
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="numerology",
        prompt=NUMEROLOGY.format(
            name=name,
            birth=bd.strftime("%d.%m.%Y"),
            life_path=lp,
            day_num=day_n,
        ),
        header=reading_header("Числа судьбы", f"путь {lp}"),
    )


def _saved_profile_for_book(uid: int) -> tuple[str, "date"] | None:
    """Если в профиле уже есть имя и дата рождения — вернуть (имя, дата)."""
    p = db.get_profile(uid)
    name = (p.get("name") or "").strip()
    bd_iso = (p.get("birth_date") or "").strip()
    if not name or name.lower() in ("гость", "guest", "не указано") or not bd_iso:
        return None
    try:
        bd = datetime.strptime(bd_iso, "%Y-%m-%d").date()
    except ValueError:
        bd = parse_birth_date(bd_iso)
    if not bd:
        return None
    return name, bd


async def _prompt_book_input(
    msg: Message, uid: int, state: FSMContext, kind: str, intro: str, example: str
) -> None:
    """Показывает оффер. Если имя+дата уже есть — кнопка автоподстановки вместо повторного ввода."""
    saved = _saved_profile_for_book(uid)
    if saved:
        name, bd = saved
        bd_h = bd.strftime("%d.%m.%Y")
        rows = [
            [InlineKeyboardButton(
                text=f"✅ {name}, {bd_h}", callback_data=f"bookuse:{kind}"
            )],
            [InlineKeyboardButton(
                text="✏️ Другие имя и дата", callback_data=f"booknew:{kind}"
            )],
        ]
        await state.clear()
        await msg.answer(
            f"{intro}\n\nИспользовать твои данные — <b>{name}, {bd_h}</b>?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return
    await state.set_state(Flow.hvd_input if kind == "hvd" else Flow.ultra_plus_input)
    await msg.answer(f"{intro}\n\nВведи имя и дату рождения:\n{example}")


async def _start_hvd(msg: Message, uid: int, name: str, bd: "date") -> None:
    from oracle_bot.exclusive_hvd import build_teaser, calculate
    from oracle_bot.exclusive_hvd.delivery import deliver_hvd_report

    try:
        profile = calculate(name, bd)
    except ValueError as e:
        await msg.answer(f"⚠️ {e}")
        return
    db.save_hvd_pending(uid, name, bd.isoformat())
    analytics_mod.track_reading(uid, "exclusive_hvd", has_lock=True)
    await msg.answer(build_teaser(profile))
    if is_admin_user(uid):
        await msg.answer("👑 Админ — полный разбор ХВД без оплаты…")
        await deliver_hvd_report(msg.bot, uid)
        return
    await _offer_exclusive_hvd(msg, uid)


async def _start_ultra(msg: Message, uid: int, name: str, bd: "date") -> None:
    from oracle_bot.ultra_plus import build_teaser, calculate
    from oracle_bot.ultra_plus.delivery import deliver_ultra_plus_book

    try:
        profile = calculate(name, bd)
    except ValueError as e:
        await msg.answer(f"⚠️ {e}")
        return
    db.save_ultra_plus_pending(uid, name, bd.isoformat())
    analytics_mod.track_reading(uid, "ultra_plus", has_lock=True)
    await msg.answer(build_teaser(profile))
    if is_admin_user(uid):
        await msg.answer("👑 Админ — отправляю PDF без оплаты…")
        await deliver_ultra_plus_book(msg.bot, uid)
        return
    await _offer_ultra_plus(msg, uid)


@router.callback_query(F.data.startswith("bookuse:"))
async def cb_book_use_saved(call: CallbackQuery, state: FSMContext) -> None:
    kind = (call.data or "").split(":", 1)[1]
    uid = call.from_user.id if call.from_user else 0
    await call.answer()
    await state.clear()
    msg = await _callback_chat(call)
    if not msg:
        return
    saved = _saved_profile_for_book(uid)
    if not saved:
        await state.set_state(Flow.hvd_input if kind == "hvd" else Flow.ultra_plus_input)
        await msg.answer("Введи имя и дату рождения:\n<i>Имя 15.03.1990</i>")
        return
    name, bd = saved
    if kind == "hvd":
        await _start_hvd(msg, uid, name, bd)
    else:
        await _start_ultra(msg, uid, name, bd)


@router.callback_query(F.data.startswith("booknew:"))
async def cb_book_new_data(call: CallbackQuery, state: FSMContext) -> None:
    kind = (call.data or "").split(":", 1)[1]
    await call.answer()
    msg = await _callback_chat(call)
    if not msg:
        return
    await state.set_state(Flow.hvd_input if kind == "hvd" else Flow.ultra_plus_input)
    example = "<i>Анна 15.03.1990</i>" if kind == "hvd" else "<i>Степан 21.06.1994</i>"
    await msg.answer(f"Введи имя и дату рождения:\n{example}")


@router.message(Flow.hvd_input)
async def exclusive_hvd_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = message.text or ""
    bd = parse_birth_date(text)
    if not bd:
        await message.answer("Формат: <i>Анна 15.03.1990</i> или <i>15.03.1990</i>")
        return
    name = re.sub(_DATE_RE, "", text).strip() or "Гость"
    await state.clear()
    await _start_hvd(message, uid, name, bd)


@router.message(Flow.ultra_plus_input)
async def ultra_plus_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = message.text or ""
    bd = parse_birth_date(text)
    if not bd:
        await message.answer("Формат: <i>Степан 21.06.1994</i> или <i>21.06.1994</i>")
        return
    name = re.sub(_DATE_RE, "", text).strip() or "Гость"
    await state.clear()
    await _start_ultra(message, uid, name, bd)


@router.message(Flow.chinese_birth)
async def chinese_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "chinese")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    bd = parse_birth_date(message.text or "")
    if not bd:
        await message.answer("Дата: 15.03.1990")
        return
    animal = chinese_animal(bd.year)
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="chinese",
        prompt=CHINESE.format(
            animal=animal,
            year=bd.year,
            birth=bd.strftime("%d.%m.%Y"),
        ),
        header=reading_header(animal, str(bd.year)),
    )


@router.message(Flow.tarot_question)
async def tarot_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "tarot")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    q = (message.text or "").strip() or "общий вектор на ближайшее время"
    cards = random.sample(MAJOR_ARCANA, 3)
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="tarot",
        prompt=TAROT_USER.format(cards=", ".join(cards), question=q),
        header=reading_header("Таро", ", ".join(cards)),
        temperature=0.85,
    )


@router.message(Flow.compat_dates)
async def compat_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "compat")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    dates = _DATE_RE.findall(message.text or "")
    if len(dates) < 2:
        await message.answer("Две даты: 15.03.1990 22.07.1992")
        return
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="compat",
        prompt=COMPAT_USER.format(d1=dates[0], d2=dates[1]),
        header=reading_header("Совместимость"),
    )


@router.message(Flow.palm_wait, F.photo)
async def palm_photo(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "palm")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    from bot.services.vision import download_photo_bytes, pick_largest_photo

    photo = pick_largest_photo(message.photo)
    wait = await message.answer(_WAIT["palm"])
    try:
        data = await download_photo_bytes(message.bot, photo.file_id)
        raw = await oracle_palm_reading(
            data,
            comment=message.caption or "",
            premium=has_full_access(uid),
        )
        text, cont_id = funnel.deliver(
            user_id=uid,
            module="palm",
            raw_text=raw,
            header=reading_header("Хиромантия"),
        )
    except Exception as e:
        logger.exception("palm")
        msg = str(e).replace("LLMError: ", "")
        await wait.edit_text(f"Не удалось прочитать ладонь: {msg}")
        await state.clear()
        return
    db.bump_usage(uid, "palm")
    premium = has_full_access(uid)
    analytics_mod.track_reading(uid, "palm", has_lock=bool(cont_id and not premium))
    if cont_id and not premium:
        from oracle_bot.pushes import schedule_after_teaser

        schedule_after_teaser(uid, "palm", cont_id)
    db.touch_user(uid, module="palm")
    try:
        from oracle_bot.coach import reading_footer

        footer = await reading_footer(
            uid=uid,
            module="palm",
            reading_text=text,
            user_text=message.caption or "",
        )
        if footer:
            text = text + footer
    except Exception as e:
        logger.warning("footer palm: %s", e)
    await wait.edit_text(text, reply_markup=kb_after_reading("palm", cont_id, uid))
    from oracle_bot.dialogue import build_reading_context

    db.save_session(
        uid,
        module="palm",
        snippet=text[:500],
        last_context=build_reading_context(text, cont_id, uid),
    )
    try:
        from oracle_bot.coach import after_reading_coach

        await after_reading_coach(
            message,
            uid=uid,
            module="palm",
            reading_text=text,
            user_text=message.caption or "",
            cont_id=cont_id,
        )
    except Exception as e:
        logger.warning("coach palm: %s", e)
    await state.clear()


@router.message(Flow.palm_wait)
async def palm_need_photo(message: Message) -> None:
    await message.answer("Нужно фото ладони 📷")


@router.message(Flow.dream_text)
async def dream_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "dream")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 10:
        await message.answer("Опиши сон чуть подробнее 🌙")
        return
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="dream",
        prompt=DREAM.format(dream=txt),
        header=reading_header("Сонник"),
    )


@router.message(Flow.dating_text)
async def dating_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "dating")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 5:
        await message.answer("Расскажи чуть подробнее 🙂")
        return
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="dating",
        prompt=DATING_USER.format(text=txt),
        header=reading_header("Любовь и отношения"),
    )


@router.message(Flow.psychology_text)
async def psychology_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "psychology")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 10:
        await message.answer("Расскажи подробнее — хотя бы 2–3 предложения.")
        return
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="psychology",
        prompt=PSYCHOLOGY_USER.format(text=txt),
        header=reading_header("Психолог"),
    )


@router.message(Flow.career_text)
async def career_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "career")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 5:
        await message.answer("Опиши ситуацию подробнее 💼")
        return
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="career",
        prompt=CAREER.format(text=txt),
        header=reading_header("Карьера и деньги"),
    )


@router.message(Flow.yesno_question)
async def yesno_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "yesno")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    q = (message.text or "").strip()
    if len(q) < 3:
        await message.answer("Сформулируй вопрос 🎲")
        return
    token = random.randint(1, 99)
    await state.clear()
    await _send_reading(
        message,
        uid=uid,
        module="yesno",
        prompt=YESNO.format(question=q, token=token),
        header=reading_header("Да / Нет"),
        temperature=0.9,
    )


@router.message(Flow.prof_natal_data)
async def prof_natal_data_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = message.text or ""
    bt = parse_birth_time(text)
    place = extract_place(text)
    if not bt and not place:
        await message.answer("Пример: 14:30 Москва")
        return
    db.save_profile(uid, birth_time=bt, birth_place=place)
    await state.clear()
    await message.answer(
        f"✅ Сохранено: {bt or '—'} · {place or '—'}",
        reply_markup=kb_profile(True),
    )


@router.message(Flow.natal_input)
async def natal_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "natal")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    built = mf.natal_prompt(uid, message.text or "")
    if not built:
        await message.answer("Нужна дата: 15.03.1990 14:30 Москва")
        return
    await state.clear()
    prompt, header = built
    await _send_reading(message, uid=uid, module="natal", prompt=prompt, header=header)


@router.message(Flow.past_life_focus)
async def past_life_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "past_life")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    focus = (message.text or "").strip() or "общий поиск души"
    await state.clear()
    prompt, header = mf.past_life_prompt(uid, focus)
    await _send_reading(message, uid=uid, module="past_life", prompt=prompt, header=header)


@router.message(Flow.iching_question)
async def iching_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "iching")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    q = (message.text or "").strip() or "сегодня"
    await state.clear()
    prompt, header = mf.iching_prompt(uid, q)
    await _send_reading(message, uid=uid, module="iching", prompt=prompt, header=header)


@router.message(Flow.lenormand_question)
async def lenormand_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "lenormand")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    q = (message.text or "").strip() or "общий вектор"
    await state.clear()
    prompt, header = mf.lenormand_prompt(q)
    await _send_reading(message, uid=uid, module="lenormand", prompt=prompt, header=header)


@router.message(Flow.twin_flame_text)
async def twin_flame_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "twin_flame")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 5:
        await message.answer("Расскажи подробнее 🔥")
        return
    await state.clear()
    prompt, header = mf.twin_flame_prompt(uid, txt)
    await _send_reading(message, uid=uid, module="twin_flame", prompt=prompt, header=header)


@router.message(Flow.family_karma_text)
async def family_karma_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    blocked = await _guard(uid, "family_karma")
    if blocked:
        await message.answer(blocked, reply_markup=kb_limit_reached(uid))
        await state.clear()
        return
    txt = (message.text or "").strip()
    if len(txt) < 5:
        await message.answer("Опиши родовой сценарий 🧬")
        return
    await state.clear()
    prompt, header = mf.family_karma_prompt(txt)
    await _send_reading(message, uid=uid, module="family_karma", prompt=prompt, header=header)


@router.callback_query(F.data.startswith("prod:"))
async def cb_product_info(call: CallbackQuery) -> None:
    slug = (call.data or "").split(":", 1)[-1]
    await call.answer()
    if not call.message:
        return
    try:
        from business_dashboard.storage import init_db, list_ideas
        from business_dashboard.user_assets import enrich_idea
        from business_dashboard.storage import get_done_asset_keys

        init_db()
        idea = next((i for i in list_ideas() if i["slug"] == slug), None)
        if not idea:
            await call.message.answer("Продукт в разработке — скоро будет 🔧")
            return
        enriched = enrich_idea(idea, get_done_asset_keys())
        action = enriched.get("effective_action") or idea.get("action_required") or ""
        st = idea.get("status", "")
        badge = "✅ Уже работает" if st in ("running", "connected") else "🛠 В работе"
        await call.message.answer(
            f"💰 <b>{idea['title']}</b>\n{badge}\n\n"
            f"{idea.get('potential_rub', '')}\n\n"
            f"<i>{action}</i>\n\n"
            "⭐ Премиум Оракула закрывает мистику; этот продукт — отдельное направление дохода.",
            reply_markup=kb_main(),
        )
    except Exception as e:
        logger.warning("prod info: %s", e)
        await call.message.answer("Не удалось загрузить продукт. /menu")


async def dispatch_voice_text(message: Message, state: FSMContext, text: str) -> bool:
    """Маршрутизация распознанного голоса в активный сценарий."""
    st = await state.get_state()
    if not st:
        return False
    msg = message.model_copy(update={"text": text})
    routes = {
        Flow.natal_input.state: natal_flow,
        Flow.past_life_focus.state: past_life_flow,
        Flow.numerology_input.state: numerology_flow,
        Flow.hvd_input.state: exclusive_hvd_flow,
        Flow.ultra_plus_input.state: ultra_plus_flow,
        Flow.chinese_birth.state: chinese_flow,
        Flow.tarot_question.state: tarot_flow,
        Flow.compat_dates.state: compat_flow,
        Flow.dream_text.state: dream_flow,
        Flow.dating_text.state: dating_flow,
        Flow.psychology_text.state: psychology_flow,
        Flow.career_text.state: career_flow,
        Flow.yesno_question.state: yesno_flow,
        Flow.iching_question.state: iching_flow,
        Flow.lenormand_question.state: lenormand_flow,
        Flow.twin_flame_text.state: twin_flame_flow,
        Flow.family_karma_text.state: family_karma_flow,
        Flow.portrait_birth.state: portrait_flow,
        Flow.prof_birth.state: prof_birth_flow,
        Flow.prof_name.state: prof_name_flow,
        Flow.prof_natal_data.state: prof_natal_data_flow,
    }
    handler = routes.get(st)
    if handler:
        await handler(msg, state)
        return True
    return False


@router.message(F.web_app_data)
async def on_webapp_data(message: Message, state: FSMContext) -> None:
    import json

    uid = message.from_user.id if message.from_user else 0
    try:
        data = json.loads(message.web_app_data.data)
    except (TypeError, json.JSONDecodeError):
        return
    action = data.get("action")
    analytics_mod.track_miniapp(uid, action or "unknown", data.get("module", ""))
    if action == "premium":
        await _offer_premium(message, uid)
        return
    if action == "ref":
        await cmd_ref(message)
        return
    if action == "voice":
        await message.answer(
            "🎤 <b>Голосом — удобно с утра</b>\n\n"
            "Запиши голосовое: сон, вопрос к Таро, ситуация в отношениях — "
            "я распознаю и отвечу.\n\n"
            "Или выбери раздел в /menu и уточни голосом после расклада."
        )
        return
    if action == "mod":
        await _open_module(message, state, uid, data.get("module", ""))
        return


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    from oracle_bot.config import oferta_url, self_employed_requisites_html

    uid = message.from_user.id if message.from_user else 0
    text = (
        "🔮 <b>m-Oracul — помощь</b>\n\n"
        "• /menu — все разделы\n"
        "• После чтения можно написать или сказать голосом уточнение\n"
        "• 🔓 Продолжить — скрытая часть (Stars)\n"
        "• ⭐ Премиум — безлимит\n"
        "• /ref — пригласи друга\n"
        "• /stop_push — отключить напоминания\n\n"
        f"📋 <a href=\"{oferta_url()}\">Публичная оферта</a>\n"
        f"{self_employed_requisites_html()}"
    )
    if _is_admin(uid):
        text += (
            "\n\n<b>Админ:</b>\n"
            "• /stats — аналитика\n"
            "• /daily — отчёт за сегодня\n"
            "• /broadcast текст — рассылка всем\n"
            "• /free_day — бесплатный день + рассылка"
        )
    await message.answer(text, reply_markup=kb_main())


@router.message(Command("stop_push"))
async def cmd_stop_push(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    db.set_push_opt_out(uid)
    await message.answer("🔕 Напоминания отключены. /menu — когда захочешь вернуться.")


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        return
    txt = (message.text or "").strip()
    if txt.startswith("/"):
        return
    if len(txt) >= 3:
        from oracle_bot.dialogue import answer_followup, has_context

        if has_context(message.from_user.id if message.from_user else 0):
            if await answer_followup(message, txt):
                return
    if len(txt) >= 8:
        from oracle_bot.coach import coach_from_free_text

        await coach_from_free_text(message, txt)
        return
    await message.answer(
        "Выбери раздел 👇 или /menu",
        reply_markup=kb_main(),
    )
