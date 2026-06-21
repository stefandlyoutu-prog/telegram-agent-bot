"""Действия Mini App: бот шлёт ответ в чат (работает из кнопки меню «Приложение»)."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Chat, LabeledPrice, User
from aiogram.utils.web_app import safe_parse_webapp_init_data

from oracle_bot.config import ORACLE_BOT_TOKEN, ORACLE_PREMIUM_STARS
from oracle_bot import analytics as analytics_mod


class WebappReply:
    """Минимальный message.answer для вызова из WebApp без Update."""

    def __init__(self, bot: Bot, uid: int, user: User):
        self.bot = bot
        self.chat = Chat(id=uid, type="private")
        self.from_user = user

    async def answer(self, text: str, **kwargs: Any):
        return await self.bot.send_message(self.chat.id, text, **kwargs)

    async def answer_invoice(self, **kwargs: Any):
        return await self.bot.send_invoice(chat_id=self.chat.id, **kwargs)


async def dispatch_webapp_action(
    bot: Bot,
    dp: Dispatcher,
    init_data: str,
    *,
    action: str,
    module: str = "",
) -> None:
    if not init_data.strip():
        raise ValueError("init_data required")
    if not ORACLE_BOT_TOKEN:
        raise ValueError("bot token not configured")

    parsed = safe_parse_webapp_init_data(ORACLE_BOT_TOKEN, init_data)
    if not parsed.user:
        raise ValueError("user missing in init_data")

    uid = parsed.user.id
    user = parsed.user
    me = await bot.get_me()
    state = FSMContext(
        storage=dp.storage,
        key=StorageKey(bot_id=me.id, chat_id=uid, user_id=uid),
    )
    msg = WebappReply(bot, uid, user)

    from oracle_bot import storage as db
    from oracle_bot.handlers import _open_module

    db.ensure_user(uid)
    analytics_mod.track_miniapp(uid, action or "unknown", module)

    if action == "premium":
        from oracle_bot.paywall import stars_enabled

        if stars_enabled():
            await _send_premium_invoice_patched(msg)
        else:
            analytics_mod.track_referral_prompt(uid, "miniapp:premium")
            await cmd_ref_patched(msg, uid)
        return
    if action == "ref":
        await cmd_ref_patched(msg, uid)
        return
    if action == "voice":
        await msg.answer(
            "🎤 <b>Голосом — удобно с утра</b>\n\n"
            "Запиши голосовое: сон, вопрос к Таро, ситуация в отношениях — "
            "я распознаю и отвечу.\n\n"
            "Или выбери раздел в /menu и уточни голосом после расклада."
        )
        return
    if action == "mod":
        await _open_module(msg, state, uid, module)
        return

    raise ValueError(f"unknown action: {action}")


async def _send_premium_invoice_patched(msg: WebappReply) -> None:
    uid = msg.from_user.id if msg.from_user else 0
    if uid:
        analytics_mod.track_payment_intent(uid, "premium_30d")
    await msg.answer_invoice(
        title="Оракул — Премиум 30 дней",
        description="Безлимит + все продолжения без 🔒. Все 15+ разделов.",
        payload="premium_30d",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=ORACLE_PREMIUM_STARS)],
    )


async def cmd_ref_patched(msg: WebappReply, uid: int) -> None:
    from oracle_bot import storage as db
    from oracle_bot.referrals import stats_text
    from oracle_bot.keyboards import kb_referral

    db.ensure_user(uid)
    await msg.answer(stats_text(uid), reply_markup=kb_referral(uid))
