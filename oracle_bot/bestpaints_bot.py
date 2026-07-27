"""Telegram: Лидоруб создаёт замер; админ — график замерщиков/менеджеров."""

from __future__ import annotations

import logging
import os
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from oracle_bot import bestpaints_crm as crm
from oracle_bot.config import ORACLE_ADMIN_IDS

logger = logging.getLogger("oracle_bot.bestpaints")
router = Router(name="bestpaints")


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


class NewZamer(StatesGroup):
    title = State()
    qualification = State()
    address = State()
    measure_date = State()
    client = State()
    audio = State()


class Grafik(StatesGroup):
    pick = State()



@router.message(Command("chatid", "bp_chatid"))
async def cmd_chatid(message: Message):
    """Покажет chat_id — добавьте бота в группу ops/подписанные и вызовите /chatid."""
    if not _enabled():
        return
    chat = message.chat
    title = chat.title or getattr(chat, "full_name", None) or "-"
    await message.answer(
        f"chat_id = {chat.id}\n"
        f"тип: {chat.type}\n"
        f"title: {title}\n\n"
        "Скопируйте число и пришлите:\n"
        "· ops → BESTPAINTS_TG_CHAT_OPS\n"
        "· подписанные договоры → BESTPAINTS_TG_CHAT_SIGNED"
    )


@router.message(Command("bp", "bestpaints", "zamer_help"))
async def cmd_help(message: Message):
    if not _enabled():
        return
    await message.answer(
        "BestPaints · замеры\n\n"
        "Лидоруб:\n"
        "/zamer — создать новый замер (сделка)\n\n"
        "Админ / группы:\n/chatid — узнать Chat ID группы\n"
        "/grafik — кто сегодня в графике\n"
        "/grafik_add YYYY-MM-DD surveyor|manager ID — добавить в график\n"
        "/grafik_clear YYYY-MM-DD — очистить день\n"
        "/bp_staff — список ID замерщиков/менеджеров\n"
    )


@router.message(Command("bp_staff"))
async def cmd_staff(message: Message):
    if not _enabled() or not message.from_user or not _is_admin(message.from_user.id):
        return
    staff = crm.load_staff()
    lines = ["Замерщики:"]
    for s in staff.get("surveyors") or []:
        lines.append(f"  {s.get('id')} — {s.get('name')} {s.get('phone')}")
    lines.append("Менеджеры:")
    for m in staff.get("managers") or []:
        lines.append(f"  {m.get('id')} — {m.get('name')} {m.get('phone')}")
    await message.answer("\n".join(lines) or "Пусто")


@router.message(Command("grafik"))
async def cmd_grafik(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await message.answer("Только админ заполняет график.")
        return
    day = (command.args or "").strip() or crm.today_str()
    rows = crm.list_schedule(day)
    if not rows:
        await message.answer(
            f"График на {day} пуст.\n"
            f"Добавьте: /grafik_add {day} surveyor sv_ivanov\n"
            f"Список ID: /bp_staff"
        )
        return
    lines = [f"График {day}:"]
    for r in rows:
        lines.append(f"· {r['role']}: {r['person_name']} ({r['person_id']})")
    await message.answer("\n".join(lines))


@router.message(Command("grafik_add"))
async def cmd_grafik_add(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user or not _is_admin(message.from_user.id):
        return
    parts = (command.args or "").split()
    if len(parts) < 3:
        await message.answer("Формат: /grafik_add YYYY-MM-DD surveyor|manager ID")
        return
    day, role, pid = parts[0], parts[1], parts[2]
    try:
        crm.set_schedule(role, pid, day)
    except ValueError as e:
        await message.answer(f"Ошибка: {e}")
        return
    await message.answer(f"OK: {role} {pid} → {day}")


@router.message(Command("grafik_clear"))
async def cmd_grafik_clear(message: Message, command: CommandObject):
    if not _enabled() or not message.from_user or not _is_admin(message.from_user.id):
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
    await state.clear()
    await state.set_state(NewZamer.title)
    await message.answer(
        "Новый замер BestPaints\n\n"
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
    await message.answer("5/6 Клиент: имя и телефон одной строкой (или «-»):")


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
    if obj["status"] == "created":
        await message.answer(
            f"Сделка «{obj['title']}» создана, но график замерщиков пуст.\n"
            f"Админ должен заполнить /grafik.\n{link}"
        )
    else:
        await message.answer(
            f"✅ Сделка в работе\n"
            f"«{obj['title']}»\n"
            f"Статус: {obj['status_label']}\n"
            f"Замерщик: {obj['surveyor_name']}\n"
            f"{link}"
        )
