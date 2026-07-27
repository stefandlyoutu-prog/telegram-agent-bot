"""BestPaints CRM: сделки замера (Лидоруб → график → замерщик → менеджер)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("BESTPAINTS_TZ", "Europe/Moscow"))

# Статусы воронки (как в ТЗ)
STATUSES = [
    ("created", "Создана", "#9aada2"),
    ("assigned", "Замер назначен", "#c4a35a"),
    ("accepted", "Замерщик взял в работу", "#6fcf97"),
    ("visit_confirmed", "Выезд подтверждён", "#56ccf2"),
    ("on_site", "На адресе · замер", "#2f80ed"),
    ("contract_signed", "Договор заключён", "#27ae60"),
    ("contract_declined", "Не заключён", "#e07a6a"),
    ("manager_assigned", "У менеджера", "#f2994a"),
    ("manager_accepted", "Менеджер взял", "#219653"),
    ("closed", "Закрыта", "#4f5b58"),
]

STATUS_MAP = {s[0]: {"label": s[1], "color": s[2]} for s in STATUSES}
VALID_STATUSES = set(STATUS_MAP)

CHECKLIST_SIGNED = [
    {"id": "photos", "label": "Фото объекта загружены (ссылка)"},
    {"id": "video", "label": "Видео загружено (ссылка)"},
    {"id": "tz", "label": "ТЗ по сделке загружено (ссылка)"},
    {"id": "contract_scan", "label": "Договор / скан приложен"},
    {"id": "pay_terms", "label": "Этапы оплаты озвучены клиенту"},
]

CHECKLIST_DECLINED = [
    {"id": "reason", "label": "Причина отказа записана"},
    {"id": "why", "label": "Почему не заключили (подробно)"},
    {"id": "objection", "label": "Возражение / конкурент"},
    {"id": "photos", "label": "Фото/замер сохранены (ссылка)"},
    {"id": "tz_draft", "label": "Черновик ТЗ / смета для менеджера"},
]


def _db_path() -> Path:
    raw = os.getenv("BESTPAINTS_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    if Path("/var/data").exists():
        return Path("/var/data/bestpaints_crm.db")
    return Path(__file__).resolve().parents[1] / "data" / "bestpaints_crm.db"


def _staff_path() -> Path:
    return Path(__file__).resolve().parent / "static" / "bestpaints" / "data" / "crm_staff.json"


def load_staff() -> dict[str, Any]:
    path = _staff_path()
    if not path.exists():
        return {"surveyors": [], "managers": [], "zones": [], "escalation_hours": 2}
    return json.loads(path.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(objects)").fetchall()}
    alters = {
        "qualification": "TEXT NOT NULL DEFAULT ''",
        "measure_date": "TEXT NOT NULL DEFAULT ''",
        "audio_json": "TEXT NOT NULL DEFAULT '[]'",
        "uploads_json": "TEXT NOT NULL DEFAULT '{}'",
        "refusal_reason": "TEXT NOT NULL DEFAULT ''",
        "deleted_at": "REAL",
        "lidarub_tg_id": "TEXT NOT NULL DEFAULT ''",
        "visit_reminded_at": "REAL",
        "deal_source": "TEXT NOT NULL DEFAULT 'web'",
    }
    for name, decl in alters.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE objects ADD COLUMN {name} {decl}")
    # rename semantic: ledorub_* остаётся в БД, в API отдаём как lidarub


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              address TEXT NOT NULL DEFAULT '',
              client_name TEXT NOT NULL DEFAULT '',
              client_phone TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'created',
              surveyor_id TEXT NOT NULL DEFAULT '',
              surveyor_name TEXT NOT NULL DEFAULT '',
              surveyor_phone TEXT NOT NULL DEFAULT '',
              manager_id TEXT NOT NULL DEFAULT '',
              manager_name TEXT NOT NULL DEFAULT '',
              manager_phone TEXT NOT NULL DEFAULT '',
              ledorub_name TEXT NOT NULL DEFAULT '',
              ledorub_phone TEXT NOT NULL DEFAULT '',
              survey_local_id TEXT NOT NULL DEFAULT '',
              checklist_json TEXT NOT NULL DEFAULT '{}',
              notes TEXT NOT NULL DEFAULT '',
              qualification TEXT NOT NULL DEFAULT '',
              measure_date TEXT NOT NULL DEFAULT '',
              audio_json TEXT NOT NULL DEFAULT '[]',
              uploads_json TEXT NOT NULL DEFAULT '{}',
              refusal_reason TEXT NOT NULL DEFAULT '',
              deleted_at REAL,
              lidarub_tg_id TEXT NOT NULL DEFAULT '',
              visit_reminded_at REAL,
              deal_source TEXT NOT NULL DEFAULT 'web',
              assigned_at REAL,
              accepted_at REAL,
              visit_confirmed_at REAL,
              on_site_at REAL,
              estimate_at REAL,
              contract_at REAL,
              escalated_at REAL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              object_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              message TEXT NOT NULL,
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedule (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              role TEXT NOT NULL,
              person_id TEXT NOT NULL,
              work_date TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL,
              UNIQUE(role, person_id, work_date)
            );
            CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);
            CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule(work_date, role);
            """
        )
        _ensure_columns(conn)


def _now() -> float:
    return time.time()


def today_str() -> str:
    return datetime.now(TZ).date().isoformat()


def _parse_json(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw or "") if raw else default
    except json.JSONDecodeError:
        return default


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    d["checklist"] = _parse_json(d.pop("checklist_json", None) or "{}", {})
    d["audio"] = _parse_json(d.pop("audio_json", None) or "[]", [])
    d["uploads"] = _parse_json(d.pop("uploads_json", None) or "{}", {})
    # aliases
    d["lidarub_name"] = d.get("ledorub_name") or ""
    d["lidarub_phone"] = d.get("ledorub_phone") or ""
    d["deal_name"] = d.get("title") or ""
    meta = STATUS_MAP.get(d.get("status") or "", {"label": d.get("status"), "color": "#999"})
    d["status_label"] = meta["label"]
    d["status_color"] = meta["color"]
    d["is_deleted"] = bool(d.get("deleted_at"))
    return d


def log_event(object_id: str, kind: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
            (object_id, kind, message, _now()),
        )


def notify_phones(text: str, phones: list[str]) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for phone in phones:
        p = (phone or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        notes.extend(notify_all(text, phone=p, skip_tg=True))
    # one TG ops message
    notes.extend(notify_all(text, phone="", skip_tg=False))
    return notes


def notify_all(text: str, *, phone: str = "", telegram_chat: str = "", skip_tg: bool = False) -> list[str]:
    notes: list[str] = []
    if phone and os.getenv("BESTPAINTS_SMS_URL", "").strip():
        notes.append(_send_sms(phone, text))
    elif phone:
        notes.append(f"SMS stub → {phone}: {text[:120]}")
    if skip_tg:
        return notes
    chat = telegram_chat or os.getenv("BESTPAINTS_TG_CHAT_OPS", "").strip()
    if chat and (
        os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip() or os.getenv("ORACLE_BOT_TOKEN", "").strip()
    ):
        notes.append(_send_telegram(chat, text))
    elif text and chat:
        notes.append(f"TG stub → {chat}: {text[:120]}")
    elif text and not chat:
        notes.append(f"TG stub: {text[:120]}")
    return notes


def _send_telegram(chat_id: str, text: str) -> str:
    token = os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip() or os.getenv("ORACLE_BOT_TOKEN", "").strip()
    if not token:
        return "TG skip: no token"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3500]}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=20) as r:
            r.read()
        return f"TG ok → {chat_id}"
    except Exception as e:  # noqa: BLE001
        return f"TG fail → {chat_id}: {e}"


def _send_sms(phone: str, text: str) -> str:
    tpl = os.getenv("BESTPAINTS_SMS_URL", "").strip()
    if not tpl:
        return "SMS stub"
    url = tpl.replace("{phone}", urllib.parse.quote(phone)).replace("{text}", urllib.parse.quote(text[:300]))
    try:
        method = os.getenv("BESTPAINTS_SMS_METHOD", "GET").upper()
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return f"SMS ok → {phone}"
    except Exception as e:  # noqa: BLE001
        return f"SMS fail → {phone}: {e}"


def _person_by_id(role: str, person_id: str) -> dict[str, str] | None:
    staff = load_staff()
    key = "surveyors" if role == "surveyor" else "managers"
    for p in staff.get(key) or []:
        if p.get("id") == person_id:
            return {"id": p.get("id") or "", "name": p.get("name") or "", "phone": p.get("phone") or ""}
    return None


def set_schedule(role: str, person_id: str, work_date: str, note: str = "") -> dict[str, Any]:
    init_db()
    if role not in ("surveyor", "manager"):
        raise ValueError("role must be surveyor|manager")
    if not _person_by_id(role, person_id):
        raise ValueError("unknown person_id")
    now = _now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO schedule(role, person_id, work_date, note, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(role, person_id, work_date) DO UPDATE SET note=excluded.note
            """,
            (role, person_id, work_date, note, now),
        )
    return {"ok": True, "role": role, "person_id": person_id, "work_date": work_date}


def clear_schedule(work_date: str, role: str | None = None) -> int:
    init_db()
    with connect() as conn:
        if role:
            cur = conn.execute("DELETE FROM schedule WHERE work_date=? AND role=?", (work_date, role))
        else:
            cur = conn.execute("DELETE FROM schedule WHERE work_date=?", (work_date,))
        return cur.rowcount


def list_schedule(work_date: str | None = None) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        if work_date:
            rows = conn.execute(
                "SELECT * FROM schedule WHERE work_date=? ORDER BY role, person_id", (work_date,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM schedule ORDER BY work_date DESC, role").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        person = _person_by_id(d["role"], d["person_id"]) or {}
        d["person_name"] = person.get("name") or d["person_id"]
        d["person_phone"] = person.get("phone") or ""
        out.append(d)
    return out


def on_duty(role: str, work_date: str | None = None) -> list[dict[str, str]]:
    """Who is on schedule for date (default today)."""
    d = work_date or today_str()
    people = []
    for row in list_schedule(d):
        if row["role"] != role:
            continue
        p = _person_by_id(role, row["person_id"])
        if p:
            people.append(p)
    return people


def pick_surveyor_from_schedule(work_date: str | None = None, address: str = "") -> tuple[dict[str, str] | None, str]:
    """
    Returns (person|None, reason).
    Prefer on-duty surveyors; among them prefer zone match; else first on duty.
    If schedule empty → (None, 'no_schedule').
    """
    duty = on_duty("surveyor", work_date)
    if not duty:
        return None, "no_schedule"

    staff = load_staff()
    addr = (address or "").lower()
    zone_ids: list[str] = []
    for zone in staff.get("zones") or []:
        keys = [str(k).lower() for k in zone.get("match") or []]
        if keys and any(k in addr for k in keys):
            zone_ids.append(zone.get("surveyor_id") or "")

    for sid in zone_ids:
        for p in duty:
            if p["id"] == sid:
                return p, "schedule+zone"
    # round-robin-ish: least assigned open deals today
    counts: dict[str, int] = {p["id"]: 0 for p in duty}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT surveyor_id, COUNT(*) c FROM objects
            WHERE deleted_at IS NULL AND status NOT IN ('closed')
              AND surveyor_id != ''
            GROUP BY surveyor_id
            """
        ).fetchall()
        for r in rows:
            if r["surveyor_id"] in counts:
                counts[r["surveyor_id"]] = r["c"]
    duty_sorted = sorted(duty, key=lambda p: (counts.get(p["id"], 0), p["name"]))
    return duty_sorted[0], "schedule"


def pick_manager_from_schedule(work_date: str | None = None) -> tuple[dict[str, str] | None, str]:
    duty = on_duty("manager", work_date)
    if not duty:
        # fallback any manager from staff
        managers = load_staff().get("managers") or []
        if not managers:
            return None, "no_managers"
        m = managers[0]
        return {"id": m.get("id") or "", "name": m.get("name") or "", "phone": m.get("phone") or ""}, "staff_fallback"
    return duty[0], "schedule"


def create_object(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    oid = "o_" + uuid.uuid4().hex[:12]
    title = (payload.get("title") or payload.get("deal_name") or "").strip() or "Сделка"
    address = (payload.get("address") or "").strip()
    client_name = (payload.get("client_name") or "").strip()
    client_phone = (payload.get("client_phone") or "").strip()
    lidarub_name = (payload.get("lidarub_name") or payload.get("ledorub_name") or "").strip() or "Лидоруб"
    lidarub_phone = (payload.get("lidarub_phone") or payload.get("ledorub_phone") or "").strip()
    qualification = (payload.get("qualification") or payload.get("comment") or "").strip()
    measure_date = (payload.get("measure_date") or "").strip()
    audio = payload.get("audio") or []
    if not isinstance(audio, list):
        audio = []
    deal_source = (payload.get("deal_source") or "web").strip()
    lidarub_tg_id = str(payload.get("lidarub_tg_id") or "")
    now = _now()

    # assignment date = measure day if set else today
    assign_day = measure_date or today_str()
    surveyor = None
    assign_reason = ""
    if payload.get("surveyor_id"):
        surveyor = _person_by_id("surveyor", str(payload["surveyor_id"]))
        assign_reason = "manual"
    if not surveyor:
        surveyor, assign_reason = pick_surveyor_from_schedule(assign_day, address)

    status = "assigned" if surveyor and surveyor.get("id") else "created"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO objects(
              id, title, address, client_name, client_phone, status,
              surveyor_id, surveyor_name, surveyor_phone,
              ledorub_name, ledorub_phone, checklist_json,
              qualification, measure_date, audio_json, deal_source, lidarub_tg_id,
              assigned_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                oid,
                title,
                address,
                client_name,
                client_phone,
                status,
                (surveyor or {}).get("id") or "",
                (surveyor or {}).get("name") or "",
                (surveyor or {}).get("phone") or "",
                lidarub_name,
                lidarub_phone,
                "{}",
                qualification,
                measure_date,
                json.dumps(audio, ensure_ascii=False),
                deal_source,
                lidarub_tg_id,
                now if status == "assigned" else None,
                now,
                now,
            ),
        )

    if status == "created":
        msg = (
            f"⚠️ BestPaints: сделка «{title}» создана, но график замерщиков на {assign_day} пуст. "
            f"Админ: заполните график (/grafik). Адрес: {address}"
        )
        notes = notify_all(msg)
        log_event(oid, "no_schedule", msg + " | " + "; ".join(notes))
    else:
        log_event(
            oid,
            "created",
            f"Сделка создана Лидорубом «{lidarub_name}»: {title}. Назначен {surveyor['name']} ({assign_reason})",
        )
        link = f"https://moracul.ru/bestpaints/?crm={oid}"
        msg = (
            f"BestPaints: создана сделка «{title}». Адрес: {address}. Дата замера: {measure_date or '—'}. "
            f"Квалификация: {qualification[:200] or '—'}. "
            f"Откройте {link} и нажмите «Взял в работу»."
        )
        notes = notify_phones(msg, [(surveyor or {}).get("phone") or ""])
        log_event(oid, "notify_surveyor", "; ".join(notes))

    obj = get_object(oid)
    assert obj
    obj["assign_reason"] = assign_reason
    obj["notify"] = notes if status == "assigned" else notes
    return obj


def list_objects(*, status: str | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
    init_db()
    escalate_overdue()
    send_visit_reminders()
    with connect() as conn:
        q = "SELECT * FROM objects WHERE 1=1"
        params: list[Any] = []
        if not include_deleted:
            q += " AND deleted_at IS NULL"
        if status:
            q += " AND status=?"
            params.append(status)
        q += " ORDER BY updated_at DESC"
        rows = conn.execute(q, params).fetchall()
    return [_row_to_dict(r) for r in rows if r]


def get_object(oid: str, *, include_deleted: bool = True) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
    obj = _row_to_dict(row)
    if obj and obj.get("is_deleted") and not include_deleted:
        return None
    return obj


def list_events(oid: str) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, message, created_at FROM events WHERE object_id=? ORDER BY id DESC LIMIT 80",
            (oid,),
        ).fetchall()
    return [dict(r) for r in rows]


def escalate_overdue() -> int:
    hours = float(load_staff().get("escalation_hours") or os.getenv("BESTPAINTS_ESCALATION_HOURS", "2"))
    cutoff = _now() - hours * 3600
    n = 0
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM objects
            WHERE status='assigned' AND deleted_at IS NULL
              AND assigned_at IS NOT NULL AND assigned_at < ?
              AND (escalated_at IS NULL OR escalated_at=0)
            """,
            (cutoff,),
        ).fetchall()
        for row in rows:
            d = dict(row)
            conn.execute(
                "UPDATE objects SET escalated_at=?, updated_at=? WHERE id=?",
                (_now(), _now(), d["id"]),
            )
            msg = (
                f"⚠️ Замерщик не взял в работу за {hours:g} ч: «{d['title']}», {d['address']}. "
                f"Назначен: {d['surveyor_name']} ({d['surveyor_phone']})."
            )
            notes = notify_phones(msg, [d.get("ledorub_phone") or ""])
            conn.execute(
                "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
                (d["id"], "escalation", msg + " | " + "; ".join(notes), _now()),
            )
            n += 1
    return n


def send_visit_reminders() -> int:
    """SMS day before measure_date if not yet visit_confirmed."""
    tomorrow = (datetime.now(TZ).date() + timedelta(days=1)).isoformat()
    n = 0
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM objects
            WHERE deleted_at IS NULL
              AND measure_date=?
              AND status IN ('accepted')
              AND (visit_reminded_at IS NULL OR visit_reminded_at=0)
            """,
            (tomorrow,),
        ).fetchall()
        for row in rows:
            d = dict(row)
            conn.execute(
                "UPDATE objects SET visit_reminded_at=?, updated_at=? WHERE id=?",
                (_now(), _now(), d["id"]),
            )
            link = f"https://moracul.ru/bestpaints/?crm={d['id']}"
            msg = (
                f"BestPaints: завтра замер «{d['title']}» ({d['address']}). "
                f"Позвоните клиенту и нажмите «Выезд подтверждён»: {link}"
            )
            notes = notify_phones(msg, [d.get("surveyor_phone") or ""])
            conn.execute(
                "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
                (d["id"], "visit_reminder", msg + " | " + "; ".join(notes), _now()),
            )
            n += 1
    return n


def _broadcast_status(obj: dict[str, Any], label: str) -> list[str]:
    link = f"https://moracul.ru/bestpaints/?crm={obj['id']}"
    msg = f"BestPaints: «{obj['title']}» → {label}. Адрес: {obj.get('address')}. {link}"
    phones = [
        obj.get("surveyor_phone") or "",
        obj.get("lidarub_phone") or obj.get("ledorub_phone") or "",
        obj.get("manager_phone") or "",
        obj.get("client_phone") or "",
    ]
    # client SMS optional — skip client by default to avoid spam; include staff only
    phones = [
        obj.get("surveyor_phone") or "",
        obj.get("lidarub_phone") or obj.get("ledorub_phone") or "",
        obj.get("manager_phone") or "",
    ]
    return notify_phones(msg, phones)


def soft_delete(oid: str) -> dict[str, Any]:
    obj = get_object(oid)
    if not obj:
        raise ValueError("object not found")
    with connect() as conn:
        conn.execute(
            "UPDATE objects SET deleted_at=?, updated_at=?, status=status WHERE id=?",
            (_now(), _now(), oid),
        )
    log_event(oid, "delete", "Сделка удалена (в корзине CRM)")
    out = get_object(oid)
    assert out
    return out


def restore_deleted(oid: str) -> dict[str, Any]:
    obj = get_object(oid, include_deleted=True)
    if not obj:
        raise ValueError("object not found")
    with connect() as conn:
        conn.execute("UPDATE objects SET deleted_at=NULL, updated_at=? WHERE id=?", (_now(), oid))
    log_event(oid, "restore", "Сделка восстановлена из удаления")
    out = get_object(oid)
    assert out
    return out


def transition(oid: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    obj = get_object(oid, include_deleted=True)
    if not obj:
        raise ValueError("object not found")
    if obj.get("is_deleted") and action not in ("restore", "purge"):
        raise ValueError("сделка удалена — сначала восстановите")

    now = _now()
    updates: dict[str, Any] = {"updated_at": now}
    message = action

    if action == "accept":
        updates["status"] = "accepted"
        updates["accepted_at"] = now
        message = f"{obj['surveyor_name'] or 'Замерщик'} взял в работу"
        _broadcast_status({**obj, **updates, "id": oid, "title": obj["title"], "address": obj["address"]}, "Замерщик взял в работу")

    elif action == "confirm_visit":
        updates["status"] = "visit_confirmed"
        updates["visit_confirmed_at"] = now
        message = "Выезд подтверждён"
        _broadcast_status(obj, "Выезд подтверждён")

    elif action in ("arrive", "start_measure"):
        updates["status"] = "on_site"
        updates["on_site_at"] = now
        message = "На адресе у клиента — начинаю замер"
        _broadcast_status(obj, "На адресе · замер начат")

    elif action == "estimate_done":
        # совместимость: оставляем на объекте, статус не обязателен
        updates["estimate_at"] = now
        if payload.get("survey_local_id"):
            updates["survey_local_id"] = payload["survey_local_id"]
        message = "Смета/замер сохранены"

    elif action in ("sign_contract", "sign_on_site"):
        updates["status"] = "contract_signed"
        updates["contract_at"] = now
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_SIGNED}, ensure_ascii=False)
        message = "Договор заключён на адресе"
        chat = os.getenv("BESTPAINTS_TG_CHAT_SIGNED", "").strip()
        notify_all(
            f"✍️ Договор заключён: «{obj['title']}»\nАдрес: {obj['address']}\nКлиент: {obj['client_name']} {obj['client_phone']}\nЗамерщик: {obj['surveyor_name']}",
            telegram_chat=chat,
        )
        _broadcast_status(obj, "Договор заключён")

    elif action in ("decline_contract", "decline_on_site"):
        updates["status"] = "contract_declined"
        updates["contract_at"] = now
        if payload.get("refusal_reason"):
            updates["refusal_reason"] = str(payload["refusal_reason"])
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_DECLINED}, ensure_ascii=False)
        message = "Договор не заключён на адресе"
        _broadcast_status(obj, "Не заключён — уйдёт менеджеру")

    elif action == "assign_manager":
        mid = (payload.get("manager_id") or "").strip()
        mgr = _person_by_id("manager", mid) if mid else None
        if not mgr:
            mgr, reason = pick_manager_from_schedule(obj.get("measure_date") or today_str())
            if not mgr:
                raise ValueError("нет менеджера в графике и в справочнике")
        else:
            reason = "manual"
        updates["status"] = "manager_assigned"
        updates["manager_id"] = mgr.get("id") or ""
        updates["manager_name"] = mgr.get("name") or ""
        updates["manager_phone"] = mgr.get("phone") or ""
        message = f"Назначен менеджер {updates['manager_name']} ({reason}) — защита ТЗ"
        notify_phones(
            f"🔔 Бери в работу (защита ТЗ): «{obj['title']}», {obj['address']}. "
            f"https://moracul.ru/bestpaints/?crm={oid}",
            [updates["manager_phone"]],
        )

    elif action == "manager_accept":
        updates["status"] = "manager_accepted"
        message = f"Менеджер {obj.get('manager_name') or ''} взял в работу"

    elif action == "close":
        updates["status"] = "closed"
        message = "Сделка закрыта"

    elif action == "reopen":
        # вернуть в работу: обычно к accepted или assigned
        target = (payload.get("status") or "accepted").strip()
        if target not in VALID_STATUSES or target == "closed":
            target = "accepted"
        updates["status"] = target
        updates["deleted_at"] = None
        message = f"Вернули в работу → {STATUS_MAP[target]['label']}"
        _broadcast_status(obj, f"Снова в работе: {STATUS_MAP[target]['label']}")

    elif action == "set_status":
        target = (payload.get("status") or "").strip()
        if target not in VALID_STATUSES:
            raise ValueError(f"unknown status: {target}")
        updates["status"] = target
        message = f"Статус вручную: {STATUS_MAP[target]['label']}"
        _broadcast_status(obj, STATUS_MAP[target]["label"])

    elif action == "delete":
        return soft_delete(oid)

    elif action == "restore":
        return restore_deleted(oid)

    elif action == "purge":
        with connect() as conn:
            conn.execute("DELETE FROM events WHERE object_id=?", (oid,))
            conn.execute("DELETE FROM objects WHERE id=?", (oid,))
        return {"id": oid, "purged": True}

    elif action == "save_checklist":
        updates["checklist_json"] = json.dumps(payload.get("checklist") or {}, ensure_ascii=False)
        if payload.get("uploads"):
            updates["uploads_json"] = json.dumps(payload.get("uploads") or {}, ensure_ascii=False)
        if payload.get("refusal_reason"):
            updates["refusal_reason"] = str(payload["refusal_reason"])
        message = "Чек-лист / ссылки обновлены"

    elif action == "link_survey":
        updates["survey_local_id"] = payload.get("survey_local_id") or ""
        message = "Привязан локальный замер"

    elif action == "save_uploads":
        updates["uploads_json"] = json.dumps(payload.get("uploads") or {}, ensure_ascii=False)
        message = "Ссылки на загрузки сохранены"

    elif action == "reassign_surveyor":
        sid = (payload.get("surveyor_id") or "").strip()
        person = _person_by_id("surveyor", sid) if sid else None
        if not person:
            person, reason = pick_surveyor_from_schedule(obj.get("measure_date") or today_str(), obj.get("address") or "")
            if not person:
                raise ValueError("график замерщиков пуст")
        else:
            reason = "manual"
        updates["surveyor_id"] = person["id"]
        updates["surveyor_name"] = person["name"]
        updates["surveyor_phone"] = person["phone"]
        updates["status"] = "assigned"
        updates["assigned_at"] = now
        updates["escalated_at"] = None
        message = f"Переназначен замерщик {person['name']} ({reason})"
        notify_phones(
            f"BestPaints: вам назначена сделка «{obj['title']}». https://moracul.ru/bestpaints/?crm={oid}",
            [person["phone"]],
        )

    else:
        raise ValueError(f"unknown action: {action}")

    # auto-assign manager after decline if still declined
    if updates.get("status") == "contract_declined" and action in ("decline_contract", "decline_on_site"):
        # keep declined; UI offers assign_manager — or auto:
        if os.getenv("BESTPAINTS_AUTO_MANAGER", "1").strip() not in ("0", "false", "no"):
            mgr, reason = pick_manager_from_schedule(obj.get("measure_date") or today_str())
            if mgr:
                updates["status"] = "manager_assigned"
                updates["manager_id"] = mgr["id"]
                updates["manager_name"] = mgr["name"]
                updates["manager_phone"] = mgr["phone"]
                message += f" → менеджер {mgr['name']}"
                notify_phones(
                    f"🔔 Бери в работу (защита ТЗ): «{obj['title']}», {obj['address']}. "
                    f"https://moracul.ru/bestpaints/?crm={oid}",
                    [mgr["phone"]],
                )

    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [oid]
    with connect() as conn:
        conn.execute(f"UPDATE objects SET {sets} WHERE id=?", vals)
    log_event(oid, action, message)
    out = get_object(oid)
    assert out
    return out


def meta() -> dict[str, Any]:
    init_db()
    return {
        "statuses": [{"id": a, "label": b, "color": c} for a, b, c in STATUSES],
        "staff": load_staff(),
        "checklists": {"signed": CHECKLIST_SIGNED, "declined": CHECKLIST_DECLINED},
        "escalation_hours": load_staff().get("escalation_hours", 2),
        "schedule_today": list_schedule(today_str()),
        "on_duty_surveyors": on_duty("surveyor"),
        "on_duty_managers": on_duty("manager"),
        "today": today_str(),
        "roles_hint": "Лидоруб создаёт сделку в ТГ; админ заполняет график; замерщик/менеджер ведут статусы в веб.",
    }
