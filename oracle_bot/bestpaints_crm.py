"""BestPaints CRM: сделки замера (Лидоруб → график → замерщик → менеджер)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

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


def _staff_bundled_path() -> Path:
    return Path(__file__).resolve().parent / "static" / "bestpaints" / "data" / "crm_staff.json"


def _staff_runtime_path() -> Path:
    """Editable staff lives next to DB (persists on Render disk)."""
    raw = os.getenv("BESTPAINTS_STAFF_PATH", "").strip()
    if raw:
        return Path(raw)
    if Path("/var/data").exists():
        return Path("/var/data/bestpaints_staff.json")
    return Path(__file__).resolve().parents[1] / "data" / "bestpaints_staff.json"


def _normalize_username(raw: str | None) -> str:
    u = (raw or "").strip().lstrip("@").lower()
    return u


def _normalize_person(p: dict[str, Any], *, role: str) -> dict[str, Any]:
    pid = str(p.get("id") or "").strip()
    if not pid:
        prefix = {"surveyor": "sv", "manager": "mg", "lidarub": "ld"}.get(role, "p")
        pid = f"{prefix}_{uuid.uuid4().hex[:6]}"
    return {
        "id": pid,
        "name": str(p.get("name") or "").strip() or pid,
        "phone": str(p.get("phone") or "").strip(),
        "tg_username": _normalize_username(p.get("tg_username") or p.get("username")),
        "tg_id": str(p.get("tg_id") or "").strip(),
        "note": str(p.get("note") or "").strip(),
    }


def _default_staff() -> dict[str, Any]:
    return {
        "escalation_hours": 2,
        "lidarubs": [],
        "surveyors": [],
        "managers": [],
        "zones": [],
    }


def load_staff() -> dict[str, Any]:
    runtime = _staff_runtime_path()
    bundled = _staff_bundled_path()
    data: dict[str, Any] = _default_staff()
    src = runtime if runtime.exists() else bundled
    if src.exists():
        try:
            loaded = json.loads(src.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except json.JSONDecodeError:
            pass
    # normalize people
    for key, role in (("surveyors", "surveyor"), ("managers", "manager"), ("lidarubs", "lidarub")):
        people = data.get(key) or []
        data[key] = [_normalize_person(p, role=role) for p in people if isinstance(p, dict)]
    data.setdefault("zones", [])
    data.setdefault("escalation_hours", 2)
    return data


def save_staff(data: dict[str, Any]) -> dict[str, Any]:
    """Persist staff to runtime path. Returns normalized staff."""
    out = _default_staff()
    out["escalation_hours"] = float(data.get("escalation_hours") or 2)
    out["zones"] = data.get("zones") if isinstance(data.get("zones"), list) else []
    for key, role in (("surveyors", "surveyor"), ("managers", "manager"), ("lidarubs", "lidarub")):
        people = data.get(key) or []
        out[key] = [_normalize_person(p, role=role) for p in people if isinstance(p, dict) and str(p.get("name") or "").strip()]
    path = _staff_runtime_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def upsert_person(role: str, person: dict[str, Any]) -> dict[str, Any]:
    role = (role or "").strip().lower()
    key = {"surveyor": "surveyors", "manager": "managers", "lidarub": "lidarubs"}.get(role)
    if not key:
        raise ValueError("role must be surveyor|manager|lidarub")
    staff = load_staff()
    base = _normalize_person(person, role=role)
    people = list(staff.get(key) or [])
    replaced = False
    for i, old in enumerate(people):
        if old.get("id") == base["id"] or (
            base["tg_username"] and _normalize_username(old.get("tg_username")) == base["tg_username"]
        ):
            merged = dict(old)
            merged["id"] = base["id"] or old.get("id") or base["id"]
            for field in ("name", "phone", "tg_username", "tg_id", "note"):
                if field in person and person.get(field) is not None:
                    if field == "tg_username":
                        merged[field] = _normalize_username(person.get(field))
                    else:
                        merged[field] = str(person.get(field) or "").strip()
            if not merged.get("name"):
                merged["name"] = base["name"]
            people[i] = merged
            replaced = True
            break
    if not replaced:
        people.append(base)
    staff[key] = people
    saved = save_staff(staff)
    # удобно для UI: вернуть и человека, и весь staff (обратная совместимость — ключи staff на верхнем уровне)
    pid = base["id"]
    person = next((p for p in (saved.get(key) or []) if p.get("id") == pid), base)
    if not replaced:
        # мог смержиться по tg_username с другим id
        for p in saved.get(key) or []:
            if base.get("tg_username") and p.get("tg_username") == base["tg_username"]:
                person = p
                break
            if (p.get("name") or "") == (base.get("name") or "") and p is person:
                person = p
    out = dict(saved)
    out["person"] = person
    out["role"] = role
    return out


def delete_person(role: str, person_id: str) -> dict[str, Any]:
    role = (role or "").strip().lower()
    key = {"surveyor": "surveyors", "manager": "managers", "lidarub": "lidarubs"}.get(role)
    if not key:
        raise ValueError("role must be surveyor|manager|lidarub")
    staff = load_staff()
    pid = str(person_id or "").strip()
    staff[key] = [p for p in (staff.get(key) or []) if p.get("id") != pid]
    return save_staff(staff)


def link_telegram_user(*, tg_id: str | int, username: str = "", full_name: str = "") -> dict[str, Any] | None:
    """Bind Telegram user to staff row by @username. Returns matched person or None."""
    uid = str(tg_id).strip()
    uname = _normalize_username(username)
    if not uid and not uname:
        return None
    staff = load_staff()
    changed = False
    matched: dict[str, Any] | None = None
    for key, role in (("surveyors", "surveyor"), ("managers", "manager"), ("lidarubs", "lidarub")):
        people = list(staff.get(key) or [])
        for i, p in enumerate(people):
            hit = bool(
                (uname and _normalize_username(p.get("tg_username")) == uname)
                or (uid and str(p.get("tg_id") or "") == uid)
            )
            if not hit:
                continue
            row = dict(p)
            if uid and row.get("tg_id") != uid:
                row["tg_id"] = uid
                changed = True
            if uname and _normalize_username(row.get("tg_username")) != uname:
                row["tg_username"] = uname
                changed = True
            if full_name and not (row.get("name") or "").strip():
                row["name"] = full_name
                changed = True
            people[i] = row
            matched = {**row, "role": role}
        staff[key] = people
    if changed:
        save_staff(staff)
    return matched


def find_person_by_tg(tg_id: str | int = "", username: str = "") -> dict[str, Any] | None:
    uid = str(tg_id or "").strip()
    uname = _normalize_username(username)
    staff = load_staff()
    for key, role in (("surveyors", "surveyor"), ("managers", "manager"), ("lidarubs", "lidarub")):
        for p in staff.get(key) or []:
            if uid and str(p.get("tg_id") or "") == uid:
                return {**p, "role": role}
            if uname and _normalize_username(p.get("tg_username")) == uname:
                return {**p, "role": role}
    return None


def toggle_schedule(role: str, person_id: str, work_date: str) -> dict[str, Any]:
    """Add person to day if missing, else remove."""
    init_db()
    day = work_date or today_str()
    if role not in ("surveyor", "manager"):
        raise ValueError("role must be surveyor|manager")
    if not _person_by_id(role, person_id):
        raise ValueError("unknown person_id")
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM schedule WHERE role=? AND person_id=? AND work_date=?",
            (role, person_id, day),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM schedule WHERE role=? AND person_id=? AND work_date=?", (role, person_id, day))
            return {"ok": True, "on_duty": False, "role": role, "person_id": person_id, "work_date": day}
    set_schedule(role, person_id, day)
    return {"ok": True, "on_duty": True, "role": role, "person_id": person_id, "work_date": day}


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
        "amount_subtotal": "REAL NOT NULL DEFAULT 0",
        "discount_pct": "REAL NOT NULL DEFAULT 0",
        "amount_total": "REAL NOT NULL DEFAULT 0",
        "area_m2": "REAL NOT NULL DEFAULT 0",
        "signed_place": "TEXT NOT NULL DEFAULT ''",
        "lidarub_id": "TEXT NOT NULL DEFAULT ''",
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
            CREATE TABLE IF NOT EXISTS tg_chats (
              role TEXT PRIMARY KEY,
              chat_id TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              updated_at REAL NOT NULL
            );
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
    d["amount_subtotal"] = float(d.get("amount_subtotal") or 0)
    d["discount_pct"] = float(d.get("discount_pct") or 0)
    d["amount_total"] = float(d.get("amount_total") or 0)
    d["area_m2"] = float(d.get("area_m2") or 0)
    d["signed_place"] = (d.get("signed_place") or "").strip()
    return d


def _money_fields(payload: dict[str, Any]) -> dict[str, float]:
    """Parse money from payload; recompute total if discount/subtotal given."""
    out: dict[str, float] = {}
    if "area_m2" in payload and payload.get("area_m2") is not None:
        try:
            out["area_m2"] = max(0.0, float(payload.get("area_m2") or 0))
        except (TypeError, ValueError):
            out["area_m2"] = 0.0
    sub = payload.get("amount_subtotal", payload.get("subtotal"))
    disc = payload.get("discount_pct", payload.get("discount"))
    total = payload.get("amount_total", payload.get("total"))
    try:
        if sub is not None and str(sub).strip() != "":
            out["amount_subtotal"] = max(0.0, float(sub))
    except (TypeError, ValueError):
        pass
    try:
        if disc is not None and str(disc).strip() != "":
            out["discount_pct"] = min(100.0, max(0.0, float(disc)))
    except (TypeError, ValueError):
        pass
    if "amount_subtotal" in out or "discount_pct" in out:
        # need both to recompute — caller merges with existing
        pass
    try:
        if total is not None and str(total).strip() != "" and "amount_subtotal" not in out:
            out["amount_total"] = max(0.0, float(total))
    except (TypeError, ValueError):
        pass
    return out


def _apply_money(updates: dict[str, Any], obj: dict[str, Any], payload: dict[str, Any]) -> None:
    keys = ("amount_subtotal", "discount_pct", "amount_total", "subtotal", "total", "discount", "area_m2")
    if not any(k in payload for k in keys):
        return
    money = _money_fields(payload)
    sub = float(money.get("amount_subtotal", obj.get("amount_subtotal") or 0))
    disc = float(money.get("discount_pct", obj.get("discount_pct") or 0))
    if "amount_subtotal" in money:
        updates["amount_subtotal"] = sub
        sub = money["amount_subtotal"]
    if "discount_pct" in money:
        updates["discount_pct"] = disc
        disc = money["discount_pct"]
    if "area_m2" in money:
        updates["area_m2"] = money["area_m2"]
    if "amount_subtotal" in money or "discount_pct" in money:
        updates["amount_total"] = round(float(sub) * (1 - float(disc) / 100.0), 2)
    elif "amount_total" in money:
        updates["amount_total"] = money["amount_total"]
        if not float(obj.get("amount_subtotal") or 0):
            updates["amount_subtotal"] = money["amount_total"]
            updates.setdefault("discount_pct", float(obj.get("discount_pct") or 0))


def log_event(object_id: str, kind: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
            (object_id, kind, message, _now()),
        )


def _msg_lines(*parts: str) -> str:
    """Столбик для TG/SMS: без пустых строк, без «простыни»."""
    out: list[str] = []
    for p in parts:
        s = (p or "").strip()
        if s:
            out.append(s)
    return "\n".join(out)


def format_deal_created(
    *,
    title: str,
    address: str,
    measure_date: str,
    qualification: str,
    link: str,
    surveyor_name: str = "",
) -> str:
    return _msg_lines(
        "🏠 BestPaints · новая сделка",
        f"«{title}»",
        f"📍 {address or '—'}",
        f"📅 Замер: {measure_date or '—'}",
        f"🏷️ {qualification[:200] or '—'}" if (qualification or "").strip() else "",
        f"👷 {surveyor_name}" if surveyor_name else "",
        "",
        "👉 Откройте и нажмите «Взял в работу»:",
        link,
    )


def format_status_change(*, title: str, label: str, address: str, link: str) -> str:
    return _msg_lines(
        "BestPaints · статус",
        f"«{title}»",
        f"→ {label}",
        f"📍 {address or '—'}",
        link,
    )


def format_no_schedule(*, title: str, address: str, assign_day: str) -> str:
    return _msg_lines(
        "⚠️ BestPaints · нет графика",
        f"«{title}»",
        f"📍 {address or '—'}",
        f"На {assign_day} замерщиков нет в графике.",
        "Админ: заполните /grafik",
    )


def format_visit_reminder(*, title: str, address: str, link: str) -> str:
    return _msg_lines(
        "BestPaints · завтра замер",
        f"«{title}»",
        f"📍 {address or '—'}",
        "Позвоните клиенту и нажмите «Выезд подтверждён»:",
        link,
    )


def format_assigned(*, title: str, link: str) -> str:
    return _msg_lines(
        "BestPaints · вам сделка",
        f"«{title}»",
        link,
    )


def format_manager_take(*, title: str, address: str, link: str) -> str:
    return _msg_lines(
        "🔔 BestPaints · защита ТЗ",
        f"«{title}»",
        f"📍 {address or '—'}",
        "Берите в работу:",
        link,
    )


def format_contract_signed(*, title: str, address: str, client: str, surveyor: str) -> str:
    return _msg_lines(
        "✍️ BestPaints · договор заключён",
        f"«{title}»",
        f"📍 {address or '—'}",
        f"Клиент: {client or '—'}",
        f"Замерщик: {surveyor or '—'}",
    )


def format_escalation(*, title: str, address: str, surveyor: str, phone: str, hours: float) -> str:
    return _msg_lines(
        f"⚠️ BestPaints · не взяли за {hours:g} ч",
        f"«{title}»",
        f"📍 {address or '—'}",
        f"Назначен: {surveyor or '—'} ({phone or '—'})",
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
        preview = text.replace("\n", " / ")[:120]
        notes.append(f"SMS stub → {phone}: {preview}")
    if skip_tg:
        return notes
    chat = telegram_chat or resolve_chat("ops")
    if chat and (
        os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip() or os.getenv("ORACLE_BOT_TOKEN", "").strip()
    ):
        notes.append(_send_telegram(chat, text))
    elif text and chat:
        preview = text.replace("\n", " / ")[:120]
        notes.append(f"TG stub → {chat}: {preview}")
    elif text and not chat:
        preview = text.replace("\n", " / ")[:120]
        notes.append(f"TG stub: {preview}")
    return notes


def _send_telegram(chat_id: str, text: str) -> str:
    token = os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip() or os.getenv("ORACLE_BOT_TOKEN", "").strip()
    if not token:
        return "TG skip: no token"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text[:3500],
            "disable_web_page_preview": "true",
        }
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=8) as r:
            raw = r.read().decode("utf-8", errors="replace")
        mid = ""
        try:
            mid = str(json.loads(raw).get("result", {}).get("message_id") or "")
        except Exception:  # noqa: BLE001
            mid = ""
        return f"TG ok → {chat_id}" + (f" #{mid}" if mid else "")
    except Exception as e:  # noqa: BLE001
        return f"TG fail → {chat_id}: {e}"


def _send_sms(phone: str, text: str) -> str:
    tpl = os.getenv("BESTPAINTS_SMS_URL", "").strip()
    if not tpl:
        return "SMS stub"
    # SMS: столбик → короткие строки через " · " чтобы уложиться в лимит шлюза
    flat = " · ".join(line for line in text.splitlines() if line.strip())
    url = tpl.replace("{phone}", urllib.parse.quote(phone)).replace("{text}", urllib.parse.quote(flat[:300]))
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
    key = "surveyors" if role == "surveyor" else "managers" if role == "manager" else "lidarubs"
    for p in staff.get(key) or []:
        if p.get("id") == person_id:
            return {
                "id": p.get("id") or "",
                "name": p.get("name") or "",
                "phone": p.get("phone") or "",
                "tg_username": p.get("tg_username") or "",
                "tg_id": p.get("tg_id") or "",
            }
    return None


def _person_label(person: dict[str, Any] | None) -> str:
    if not person:
        return ""
    name = person.get("name") or person.get("id") or ""
    u = _normalize_username(person.get("tg_username"))
    return f"{name} (@{u})" if u else name


def _mention_of(person: dict[str, Any] | None) -> str:
    if not person:
        return ""
    u = _normalize_username(person.get("tg_username"))
    return f"@{u}" if u else ""


def _person_from_obj(obj: dict[str, Any], role: str) -> dict[str, str] | None:
    """Собрать человека из сделки + справочника (для @тега)."""
    if role == "surveyor":
        pid = (obj.get("surveyor_id") or "").strip()
        base = _person_by_id("surveyor", pid) if pid else None
        name = (base or {}).get("name") or obj.get("surveyor_name") or ""
        phone = (base or {}).get("phone") or obj.get("surveyor_phone") or ""
        if not name and not phone:
            return None
        return {
            "id": pid or (base or {}).get("id") or "",
            "name": name,
            "phone": phone,
            "tg_username": (base or {}).get("tg_username") or "",
            "tg_id": (base or {}).get("tg_id") or "",
        }
    if role == "manager":
        pid = (obj.get("manager_id") or "").strip()
        base = _person_by_id("manager", pid) if pid else None
        name = (base or {}).get("name") or obj.get("manager_name") or ""
        phone = (base or {}).get("phone") or obj.get("manager_phone") or ""
        if not name and not phone:
            return None
        return {
            "id": pid or (base or {}).get("id") or "",
            "name": name,
            "phone": phone,
            "tg_username": (base or {}).get("tg_username") or "",
            "tg_id": (base or {}).get("tg_id") or "",
        }
    if role == "lidarub":
        name = obj.get("lidarub_name") or obj.get("ledorub_name") or ""
        phone = obj.get("lidarub_phone") or obj.get("ledorub_phone") or ""
        tg_id = str(obj.get("lidarub_tg_id") or "")
        # найти в справочнике по имени/телефону/tg_id
        base = None
        for p in load_staff().get("lidarubs") or []:
            if tg_id and str(p.get("tg_id") or "") == tg_id:
                base = p
                break
            if phone and (p.get("phone") or "") == phone:
                base = p
                break
            if name and (p.get("name") or "") == name:
                base = p
                break
        if base:
            return {
                "id": base.get("id") or "",
                "name": base.get("name") or name,
                "phone": base.get("phone") or phone,
                "tg_username": base.get("tg_username") or "",
                "tg_id": str(base.get("tg_id") or tg_id or ""),
            }
        if not name and not phone and not tg_id:
            return None
        return {"id": "", "name": name, "phone": phone, "tg_username": "", "tg_id": tg_id}
    return None


def notify_person_direct(text: str, person: dict[str, Any] | None) -> list[str]:
    """SMS + личка TG, без дубля в Ops. Всегда с @тегом адресата."""
    notes: list[str] = []
    if not person:
        return notes
    mention = _mention_of(person)
    who = person.get("name") or mention or person.get("id") or "сотрудник"
    body = _msg_lines(mention or f"→ {who}", text)
    phone = (person.get("phone") or "").strip()
    if phone:
        notes.extend(notify_all(body, phone=phone, skip_tg=True))
    tg_id = str(person.get("tg_id") or "").strip()
    if tg_id:
        notes.append(_send_telegram(tg_id, body))
    return notes


def notify_person(text: str, person: dict[str, Any] | None) -> list[str]:
    """SMS + DM + одно сообщение в Ops с @тегом человека."""
    notes: list[str] = []
    if not person:
        return notify_all(text)
    mention = _mention_of(person)
    who = person.get("name") or mention or person.get("id") or "сотрудник"
    body = _msg_lines(mention or f"→ {who}", text)
    notes.extend(notify_person_direct(text, person))
    notes.extend(notify_all(body, phone="", skip_tg=False))
    return notes


def notify_tagged_stakeholders(text: str, people: list[dict[str, Any] | None], *, ops: bool = True) -> list[str]:
    """Каждому — своё SMS/DM с тегом; в Ops — одно сообщение со всеми @."""
    notes: list[str] = []
    uniq: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in people:
        if not p:
            continue
        key = str(p.get("id") or "") + "|" + str(p.get("phone") or "") + "|" + _normalize_username(p.get("tg_username"))
        if key in seen or key == "||":
            continue
        seen.add(key)
        uniq.append(p)
        notes.extend(notify_person_direct(text, p))
    if ops:
        mentions = " ".join(_mention_of(p) for p in uniq if _mention_of(p))
        names = ", ".join((p.get("name") or "?") for p in uniq) or "команда"
        head = mentions if mentions else f"→ {names}"
        notes.extend(notify_all(_msg_lines(head, text), phone="", skip_tg=False))
    return notes


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
        return {
            "id": m.get("id") or "",
            "name": m.get("name") or "",
            "phone": m.get("phone") or "",
            "tg_username": m.get("tg_username") or "",
            "tg_id": m.get("tg_id") or "",
        }, "staff_fallback"
    return duty[0], "schedule"


def create_object(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    oid = "o_" + uuid.uuid4().hex[:12]
    title = (payload.get("title") or payload.get("deal_name") or "").strip() or "Сделка"
    address = (payload.get("address") or "").strip()
    client_name = (payload.get("client_name") or "").strip()
    client_phone = (payload.get("client_phone") or "").strip()
    lidarub_id = str(payload.get("lidarub_id") or "").strip()
    lidarub_person = _person_by_id("lidarub", lidarub_id) if lidarub_id else None
    lidarub_name = (
        (lidarub_person or {}).get("name")
        or (payload.get("lidarub_name") or payload.get("ledorub_name") or "").strip()
        or "Лидоруб"
    )
    lidarub_phone = (lidarub_person or {}).get("phone") or (payload.get("lidarub_phone") or payload.get("ledorub_phone") or "").strip()
    lidarub_id = (lidarub_person or {}).get("id") or lidarub_id
    manager_id = str(payload.get("manager_id") or "").strip()
    manager_person = _person_by_id("manager", manager_id) if manager_id else None
    manager_name = (manager_person or {}).get("name") or ""
    manager_phone = (manager_person or {}).get("phone") or ""
    manager_id = (manager_person or {}).get("id") or ""
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
              manager_id, manager_name, manager_phone,
              ledorub_name, ledorub_phone, lidarub_id, checklist_json,
              qualification, measure_date, audio_json, deal_source, lidarub_tg_id,
              assigned_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                manager_id,
                manager_name,
                manager_phone,
                lidarub_name,
                lidarub_phone,
                lidarub_id,
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
        msg = format_no_schedule(title=title, address=address, assign_day=assign_day)
        notes = notify_all(msg)
        log_event(oid, "no_schedule", msg.replace("\n", " | ") + " | " + "; ".join(notes))
    else:
        log_event(
            oid,
            "created",
            f"Сделка создана Лидорубом «{lidarub_name}»: {title}. Назначен {surveyor['name']} ({assign_reason})",
        )
        link = f"https://moracul.ru/bestpaints/?crm={oid}"
        msg = format_deal_created(
            title=title,
            address=address,
            measure_date=measure_date or "",
            qualification=qualification or "",
            link=link,
            surveyor_name=surveyor.get("name") or "",
        )
        notes = notify_person(msg, surveyor)
        log_event(oid, "notify_surveyor", "; ".join(notes))

    obj = get_object(oid)
    assert obj
    obj["assign_reason"] = assign_reason
    obj["notify"] = notes if status == "assigned" else notes
    return obj


def create_imported_deal(payload: dict[str, Any]) -> dict[str, Any]:
    """Сделка из уже готовой сметы (отправленной клиенту раньше другим способом).

    Один вызов: создаёт объект (с ручным выбором лидоруба/менеджера/замерщика)
    и сразу переводит его в «На адресе · замер» с суммой/скидкой/локальным ID сметы —
    чтобы дальше работали обычные кнопки «Заключил» / «Не заключил» и кабинет клиента.
    """
    client = payload.get("client") if isinstance(payload.get("client"), dict) else {}
    create_payload = {
        "title": (payload.get("title") or client.get("name") or "").strip() or "Смета (импорт)",
        "address": (payload.get("address") or client.get("address") or "").strip(),
        "client_name": (payload.get("client_name") or client.get("name") or "").strip(),
        "client_phone": (payload.get("client_phone") or client.get("phone") or "").strip(),
        "measure_date": (payload.get("measure_date") or "").strip() or today_str(),
        "qualification": (payload.get("qualification") or "").strip()
        or "Импорт готовой сметы — уже отправлена клиенту другим способом",
        "surveyor_id": payload.get("surveyor_id") or "",
        "lidarub_id": payload.get("lidarub_id") or "",
        "manager_id": payload.get("manager_id") or "",
        "deal_source": "import_estimate",
    }
    obj = create_object(create_payload)
    return transition(obj["id"], "import_estimate", payload)


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
            msg = format_escalation(
                title=d["title"],
                address=d.get("address") or "",
                surveyor=d.get("surveyor_name") or "",
                phone=d.get("surveyor_phone") or "",
                hours=hours,
            )
            notes = notify_tagged_stakeholders(
                msg,
                [
                    _person_from_obj(d, "lidarub"),
                    _person_from_obj(d, "surveyor"),
                ],
            )
            conn.execute(
                "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
                (d["id"], "escalation", msg.replace("\n", " | ") + " | " + "; ".join(notes), _now()),
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
            msg = format_visit_reminder(title=d["title"], address=d.get("address") or "", link=link)
            notes = notify_tagged_stakeholders(msg, [_person_from_obj(d, "surveyor")])
            conn.execute(
                "INSERT INTO events(object_id, kind, message, created_at) VALUES (?,?,?,?)",
                (d["id"], "visit_reminder", msg.replace("\n", " | ") + " | " + "; ".join(notes), _now()),
            )
            n += 1
    return n


def _broadcast_status(obj: dict[str, Any], label: str) -> list[str]:
    link = f"https://moracul.ru/bestpaints/?crm={obj['id']}"
    msg = format_status_change(
        title=obj.get("title") or "",
        label=label,
        address=obj.get("address") or "",
        link=link,
    )
    try:
        return notify_tagged_stakeholders(
            msg,
            [
                _person_from_obj(obj, "surveyor"),
                _person_from_obj(obj, "lidarub"),
                _person_from_obj(obj, "manager"),
            ],
        )
    except Exception as e:  # noqa: BLE001 — уведомления не должны ломать смену статуса
        log.warning("bestpaints broadcast failed for %s: %s", obj.get("id"), e)
        return [f"notify fail: {e}"]


def _run_side_effects(effects: list[Callable[[], Any]]) -> None:
    """SMS/TG после успешного UPDATE — иначе деплой/таймаут Telegram даёт «Ошибка API» без смены статуса."""
    for fn in effects:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.warning("bestpaints side effect failed: %s", e)


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
    side_effects: list[Callable[[], Any]] = []

    if action == "accept":
        updates["status"] = "accepted"
        updates["accepted_at"] = now
        message = f"{obj['surveyor_name'] or 'Замерщик'} взял в работу"
        snap = {**obj, **updates, "id": oid, "title": obj["title"], "address": obj["address"]}
        side_effects.append(lambda s=snap: _broadcast_status(s, "Замерщик взял в работу"))

    elif action == "confirm_visit":
        updates["status"] = "visit_confirmed"
        updates["visit_confirmed_at"] = now
        message = "Выезд подтверждён"
        side_effects.append(lambda: _broadcast_status(obj, "Выезд подтверждён"))

    elif action in ("arrive", "start_measure"):
        updates["status"] = "on_site"
        updates["on_site_at"] = now
        message = "На адресе у клиента — начинаю замер"
        side_effects.append(lambda: _broadcast_status(obj, "На адресе · замер начат"))

    elif action == "estimate_done":
        # совместимость: оставляем на объекте, статус не обязателен
        updates["estimate_at"] = now
        if payload.get("survey_local_id"):
            updates["survey_local_id"] = payload["survey_local_id"]
        _apply_money(updates, obj, payload)
        message = "Смета/замер сохранены"

    elif action in ("sign_contract", "sign_on_site"):
        updates["status"] = "contract_signed"
        updates["contract_at"] = now
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_SIGNED}, ensure_ascii=False)
        _apply_money(updates, obj, payload)
        place_raw = str(payload.get("signed_place") or "").strip().lower()
        from_office = obj.get("status") in ("manager_assigned", "manager_accepted")
        if place_raw in ("office", "офис", "from_office"):
            place = "office"
        elif place_raw in ("on_site", "address", "на_адресе", "site"):
            place = "on_site"
        else:
            place = "office" if from_office else "on_site"
        updates["signed_place"] = place
        message = "Договор заключён из офиса" if place == "office" else "Договор заключён на адресе"
        chat = resolve_chat("signed")
        signed_msg = format_contract_signed(
            title=obj.get("title") or "",
            address=obj.get("address") or "",
            client=f"{obj.get('client_name') or ''} {obj.get('client_phone') or ''}".strip(),
            surveyor=obj.get("surveyor_name") or "",
        )
        if place == "office":
            signed_msg = _msg_lines(signed_msg, "Место: офис (мотивация 1%)")
        surveyor_p = _person_from_obj(obj, "surveyor")
        mention = _mention_of(surveyor_p)
        signed_body = _msg_lines(mention or f"→ {obj.get('surveyor_name') or 'замерщик'}", signed_msg)
        place_label = " · офис" if place == "office" else " · на адресе"
        snap = {**obj, **updates, "id": oid}

        def _notify_signed(body=signed_body, tg=chat, s=snap, pl=place_label) -> None:
            notify_all(body, telegram_chat=tg)
            _broadcast_status(s, "Договор заключён" + pl)

        side_effects.append(_notify_signed)

    elif action in ("decline_contract", "decline_on_site"):
        updates["status"] = "contract_declined"
        updates["contract_at"] = now
        if payload.get("refusal_reason"):
            updates["refusal_reason"] = str(payload["refusal_reason"])
        updates["checklist_json"] = json.dumps({i["id"]: False for i in CHECKLIST_DECLINED}, ensure_ascii=False)
        _apply_money(updates, obj, payload)
        message = "Договор не заключён на адресе"
        side_effects.append(lambda: _broadcast_status(obj, "Не заключён — уйдёт менеджеру"))

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
        mgr_notify = {
            "name": updates["manager_name"],
            "phone": updates["manager_phone"],
            "tg_username": (mgr or {}).get("tg_username") or "",
            "tg_id": (mgr or {}).get("tg_id") or "",
        }
        side_effects.append(
            lambda m=mgr_notify: notify_person(
                format_manager_take(
                    title=obj.get("title") or "",
                    address=obj.get("address") or "",
                    link=f"https://moracul.ru/bestpaints/?crm={oid}",
                ),
                m,
            )
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
        label = f"Снова в работе: {STATUS_MAP[target]['label']}"
        side_effects.append(lambda lab=label: _broadcast_status(obj, lab))

    elif action == "set_status":
        target = (payload.get("status") or "").strip()
        if target not in VALID_STATUSES:
            raise ValueError(f"unknown status: {target}")
        updates["status"] = target
        if target in WON_STATUSES and not (obj.get("signed_place") or "").strip():
            place_raw = str(payload.get("signed_place") or "").strip().lower()
            if place_raw in ("office", "офис", "from_office"):
                updates["signed_place"] = "office"
            elif place_raw in ("on_site", "address", "site", "на_адресе"):
                updates["signed_place"] = "on_site"
            elif obj.get("status") in ("manager_assigned", "manager_accepted"):
                updates["signed_place"] = "office"
            else:
                updates["signed_place"] = "on_site"
        if target in WON_STATUSES and not obj.get("contract_at"):
            updates["contract_at"] = now
        message = f"Статус вручную: {STATUS_MAP[target]['label']}"
        label = STATUS_MAP[target]["label"]
        side_effects.append(lambda lab=label: _broadcast_status(obj, lab))

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
        _apply_money(updates, obj, payload)
        message = "Привязан локальный замер"

    elif action == "save_uploads":
        updates["uploads_json"] = json.dumps(payload.get("uploads") or {}, ensure_ascii=False)
        message = "Ссылки на загрузки сохранены"

    elif action == "save_money":
        _apply_money(updates, obj, payload)
        if not any(k in updates for k in ("amount_subtotal", "discount_pct", "amount_total", "area_m2")):
            raise ValueError("укажите сумму или скидку")
        message = (
            f"Смета в CRM: {updates.get('amount_total', obj.get('amount_total')):,.0f} ₽"
            f" (скидка {updates.get('discount_pct', obj.get('discount_pct')):g}%)"
        ).replace(",", " ")

    elif action == "import_estimate":
        # Смета уже была рассчитана и отправлена клиенту другим способом (до CRM) —
        # сразу переводим сделку в «На адресе · замер» (эквивалент «замер и смета готовы»),
        # дальше обычные кнопки «Заключил» / «Не заключил».
        updates["status"] = "on_site"
        updates["assigned_at"] = obj.get("assigned_at") or now
        updates["accepted_at"] = obj.get("accepted_at") or now
        updates["visit_confirmed_at"] = obj.get("visit_confirmed_at") or now
        updates["on_site_at"] = obj.get("on_site_at") or now
        if payload.get("survey_local_id"):
            updates["survey_local_id"] = str(payload["survey_local_id"])
        _apply_money(updates, obj, payload)
        total_val = float(updates.get("amount_total", obj.get("amount_total") or 0) or 0)
        disc_val = float(updates.get("discount_pct", obj.get("discount_pct") or 0) or 0)
        src_note = (payload.get("source_note") or "").strip()
        parts = [f"Импорт готовой сметы (роль оператора: {payload.get('actor_role') or 'лидоруб'})"]
        if src_note:
            parts.append(f"источник: {src_note}"[:200])
        if total_val:
            parts.append(f"сумма {total_val:,.0f} ₽".replace(",", " "))
        if disc_val:
            parts.append(f"скидка {disc_val:g}%")
        message = " · ".join(parts)

    elif action == "reassign_surveyor":
        sid = (payload.get("surveyor_id") or "").strip()
        person = _person_by_id("surveyor", sid) if sid else None
        if not person:
            person, reason = pick_surveyor_from_schedule(obj.get("measure_date") or today_str(), obj.get("address") or "")
            if not person:
                raise ValueError(
                    "В графике никого нет — выберите замерщика из списка или создайте нового на карточке сделки"
                )
        else:
            reason = "manual"
        updates["surveyor_id"] = person["id"]
        updates["surveyor_name"] = person["name"]
        updates["surveyor_phone"] = person["phone"]
        updates["status"] = "assigned"
        updates["assigned_at"] = now
        updates["escalated_at"] = None
        message = f"Переназначен замерщик {person['name']} ({reason})"
        side_effects.append(
            lambda p=person: notify_person(
                format_assigned(title=obj.get("title") or "", link=f"https://moracul.ru/bestpaints/?crm={oid}"),
                p,
            )
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
                side_effects.append(
                    lambda m=mgr: notify_person(
                        format_manager_take(
                            title=obj.get("title") or "",
                            address=obj.get("address") or "",
                            link=f"https://moracul.ru/bestpaints/?crm={oid}",
                        ),
                        m,
                    )
                )

    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [oid]
    with connect() as conn:
        conn.execute(f"UPDATE objects SET {sets} WHERE id=?", vals)
    log_event(oid, action, message)
    _run_side_effects(side_effects)
    out = get_object(oid)
    assert out
    return out


def register_tg_chat(chat_id: str | int, title: str = "", role: str | None = None) -> dict[str, Any]:
    """Привязать Telegram-группу. role: ops|signed|auto по названию."""
    init_db()
    cid = str(chat_id).strip()
    title = (title or "").strip()
    low = title.lower()
    if not role:
        if "подпис" in low or "signed" in low:
            role = "signed"
        elif "ops" in low or "операц" in low:
            role = "ops"
        else:
            role = "ops"  # default when unknown
    if role not in ("ops", "signed"):
        raise ValueError("role must be ops|signed")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tg_chats(role, chat_id, title, updated_at) VALUES (?,?,?,?)
            ON CONFLICT(role) DO UPDATE SET chat_id=excluded.chat_id, title=excluded.title, updated_at=excluded.updated_at
            """,
            (role, cid, title, _now()),
        )
    return {"role": role, "chat_id": cid, "title": title}


def list_tg_chats() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT role, chat_id, title, updated_at FROM tg_chats").fetchall()
    return {r["role"]: {"chat_id": r["chat_id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows}


def resolve_chat(role: str) -> str:
    """Env overrides DB."""
    env_key = "BESTPAINTS_TG_CHAT_OPS" if role == "ops" else "BESTPAINTS_TG_CHAT_SIGNED"
    env_val = os.getenv(env_key, "").strip()
    if env_val:
        return env_val
    chats = list_tg_chats()
    return str((chats.get(role) or {}).get("chat_id") or "")



def _period_bounds(period: str, date_from: str | None = None, date_to: str | None = None) -> tuple[float | None, float | None, str, str]:
    """Return (ts_from, ts_to, label_from, label_to) in Moscow TZ."""
    today = datetime.now(TZ).date()
    if date_from or date_to:
        d0 = date.fromisoformat(date_from) if date_from else date(1970, 1, 1)
        d1 = date.fromisoformat(date_to) if date_to else today
        start = datetime(d0.year, d0.month, d0.day, tzinfo=TZ)
        end = datetime(d1.year, d1.month, d1.day, 23, 59, 59, tzinfo=TZ)
        return start.timestamp(), end.timestamp(), d0.isoformat(), d1.isoformat()
    p = (period or "30d").strip().lower()
    if p in ("all", "всё", "vse"):
        return None, None, "", today.isoformat()
    # Конкретный календарный месяц: m:YYYY-MM
    if p.startswith("m:") and len(p) >= 9:
        try:
            y_s, m_s = p[2:].split("-", 1)
            y, mo = int(y_s), int(m_s)
            d0 = date(y, mo, 1)
            if mo == 12:
                d1 = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                d1 = date(y, mo + 1, 1) - timedelta(days=1)
            if d1 > today:
                d1 = today
            start = datetime(d0.year, d0.month, d0.day, tzinfo=TZ)
            end = datetime(d1.year, d1.month, d1.day, 23, 59, 59, tzinfo=TZ)
            return start.timestamp(), end.timestamp(), d0.isoformat(), d1.isoformat()
        except ValueError:
            pass
    if p in ("today", "день", "1d"):
        d0 = today
    elif p in ("7d", "week", "неделя"):
        d0 = today - timedelta(days=6)
    elif p in ("month", "месяц", "mtd"):
        d0 = today.replace(day=1)
    else:  # 30d default
        d0 = today - timedelta(days=29)
        p = "30d"
    start = datetime(d0.year, d0.month, d0.day, tzinfo=TZ)
    end = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=TZ)
    return start.timestamp(), end.timestamp(), d0.isoformat(), today.isoformat()


IN_WORK_STATUSES = {
    "created",
    "assigned",
    "accepted",
    "visit_confirmed",
    "on_site",
    "manager_assigned",
    "manager_accepted",
}
WON_STATUSES = {"contract_signed", "closed"}
LOST_STATUSES = {"contract_declined"}
# manager_* after decline still "not signed" pipeline — count separately as open_lost

PAYROLL_RULES = [
    {"id": "onsite_0", "place": "on_site", "discount_min": 0, "discount_max": 0, "rate_pct": 5, "label": "На адресе · скидка 0% → 5%"},
    {"id": "onsite_1_5", "place": "on_site", "discount_min": 1, "discount_max": 5, "rate_pct": 3, "label": "На адресе · скидка 1–5% → 3%"},
    {"id": "onsite_6_10", "place": "on_site", "discount_min": 6, "discount_max": 10, "rate_pct": 2, "label": "На адресе · скидка 6–10% → 2%"},
    {"id": "onsite_over_10", "place": "on_site", "discount_min": 10.0001, "discount_max": 100, "rate_pct": 2, "label": "На адресе · скидка >10% → 2%"},
    {"id": "office", "place": "office", "discount_min": 0, "discount_max": 100, "rate_pct": 1, "label": "Из офиса → 1%"},
]

# Мотивация менеджера с заключённого договора (ставка из env или 1%)
MANAGER_PAYROLL_RULES = [
    {"id": "manager_default", "rate_pct": float(os.getenv("BESTPAINTS_MANAGER_RATE_PCT", "1") or "1"), "label": "Менеджер · % от суммы договора"},
]


def calc_manager_commission(*, amount_total: float, rate_pct: float | None = None) -> dict[str, Any]:
    total = max(0.0, float(amount_total or 0))
    rate = float(rate_pct if rate_pct is not None else (os.getenv("BESTPAINTS_MANAGER_RATE_PCT", "1") or "1"))
    commission = round(total * rate / 100.0, 2)
    return {
        "rate_pct": rate,
        "commission": commission,
        "rule": f"Менеджер → {rate:g}%",
        "rule_id": "manager_default",
        "amount_total": total,
    }


def _infer_signed_place(obj: dict[str, Any]) -> str:
    """on_site | office — из поля или эвристики по воронке."""
    raw = (obj.get("signed_place") or "").strip().lower()
    if raw in ("office", "офис", "from_office"):
        return "office"
    if raw in ("on_site", "address", "site", "на_адресе"):
        return "on_site"
    # эвристика для старых сделок без поля
    if obj.get("manager_id") or obj.get("manager_name"):
        # менеджер появился обычно после отказа на адресе → офис
        if obj.get("status") in WON_STATUSES:
            return "office"
    if obj.get("on_site_at"):
        return "on_site"
    return "on_site"


def calc_surveyor_commission(
    *,
    amount_total: float,
    discount_pct: float,
    signed_place: str,
) -> dict[str, Any]:
    """Мотивация замерщика с заключённого договора."""
    total = max(0.0, float(amount_total or 0))
    disc = max(0.0, float(discount_pct or 0))
    place = "office" if (signed_place or "").strip().lower() in ("office", "офис", "from_office") else "on_site"
    if place == "office":
        rate = 1.0
        rule = "Из офиса → 1%"
        rule_id = "office"
    elif disc <= 0:
        rate = 5.0
        rule = "На адресе · скидка 0% → 5%"
        rule_id = "onsite_0"
    elif disc <= 5:
        rate = 3.0
        rule = "На адресе · скидка 1–5% → 3%"
        rule_id = "onsite_1_5"
    elif disc <= 10:
        rate = 2.0
        rule = "На адресе · скидка 6–10% → 2%"
        rule_id = "onsite_6_10"
    else:
        rate = 2.0
        rule = "На адресе · скидка >10% → 2%"
        rule_id = "onsite_over_10"
    commission = round(total * rate / 100.0, 2)
    return {
        "signed_place": place,
        "place_label": "Из офиса" if place == "office" else "На адресе",
        "rate_pct": rate,
        "commission": commission,
        "rule": rule,
        "rule_id": rule_id,
        "discount_pct": disc,
        "amount_total": total,
    }


def payroll(*, period: str = "30d", date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """ЗП замерщиков и менеджеров: сумма мотивации и кликабельная история сделок."""
    init_db()
    ts_from, ts_to, label_from, label_to = _period_bounds(period, date_from, date_to)
    objs = list_objects(include_deleted=False)

    def in_period(ts: float | None) -> bool:
        if ts is None:
            return ts_from is None
        if ts_from is not None and ts < ts_from:
            return False
        if ts_to is not None and ts > ts_to:
            return False
        return True

    def outcome_ts(o: dict[str, Any]) -> float | None:
        return o.get("contract_at") or o.get("updated_at")

    won = [o for o in objs if o.get("status") in WON_STATUSES and in_period(outcome_ts(o))]
    buckets: dict[str, dict[str, Any]] = {}
    mgr_buckets: dict[str, dict[str, Any]] = {}
    grand = 0.0
    grand_mgr = 0.0
    for o in won:
        total = float(o.get("amount_total") or 0)
        if total <= 0:
            continue
        place = _infer_signed_place(o)
        calc = calc_surveyor_commission(
            amount_total=total,
            discount_pct=float(o.get("discount_pct") or 0),
            signed_place=place,
        )
        name = o.get("surveyor_name") or "Без замерщика"
        sid = o.get("surveyor_id") or ""
        key = sid or name
        b = buckets.setdefault(
            key,
            {
                "surveyor_id": sid,
                "name": name,
                "deals_count": 0,
                "sum_contracts": 0.0,
                "sum_payroll": 0.0,
                "deals": [],
            },
        )
        b["deals_count"] += 1
        b["sum_contracts"] += total
        b["sum_payroll"] += calc["commission"]
        grand += calc["commission"]
        deal_row = {
            "id": o["id"],
            "title": o.get("title") or "",
            "address": o.get("address") or "",
            "measure_date": o.get("measure_date") or "",
            "status": o.get("status"),
            "status_label": o.get("status_label") or "",
            "amount_total": total,
            "discount_pct": float(o.get("discount_pct") or 0),
            "signed_place": calc["signed_place"],
            "place_label": calc["place_label"],
            "rate_pct": calc["rate_pct"],
            "commission": calc["commission"],
            "rule": calc["rule"],
            "contract_at": o.get("contract_at"),
        }
        b["deals"].append(deal_row)

        mname = (o.get("manager_name") or "").strip()
        mid = (o.get("manager_id") or "").strip()
        if mname or mid:
            mcalc = calc_manager_commission(amount_total=total)
            mkey = mid or mname
            mb = mgr_buckets.setdefault(
                mkey,
                {
                    "manager_id": mid,
                    "name": mname or "Без менеджера",
                    "deals_count": 0,
                    "sum_contracts": 0.0,
                    "sum_payroll": 0.0,
                    "deals": [],
                },
            )
            mb["deals_count"] += 1
            mb["sum_contracts"] += total
            mb["sum_payroll"] += mcalc["commission"]
            grand_mgr += mcalc["commission"]
            mb["deals"].append(
                {
                    **deal_row,
                    "rate_pct": mcalc["rate_pct"],
                    "commission": mcalc["commission"],
                    "rule": mcalc["rule"],
                    "place_label": "Менеджер",
                }
            )

    by_surveyor = sorted(buckets.values(), key=lambda x: (-x["sum_payroll"], -x["deals_count"]))
    for b in by_surveyor:
        b["sum_contracts"] = round(b["sum_contracts"], 2)
        b["sum_payroll"] = round(b["sum_payroll"], 2)
        b["deals"].sort(key=lambda d: -(d.get("contract_at") or 0))

    by_manager = sorted(mgr_buckets.values(), key=lambda x: (-x["sum_payroll"], -x["deals_count"]))
    for b in by_manager:
        b["sum_contracts"] = round(b["sum_contracts"], 2)
        b["sum_payroll"] = round(b["sum_payroll"], 2)
        b["deals"].sort(key=lambda d: -(d.get("contract_at") or 0))

    return {
        "period": period or "custom",
        "from": label_from,
        "to": label_to,
        "rules": PAYROLL_RULES,
        "manager_rules": MANAGER_PAYROLL_RULES,
        "total_payroll": round(grand, 2),
        "total_manager_payroll": round(grand_mgr, 2),
        "by_surveyor": by_surveyor,
        "by_manager": by_manager,
    }


def analytics(*, period: str = "30d", date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    init_db()
    ts_from, ts_to, label_from, label_to = _period_bounds(period, date_from, date_to)
    objs = list_objects(include_deleted=False)

    def in_period(ts: float | None) -> bool:
        if ts is None:
            return ts_from is None
        if ts_from is not None and ts < ts_from:
            return False
        if ts_to is not None and ts > ts_to:
            return False
        return True

    created = [o for o in objs if in_period(o.get("created_at"))]
    # outcome by contract_at if set else updated_at for closed/signed in period
    def outcome_ts(o: dict[str, Any]) -> float | None:
        return o.get("contract_at") or o.get("updated_at")

    signed = [o for o in objs if o.get("status") in WON_STATUSES and in_period(outcome_ts(o))]
    declined = [
        o
        for o in objs
        if o.get("status") in LOST_STATUSES | {"manager_assigned", "manager_accepted"}
        and in_period(outcome_ts(o))
    ]
    in_work = [o for o in objs if o.get("status") in IN_WORK_STATUSES]
    measured = [
        o
        for o in created
        if o.get("on_site_at") or o.get("status") in ("on_site", "contract_signed", "contract_declined", "manager_assigned", "manager_accepted", "closed")
    ]

    def money_sum(rows: list[dict[str, Any]]) -> float:
        return round(sum(float(o.get("amount_total") or 0) for o in rows), 2)

    def money_sub(rows: list[dict[str, Any]]) -> float:
        return round(sum(float(o.get("amount_subtotal") or 0) for o in rows), 2)

    signed_sum = money_sum(signed)
    declined_sum = money_sum(declined)
    in_work_sum = money_sum(in_work)
    pipeline_sum = money_sum(created)
    decided = len(signed) + len(declined)
    conversion = round(100.0 * len(signed) / decided, 1) if decided else 0.0
    with_money = [o for o in signed if float(o.get("amount_total") or 0) > 0]
    avg_check = round(signed_sum / len(with_money), 2) if with_money else 0.0
    discounts = [float(o.get("discount_pct") or 0) for o in signed + declined if float(o.get("amount_subtotal") or 0) > 0 or float(o.get("discount_pct") or 0) > 0]
    avg_discount = round(sum(discounts) / len(discounts), 1) if discounts else 0.0
    discount_rub = round(money_sub(signed) - signed_sum, 2) if signed else 0.0
    area_sum = round(sum(float(o.get("area_m2") or 0) for o in measured), 1)

    by_status: dict[str, int] = {}
    for o in created:
        st = o.get("status") or "created"
        by_status[st] = by_status.get(st, 0) + 1

    by_surveyor: list[dict[str, Any]] = []
    buckets: dict[str, dict[str, Any]] = {}
    for o in created:
        name = o.get("surveyor_name") or "Без замерщика"
        b = buckets.setdefault(name, {"name": name, "deals": 0, "signed": 0, "declined": 0, "sum_signed": 0.0, "sum_work": 0.0})
        b["deals"] += 1
        if o.get("status") in WON_STATUSES:
            b["signed"] += 1
            b["sum_signed"] += float(o.get("amount_total") or 0)
        elif o.get("status") in LOST_STATUSES | {"manager_assigned", "manager_accepted"}:
            b["declined"] += 1
        if o.get("status") in IN_WORK_STATUSES:
            b["sum_work"] += float(o.get("amount_total") or 0)
    by_surveyor = sorted(buckets.values(), key=lambda x: (-x["sum_signed"], -x["deals"]))
    for b in by_surveyor:
        b["sum_signed"] = round(b["sum_signed"], 2)
        b["sum_work"] = round(b["sum_work"], 2)

    funnel = []
    for sid, label, color in STATUSES:
        funnel.append({"id": sid, "label": label, "color": color, "count": by_status.get(sid, 0)})

    return {
        "period": period or "custom",
        "from": label_from,
        "to": label_to,
        "kpis": {
            "deals_created": len(created),
            "in_work": len(in_work),
            "in_work_sum": in_work_sum,
            "signed": len(signed),
            "signed_sum": signed_sum,
            "declined": len(declined),
            "declined_sum": declined_sum,
            "conversion_pct": conversion,
            "avg_check": avg_check,
            "avg_discount_pct": avg_discount,
            "discount_rub": discount_rub,
            "measures": len(measured),
            "area_m2": area_sum,
            "pipeline_sum": pipeline_sum,
            "without_amount": sum(1 for o in created if float(o.get("amount_total") or 0) <= 0),
        },
        "funnel": funnel,
        "by_surveyor": by_surveyor,
        "top_signed": sorted(
            [
                {
                    "id": o["id"],
                    "title": o.get("title"),
                    "amount_total": float(o.get("amount_total") or 0),
                    "discount_pct": float(o.get("discount_pct") or 0),
                    "surveyor_name": o.get("surveyor_name") or "",
                }
                for o in signed
                if float(o.get("amount_total") or 0) > 0
            ],
            key=lambda x: -x["amount_total"],
        )[:5],
    }


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
        "tg_chats": list_tg_chats(),
        "tg_ops": resolve_chat("ops"),
        "tg_signed": resolve_chat("signed"),
        "roles_hint": "Лидоруб создаёт сделку в ТГ; админ заполняет график; замерщик/менеджер ведут статусы в веб.",
        "analytics_hint": "Вкладки «Аналитика» и «ЗП»: суммы, конверсия, мотивация замерщика.",
        "payroll_rules": PAYROLL_RULES,
    }
