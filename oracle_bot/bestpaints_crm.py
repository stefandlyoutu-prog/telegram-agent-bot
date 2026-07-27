"""BestPaints CRM: объекты, статусы, назначение, чек-листы, уведомления."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

STATUSES = [
    ("created", "Создан", "#9aada2"),
    ("assigned", "Назначен замерщик", "#c4a35a"),
    ("accepted", "Взял в работу", "#6fcf97"),
    ("visit_confirmed", "Выезд подтверждён", "#56ccf2"),
    ("on_site", "На объекте", "#2f80ed"),
    ("estimate_done", "Смета готова", "#bb6bd9"),
    ("contract_signed", "Договор подписан", "#27ae60"),
    ("contract_declined", "Договор не заключён", "#e07a6a"),
    ("manager_assigned", "Менеджер назначен", "#f2994a"),
    ("manager_accepted", "Менеджер взял", "#219653"),
    ("closed", "Закрыт", "#4f5b58"),
]

STATUS_MAP = {s[0]: {"label": s[1], "color": s[2]} for s in STATUSES}

CHECKLIST_SIGNED = [
    {"id": "photos", "label": "Фото объекта загружены"},
    {"id": "estimate", "label": "Смета согласована с клиентом"},
    {"id": "contract_scan", "label": "Договор подписан / скан приложен"},
    {"id": "pay_terms", "label": "Этапы оплаты озвучены"},
    {"id": "handoff", "label": "Передано менеджеру/производству"},
]

CHECKLIST_DECLINED = [
    {"id": "reason", "label": "Причина отказа зафиксирована"},
    {"id": "followup", "label": "Дата повторного контакта"},
    {"id": "competitor", "label": "Конкурент / возражение записаны"},
    {"id": "manager_brief", "label": "Бриф для менеджера заполнен"},
    {"id": "photos", "label": "Фото/замер сохранены"},
]


def _db_path() -> Path:
    raw = os.getenv("BESTPAINTS_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    # Prefer Render disk if present
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
            CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);
            """
        )


def _now() -> float:
    return time.time()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    try:
        d["checklist"] = json.loads(d.pop("checklist_json") or "{}")
    except json.JSONDecodeError:
        d["checklist"] = {}
    meta = STATUS_MAP.get(d.get("status") or "", {"label": d.get("status"), "color": "#999"})
    d["status_label"] = meta["label"]
    d["status_color"] = meta["color"]
    return d


def pick_surveyor(address: str) -> dict[str, str] | None:
    staff = load_staff()
    addr = (address or "").lower()
    for zone in staff.get("zones") or []:
        keys = [str(k).lower() for k in zone.get("match") or []]
        if keys and any(k in addr for k in keys):
            sid = zone.get("surveyor_id")
            for s in staff.get("surveyors") or []:
                if s.get("id") == sid:
                    return {
                        "id": s.get("id") or "",
                        "name": s.get("name") or "",
                        "phone": s.get("phone") or "",
                    }
    # fallback first surveyor
    surv = (staff.get("surveyors") or [None])[0]
    if not surv:
        return None
    return {"id": surv.get("id") or "", "name": surv.get("name") or "", "phone": surv.get("phone") or ""}


def log_event(object_id: str, kind: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
            (object_id, kind, message, _now()),
        )


def notify_all(text: str, *, phone: str = "", telegram_chat: str = "") -> list[str]:
    """Send SMS/Telegram if configured. Returns list of delivery notes."""
    notes: list[str] = []
    if phone and os.getenv("BESTPAINTS_SMS_URL", "").strip():
        notes.append(_send_sms(phone, text))
    elif phone:
        notes.append(f"SMS stub → {phone}: {text[:120]}")
    chat = telegram_chat or os.getenv("BESTPAINTS_TG_CHAT_OPS", "").strip()
    if chat and os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip():
        notes.append(_send_telegram(chat, text))
    elif text:
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
    """Generic GET/POST SMS gateway. BESTPAINTS_SMS_URL may contain {phone} {text}."""
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


def create_object(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    oid = "o_" + uuid.uuid4().hex[:12]
    title = (payload.get("title") or "").strip() or "Объект"
    address = (payload.get("address") or "").strip()
    client_name = (payload.get("client_name") or "").strip()
    client_phone = (payload.get("client_phone") or "").strip()
    ledorub_name = (payload.get("ledorub_name") or "").strip() or "Ледоруб"
    ledorub_phone = (payload.get("ledorub_phone") or "").strip()
    now = _now()

    surveyor = None
    if payload.get("surveyor_id"):
        for s in load_staff().get("surveyors") or []:
            if s.get("id") == payload["surveyor_id"]:
                surveyor = {"id": s["id"], "name": s.get("name") or "", "phone": s.get("phone") or ""}
                break
    if not surveyor:
        surveyor = pick_surveyor(address) or {"id": "", "name": "", "phone": ""}

    status = "assigned" if surveyor.get("id") else "created"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO objects(
              id, title, address, client_name, client_phone, status,
              surveyor_id, surveyor_name, surveyor_phone,
              ledorub_name, ledorub_phone, checklist_json,
              assigned_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                oid,
                title,
                address,
                client_name,
                client_phone,
                status,
                surveyor.get("id") or "",
                surveyor.get("name") or "",
                surveyor.get("phone") or "",
                ledorub_name,
                ledorub_phone,
                "{}",
                now if status == "assigned" else None,
                now,
                now,
            ),
        )
    log_event(oid, "created", f"Объект создан: {title}, {address}")
    notes = []
    if status == "assigned" and surveyor.get("phone"):
        msg = (
            f"BestPaints: новый замер «{title}». Адрес: {address}. Клиент: {client_name} {client_phone}. "
            f"Откройте https://moracul.ru/bestpaints/ и нажмите «Взял в работу»."
        )
        notes = notify_all(msg, phone=surveyor.get("phone") or "")
        log_event(oid, "notify_surveyor", "; ".join(notes))
    obj = get_object(oid)
    assert obj
    obj["notify"] = notes
    return obj


def list_objects(status: str | None = None) -> list[dict[str, Any]]:
    init_db()
    escalate_overdue()
    with connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM objects WHERE status=? ORDER BY updated_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM objects ORDER BY updated_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows if r]


def get_object(oid: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
    return _row_to_dict(row)


def list_events(oid: str) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, message, created_at FROM events WHERE object_id=? ORDER BY id DESC LIMIT 50",
            (oid,),
        ).fetchall()
    return [dict(r) for r in rows]


def escalate_overdue() -> int:
    """Escalate assigned but not accepted within N hours."""
    hours = float(load_staff().get("escalation_hours") or os.getenv("BESTPAINTS_ESCALATION_HOURS", "2"))
    cutoff = _now() - hours * 3600
    n = 0
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM objects
            WHERE status='assigned' AND assigned_at IS NOT NULL AND assigned_at < ?
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
            notes = notify_all(msg, phone=d.get("ledorub_phone") or "")
            conn.execute(
                "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
                (d["id"], "escalation", msg + " | " + "; ".join(notes), _now()),
            )
            n += 1
    return n


def transition(oid: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    obj = get_object(oid)
    if not obj:
        raise ValueError("object not found")
    now = _now()
    updates: dict[str, Any] = {"updated_at": now}
    event = action
    message = action

    if action == "accept":
        updates["status"] = "accepted"
        updates["accepted_at"] = now
        message = f"{obj['surveyor_name'] or 'Замерщик'} взял в работу"
        notify_all(
            f"✅ Взял в работу: «{obj['title']}» ({obj['address']})",
            phone=obj.get("ledorub_phone") or "",
        )
    elif action == "confirm_visit":
        updates["status"] = "visit_confirmed"
        updates["visit_confirmed_at"] = now
        message = "Выезд согласован с заказчиком"
        notify_all(
            f"📅 Выезд подтверждён: «{obj['title']}»",
            phone=obj.get("ledorub_phone") or "",
        )
    elif action == "arrive":
        updates["status"] = "on_site"
        updates["on_site_at"] = now
        message = "Замерщик на объекте"
    elif action == "estimate_done":
        updates["status"] = "estimate_done"
        updates["estimate_at"] = now
        if payload.get("survey_local_id"):
            updates["survey_local_id"] = payload["survey_local_id"]
        message = "Смета создана / обновлена"
    elif action == "sign_contract":
        updates["status"] = "contract_signed"
        updates["contract_at"] = now
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_SIGNED}, ensure_ascii=False)
        message = "Договор подписан"
        chat = os.getenv("BESTPAINTS_TG_CHAT_SIGNED", "").strip()
        notify_all(
            f"✍️ Подписан договор: «{obj['title']}»\nАдрес: {obj['address']}\nКлиент: {obj['client_name']} {obj['client_phone']}\nЗамерщик: {obj['surveyor_name']}",
            telegram_chat=chat,
        )
    elif action == "decline_contract":
        updates["status"] = "contract_declined"
        updates["contract_at"] = now
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_DECLINED}, ensure_ascii=False)
        message = "Договор не заключён"
    elif action == "assign_manager":
        staff = load_staff()
        mid = (payload.get("manager_id") or "").strip()
        mgr = None
        managers = staff.get("managers") or []
        if mid:
            mgr = next((m for m in managers if m.get("id") == mid), None)
        if not mgr and managers:
            mgr = managers[0]
        if not mgr:
            raise ValueError("no managers configured")
        updates["status"] = "manager_assigned"
        updates["manager_id"] = mgr.get("id") or ""
        updates["manager_name"] = mgr.get("name") or ""
        updates["manager_phone"] = mgr.get("phone") or ""
        message = f"Назначен менеджер {updates['manager_name']}"
        notify_all(
            f"🔔 Бери в работу: «{obj['title']}», {obj['address']}. Договор не заключён. Откройте BestPaints.",
            phone=updates["manager_phone"],
        )
    elif action == "manager_accept":
        updates["status"] = "manager_accepted"
        message = f"Менеджер {obj.get('manager_name') or ''} взял в работу"
    elif action == "close":
        updates["status"] = "closed"
        message = "Цепочка закрыта"
    elif action == "save_checklist":
        updates["checklist_json"] = json.dumps(payload.get("checklist") or {}, ensure_ascii=False)
        message = "Чек-лист обновлён"
    elif action == "link_survey":
        updates["survey_local_id"] = payload.get("survey_local_id") or ""
        message = "Привязан локальный замер"
    else:
        raise ValueError(f"unknown action: {action}")

    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [oid]
    with connect() as conn:
        conn.execute(f"UPDATE objects SET {sets} WHERE id=?", vals)
    log_event(oid, event, message)
    out = get_object(oid)
    assert out
    return out


def meta() -> dict[str, Any]:
    return {
        "statuses": [{"id": a, "label": b, "color": c} for a, b, c in STATUSES],
        "staff": load_staff(),
        "checklists": {"signed": CHECKLIST_SIGNED, "declined": CHECKLIST_DECLINED},
        "escalation_hours": load_staff().get("escalation_hours", 2),
    }
