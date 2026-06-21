from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from work_bot import storage as db
from work_bot.admin_notify import notify_admins
from work_bot.config import MIN_WITHDRAWAL_RUB, WORK_ADMIN_IDS, WORK_BOT_USERNAME
from work_bot.keyboards import (
    kb_admin_review,
    kb_auto_tasks,
    kb_balance,
    kb_main,
    kb_partners,
    kb_task_actions,
    kb_tasks,
)
from work_bot.partners import (
    auto_tasks,
    partner_by_slug,
    ref_link,
    task_by_id,
    task_display,
    tasks_for_partner,
)
from work_bot.pushes import schedule_idle_nudge, schedule_task_reminder

logger = logging.getLogger(__name__)
router = Router()


class Flow(StatesGroup):
    submit_proof = State()
    withdraw_details = State()


def _is_admin(uid: int) -> bool:
    return uid in WORK_ADMIN_IDS


def _user_line(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "?"
    name = (u.first_name or "").strip()
    uname = f"@{u.username}" if u.username else f"id{u.id}"
    return f"{name} · {uname}" if name else uname


def _welcome() -> str:
    return (
        "💼 <b>Работа онлайн</b>\n\n"
        "Помогаем зарабатывать на простых заданиях: установки, подписки, "
        "приведение клиентов по партнёрским программам.\n\n"
        "<b>Как это работает:</b>\n"
        "1. Выбираешь партнёра или авто-задание\n"
        "2. Выполняешь по инструкции\n"
        "3. Сдаёшь отчёт (фото + «готово»)\n"
        "4. После проверки — деньги на баланс\n"
        "5. Вывод от <b>5 000 ₽</b> — заявка приходит админу\n\n"
        f"Выплата исполнителю — <b>10%</b> от комиссии партнёрки."
    )


def _help_text() -> str:
    return (
        "❓ <b>Помощь</b>\n\n"
        "• <b>Партнёр</b> — выбираешь Яндекс, Ozon и т.д.\n"
        "• <b>Авто</b> — список всех заданий сразу\n"
        "• Отчёт: фото-скрин + короткий текст\n"
        "• Проверка вручную — 1–24 ч\n"
        "• Вывод: СБП / карта / кошелёк в заявке\n"
        "• Минимум вывода: <b>5 000 ₽</b>\n\n"
        "/stop — отключить напоминания"
    )


def _balance_text(uid: int) -> str:
    w = db.get_worker(uid)
    bal = float(w.get("balance_rub") or 0)
    earned = float(w.get("total_earned_rub") or 0)
    withdrawn = float(w.get("total_withdrawn_rub") or 0)
    approved = int(w.get("approved_count") or 0)
    rejected = int(w.get("rejected_count") or 0)
    left = max(0, MIN_WITHDRAWAL_RUB - bal)
    lines = [
        "💰 <b>Баланс</b>\n",
        f"Доступно: <b>{bal:,.0f} ₽</b>".replace(",", " "),
        f"Всего заработано: {earned:,.0f} ₽".replace(",", " "),
        f"Выведено: {withdrawn:,.0f} ₽".replace(",", " "),
        f"Заданий принято: {approved} · отклонено: {rejected}",
    ]
    if bal < MIN_WITHDRAWAL_RUB:
        lines.append(f"\nДо вывода: <b>{left:,.0f} ₽</b>".replace(",", " "))
    else:
        lines.append("\n✅ Можно подать заявку на вывод.")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    u = message.from_user
    is_new = db.ensure_worker(
        uid,
        username=u.username if u else "",
        first_name=u.first_name if u else "",
    )
    if is_new:
        await notify_admins(
            message.bot,
            f"🆕 <b>Новый в @{WORK_BOT_USERNAME}</b>\n👤 {_user_line(message)}",
        )
        schedule_idle_nudge(uid)
    await message.answer(_welcome(), reply_markup=kb_main())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_welcome(), reply_markup=kb_main())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_help_text(), reply_markup=kb_main())


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await message.answer(_balance_text(uid), reply_markup=kb_balance(float(db.get_worker(uid).get("balance_rub") or 0)))


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    db.set_push_opt_out(uid)
    await message.answer("🔕 Напоминания отключены. /menu — когда захочешь.")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _is_admin(uid):
        return
    s = db.admin_stats()
    await message.answer(
        "📊 <b>Админ</b>\n\n"
        f"Исполнителей: {s['workers']}\n"
        f"На проверке: {s['pending_review']}\n"
        f"Заявок на вывод: {s['pending_withdraw']}\n"
        f"Балансы на счетах: {s['balance_total']:,.0f} ₽".replace(",", " "),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "nav:menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer(_welcome(), reply_markup=kb_main())
    await call.answer()


@router.callback_query(F.data == "nav:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.message.answer(_help_text(), reply_markup=kb_main())
    await call.answer()


@router.callback_query(F.data == "nav:balance")
async def cb_balance(call: CallbackQuery) -> None:
    uid = call.from_user.id
    bal = float(db.get_worker(uid).get("balance_rub") or 0)
    await call.message.answer(_balance_text(uid), reply_markup=kb_balance(bal))
    await call.answer()


@router.callback_query(F.data == "nav:withdraw_info")
async def cb_withdraw_info(call: CallbackQuery) -> None:
    uid = call.from_user.id
    bal = float(db.get_worker(uid).get("balance_rub") or 0)
    left = max(0, MIN_WITHDRAWAL_RUB - bal)
    await call.message.answer(
        f"💸 Вывод доступен от <b>{MIN_WITHDRAWAL_RUB:,} ₽</b>\n\n"
        f"Сейчас на балансе: {bal:,.0f} ₽\n"
        f"Осталось заработать: <b>{left:,.0f} ₽</b>\n\n"
        "Бери задания — после проверки сумма копится.".replace(",", " "),
        reply_markup=kb_main(),
    )
    await call.answer()


@router.callback_query(F.data == "nav:withdraw")
async def cb_withdraw(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    bal = float(db.get_worker(uid).get("balance_rub") or 0)
    if bal < MIN_WITHDRAWAL_RUB:
        await call.answer(f"Минимум {MIN_WITHDRAWAL_RUB} ₽", show_alert=True)
        return
    await state.set_state(Flow.withdraw_details)
    await call.message.answer(
        f"💸 <b>Заявка на вывод {bal:,.0f} ₽</b>\n\n"
        "Напиши одним сообщением:\n"
        "• ФИО\n"
        "• СБП / карта / кошелёк\n"
        "• Банк (если карта)\n"
        "• Телефон для связи".replace(",", " "),
    )
    await call.answer()


@router.message(Flow.withdraw_details)
async def withdraw_details_flow(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    details = (message.text or "").strip()
    if len(details) < 15:
        await message.answer("Нужны реквизиты подробнее (ФИО + куда перевести).")
        return
    bal = float(db.get_worker(uid).get("balance_rub") or 0)
    if bal < MIN_WITHDRAWAL_RUB:
        await state.clear()
        await message.answer("Баланс изменился — вывод недоступен.", reply_markup=kb_main())
        return
    try:
        wid = db.create_withdrawal(uid, bal, details)
    except ValueError:
        await state.clear()
        await message.answer("Недостаточно средств.", reply_markup=kb_main())
        return
    await state.clear()
    history = db.user_assignments(uid, limit=15)
    approved_lines = []
    for a in history:
        if a["status"] == "approved":
            t = task_by_id(a["task_id"])
            title = t.title if t else a["task_id"]
            approved_lines.append(f"• {title} — {a['reward_rub']:,.0f} ₽".replace(",", " "))
    hist = "\n".join(approved_lines[:10]) or "—"
    w = db.get_worker(uid)
    await notify_admins(
        message.bot,
        "💸 <b>Заявка на вывод</b>\n\n"
        f"👤 {_user_line(message)}\n"
        f"💰 Сумма: <b>{bal:,.0f} ₽</b>\n"
        f"✅ Принято заданий: {w.get('approved_count', 0)}\n"
        f"❌ Отклонено: {w.get('rejected_count', 0)}\n\n"
        f"<b>Реквизиты:</b>\n{details}\n\n"
        f"<b>Выполненные задания:</b>\n{hist}\n\n"
        f"ID заявки: #{wid}",
    )
    await message.answer(
        "✅ Заявка отправлена. Перевод после проверки — обычно 1–3 дня.",
        reply_markup=kb_main(),
    )


@router.callback_query(F.data == "nav:history")
async def cb_history(call: CallbackQuery) -> None:
    uid = call.from_user.id
    rows = db.user_assignments(uid, limit=10)
    if not rows:
        await call.message.answer("Пока нет заданий. Нажми «Авто-задания».", reply_markup=kb_main())
        await call.answer()
        return
    status_emoji = {
        "active": "🟡",
        "submitted": "⏳",
        "approved": "✅",
        "rejected": "❌",
    }
    lines = ["📋 <b>Мои задания</b>\n"]
    for a in rows:
        t = task_by_id(a["task_id"])
        title = t.title if t else a["task_id"]
        em = status_emoji.get(a["status"], "•")
        lines.append(f"{em} {title} — {a['reward_rub']:,.0f} ₽".replace(",", " "))
    await call.message.answer("\n".join(lines), reply_markup=kb_main())
    await call.answer()


@router.callback_query(F.data == "mode:manual")
async def cb_mode_manual(call: CallbackQuery) -> None:
    uid = call.from_user.id
    db.set_mode(uid, "manual")
    await call.message.answer(
        "🤝 <b>Выбери партнёра</b>\n\nКаждый — свои задания и выплаты.",
        reply_markup=kb_partners(),
    )
    await call.answer()


@router.callback_query(F.data == "mode:auto")
async def cb_mode_auto(call: CallbackQuery) -> None:
    uid = call.from_user.id
    db.set_mode(uid, "auto")
    await call.message.answer(
        "⚡ <b>Авто-задания</b>\n\nВсе доступные задачи — выбирай по сумме.",
        reply_markup=kb_auto_tasks(),
    )
    await call.answer()


@router.callback_query(F.data == "nav:back_mode")
async def cb_back_mode(call: CallbackQuery) -> None:
    w = db.get_worker(call.from_user.id)
    if w.get("mode") == "auto":
        await cb_mode_auto(call)
    else:
        await cb_mode_manual(call)


@router.callback_query(F.data.startswith("partner:"))
async def cb_partner(call: CallbackQuery) -> None:
    slug = call.data.split(":", 1)[1]
    p = partner_by_slug(slug)
    if not p:
        await call.answer("Не найден", show_alert=True)
        return
    tasks = tasks_for_partner(slug)
    if not tasks:
        await call.answer("Заданий пока нет", show_alert=True)
        return
    await call.message.answer(
        f"{p.emoji} <b>{p.title}</b>\n{p.desc}",
        reply_markup=kb_tasks(tasks),
    )
    await call.answer()


@router.callback_query(F.data.startswith("task:"))
async def cb_task(call: CallbackQuery) -> None:
    task_id = call.data.split(":", 1)[1]
    await _assign_task(call, task_id)


async def _assign_task(call: CallbackQuery, task_id: str) -> None:
    uid = call.from_user.id
    task = task_by_id(task_id)
    if not task:
        await call.answer("Задание не найдено", show_alert=True)
        return
    existing = db.active_assignment(uid, task_id)
    if existing:
        if existing["status"] == "submitted":
            await call.answer("Отчёт на проверке", show_alert=True)
            return
        aid = int(existing["id"])
        await call.message.answer(
            "У тебя уже есть это задание. Сдай отчёт или выбери другое.",
            reply_markup=kb_task_actions(aid),
        )
        await call.answer()
        return
    d = task_display(task)
    link = ref_link(task, uid)
    link_line = f"\n\n🔗 <b>Ссылка:</b>\n{link}" if link else (
        "\n\n⚠️ Ссылка скоро появится — админ подключает партнёрку."
    )
    aid = db.create_assignment(uid, task_id, float(d["worker_reward_rub"]))
    schedule_task_reminder(uid)
    text = (
        f"📌 <b>{task.title}</b>\n\n"
        f"💵 Выплата после проверки: <b>{d['worker_reward_rub']} ₽</b>\n\n"
        f"<b>Инструкция:</b>\n{task.steps}\n\n"
        f"<b>Отчёт:</b> {task.proof_hint}"
        f"{link_line}"
    )
    await call.message.answer(text, reply_markup=kb_task_actions(aid))
    await call.answer("Задание взято")


@router.callback_query(F.data.startswith("submit:"))
async def cb_submit(call: CallbackQuery, state: FSMContext) -> None:
    aid = int(call.data.split(":", 1)[1])
    a = db.get_assignment(aid)
    if not a or int(a["user_id"]) != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return
    if a["status"] != "active":
        await call.answer("Уже сдано", show_alert=True)
        return
    await state.set_state(Flow.submit_proof)
    await state.update_data(assignment_id=aid)
    await call.message.answer(
        "📤 <b>Сдай отчёт</b>\n\n"
        "Пришли <b>фото</b> (скрин) и в подписи напиши «готово» + детали.\n"
        "Можно отдельным сообщением: сначала фото, потом текст."
    )
    await call.answer()


@router.message(Flow.submit_proof, F.photo)
async def proof_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    aid = int(data.get("assignment_id", 0))
    a = db.get_assignment(aid)
    if not a or int(a["user_id"]) != (message.from_user.id if message.from_user else 0):
        await state.clear()
        return
    fid = message.photo[-1].file_id
    caption = (message.caption or "").strip()
    if caption:
        await _finalize_submit(message, state, aid, caption, fid)
        return
    await state.update_data(proof_file_id=fid)
    await message.answer("Фото получено. Теперь напиши текст: «готово» + детали.")


@router.message(Flow.submit_proof, F.text)
async def proof_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    aid = int(data.get("assignment_id", 0))
    a = db.get_assignment(aid)
    if not a or int(a["user_id"]) != (message.from_user.id if message.from_user else 0):
        await state.clear()
        return
    fid = data.get("proof_file_id", "")
    if not fid:
        await message.answer("Сначала пришли фото-скрин.")
        return
    text = (message.text or "").strip()
    await _finalize_submit(message, state, aid, text, fid)


async def _finalize_submit(
    message: Message, state: FSMContext, aid: int, text: str, fid: str
) -> None:
    db.submit_assignment(aid, proof_text=text, proof_file_id=fid)
    await _notify_admin_submit(message, aid, text, fid)
    await state.clear()
    await message.answer("✅ Отчёт отправлен на проверку.", reply_markup=kb_main())


async def _notify_admin_submit(message: Message, aid: int, text: str, fid: str) -> None:
    a = db.get_assignment(aid)
    task = task_by_id(a["task_id"]) if a else None
    title = task.title if task else "?"
    w = db.get_worker(int(a["user_id"])) if a else {}
    trust = ""
    appr = int(w.get("approved_count") or 0)
    rej = int(w.get("rejected_count") or 0)
    if rej > appr and rej >= 2:
        trust = "\n⚠️ <b>Много отклонений</b> — проверь внимательно"
    await notify_admins(
        message.bot,
        "📥 <b>Новый отчёт</b>\n\n"
        f"👤 {_user_line(message)}\n"
        f"📌 {title}\n"
        f"💵 {a['reward_rub']:,.0f} ₽\n"
        f"📝 {text}\n"
        f"✅ ранее: {appr} · ❌ {rej}{trust}",
    )
    for aid_admin in WORK_ADMIN_IDS:
        try:
            await message.bot.send_photo(
                aid_admin,
                fid,
                caption=f"Отчёт #{aid}",
                reply_markup=kb_admin_review(aid),
            )
        except Exception as e:
            logger.warning("admin photo %s: %s", aid_admin, e)


@router.callback_query(F.data.startswith("adm:ok:"))
async def cb_adm_ok(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    aid = int(call.data.split(":", 2)[2])
    row = db.approve_assignment(aid)
    if not row:
        await call.answer("Уже обработано", show_alert=True)
        return
    uid = int(row["user_id"])
    reward = float(row["reward_rub"])
    from work_bot.pushes import build_push

    try:
        await call.bot.send_message(
            uid,
            build_push(uid, "approved", {"reward": reward}),
            parse_mode="HTML",
            reply_markup=kb_main(),
        )
    except Exception:
        pass
    await call.message.answer(f"✅ Принято #{aid} · +{reward:,.0f} ₽".replace(",", " "))
    await call.answer("Зачислено")


@router.callback_query(F.data.startswith("adm:no:"))
async def cb_adm_no(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    aid = int(call.data.split(":", 2)[2])
    row = db.reject_assignment(aid, note="не прошло проверку")
    if not row:
        await call.answer("Уже обработано", show_alert=True)
        return
    uid = int(row["user_id"])
    from work_bot.pushes import build_push

    try:
        await call.bot.send_message(
            uid,
            build_push(uid, "rejected", {}),
            parse_mode="HTML",
            reply_markup=kb_main(),
        )
    except Exception:
        pass
    await call.message.answer(f"❌ Отклонено #{aid}")
    await call.answer("Отклонено")


@router.message(F.text)
async def fallback(message: Message) -> None:
    if (message.text or "").startswith("/"):
        return
    await message.answer("Нажми /menu — выбор заданий.", reply_markup=kb_main())
