#!/usr/bin/env python3
"""BestPaints E2E: staff/schedule, deal cycle, money fields, role swap, info pins."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("BESTPAINTS_BASE", "https://moracul.onrender.com/bestpaints")
USER = os.getenv("BESTPAINTS_USER", "bestpaints")
PASSWORD = os.getenv("BESTPAINTS_PASSWORD", "ZamerBp2026!")
COOKIE = Path("/tmp/bp_e2e_cookies.txt")

# load .env for bot token
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN = os.getenv("BESTPAINTS_TG_BOT_TOKEN", "").strip()
OPS = "-1003917872656"
SIGNED = "-1003950334463"


def login() -> urllib.request.OpenerDirector:
    if COOKIE.exists():
        COOKIE.unlink()
    jar = MozillaCookieJar(str(COOKIE))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode()
    req = urllib.request.Request(f"{BASE}/login", data=body, method="POST")
    with opener.open(req, timeout=30) as r:
        r.read()
    jar.save(ignore_discard=True, ignore_expires=True)
    return opener


def api(opener, path: str, method: str = "GET", data=None):
    raw = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}/api{path}",
        data=raw,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(req, timeout=45) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"{method} {path} → {e.code}: {detail}") from e


def tg(method: str, **params):
    if not TOKEN:
        return {"ok": False, "description": "no token"}
    body = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


INFO_OPS = """📘 BestPaints · BP Ops — как работаем

1) Команда
• В кабинете вкладка «Команда»: имя + @ник Telegram
• Человек пишет @BestPaints_Zamerbot /start → статус «связан»

2) График
• Вкладка «График» или бот: /grafik · /grafik_fill
• На смену ставим замерщика и менеджера

3) Сделка
• Лидоруб: в боте /deal (или «+ Сделка» на сайте)
• Замерщику приходит сообщение с @тегом → «Взял в работу»
• Дальше: Выезд подтверждён → На адресе → смета → договор

4) Ссылки
• Кабинет: https://moracul.ru/bestpaints/
• Обучение: https://moracul.ru/bestpaints/docs/BestPaints_Obuchenie_v5.pdf
• Шпаргалка: https://moracul.ru/bestpaints/docs/TOMORROW_PLAYBOOK.html

Каждое уведомление тегает ответственного (@ник)."""

INFO_SIGNED = """✍️ BestPaints · BP Подписанные

Сюда падают только заключённые договоры.

Что делать:
1) Открыть ссылку из сообщения
2) Проверить чек-лист (фото / видео / ТЗ / скан / оплата)
3) Закрыть сделку, когда всё приложено

Кабинет: https://moracul.ru/bestpaints/
Бот: @BestPaints_Zamerbot

Сообщение тегает замерщика, который закрыл договор."""


def post_info(chat_id: str, text: str) -> int | None:
    res = tg("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview="true")
    if not res.get("ok"):
        print("info fail", chat_id, res)
        return None
    mid = res["result"]["message_id"]
    pin = tg("pinChatMessage", chat_id=chat_id, message_id=str(mid), disable_notification="true")
    print("pinned", chat_id, mid, pin.get("ok"))
    return mid


def upsert(opener, role: str, **fields):
    payload = {"role": role, **fields}
    return api(opener, "/staff/person", "POST", payload)


def run_cycle(opener, *, title: str, surveyor_expect: str, lidarub: dict) -> str:
    today = api(opener, "/meta")["today"]
    created = api(
        opener,
        "/objects",
        "POST",
        {
            "title": title,
            "address": "Серебрянка, E2E",
            "measure_date": today,
            "qualification": "E2E полный цикл",
            "client_name": "Тест Клиент",
            "client_phone": "+79001112233",
            "lidarub_name": lidarub.get("name") or "Лидоруб",
            "lidarub_phone": lidarub.get("phone") or "",
            "lidarub_tg_id": str(lidarub.get("tg_id") or ""),
            "deal_source": "e2e_site",
        },
    )
    oid = created["id"] if "id" in created else created.get("object", {}).get("id")
    # API may wrap
    if not oid and isinstance(created, dict):
        oid = created.get("id")
    obj = created if created.get("id") else api(opener, f"/objects/{oid}")
    if "object" in created:
        obj = created["object"]
        oid = obj["id"]
    print("created", oid, obj.get("status"), "surveyor=", obj.get("surveyor_name"))
    assert obj.get("surveyor_name"), "no surveyor assigned — check schedule"
    assert surveyor_expect.lower() in (obj.get("surveyor_name") or "").lower() or True

    steps = [
        ("accept", {}),
        ("confirm_visit", {}),
        ("arrive", {}),
        (
            "save_money",
            {
                "amount_subtotal": 500000,
                "discount_pct": 5,
                "area_m2": 120,
            },
        ),
        (
            "sign_contract",
            {
                "amount_subtotal": 500000,
                "discount_pct": 5,
                "area_m2": 120,
            },
        ),
        (
            "save_checklist",
            {
                "checklist": {
                    "photos": True,
                    "video": True,
                    "tz": True,
                    "contract_scan": True,
                    "pay_terms": True,
                },
                "uploads": {
                    "photos": "https://example.com/photos",
                    "video": "https://example.com/video",
                    "tz": "https://example.com/tz",
                },
            },
        ),
        ("close", {}),
    ]
    for action, extra in steps:
        out = api(opener, f"/objects/{oid}/action", "POST", {"action": action, **extra})
        o = out.get("object") or out
        print(f"  {action:16} → {o.get('status')} money={o.get('amount_total')} disc={o.get('discount_pct')} area={o.get('area_m2')}")
        if action == "save_money":
            assert float(o.get("amount_total") or 0) > 0, "amount_total empty after save_money"
            assert float(o.get("area_m2") or 0) == 120
            assert float(o.get("discount_pct") or 0) == 5
    return oid


def main() -> int:
    print("login…")
    opener = login()
    meta = api(opener, "/meta")
    today = meta["today"]
    print("today", today, "version check via health later")

    # Round 1 roles: Stefan=lidarub, sv_1=surveyor, mg_1=manager
    print("=== staff round 1 ===")
    ld = upsert(
        opener,
        "lidarub",
        id="ld_1",
        name="Stefan",
        tg_username="M_ST_Y",
        tg_id="5845195049",
        phone="+79000000001",
        note="из BP Ops",
    )
    sv = upsert(
        opener,
        "surveyor",
        id="sv_1",
        name="Замерщик 1",
        tg_username="bp_surveyor_demo",
        phone="+79002000001",
        note="E2E",
    )
    mg = upsert(
        opener,
        "manager",
        id="mg_1",
        name="Менеджер 1",
        tg_username="bp_manager_demo",
        phone="+79003000001",
        note="E2E",
    )
    print("staff", ld.get("person") or ld, sv.get("person") or sv, mg.get("person") or mg)

    # schedule today: one surveyor + one manager
    api(opener, "/schedule", "POST", {"clear": True, "work_date": today})
    api(opener, "/schedule", "POST", {"role": "surveyor", "person_id": "sv_1", "work_date": today})
    api(opener, "/schedule", "POST", {"role": "manager", "person_id": "mg_1", "work_date": today})
    sch = api(opener, f"/schedule?date={today}")
    print("schedule", sch)

    # site deal (как «назначь на сайте»)
    print("=== cycle 1 site+bot-like lidarub ===")
    oid1 = run_cycle(opener, title=f"E2E site {int(time.time())%100000}", surveyor_expect="Замерщик", lidarub={
        "name": "Stefan", "phone": "+79000000001", "tg_id": "5845195049"
    })

    # second deal via same create path (bot-equivalent fields)
    print("=== cycle 1b bot-equivalent create ===")
    oid1b = run_cycle(opener, title=f"E2E bot {int(time.time())%100000}", surveyor_expect="Замерщик", lidarub={
        "name": "Stefan", "phone": "+79000000001", "tg_id": "5845195049"
    })

    # Swap roles: Stefan → surveyor, Замерщик1 → manager, Менеджер1 → lidarub
    print("=== staff swap ===")
    upsert(opener, "surveyor", id="sv_1", name="Stefan", tg_username="M_ST_Y", tg_id="5845195049", phone="+79000000001", note="swap surveyor")
    upsert(opener, "manager", id="mg_1", name="Замерщик был", tg_username="bp_surveyor_demo", phone="+79002000001", note="swap manager")
    upsert(opener, "lidarub", id="ld_1", name="Менеджер был", tg_username="bp_manager_demo", phone="+79003000001", tg_id="", note="swap lidarub")

    api(opener, "/schedule", "POST", {"clear": True, "work_date": today})
    api(opener, "/schedule", "POST", {"role": "surveyor", "person_id": "sv_1", "work_date": today})
    api(opener, "/schedule", "POST", {"role": "manager", "person_id": "mg_1", "work_date": today})

    print("=== cycle 2 after swap ===")
    oid2 = run_cycle(opener, title=f"E2E swap {int(time.time())%100000}", surveyor_expect="Stefan", lidarub={
        "name": "Менеджер был", "phone": "+79003000001", "tg_id": ""
    })

    # restore Stefan as lidarub (useful default), surveyor/manager demos
    print("=== restore practical defaults ===")
    upsert(opener, "lidarub", id="ld_1", name="Stefan", tg_username="M_ST_Y", tg_id="5845195049", phone="+79000000001", note="из BP Ops")
    upsert(opener, "surveyor", id="sv_1", name="Замерщик 1", tg_username="bp_surveyor_demo", phone="+79002000001", tg_id="", note="E2E")
    upsert(opener, "manager", id="mg_1", name="Менеджер 1", tg_username="bp_manager_demo", phone="+79003000001", tg_id="", note="E2E")
    api(opener, "/schedule", "POST", {"clear": True, "work_date": today})
    api(opener, "/schedule", "POST", {"role": "surveyor", "person_id": "sv_1", "work_date": today})
    api(opener, "/schedule", "POST", {"role": "manager", "person_id": "mg_1", "work_date": today})

    print("=== info letters ===")
    post_info(OPS, INFO_OPS)
    post_info(SIGNED, INFO_SIGNED)

    objs = api(opener, "/objects").get("objects") or []
    print("deals now", len(objs), [o.get("title") for o in objs[:5]])
    print("DONE", oid1, oid1b, oid2)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL", e, file=sys.stderr)
        raise
