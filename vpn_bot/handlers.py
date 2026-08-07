"""Хендлеры VPN-бота: /start, тарифы, мой ключ, пробный период, помощь."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from vpn_bot import storage as db
from vpn_bot.access import fulfill_invoice_sync, start_trial
from vpn_bot.config import (
    VPN_ADMIN_IDS,
    VPN_BRAND_NAME,
    VPN_HELP_CONTACT,
    VPN_NEWS_CHANNEL,
    get_tariff,
    robokassa_configured,
)
from vpn_bot.keyboards import kb_back, kb_key, kb_main, kb_pay, kb_tariffs
from vpn_bot.marzban_client import MarzbanClient, MarzbanError
from vpn_bot.robokassa import build_payment_url

logger = logging.getLogger(__name__)
router = Router(name="vpn_bot")


WELCOME = (
    f"👋 Привет! Это бот <b>{VPN_BRAND_NAME}</b>.\n\n"
    "Здесь можно получить личный VPN-ключ и подключить его в готовом приложении "
    "(Happ / v2rayNG / Hiddify — на выбор).\n\n"
    "🔑 «Мой ключ» — ссылка и QR для подключения\n"
    "💳 «Купить / продлить» — тарифы\n"
    "🎁 «Пробный период» — бесплатно на несколько дней"
)

HOWTO = (
    "<b>Как подключить ключ</b>\n\n"
    "1. Установи одно из приложений:\n"
    "   • <b>Happ</b> — happ.su (iOS/Android/Windows/macOS)\n"
    "   • <b>v2rayNG</b> — Android\n"
    "   • <b>Hiddify</b> — iOS/Android/Windows/macOS\n"
    "2. Скопируй ссылку из «🔑 Мой ключ» (или отсканируй QR).\n"
    "3. В приложении: «Добавить подписку по ссылке» / «Import from clipboard» — вставь ссылку.\n"
    "4. Обнови список серверов и нажми «Подключить»."
)


def _fmt_expiry(expires_at: str | None) -> str:
    if not expires_at:
        return "—"
    try:
        dt = datetime.fromisoformat(expires_at)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return expires_at[:10]


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    db.ensure_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await message.answer(WELCOME, reply_markup=kb_main())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HOWTO, reply_markup=kb_back())


@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(WELCOME, reply_markup=kb_main())
    await callback.answer()


@router.callback_query(F.data == "howto")
async def cb_howto(callback: CallbackQuery) -> None:
    await callback.message.edit_text(HOWTO, reply_markup=kb_back())
    await callback.answer()


async def _send_key_card(callback_or_message, user_id: int, subscription_url: str, expires_at: str | None) -> None:
    import html

    import qrcode

    qr_img = qrcode.make(subscription_url, box_size=8, border=2)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    caption = (
        f"🔑 <b>Твой ключ</b>\n"
        f"Активен до: <b>{_fmt_expiry(expires_at)}</b>\n\n"
        "QR для сканирования или скопируй ссылку в следующем сообщении 👇"
    )
    photo = BufferedInputFile(buf.read(), filename="vpn_key_qr.png")
    target = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    await target.answer_photo(photo=photo, caption=caption)
    safe_url = html.escape(subscription_url)
    await target.answer(
        "👇 <b>Нажми на ссылку</b> — скопируется в буфер:\n\n"
        f"<code>{safe_url}</code>\n\n"
        "Или нажми «📋 Скопировать ключ» и вставь в Happ / v2rayNG / Hiddify.",
        reply_markup=kb_key(subscription_url),
    )


@router.callback_query(F.data == "my_key")
async def cb_my_key(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    sub = db.get_subscription(user_id)
    if not sub or not sub.get("expires_at"):
        await callback.message.edit_text(
            "У тебя пока нет активного ключа.\n"
            "Начни с бесплатного пробного периода или купи тариф 👇",
            reply_markup=kb_main(),
        )
        await callback.answer()
        return
    try:
        client = MarzbanClient()
        obj = await client.get_user(sub["marzban_username"])
    except MarzbanError:
        logger.exception("my_key: marzban lookup failed for user %s", user_id)
        await callback.answer("Сервер временно недоступен, попробуй позже.", show_alert=True)
        return
    if not obj:
        await callback.answer("Ключ не найден, обратись в поддержку.", show_alert=True)
        return
    await callback.answer()
    await _send_key_card(callback, user_id, MarzbanClient.subscription_url(obj), sub.get("expires_at"))


@router.callback_query(F.data == "trial")
async def cb_trial(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    await callback.answer("Готовим пробный ключ…")
    try:
        result = await start_trial(user_id)
    except MarzbanError:
        logger.exception("trial: marzban error for user %s", user_id)
        await callback.message.answer("Сервер временно недоступен, попробуй позже.")
        return
    if result is None:
        await callback.message.answer(
            "Пробный период уже использован. Загляни в «💳 Купить / продлить».",
            reply_markup=kb_main(),
        )
        return
    await _send_key_card(callback, user_id, result["subscription_url"], result["expires_at"])


@router.callback_query(F.data == "buy")
async def cb_buy(callback: CallbackQuery) -> None:
    if not robokassa_configured():
        await callback.answer("Оплата пока не настроена, зайди позже.", show_alert=True)
        return
    await callback.message.edit_text("Выбери тариф:", reply_markup=kb_tariffs())
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:"))
async def cb_tariff_selected(callback: CallbackQuery) -> None:
    tariff_id = callback.data.split(":", 1)[1]
    tariff = get_tariff(tariff_id)
    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    user_id = callback.from_user.id
    db.ensure_user(user_id)
    inv_id = db.create_invoice(user_id, tariff_id, tariff["days"], tariff["price_rub"])
    pay_url = build_payment_url(
        inv_id=inv_id,
        out_sum=tariff["price_rub"],
        description=f"{VPN_BRAND_NAME}: {tariff['title']}",
        shp={"Shp_uid": str(user_id)},
    )
    await callback.message.edit_text(
        f"<b>{tariff['title']}</b> — {tariff['price_rub']}₽\n\n"
        "Нажми «Оплатить», после оплаты вернись и нажми «Я оплатил — проверить».",
        reply_markup=kb_pay(pay_url, inv_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check:"))
async def cb_check_payment(callback: CallbackQuery) -> None:
    inv_id = int(callback.data.split(":", 1)[1])
    inv = db.get_invoice(inv_id)
    if not inv:
        await callback.answer("Инвойс не найден", show_alert=True)
        return
    if inv["status"] == "paid":
        sub = db.get_subscription(callback.from_user.id)
        exp = _fmt_expiry(sub.get("expires_at")) if sub else "—"
        await callback.message.edit_text(
            f"✅ Оплата подтверждена. Ключ активен до <b>{exp}</b>.\nОткрой «🔑 Мой ключ».",
            reply_markup=kb_main(),
        )
    else:
        await callback.answer("Пока не видим оплату. Если платил — подожди минуту и проверь снова.", show_alert=True)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in VPN_ADMIN_IDS:
        return
    s = db.stats()
    await message.answer(
        "📊 <b>Статистика VPN-бота</b>\n"
        f"Пользователей: {s['users']}\n"
        f"Активных ключей: {s['active_subscriptions']}\n"
        f"Оплаченных инвойсов: {s['paid_invoices']}\n"
        f"Выручка: {s['revenue_rub']}₽"
    )
