#!/usr/bin/env python3
"""Smoke-тест импорта готовой сметы (уже отправленной клиенту другим способом) → сделка."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

td = tempfile.mkdtemp()
os.environ["BESTPAINTS_DB_PATH"] = str(Path(td) / "t.db")
os.environ["BESTPAINTS_STAFF_PATH"] = str(Path(td) / "staff.json")

from oracle_bot import bestpaints_crm as crm  # noqa: E402
from oracle_bot.bestpaints_estimate_import import (  # noqa: E402
    merge_estimates,
    normalize_estimate,
)

failed = 0


def ok(c, m):
    global failed
    print(("OK" if c else "FAIL"), m)
    if not c:
        failed += 1


# --- normalize_estimate: числа, строки, дозаполнение ---
n = normalize_estimate(
    {
        "confidence": 0.9,
        "client": {"name": "Иванов", "phone": "8 900 111-22-33", "address": "ул. Ленина 1"},
        "title": "Дом Иванова",
        "subtotal": "150 000",
        "discountPct": "10",
        "lines": [
            {"name": "Покраска фасада", "qty": "60", "unit": "м2", "price": "2000"},
            {"name": "Пропитка торцов", "qty": None, "price": None, "sum": "5000"},
            {"name": "", "qty": 1, "price": 0, "sum": None},  # пустое имя без суммы — должно отфильтроваться
        ],
    }
)
ok(n["client"]["name"] == "Иванов", "client name parsed")
ok(n["subtotal"] == 150000.0, "subtotal comma/space stripped")
ok(n["discountPct"] == 10.0, "discountPct parsed")
ok(len(n["lines"]) == 2, "empty nameless line dropped")
ok(n["lines"][0]["sum"] == 120000.0, "line sum computed from qty*price")
ok(n["lines"][1]["qty"] == 1.0 and n["lines"][1]["price"] == 5000.0, "line qty/price backfilled from sum")

# --- merge_estimates: конкатенация строк с нескольких фото (страниц), без потери данных ---
part1 = normalize_estimate(
    {
        "client": {"name": "Петров"},
        "subtotal": None,
        "lines": [{"name": "Работа A", "qty": 1, "price": 1000, "sum": 1000}],
    }
)
part2 = normalize_estimate(
    {
        "client": {"phone": "89990000000"},
        "lines": [
            {"name": "Работа B", "qty": 1, "price": 2000, "sum": 2000},
            {"name": "Работа C", "qty": 1, "price": 3000, "sum": 3000},
        ],
    }
)
merged = merge_estimates(part1, part2)
ok(len(merged["lines"]) == 3, "merge_estimates concatenates lines from all parts (no data loss)")
ok(merged["client"]["name"] == "Петров" and merged["client"]["phone"] == "89990000000", "merge fills missing client fields from other parts")

dup_part = normalize_estimate({"lines": [{"name": "Работа A", "qty": 1, "price": 1000, "sum": 1000}]})
merged_dedup = merge_estimates(part1, dup_part)
ok(len(merged_dedup["lines"]) == 1, "merge_estimates dedups exact-duplicate lines (retake photos)")

# --- create_imported_deal: полный сценарий создания сделки из готовой сметы ---
crm.upsert_person("lidarub", {"id": "lid1", "name": "Тест Лидоруб", "phone": "+79990000001"})
crm.upsert_person("manager", {"id": "mgr1", "name": "Тест Менеджер", "phone": "+79990000002"})
crm.upsert_person("surveyor", {"id": "sv1", "name": "Тест Замерщик", "phone": "+79990000003"})

obj = crm.create_imported_deal(
    {
        "title": "Импорт: Сидоров",
        "address": "ул. Тестовая, 5",
        "client_name": "Сидоров С.С.",
        "client_phone": "+79990002222",
        "lidarub_id": "lid1",
        "manager_id": "mgr1",
        "surveyor_id": "sv1",
        "subtotal": 200000,
        "discount_pct": 10,
        "total": 180000,
        "area_m2": 120,
        "survey_local_id": "survey-xyz",
        "source_note": "скрин из WhatsApp",
        "actor_role": "lidarub",
    }
)
ok(obj["status"] == "on_site", "imported deal lands on on_site (ready for signed/declined)")
ok(obj["lidarub_id"] == "lid1" and obj["manager_id"] == "mgr1" and obj["surveyor_id"] == "sv1", "manual roles resolved by id")
ok(obj["amount_total"] == 180000.0 and obj["discount_pct"] == 10.0, "money applied from payload")
ok(obj["survey_local_id"] == "survey-xyz", "survey_local_id linked (builder/estimate can resume)")
ok(obj["deal_source"] == "import_estimate", "deal_source tagged for badge in UI")
ok(all(obj.get(f"{k}_at") for k in ("assigned", "accepted", "visit_confirmed", "on_site")), "timestamps backfilled")
events = crm.list_events(obj["id"])
ok(any("Импорт готовой сметы" in (e.get("message") or "") for e in events), "audit event logged with operator role")
ok(any("источник" in (e.get("message") or "") for e in events), "source note logged for audit")

# лидоруб обязателен только на уровне UI (валидация в форме); бэкенд не должен падать,
# если его всё же не передали — деградирует на генерическое имя "Лидоруб".
try:
    obj2 = crm.create_imported_deal(
        {
            "title": "Без лидоруба",
            "client_phone": "+79990003333",
            "manager_id": "mgr1",
        }
    )
    ok(obj2["status"] == "on_site", "create_imported_deal degrades gracefully without lidarub_id (no crash)")
except Exception as e:  # noqa: BLE001
    ok(False, f"unexpected crash without lidarub_id: {e}")

# --- фронтенд: кнопка, модуль, роуты подключены ---
BP = ROOT / "oracle_bot/static/bestpaints"
crmjs = (BP / "js/crm.js").read_text(encoding="utf-8")
ok("bindImportEstimatePanel" in crmjs, "crm.js binds import panel")
ok("Загрузить готовую смету" in crmjs, "import button label present")
ok("import_estimate" in crmjs, "import badge keyed on deal_source")

ie = (BP / "js/estimate_import.js").read_text(encoding="utf-8")
ok("data-cf" in ie and "data-lf" not in ie, "line inputs use data-cf (matches .custom-line responsive CSS)")

web = (ROOT / "oracle_bot/webapp.py").read_text(encoding="utf-8")
ok("/bestpaints/api/parse-estimate" in web, "server parse-estimate route")
ok("/bestpaints/api/objects/import-estimate" in web, "server import-estimate route")

sw = (BP / "sw.js").read_text(encoding="utf-8")
ok("estimate_import.js" in sw, "sw precaches estimate_import.js")

print("ALL PASSED" if not failed else f"{failed} FAILURES")
sys.exit(1 if failed else 0)
