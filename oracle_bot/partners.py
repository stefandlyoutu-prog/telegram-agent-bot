"""Партнёрская программа Оракула: 25% с оплат приведённой аудитории.

Для админов пабликов/каналов: партнёр получает персональную ссылку
t.me/<bot>?start=p_<его id>. Все, кто пришёл по ней, привязываются к партнёру
(first-touch, навсегда). С каждой оплаты картой (Робокасса) партнёру
начисляется 25%. Выплата по запросу от MIN_PAYOUT_RUB на СБП.
"""

from __future__ import annotations

import logging

from oracle_bot import storage as db

logger = logging.getLogger(__name__)

COMMISSION_PCT = 25
MIN_PAYOUT_RUB = 500


def partner_link(partner_id: int) -> str:
    from oracle_bot.config import ORACLE_BOT_USERNAME

    return f"https://t.me/{ORACLE_BOT_USERNAME}?start=p_{partner_id}"


def handle_start_arg(user_id: int, args: str) -> int | None:
    """Если /start p_<id> — привязать пользователя к партнёру. Вернёт partner_id."""
    raw = (args or "").strip().lower()
    if not raw.startswith("p_"):
        return None
    try:
        pid = int(raw[2:])
    except ValueError:
        return None
    if db.set_partner_ref(user_id, pid):
        db.set_signup_source(user_id, f"partner_{pid}")
        db.log_event(user_id, "partner_join", str(pid))
        return pid
    return None


def credit_for_payment(payer_id: int, kind: str, amount_rub: int) -> tuple[int, int] | None:
    """Начислить партнёру 25% с оплаты. Вернёт (partner_id, комиссия) или None."""
    if amount_rub <= 0:
        return None
    partner_id = db.get_partner_ref(payer_id)
    if not partner_id:
        return None
    commission = max(1, amount_rub * COMMISSION_PCT // 100)
    db.add_partner_earning(partner_id, payer_id, kind, amount_rub, commission)
    logger.info("partner %s: +%s₽ за оплату %s от %s", partner_id, commission, kind, payer_id)
    return partner_id, commission


def partner_text(partner_id: int) -> str:
    st = db.partner_stats(partner_id)
    link = partner_link(partner_id)
    return (
        "🤝 <b>Партнёрская программа Оракула</b>\n\n"
        f"Ты получаешь <b>{COMMISSION_PCT}%</b> с каждой оплаты людей, которые пришли по "
        "твоей ссылке. Навсегда: привязка не сгорает, платят ли они через день или через "
        "месяц.\n\n"
        f"🔗 Твоя ссылка:\n<code>{link}</code>\n\n"
        "Куда ставить: пост в паблике, описание канала, сторис, комментарии. Что "
        "продаётся: разбор личности ХВД (599₽), персональная книга (1499₽), премиум "
        "(299₽/мес) — с каждой оплаты тебе идёт доля.\n\n"
        "📊 <b>Твоя статистика:</b>\n"
        f"• Пришло по ссылке: <b>{st['referred']}</b> чел.\n"
        f"• Оплат от них: <b>{st['payments']}</b>\n"
        f"• Начислено всего: <b>{st['earned_rub']}₽</b>\n"
        f"• Выплачено: <b>{st['paid_rub']}₽</b>\n"
        f"• К выплате: <b>{st['balance_rub']}₽</b>\n\n"
        f"💸 Выплата от {MIN_PAYOUT_RUB}₽ на СБП — кнопка ниже."
    )
