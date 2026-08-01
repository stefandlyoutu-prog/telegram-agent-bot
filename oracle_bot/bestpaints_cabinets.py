"""Клиентские кабинеты BestPaints: смета на сервере, вход по телефону, лог изменений."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from typing import Any

from oracle_bot import bestpaints_crm as crm

COOKIE_NAME = "bp_client_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60 дней
TOKEN_TTL = 60 * 60 * 24 * 90  # magic link 90 дней

# Поля, которые клиент может менять (остальное сервер не принимает в patch)
CLIENT_EDITABLE_HINTS = (
    "buildings[].tech.*",
    "buildings[].condition",
    "buildings[].houseType",
    "buildings[].colors",
    "buildings[].previewColor",
    "buildings[].humidity",
    "buildings[].material",
    "estimate.discountPct",
    "estimate.payments",
    "client.name",
    "client.email",
)


def _secret() -> bytes:
    raw = (
        os.getenv("BESTPAINTS_SESSION_SECRET")
        or os.getenv("ORACLE_BOT_TOKEN")
        or "bp-survey-dev-secret"
    ).strip()
    return raw.encode("utf-8")


def normalize_phone(raw: str | None) -> str:
    digits = re.sub(r"\D+", "", str(raw or ""))
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_phone(a), normalize_phone(b)
    if not na or not nb:
        return False
    return na == nb or na[-10:] == nb[-10:]


def init_db() -> None:
    crm.init_db()
    with crm.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bp_surveys (
              id TEXT PRIMARY KEY,
              object_id TEXT NOT NULL DEFAULT '',
              cabinet_id TEXT NOT NULL DEFAULT '',
              payload_json TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 1,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bp_surveys_object ON bp_surveys(object_id);
            CREATE INDEX IF NOT EXISTS idx_bp_surveys_cabinet ON bp_surveys(cabinet_id);

            CREATE TABLE IF NOT EXISTS cabinets (
              id TEXT PRIMARY KEY,
              object_id TEXT NOT NULL UNIQUE,
              survey_id TEXT NOT NULL DEFAULT '',
              client_phone TEXT NOT NULL,
              client_name TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'active',
              access_code TEXT NOT NULL DEFAULT '',
              created_from TEXT NOT NULL DEFAULT 'estimate',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              last_client_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_cabinets_phone ON cabinets(client_phone);
            CREATE INDEX IF NOT EXISTS idx_cabinets_status ON cabinets(status);

            CREATE TABLE IF NOT EXISTS cabinet_tokens (
              token TEXT PRIMARY KEY,
              cabinet_id TEXT NOT NULL,
              purpose TEXT NOT NULL DEFAULT 'magic',
              expires_at REAL NOT NULL,
              used_at REAL,
              revoked_at REAL,
              created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cab_tokens_cab ON cabinet_tokens(cabinet_id);

            CREATE TABLE IF NOT EXISTS cabinet_sessions (
              id TEXT PRIMARY KEY,
              cabinet_id TEXT NOT NULL,
              phone TEXT NOT NULL,
              token_hash TEXT NOT NULL,
              expires_at REAL NOT NULL,
              created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cab_sess_hash ON cabinet_sessions(token_hash);

            CREATE TABLE IF NOT EXISTS change_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              object_id TEXT NOT NULL DEFAULT '',
              cabinet_id TEXT NOT NULL DEFAULT '',
              actor_type TEXT NOT NULL,
              actor_id TEXT NOT NULL DEFAULT '',
              action TEXT NOT NULL,
              message TEXT NOT NULL DEFAULT '',
              before_json TEXT NOT NULL DEFAULT '',
              after_json TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_changelog_object ON change_log(object_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_changelog_cabinet ON change_log(cabinet_id, created_at DESC);
            """
        )


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def log_change(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    message: str = "",
    object_id: str = "",
    cabinet_id: str = "",
    actor_type: str = "system",
    actor_id: str = "",
    before: Any = None,
    after: Any = None,
) -> None:
    with crm.connect() as conn:
        conn.execute(
            """
            INSERT INTO change_log(
              entity_type, entity_id, object_id, cabinet_id,
              actor_type, actor_id, action, message,
              before_json, after_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entity_type,
                entity_id,
                object_id or "",
                cabinet_id or "",
                actor_type,
                actor_id or "",
                action,
                message or "",
                json.dumps(before if before is not None else "", ensure_ascii=False)[:20000],
                json.dumps(after if after is not None else "", ensure_ascii=False)[:20000],
                _now(),
            ),
        )


def slim_survey(survey: dict[str, Any]) -> dict[str, Any]:
    """Убираем тяжёлые dataURL фото, оставляем метаданные."""
    data = copy.deepcopy(survey or {})

    def strip_photos(photos: list) -> list:
        out = []
        for p in photos or []:
            if not isinstance(p, dict):
                continue
            item = {k: v for k, v in p.items() if k != "dataUrl"}
            item["hasImage"] = bool(p.get("dataUrl"))
            out.append(item)
        return out

    for b in data.get("buildings") or []:
        if isinstance(b, dict):
            b["photos"] = strip_photos(b.get("photos") or [])
            for w in (b.get("measure") or {}).get("walls") or []:
                if isinstance(w, dict):
                    w["photos"] = strip_photos(w.get("photos") or [])
    return data


def _row_cab(row) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    return d


def get_cabinet(cab_id: str) -> dict[str, Any] | None:
    with crm.connect() as conn:
        row = conn.execute("SELECT * FROM cabinets WHERE id=?", (cab_id,)).fetchone()
    return _row_cab(row)


def get_cabinet_by_object(object_id: str) -> dict[str, Any] | None:
    with crm.connect() as conn:
        row = conn.execute("SELECT * FROM cabinets WHERE object_id=?", (object_id,)).fetchone()
    return _row_cab(row)


def list_cabinets(*, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    q = "SELECT * FROM cabinets"
    args: list[Any] = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY updated_at DESC LIMIT ?"
    args.append(int(limit))
    with crm.connect() as conn:
        rows = conn.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = _row_cab(r)
        obj = crm.get_object(d["object_id"], include_deleted=True) if d else None
        if d:
            d["object"] = {
                "id": d["object_id"],
                "title": (obj or {}).get("title") or "",
                "address": (obj or {}).get("address") or "",
                "surveyor_name": (obj or {}).get("surveyor_name") or "",
                "manager_name": (obj or {}).get("manager_name") or "",
                "status": (obj or {}).get("status") or "",
                "amount_total": (obj or {}).get("amount_total") or 0,
            }
            out.append(d)
    return out


def get_survey(survey_id: str) -> dict[str, Any] | None:
    with crm.connect() as conn:
        row = conn.execute("SELECT * FROM bp_surveys WHERE id=?", (survey_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    return d


def save_survey_payload(
    *,
    survey_id: str | None,
    object_id: str,
    cabinet_id: str,
    payload: dict[str, Any],
    actor_type: str,
    actor_id: str,
) -> dict[str, Any]:
    slim = slim_survey(payload)
    sid = survey_id or slim.get("id") or _new_id("srv")
    slim["id"] = sid
    now = _now()
    with crm.connect() as conn:
        prev = conn.execute("SELECT payload_json, version FROM bp_surveys WHERE id=?", (sid,)).fetchone()
        if prev:
            before = json.loads(prev["payload_json"] or "{}")
            ver = int(prev["version"] or 1) + 1
            conn.execute(
                """
                UPDATE bp_surveys
                SET object_id=?, cabinet_id=?, payload_json=?, version=?, updated_at=?
                WHERE id=?
                """,
                (object_id, cabinet_id, json.dumps(slim, ensure_ascii=False), ver, now, sid),
            )
        else:
            before = {}
            ver = 1
            conn.execute(
                """
                INSERT INTO bp_surveys(id, object_id, cabinet_id, payload_json, version, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (sid, object_id, cabinet_id, json.dumps(slim, ensure_ascii=False), ver, now, now),
            )

    changes = diff_survey(before, slim)
    if changes:
        log_change(
            entity_type="survey",
            entity_id=sid,
            object_id=object_id,
            cabinet_id=cabinet_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action="survey_update",
            message=f"Изменено полей: {len(changes)} · " + "; ".join(c["label"] for c in changes[:8]),
            before=changes,
            after={"version": ver, "count": len(changes)},
        )
        # detailed rows
        for c in changes[:80]:
            log_change(
                entity_type="field",
                entity_id=sid,
                object_id=object_id,
                cabinet_id=cabinet_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action="field_change",
                message=f"{c['label']}: {c['before']} → {c['after']}",
                before=c["before"],
                after=c["after"],
            )
    return {"id": sid, "version": ver, "payload": slim, "changes": changes}


def diff_survey(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Плоский diff ключевых полей сметы/конструктора."""
    changes: list[dict[str, Any]] = []

    def add(path: str, label: str, a: Any, b: Any) -> None:
        if a == b:
            return
        sa = "" if a is None else str(a)
        sb = "" if b is None else str(b)
        if sa == sb:
            return
        changes.append({"path": path, "label": label, "before": a, "after": b})

    bc = before.get("client") or {}
    ac = after.get("client") or {}
    add("client.name", "Имя клиента", bc.get("name"), ac.get("name"))
    add("client.phone", "Телефон", bc.get("phone"), ac.get("phone"))
    add("client.email", "Email", bc.get("email"), ac.get("email"))

    be = before.get("estimate") or {}
    ae = after.get("estimate") or {}
    add("estimate.discountPct", "Скидка %", be.get("discountPct"), ae.get("discountPct"))

    bb = before.get("buildings") or []
    ab = after.get("buildings") or []
    n = max(len(bb), len(ab))
    for i in range(n):
        b0 = bb[i] if i < len(bb) else {}
        b1 = ab[i] if i < len(ab) else {}
        name = b1.get("name") or b0.get("name") or f"Строение {i+1}"
        prefix = f"buildings[{i}]"
        for key, label in (
            ("houseType", "тип покрытия"),
            ("condition", "состояние"),
            ("material", "материал"),
            ("colors", "цвет"),
            ("previewColor", "цвет превью"),
            ("humidity", "влажность"),
        ):
            add(f"{prefix}.{key}", f"{name} · {label}", b0.get(key), b1.get(key))
        t0 = b0.get("tech") or {}
        t1 = b1.get("tech") or {}
        for key, label in (
            ("techId", "технология фасада"),
            ("paintId", "ЛКМ фасада"),
            ("coatingWant", "тип покрытия ЛКМ"),
            ("techIdInterior", "технология интерьера"),
            ("paintIdInterior", "ЛКМ интерьера"),
        ):
            add(f"{prefix}.tech.{key}", f"{name} · {label}", t0.get(key), t1.get(key))
        # walls lengths/heights
        w0 = {(w.get("id") or w.get("label")): w for w in (b0.get("measure") or {}).get("walls") or []}
        w1 = {(w.get("id") or w.get("label")): w for w in (b1.get("measure") or {}).get("walls") or []}
        for wid, w in w1.items():
            prev = w0.get(wid) or {}
            label = w.get("label") or wid
            add(f"{prefix}.wall.{wid}.length", f"{name} · {label} длина", prev.get("length"), w.get("length"))
            add(f"{prefix}.wall.{wid}.height", f"{name} · {label} высота", prev.get("height"), w.get("height"))
    return changes


def create_or_refresh_cabinet(
    *,
    object_id: str,
    survey: dict[str, Any],
    created_from: str = "estimate",
    actor_type: str = "staff",
    actor_id: str = "staff",
    base_url: str = "https://moracul.ru",
) -> dict[str, Any]:
    obj = crm.get_object(object_id)
    if not obj:
        raise ValueError("сделка не найдена")
    phone = normalize_phone(obj.get("client_phone") or (survey.get("client") or {}).get("phone"))
    if len(phone) < 10:
        raise ValueError("Укажите телефон клиента в сделке (нужен для входа в кабинет)")

    name = (obj.get("client_name") or (survey.get("client") or {}).get("name") or "").strip()
    now = _now()
    cab = get_cabinet_by_object(object_id)
    access_code = f"{secrets.randbelow(10**6):06d}"

    if cab:
        cab_id = cab["id"]
        with crm.connect() as conn:
            conn.execute(
                """
                UPDATE cabinets
                SET client_phone=?, client_name=?, status='active', access_code=?,
                    updated_at=?, created_from=?
                WHERE id=?
                """,
                (phone, name, access_code, now, created_from, cab_id),
            )
            # revoke old magic tokens
            conn.execute(
                "UPDATE cabinet_tokens SET revoked_at=? WHERE cabinet_id=? AND purpose='magic' AND revoked_at IS NULL",
                (now, cab_id),
            )
    else:
        cab_id = _new_id("cab")
        with crm.connect() as conn:
            conn.execute(
                """
                INSERT INTO cabinets(
                  id, object_id, survey_id, client_phone, client_name, status,
                  access_code, created_from, created_at, updated_at
                ) VALUES (?,?,?,?,?,'active',?,?,?,?)
                """,
                (cab_id, object_id, "", phone, name, access_code, created_from, now, now),
            )

    saved = save_survey_payload(
        survey_id=(survey.get("id") if isinstance(survey, dict) else None),
        object_id=object_id,
        cabinet_id=cab_id,
        payload=survey,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    with crm.connect() as conn:
        conn.execute(
            "UPDATE cabinets SET survey_id=?, updated_at=? WHERE id=?",
            (saved["id"], now, cab_id),
        )

    token = secrets.token_urlsafe(24)
    with crm.connect() as conn:
        conn.execute(
            """
            INSERT INTO cabinet_tokens(token, cabinet_id, purpose, expires_at, created_at)
            VALUES (?,?,?,?,?)
            """,
            (token, cab_id, "magic", now + TOKEN_TTL, now),
        )

    # money sync to CRM object
    try:
        est = survey.get("estimate") or {}
        # totals may be computed client-side — accept optional fields
        payload_money = {}
        if survey.get("_estimateSnapshot"):
            snap = survey["_estimateSnapshot"]
            payload_money = {
                "amount_subtotal": snap.get("subtotal"),
                "discount_pct": snap.get("discountPct") or est.get("discountPct"),
                "amount_total": snap.get("total"),
                "area_m2": snap.get("area_m2") or (snap.get("areas") or {}).get("paintTotal"),
            }
        if any(payload_money.get(k) for k in ("amount_subtotal", "amount_total", "area_m2")):
            crm.transition(object_id, "estimate_done", {
                "survey_local_id": saved["id"],
                **{k: v for k, v in payload_money.items() if v is not None},
            })
        else:
            crm.transition(object_id, "link_survey", {"survey_local_id": saved["id"]})
    except Exception:
        crm.log_event(object_id, "cabinet_survey", f"Кабинет {cab_id}, survey {saved['id']}")

    link = f"{base_url.rstrip('/')}/bestpaints/c/{token}"
    log_change(
        entity_type="cabinet",
        entity_id=cab_id,
        object_id=object_id,
        cabinet_id=cab_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="cabinet_open",
        message=f"Открыт кабинет клиента · код {access_code}",
        after={"link": link, "phone": phone},
    )
    crm.log_event(object_id, "cabinet_open", f"Кабинет клиента: {link}")

    cab = get_cabinet(cab_id)
    return {
        "cabinet": cab,
        "survey_id": saved["id"],
        "version": saved["version"],
        "link": link,
        "token": token,
        "access_code": access_code,
        "phone": phone,
    }


def resolve_magic_token(token: str) -> dict[str, Any] | None:
    with crm.connect() as conn:
        row = conn.execute("SELECT * FROM cabinet_tokens WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    d = dict(row)
    now = _now()
    if d.get("revoked_at"):
        return None
    if float(d.get("expires_at") or 0) < now:
        return None
    cab = get_cabinet(d["cabinet_id"])
    if not cab or cab.get("status") != "active":
        return None
    return {"token": d, "cabinet": cab}


def _hash_session(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_client_session(cabinet_id: str, phone: str) -> str:
    raw = secrets.token_urlsafe(32)
    now = _now()
    sid = _new_id("cs")
    with crm.connect() as conn:
        conn.execute(
            """
            INSERT INTO cabinet_sessions(id, cabinet_id, phone, token_hash, expires_at, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (sid, cabinet_id, normalize_phone(phone), _hash_session(raw), now + COOKIE_MAX_AGE, now),
        )
        conn.execute(
            "UPDATE cabinets SET last_client_at=?, updated_at=? WHERE id=?",
            (now, now, cabinet_id),
        )
    cookie_val = f"{sid}:{raw}"
    log_change(
        entity_type="session",
        entity_id=sid,
        cabinet_id=cabinet_id,
        object_id=(get_cabinet(cabinet_id) or {}).get("object_id") or "",
        actor_type="client",
        actor_id=normalize_phone(phone),
        action="client_login",
        message="Клиент вошёл в кабинет",
    )
    return cookie_val


def verify_client_session(cookie_val: str | None) -> dict[str, Any] | None:
    if not cookie_val or ":" not in cookie_val:
        return None
    sid, raw = cookie_val.split(":", 1)
    with crm.connect() as conn:
        row = conn.execute("SELECT * FROM cabinet_sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if float(d.get("expires_at") or 0) < _now():
        return None
    if not secrets.compare_digest(d.get("token_hash") or "", _hash_session(raw)):
        return None
    cab = get_cabinet(d["cabinet_id"])
    if not cab or cab.get("status") != "active":
        return None
    return {"session": d, "cabinet": cab}


def client_login(*, phone: str, token: str = "", access_code: str = "") -> dict[str, Any]:
    phone_n = normalize_phone(phone)
    if len(phone_n) < 10:
        raise ValueError("Введите телефон полностью")

    cab = None
    if token:
        pack = resolve_magic_token(token)
        if not pack:
            raise ValueError("Ссылка недействительна или устарела — попросите новую у менеджера")
        cab = pack["cabinet"]
        if not phones_match(cab.get("client_phone"), phone_n):
            raise ValueError("Телефон не совпадает с кабинетом. Введите номер, который оставляли на замере")
    elif access_code:
        code = re.sub(r"\D+", "", access_code)
        with crm.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM cabinets
                WHERE client_phone=? AND access_code=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (phone_n, code),
            ).fetchone()
            if not row:
                # try last-10 phone match
                rows = conn.execute(
                    "SELECT * FROM cabinets WHERE status='active' AND access_code=? ORDER BY updated_at DESC LIMIT 20",
                    (code,),
                ).fetchall()
                for r in rows:
                    if phones_match(r["client_phone"], phone_n):
                        row = r
                        break
        if not row:
            raise ValueError("Неверный телефон или код доступа")
        cab = _row_cab(row)
    else:
        with crm.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cabinets WHERE status='active' ORDER BY updated_at DESC LIMIT 50"
            ).fetchall()
        matches = [_row_cab(r) for r in rows if phones_match(r["client_phone"], phone_n)]
        if not matches:
            raise ValueError("Кабинет не найден. Откройте ссылку из SMS/WhatsApp или введите код доступа")
        if len(matches) > 1:
            raise ValueError("Найдено несколько кабинетов — откройте персональную ссылку или введите код")
        cab = matches[0]

    assert cab
    cookie = make_client_session(cab["id"], phone_n)
    return {"cabinet": cab, "cookie": cookie}


def revoke_cabinet(cabinet_id: str, *, actor_id: str = "staff") -> dict[str, Any]:
    now = _now()
    with crm.connect() as conn:
        conn.execute("UPDATE cabinets SET status='revoked', updated_at=? WHERE id=?", (now, cabinet_id))
        conn.execute(
            "UPDATE cabinet_tokens SET revoked_at=? WHERE cabinet_id=? AND revoked_at IS NULL",
            (now, cabinet_id),
        )
    cab = get_cabinet(cabinet_id)
    log_change(
        entity_type="cabinet",
        entity_id=cabinet_id,
        object_id=(cab or {}).get("object_id") or "",
        cabinet_id=cabinet_id,
        actor_type="staff",
        actor_id=actor_id,
        action="cabinet_revoke",
        message="Кабинет отозван",
    )
    return cab or {"id": cabinet_id, "status": "revoked"}


def list_change_logs(
    *,
    cabinet_id: str = "",
    object_id: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    q = "SELECT * FROM change_log WHERE 1=1"
    args: list[Any] = []
    if cabinet_id:
        q += " AND cabinet_id=?"
        args.append(cabinet_id)
    if object_id:
        q += " AND object_id=?"
        args.append(object_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(int(limit))
    with crm.connect() as conn:
        rows = conn.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["before"] = json.loads(d.pop("before_json") or "null")
        d["after"] = json.loads(d.pop("after_json") or "null")
        out.append(d)
    return out


def client_get_bundle(cabinet: dict[str, Any]) -> dict[str, Any]:
    survey_row = get_survey(cabinet.get("survey_id") or "")
    obj = crm.get_object(cabinet["object_id"]) or {}
    return {
        "cabinet": {
            "id": cabinet["id"],
            "client_name": cabinet.get("client_name") or "",
            "client_phone": cabinet.get("client_phone") or "",
            "status": cabinet.get("status"),
            "object_id": cabinet["object_id"],
            "updated_at": cabinet.get("updated_at"),
        },
        "object": {
            "title": obj.get("title") or "",
            "address": obj.get("address") or "",
            "surveyor_name": obj.get("surveyor_name") or "",
            "amount_total": obj.get("amount_total") or 0,
        },
        "survey": (survey_row or {}).get("payload") or {},
        "version": (survey_row or {}).get("version") or 0,
    }


def client_save_survey(cabinet: dict[str, Any], survey: dict[str, Any], *, phone: str) -> dict[str, Any]:
    if cabinet.get("status") != "active":
        raise ValueError("Кабинет закрыт")
    # merge: keep server id
    survey = dict(survey or {})
    survey["id"] = cabinet.get("survey_id") or survey.get("id")
    # force client phone from cabinet
    survey.setdefault("client", {})
    if isinstance(survey["client"], dict):
        survey["client"]["phone"] = cabinet.get("client_phone") or survey["client"].get("phone")
        if cabinet.get("client_name") and not survey["client"].get("name"):
            survey["client"]["name"] = cabinet["client_name"]

    saved = save_survey_payload(
        survey_id=cabinet.get("survey_id"),
        object_id=cabinet["object_id"],
        cabinet_id=cabinet["id"],
        payload=survey,
        actor_type="client",
        actor_id=normalize_phone(phone),
    )
    with crm.connect() as conn:
        conn.execute(
            "UPDATE cabinets SET survey_id=?, updated_at=?, last_client_at=? WHERE id=?",
            (saved["id"], _now(), _now(), cabinet["id"]),
        )
    # update CRM money if snapshot present
    snap = survey.get("_estimateSnapshot") or {}
    if snap.get("total") is not None:
        try:
            crm.transition(
                cabinet["object_id"],
                "save_money",
                {
                    "amount_subtotal": snap.get("subtotal"),
                    "discount_pct": snap.get("discountPct"),
                    "amount_total": snap.get("total"),
                    "area_m2": snap.get("area_m2") or (snap.get("areas") or {}).get("paintTotal"),
                },
            )
        except Exception:
            pass
    crm.log_event(
        cabinet["object_id"],
        "client_edit",
        f"Клиент обновил смету ({len(saved.get('changes') or [])} изменений)",
    )
    return saved


def public_base_url(request_base: str | None = None) -> str:
    return (os.getenv("BESTPAINTS_PUBLIC_URL") or request_base or "https://moracul.ru").rstrip("/")
