from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from work_bot.config import MIN_WITHDRAWAL_RUB
from work_bot.partners import PARTNERS, Task, auto_tasks, tasks_for_partner


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤝 Выбрать партнёра", callback_data="mode:manual"),
                InlineKeyboardButton(text="⚡ Авто-задания", callback_data="mode:auto"),
            ],
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="nav:balance"),
                InlineKeyboardButton(text="📋 Мои задания", callback_data="nav:history"),
            ],
            [InlineKeyboardButton(text="❓ Как это работает", callback_data="nav:help")],
        ]
    )


def kb_partners() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{p.emoji} {p.title}", callback_data=f"partner:{p.slug}")]
        for p in PARTNERS
    ]
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_tasks(tasks: list[Task], *, prefix: str = "task") -> InlineKeyboardMarkup:
    from work_bot.partners import task_display

    rows = []
    for t in tasks:
        d = task_display(t)
        rows.append([
            InlineKeyboardButton(
                text=f"{d['title']} · {d['worker_reward_rub']} ₽",
                callback_data=f"{prefix}:{t.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="nav:back_mode")])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_task_actions(assignment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Сдать отчёт", callback_data=f"submit:{assignment_id}")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu")],
        ]
    )


def kb_balance(balance: float) -> InlineKeyboardMarkup:
    rows = []
    if balance >= MIN_WITHDRAWAL_RUB:
        rows.append([InlineKeyboardButton(text="💸 Вывести деньги", callback_data="nav:withdraw")])
    else:
        rows.append([
            InlineKeyboardButton(
                text=f"Вывод от {MIN_WITHDRAWAL_RUB:,} ₽".replace(",", " "),
                callback_data="nav:withdraw_info",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="⚡ Взять задание", callback_data="mode:auto"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="nav:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_review(assignment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"adm:ok:{assignment_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm:no:{assignment_id}"),
            ]
        ]
    )


def kb_auto_tasks() -> InlineKeyboardMarkup:
    return kb_tasks(auto_tasks(), prefix="task")
