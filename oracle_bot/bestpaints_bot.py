"""Telegram: Лидоруб создаёт замер; админ — график замерщиков/менеджеров."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from oracle_bot import bestpaints_crm as crm
from oracle_bot.config import ORACLE_ADMIN_IDS

logger = logging.getLogger("oracle_bot.bestpaints")
router = Router(name="bestpaints")

CABINET = "https://moracul.ru/bestpaints/"
PDF = "https://moracul.ru/bestpaints/docs/BestPaints_Obuchenie_v5.pdf?v=20260728a"
PLAYBOOK = "https://moracul.ru/bestpaints/docs/TOMORROW_PLAYBOOK.html"


def _enabled() -> bool:
    return os.getenv("BESTPAINTS_TG_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def _admin_ids() -> set[int]:
    raw = os.getenv("BESTPAINTS_ADMIN_IDS", "").strip()
    ids: set[int] = set(ORACLE_ADMIN_IDS or set())
    if raw:
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    return ids


def _lidarub_ids() -> set[int]:
    """Who may create deals. Empty = any admin OR anyone if BESTPAINTS_LIDARUB_OPEN=1."""
    raw = os.getenv("BESTPAINTS_LIDARUB_IDS", "").strip()
    ids: set[int] = set()
    if raw:
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    if not ids and os.getenv("BESTPAINTS_LIDARUB_OPEN", "0").strip() in ("1", "true", "yes"):
        return set()  # open — allow all, checked separately
    if not ids:
        return _admin_ids()
    return ids


def _can_create(uid: int) -> bool:
    if os.getenv("BESTPAINTS_LIDARUB_OPEN", "0").strip() in ("1", "true", "yes"):
        return True
    return uid in _lidarub_ids()


def _is_admin(uid: int) -> bool:
    return uid in _admin_ids()


def _can_grafik(uid: int) -> bool:
    """График: админ или открытый режим (команда на демо с 3 людьми)."""
    if _is_admin(uid):
        return True
    return os.getenv("BESTPAINTS_LIDARUB_OPEN", "0").strip() in ("1", "true", "yes")


def _help_text() -> str:
    today = crm.today_str()
    tomorrow = (datetime.now(crm.TZ).date() + timedelta(days=1)).isoformat()
    duty = crm.on_duty("surveyor", today)
    duty_s = ", ".join(p["name"] for p in duty) if duty else "ПУСТО — заполните график!"
    return (
        "🔧 BestPaints · команды и настройка\n\n"
        f"📅 Сегодня {today}\n"
        f"Замерщики в графике: {duty_s}\n\n"
        "——— КАБИНЕТ ——-\n"
        f"Сайт: {CABINET}\n"
        "Логин: bestpaints\n"
        "Пароль: ZamerBp2026!\n"
        f"Обучение PDF: {PDF}\n"
        f"Шпаргалка на завтра: {PLAYBOOK}\n\n"
        "——— ГРАФИК (календарь смен) ——-\n"
        "Без графика сделка НЕ назначается замерщику.\n"
        f"/grafik — кто в графике сегодня\n"
        f"/grafik {tomorrow} — график на дату\n"
        "/grafik_fill — ВСЕХ в график на сегодня (кнопки)\n"
        f"/grafik_fill {tomorrow} — всех на завтра\n"
        "/grafik_add YYYY-MM-DD surveyor|manager ID\n"
        "  пример: /grafik_add {today} surveyor sv_1\n"
        f"/grafik_clear {today} — очистить день\n"
        "/bp_staff — ID замерщиков и менеджеров\n\n"
        "——— ЛИДОРУБ ——-\n"
        "/zamer — создать сделку (название → квалификация → адрес → дата → клиент → аудио → «готово»)\n\n"
        "——— ГРУППЫ ——-\n"
        "/chatid — в группе BP Ops / BP Подписанные (привязка chat_id)\n"
        "Ops = лента статусов · Подписанные = только договоры\n\n"
        "——— ЦИКЛ СДЕЛКИ ——-\n"
        "1) /grafik_fill на дату замера\n"
        "2) /zamer → сделка «Замер назначен»\n"
        "3) В кабинете: Взял → Выезд → На адресе → конструктор\n"
        "4) Заключил → группа Подписанные · Не заключил → менеджер из графика\n\n"
        "/help — эта шпаргалка снова"
    )


async def setup_bot_commands(bot) -> None:
    """Меню команд в Telegram (личное и группы)."""
    private = [
        BotCommand(command="start", description="Шпаргалка: команды и настройка"),
        BotCommand(command="help", description="Все команды BestPaints"),
        BotCommand(command="zamer", description="Лидоруб: новая сделка"),
        BotCommand(command="grafik", description="Кто сегодня в графике"),
        BotCommand(command="grafik_fill", description="Поставить всех в график на день"),
        BotCommand(command="grafik_add", description="Добавить одного в график"),
        BotCommand(command="grafik_clear", description="Очистить график дня"),
        BotCommand(command="bp_staff", description="ID замерщиков / менеджеров"),
        BotCommand(command="chatid", description="Chat ID группы / привязка"),
    ]
    groups = [
        BotCommand(command="chatid", description="Привязать эту группу (Ops/Подписанные)"),
        BotCommand(command="grafik", description="Кто в графике сегодня"),
        BotCommand(command="grafik_fill", description="Заполнить график на сегодня"),
        BotCommand(command="zamer", description="Новая сделка (Лидоруб)"),
        BotCommand(command="help", description="Шпаргалка команд"),
    ]
    try:
        await bot.set_my_commands(private, scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(groups, scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(private)  # default
    except Exception:
        logger.exception("set_my_commands failed")


class NewZamer(StatesGroup):
    title = State()
    qualification = State()
    address = State()
    measure_date = State()
    client = State()
    audio = State()


class Grafik(StatesGroup):
    pick = State()


def _fill_keyboard(day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Всех на {day}",
                    callback_data=f"bpfill:{day}:all",
                )
            ],
            [
                InlineKeyboardButton(text="Только замерщики", callback_data=f"bpfill:{day}:surveyor"),
                InlineKeyboardButton(text="Только менеджеры", callback_data=f"bpfill:{day}:manager"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="bpfill:cancel")],
        ]
    )


def _fill_schedule(day: str, who: str) -> list[str]:
    staff = crm.load_staff()
    lines: list[str] = []
    roles: list[tuple[str, str]] = []
    if who in ("all", "surveyor"):
        for s in staff.get("surveyors") or []:
            roles.append(("surveyor", s["id"]))
    if who in ("all", "manager"):
        for m in staff.get("managers") or []:
            roles.append(("manager", m["id"]))
    name_by: dict[str, str] = {}
    for s in staff.get("surveyors") or []:
        name_by[f"surveyor:{s.get('id')}"] = s.get("name") or s.get("id") or ""
    for m in staff.get("managers") or []:
        name_by[f"manager:{m.get('id')}"] = m.get("name") or m.get("id") or ""
    for role, pid in roles:
        try:
            crm.set_schedule(role, pid, day)
            lines.append(f"· {role}: {name_by.get(f'{role}:{pid}', pid)}")
        except ValueError as e:
            lines.append(f"· {role} {pid}: ошибка {e}")
    return lines


@router.message(CommandStart())
@router.message(Command("help", "bp", "bestpaints", "zamer_help"))
async def cmd_start_help(message: Message):
    if not _enabled():
        return
    linked = ""
    if message.from_user:
        hit = crm.link_telegram_user(
            tg_id=message.from_user.id,
            username=message.from_user.username or "",
            full_name=message.from_user.full_name or "",
        )
        if hit:
            role_ru = {"surveyor": "замерщик", "manager": "менеджер", "lidarub": "лидоруб"}.get(
                hit.get("role") or "", hit.get("role") or ""
            )
            linked = f"\n✅ Вы в команде: {hit.get('name')} ({role_ru})\n"
        elif message.from_user.username:
            linked = (
                f"\nВаш ник @{message.from_user.username} пока не в команде.\n"
                "Админ добавляет имя+@ник во вкладке «Команда» на сайте.\n"
            )
    await message.answer(linked + _help_text())


@router.message(Command("chatid", "bp_chatid"))
async def cmd_chatid(message: Message):
    """Покажет chat_id и сохранит группу в CRM (ops / signed по названию)."""
    if not _enabled():
        return
    chat = message.chat
    title = chat.title or getattr(chat, "full_name", None) or "-"
    role = None
    low = (title or "").lower()
    if "подпис" in low or "signed" in low:
        role = "signed"
    elif "ops" in low or "операц" in low:
        role = "ops"
    saved = ""
    if chat.type in ("group", "supergroup"):
        try:
            info = crm.register_tg_chat(chat.id, title, role)
            saved = f"\n✅ Привязано как {info['role']} (chat_id={info['chat_id']})"
        except Exception as e:  # noqa: BLE001
            saved = f"\n⚠️ Не сохранил: {e}"
    await message.answer(
        f"chat_id = {chat.id}\n"
        f"тип: {chat.type}\n"
        f"title: {title}"
        f"{saved}\n\n"
        "Если писали в личку боту — перешлите любое сообщение из группы сюда."
    )


@router.message(Command("bp_staff"))
async def cmd_staff(message: Message):
    if not _enabled() or not message.from_user:
        return
    if not _can_grafik(message.from_user.id):
        await message.answer("Нет доступа к справочнику. Попросите админа.")
        return
    staff = crm.load_staff()
    lines = ["Замерщики (ID для /grafik_add):"]
    for s in staff.get("surveyors") or []:
        lines.append(f"  {s.get('id')} — {s.get('name')} {s.get('phone')}")
    lines.append("Менеджеры:")
    for m in staff.get("managers") or []:
        lines.append(f"  {m.get('id')} — {m.get('name')} {m.get('phone')}")
    lines.append("\nБыстро: /grafik_fill — поставить всех на сегодня")
    await message.answer("\n".join(lines) or "Пусто")


@router.message(Command("grafik"))
async def cmd_grafik(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user:
        return
    if not _can_grafik(message.from_user.id):
        await message.answer("Только админ / команда с доступом заполняет график.")
        return
    day = (command.args or "").strip() or crm.today_str()
    rows = crm.list_schedule(day)
    if not rows:
        await message.answer(
            f"График на {day} пуст.\n"
            f"Нажмите кнопку или: /grafik_fill {day}",
            reply_markup=_fill_keyboard(day),
        )
        return
    lines = [f"График {day}:"]
    for r in rows:
        lines.append(f"· {r['role']}: {r['person_name']} ({r['person_id']})")
    lines.append("\nДобавить ещё: /grafik_fill " + day)
    await message.answer("\n".join(lines), reply_markup=_fill_keyboard(day))


@router.message(Command("grafik_fill"))
async def cmd_grafik_fill(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user:
        return
    if not _can_grafik(message.from_user.id):
        await message.answer("Нет доступа к графику.")
        return
    day = (command.args or "").strip() or crm.today_str()
    await message.answer(
        f"Заполнить график на {day}:\n"
        "«Всех» = оба замерщика + оба менеджера.\n"
        "После этого /zamer сразу назначит замерщика.",
        reply_markup=_fill_keyboard(day),
    )


@router.callback_query(F.data.startswith("bpfill:"))
async def cb_grafik_fill(query: CallbackQuery):
    if not _enabled() or not query.from_user:
        await query.answer()
        return
    if not _can_grafik(query.from_user.id):
        await query.answer("Нет доступа", show_alert=True)
        return
    data = (query.data or "").split(":")
    if len(data) < 2 or data[1] == "cancel":
        await query.message.edit_text("Отменено.") if query.message else None
        await query.answer()
        return
    if len(data) < 3:
        await query.answer("bad")
        return
    day, who = data[1], data[2]
    lines = _fill_schedule(day, who)
    text = f"✅ График {day}:\n" + ("\n".join(lines) if lines else "никого не добавил")
    text += f"\n\nПроверка: /grafik {day}\nДальше Лидоруб: /zamer"
    if query.message:
        await query.message.edit_text(text)
    await query.answer("Готово")


@router.message(Command("grafik_add"))
async def cmd_grafik_add(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user:
        return
    if not _can_grafik(message.from_user.id):
        await message.answer("Нет доступа к графику.")
        return
    parts = (command.args or "").split()
    if len(parts) < 3:
        await message.answer(
            "Формат: /grafik_add YYYY-MM-DD surveyor|manager ID\n"
            f"Пример: /grafik_add {crm.today_str()} surveyor sv_1\n"
            "Или проще: /grafik_fill"
        )
        return
    day, role, pid = parts[0], parts[1], parts[2]
    try:
        crm.set_schedule(role, pid, day)
    except ValueError as e:
        await message.answer(f"Ошибка: {e}\nСписок ID: /bp_staff")
        return
    await message.answer(f"OK: {role} {pid} → {day}\nПроверка: /grafik {day}")


@router.message(Command("grafik_clear"))
async def cmd_grafik_clear(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user:
        return
    if not _can_grafik(message.from_user.id):
        await message.answer("Нет доступа к графику.")
        return
    day = (command.args or "").strip() or crm.today_str()
    n = crm.clear_schedule(day)
    await message.answer(f"Удалено записей графика на {day}: {n}")


@router.message(Command("zamer", "new_zamer"))
async def cmd_zamer(message: Message, state: FSMContext):
    if not _enabled() or not message.from_user:
        return
    if not _can_create(message.from_user.id):
        await message.answer("Нет доступа Лидоруба. Попросите админа добавить ваш Telegram ID.")
        return
    today = crm.today_str()
    duty = crm.on_duty("surveyor", today)
    warn = ""
    if not duty:
        warn = (
            f"\n⚠️ График замерщиков на {today} пуст — сделка останется «Создана».\n"
            f"Сначала: /grafik_fill {today}\n"
        )
    await state.clear()
    await state.set_state(NewZamer.title)
    await message.answer(
        "Новый замер BestPaints\n"
        f"{warn}\n"
        "1/6 Название сделки (как в вашей CRM):"
    )


@router.message(NewZamer.title)
async def zamer_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Введите название сделки текстом.")
        return
    await state.update_data(title=title)
    await state.set_state(NewZamer.qualification)
    await message.answer("2/6 Квалификация (комментарий к сделке):")


@router.message(NewZamer.qualification)
async def zamer_qual(message: Message, state: FSMContext):
    await state.update_data(qualification=(message.text or "").strip())
    await state.set_state(NewZamer.address)
    await message.answer("3/6 Адрес объекта:")


@router.message(NewZamer.address)
async def zamer_addr(message: Message, state: FSMContext):
    await state.update_data(address=(message.text or "").strip())
    await state.set_state(NewZamer.measure_date)
    await message.answer(f"4/6 Дата замера (YYYY-MM-DD), сегодня {crm.today_str()}:")


@router.message(NewZamer.measure_date)
async def zamer_date(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    # accept DD.MM.YYYY
    md = raw
    if "." in raw and len(raw.split(".")) == 3:
        d, m, y = raw.split(".")
        md = f"{y.zfill(4)}-{m.zfill(2)}-{d.zfill(2)}"
    if len(md) != 10 or md[4] != "-" or md[7] != "-":
        await message.answer("Формат даты: 2026-07-28 или 28.07.2026")
        return
    await state.update_data(measure_date=md)
    await state.set_state(NewZamer.client)
    duty = crm.on_duty("surveyor", md)
    note = ""
    if not duty:
        note = f"\n⚠️ На {md} график пуст. После сделки: /grafik_fill {md}"
    await message.answer(f"5/6 Клиент: имя и телефон одной строкой (или «-»):{note}")


@router.message(NewZamer.client)
async def zamer_client(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    name, phone = "", ""
    if raw and raw != "-":
        parts = raw.rsplit(" ", 1)
        if len(parts) == 2 and any(ch.isdigit() for ch in parts[1]):
            name, phone = parts[0], parts[1]
        else:
            name = raw
    await state.update_data(client_name=name, client_phone=phone, audio=[])
    await state.set_state(NewZamer.audio)
    await message.answer(
        "6/6 Пришлите аудио (voice/файл) — можно несколько.\n"
        "Когда закончите — напишите «готово»."
    )


@router.message(NewZamer.audio, F.voice | F.audio | F.document)
async def zamer_audio(message: Message, state: FSMContext):
    data = await state.get_data()
    audio: list[dict[str, Any]] = list(data.get("audio") or [])
    file_id = ""
    name = "audio"
    if message.voice:
        file_id = message.voice.file_id
        name = "voice.ogg"
    elif message.audio:
        file_id = message.audio.file_id
        name = message.audio.file_name or "audio.mp3"
    elif message.document:
        file_id = message.document.file_id
        name = message.document.file_name or "file"
    if file_id:
        audio.append({"file_id": file_id, "name": name, "tg_message_id": message.message_id})
        await state.update_data(audio=audio)
        await message.answer(f"Аудио #{len(audio)} сохранено. Ещё или «готово».")


@router.message(NewZamer.audio)
async def zamer_finish(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    if text not in ("готово", "done", "ok", "готово.", "/done"):
        await message.answer("Пришлите аудио или напишите «готово».")
        return
    data = await state.get_data()
    await state.clear()
    uid = message.from_user.id if message.from_user else 0
    uname = message.from_user.full_name if message.from_user else "Лидоруб"
    try:
        obj = crm.create_object(
            {
                "title": data.get("title"),
                "qualification": data.get("qualification"),
                "address": data.get("address"),
                "measure_date": data.get("measure_date"),
                "client_name": data.get("client_name"),
                "client_phone": data.get("client_phone"),
                "audio": data.get("audio") or [],
                "lidarub_name": uname,
                "lidarub_tg_id": str(uid),
                "deal_source": "telegram",
            }
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("create_object failed")
        await message.answer(f"Не удалось создать сделку: {e}")
        return

    link = f"https://moracul.ru/bestpaints/?crm={obj['id']}"
    md = data.get("measure_date") or crm.today_str()
    if obj["status"] == "created":
        await message.answer(
            f"Сделка «{obj['title']}» создана, но график замерщиков на {md} пуст.\n"
            f"Админ: /grafik_fill {md}\n"
            f"Потом в кабинете «Назначить из графика».\n{link}",
            reply_markup=_fill_keyboard(md),
        )
    else:
        await message.answer(
            f"✅ Сделка в работе\n"
            f"«{obj['title']}»\n"
            f"Статус: {obj['status_label']}\n"
            f"Замерщик: {obj['surveyor_name']}\n"
            f"{link}"
        )


@router.message(F.forward_from_chat)
async def forward_bind_chat(message: Message):
    """В личке: переслать сообщение из BP Ops / BP Подписанные → привязка chat_id."""
    if not _enabled() or not message.from_user:
        return
    if not _is_admin(message.from_user.id) and not _can_create(message.from_user.id):
        return
    fc = message.forward_from_chat
    if not fc or fc.type not in ("group", "supergroup"):
        return
    title = fc.title or "-"
    low = title.lower()
    role = "signed" if ("подпис" in low or "signed" in low) else "ops" if ("ops" in low or "операц" in low) else None
    try:
        info = crm.register_tg_chat(fc.id, title, role)
        await message.answer(f"✅ Группа «{title}» → {info['role']} ({info['chat_id']})")
    except Exception as e:  # noqa: BLE001
        await message.answer(f"Ошибка: {e}")


@router.my_chat_member()
async def on_added_to_group(event):
    """Автопривязка при добавлении бота в группу с нужным названием."""
    if not _enabled():
        return
    chat = event.chat
    if chat.type not in ("group", "supergroup"):
        return
    new = event.new_chat_member
    if not new or new.status not in ("member", "administrator"):
        return
    title = chat.title or ""
    low = title.lower()
    if not any(k in low for k in ("ops", "операц", "подпис", "signed", "bp ")):
        return
    role = "signed" if ("подпис" in low or "signed" in low) else "ops"
    try:
        crm.register_tg_chat(chat.id, title, role)
        logger.info("auto-bound TG %s as %s", chat.id, role)
    except Exception:
        logger.exception("auto-bind failed")
