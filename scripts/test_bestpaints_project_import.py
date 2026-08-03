#!/usr/bin/env python3
"""Smoke-тест импорта проекта дома (архитектурная документация → стены/площади) → сделка."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

td = tempfile.mkdtemp()
os.environ["BESTPAINTS_DB_PATH"] = str(Path(td) / "t.db")
os.environ["BESTPAINTS_STAFF_PATH"] = str(Path(td) / "staff.json")

from oracle_bot import bestpaints_crm as crm  # noqa: E402
from oracle_bot.bestpaints_project_import import (  # noqa: E402
    extract_wall_area_candidates,
    normalize_project,
)
from oracle_bot.bestpaints_reports import extract_plain_from_bytes  # noqa: E402

failed = 0


def ok(c, m):
    global failed
    print(("OK" if c else "FAIL"), m)
    if not c:
        failed += 1


# --- extract_wall_area_candidates: имя стены + площадь в м², как экспортируют CAD-программы ---
sample_text = (
    "Стадия Лист Листов Подп. Дата\nЗаказчик\nИсполнил Козырев А.К. 15.07.2022\n"
    "Стена01\n26.33м2\nГор 1\nВерт 1\n"
    "Стена02\n64.02м2\nГор 1\nВерт 1\n"
    "СтенаА\n50.74м2\nГор 1\nВерт 1\n"
    "Кухня-Столовая\n23.80м2\n"  # площадь комнаты — не должна попасть в стены
)
cands = extract_wall_area_candidates(sample_text)
ok(len(cands) == 3, f"finds all wall+area pairs, got {len(cands)}")
labels = {c["label"] for c in cands}
ok(labels == {"Стена01", "Стена02", "СтенаА"}, f"wall labels correct: {labels}")
ok(next(c for c in cands if c["label"] == "Стена01")["area"] == 26.33, "wall area parsed with decimal point")
ok(not any(c["label"] == "Кухня-Столовая" for c in cands), "room floor area is not mistaken for a wall")

# --- normalize_project: переиспользует схему отчёта + добирает пропущенные стены из regex ---
raw = {
    "confidence": 0.9,
    "notes": "2 этажа, кровля ~500м2",
    "client": {"name": "", "phone": "", "address": ""},
    "building": {"material": "", "name": "Дом №2"},
    "walls": [
        {"label": "Стена01", "areaManual": 26.33, "shape": "custom", "zone": "facade", "confidence": 0.9},
    ],
}
normalized = normalize_project(raw, wall_candidates=cands)
wall_labels = {w["label"] for w in normalized["walls"]}
ok(wall_labels == {"Стена01", "Стена02", "СтенаА"}, f"missing walls from regex are added back, got {wall_labels}")
ok(
    next(w for w in normalized["walls"] if w["label"] == "Стена02")["areaManual"] == 64.02,
    "auto-added wall keeps correct area",
)
ok(all(w["zone"] == "facade" and w["shape"] == "custom" for w in normalized["walls"]), "walls are facade/custom (area-only)")
ok(normalized["client"]["name"] == "", "no client invented when project has none (не выдумывает клиента)")

# --- extract_plain_from_bytes: PDF без текстового слоя не превращается в мусор ---
ok(extract_plain_from_bytes(b"not a real pdf but short", filename="x.txt") == "not a real pdf but short", "plain txt passthrough still works")
fake_pdf = b"%PDF-1.4\nnot a real pdf structure"
ok(extract_plain_from_bytes(fake_pdf, filename="broken.pdf") == "", "broken/unparseable PDF degrades to empty text, not binary garbage")

# --- create_imported_deal(source_kind=project): полный сценарий создания сделки из проекта ---
crm.upsert_person("lidarub", {"id": "lid1", "name": "Тест Лидоруб", "phone": "+79990000001"})
crm.upsert_person("manager", {"id": "mgr1", "name": "Тест Менеджер", "phone": "+79990000002"})
crm.upsert_person("surveyor", {"id": "sv1", "name": "Тест Замерщик", "phone": "+79990000003"})

obj = crm.create_imported_deal(
    {
        "title": "Дом №2 (проект)",
        "address": "",
        "client_name": "",
        "client_phone": "",
        "lidarub_id": "lid1",
        "manager_id": "mgr1",
        "surveyor_id": "sv1",
        "survey_local_id": "survey-project-1",
        "source_note": "проект дома №2 от 15.07.2022",
        "source_kind": "project",
        "actor_role": "lidarub",
    }
)
ok(obj["status"] == "on_site", "imported project deal lands on on_site (готово к замеру/конструктору)")
ok(obj["deal_source"] == "import_project", "deal_source tagged import_project for badge in UI")
ok(obj["survey_local_id"] == "survey-project-1", "survey_local_id linked (constructor can resume with prefilled walls)")
ok(float(obj.get("amount_total") or 0) == 0.0, "no money invented for a project import (только стены, смету считает конструктор)")
events = crm.list_events(obj["id"])
ok(any("Импорт проекта дома" in (e.get("message") or "") for e in events), "audit event labeled as project import, not estimate")
ok(any("источник" in (e.get("message") or "") for e in events), "source note logged for audit")

# sanity: обычный импорт сметы (source_kind по умолчанию) не ломается генерализацией
obj_est = crm.create_imported_deal(
    {
        "title": "Смета (обычная)",
        "lidarub_id": "lid1",
        "subtotal": 100000,
        "total": 100000,
        "actor_role": "lidarub",
    }
)
ok(obj_est["deal_source"] == "import_estimate", "default source_kind stays import_estimate (backward compatible)")
events_est = crm.list_events(obj_est["id"])
ok(any("Импорт готовой сметы" in (e.get("message") or "") for e in events_est), "estimate import message unchanged")

# --- фронтенд: кнопка, модуль, роуты подключены ---
BP = ROOT / "oracle_bot/static/bestpaints"
crmjs = (BP / "js/crm.js").read_text(encoding="utf-8")
ok("bindImportProjectPanel" in crmjs, "crm.js binds project import panel")
ok("Загрузить проект дома" in crmjs, "project import button label present")
ok("import_project" in crmjs, "project import badge keyed on deal_source")

pi = (BP / "js/project_import.js").read_text(encoding="utf-8")
ok("data-cf" in pi, "wall row inputs use data-cf (matches .custom-line responsive CSS)")
ok("applyReportParse" in pi, "reuses report-parse→survey mapping instead of duplicating it")
ok("source_kind" in pi and "project" in pi, "submits source_kind=project to the shared import endpoint")

web = (ROOT / "oracle_bot/webapp.py").read_text(encoding="utf-8")
ok("/bestpaints/api/parse-project" in web, "server parse-project route")
ok("parse_project_bundle" in web, "server wires parse_project_bundle")

sw = (BP / "sw.js").read_text(encoding="utf-8")
ok("project_import.js" in sw, "sw precaches project_import.js")
ok(re.search(r"bp-survey-v\d+", sw), "sw has a cache version tag")

reqs = (ROOT / "requirements-oracle.txt").read_text(encoding="utf-8")
ok(re.search(r"PyMuPDF", reqs, re.I), "PyMuPDF declared for the moracul deploy (fast PDF text extraction)")

print("ALL PASSED" if not failed else f"{failed} FAILURES")
sys.exit(1 if failed else 0)
