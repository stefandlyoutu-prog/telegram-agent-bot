"""Пуши: напоминания о заданиях и выводе."""

from __future__ import annotations

import asyncio
import json
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from work_bot import storage as db
from work_bot.config import MIN_WITHDRAWAL_RUB, WORK_PUSH_INTERVAL_SEC

logger = logging.getLogger(__name__)


def _kb_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Открыть бота", callback_data="nav:menu")]]
    )


def build_push(user_id: int, push_type: str, ctx: dict) -> str:
    w = db.get_worker(user_id)
    bal = float(w.get("balance_rub") or 0)
    if push_type == "task_remind":
        return (
            "⏰ <b>Задание ждёт отчёт</b>\n\n"
            "Ты взял(а) задачу, но ещё не сдал(а) подтверждение. "
            "Скрин + «готово» — и деньги на балансе после проверки."
        )
    if push_type == "near_withdraw":
        left = max(0, MIN_WITHDRAWAL_RUB - bal)
        return (
            f"💰 <b>До вывода осталось {left:,.0f} ₽</b>\n\n"
            f"Баланс: {bal:,.0f} ₽ · минимум вывода {MIN_WITHDRAWAL_RUB:,} ₽".replace(",", " ")
        )
    if push_type == "rejected":
        return (
            "❌ <b>Отчёт не принят</b>\n\n"
            "Проверь скрин: должно быть видно выполненное действие. "
            "Можно взять задание снова и сдать новый отчёт."
        )
    if push_type == "approved":
        reward = ctx.get("reward", 0)
        return (
            f"✅ <b>+{reward:,.0f} ₽ на баланс</b>\n\n"
            f"Итого: {bal:,.0f} ₽. Бери следующее задание!".replace(",", " ")
        )
    if push_type == "idle":
        return (
            "💼 <b>Задания онлайн</b>\n\n"
            "Установки, подписки, рефералы — от 20 ₽ за задачу. "
            "Вывод от 5 000 ₽ после проверки отчётов."
        )
    return "💼 Загляни в бот — есть новые задания."


async def process_due_pushes(bot: Bot) -> int:
    sent = 0
    for row in db.fetch_due_pushes():
        uid = int(row["user_id"])
        w = db.get_worker(uid)
        if w.get("push_opt_out") or w.get("blocked"):
            db.mark_push_sent(int(row["id"]))
            continue
        ctx = {}
        try:
            ctx = json.loads(row["context"] or "{}")
        except json.JSONDecodeError:
            pass
        text = build_push(uid, row["push_type"], ctx)
        try:
            await bot.send_message(uid, text, reply_markup=_kb_menu(), parse_mode="HTML")
            db.mark_push_sent(int(row["id"]))
            sent += 1
        except Exception as e:
            logger.warning("work push %s: %s", uid, e)
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                db.mark_push_sent(int(row["id"]))
    return sent


async def push_worker(bot: Bot, interval_sec: int = WORK_PUSH_INTERVAL_SEC) -> None:
    while True:
        try:
            n = await process_due_pushes(bot)
            if n:
                logger.info("work pushes: %d", n)
        except Exception:
            logger.exception("work push_worker")
        await asyncio.sleep(interval_sec)


def schedule_task_reminder(user_id: int) -> None:
    db.schedule_push(user_id, "task_remind", delay_hours=24)


def schedule_idle_nudge(user_id: int) -> None:
    db.schedule_push(user_id, "idle", delay_hours=72)
