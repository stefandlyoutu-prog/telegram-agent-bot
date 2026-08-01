#!/usr/bin/env python3
"""Тесты парсера отчётов замерщика BestPaints + наличиеные файлы в UI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle_bot.bestpaints_reports import (  # noqa: E402
    GOLDEN_SERGEY_CHERNY_RUCHEY,
    extract_docx_text,
    extract_plain_from_bytes,
    merge_reports,
    normalize_report,
)

BP = ROOT / "oracle_bot/static/bestpaints"
failed = 0


def ok(cond: bool, msg: str) -> None:
    global failed
    print(("OK" if cond else "FAIL"), msg)
    if not cond:
        failed += 1


def main() -> int:
    g = normalize_report(GOLDEN_SERGEY_CHERNY_RUCHEY)
    ok(g["client"]["surveyor"] == "Морозов Степан", "surveyor Морозов Степан")
    ok(g["client"]["name"] == "Сергей", "client Сергей")
    ok("Черный" in g["client"]["address"] or "Чёрный" in g["client"]["address"], "address СНТ")
    ok(g["building"]["material"] == "block", "material block")
    ok(len(g["walls"]) == 4, "4 walls")
    areas = [w["areaManual"] for w in g["walls"]]
    ok(areas == [6.6, 29.5, 11.7, 18.9], f"wall areas {areas}")
    ok(g["attention"].get("lights", 0) >= 12, "lights attention")
    ok(float(g["extrasQty"].get("cable") or 0) >= 40, "cable extras")
    ok(g["site"]["housing"] == "need", "housing need")
    ok(g["measure"]["openingsArea"] and g["measure"]["openingsArea"] > 10, "openings area")

    # суммы вида 11+1
    n = normalize_report({"attention": {"lights": "11+1"}, "walls": [{"label": "A", "areaManual": "6,6"}]})
    ok(n["attention"]["lights"] == 12, "lights 11+1 → 12")
    ok(n["walls"][0]["areaManual"] == 6.6, "comma decimal")

    # merge: стены из бланка + notes из docx
    blank = normalize_report({"walls": [{"label": "1", "areaManual": 10}], "client": {"name": "Сергей"}})
    notes = normalize_report(
        {
            "notes": "шлифовка 2 прохода",
            "client": {"surveyor": "Морозов Степан"},
            "site": {"notes": "согласовать с председателем"},
        }
    )
    m = merge_reports(blank, notes)
    ok(len(m["walls"]) == 1, "merge keeps walls")
    ok(m["client"]["surveyor"] == "Морозов Степан", "merge surveyor")
    ok("шлифовка" in m["notes"], "merge notes")

    docx = Path("/Users/polzovatel/Downloads/Отчёт.docx")
    if docx.exists():
        text = extract_docx_text(docx.read_bytes())
        ok("блок-хаус" in text.lower() or "блок" in text.lower(), "docx mentions blockhouse")
        ok("председатель" in text.lower() or "вагончик" in text.lower(), "docx быт")
        plain = extract_plain_from_bytes(docx.read_bytes(), filename="Отчёт.docx")
        ok(len(plain) > 50, "plain from docx")
    else:
        print("SKIP docx file missing")

    reports_js = (BP / "js/reports.js").read_text(encoding="utf-8")
    ok("parse-report" in reports_js, "client parse-report API")
    ok("applyReportParse" in reports_js, "applyReportParse export")
    ok("rp-demo" in reports_js, "demo button")

    app = (BP / "js/app.js").read_text(encoding="utf-8")
    ok("bindReportsPanel" in app, "reports bound in app")
    ok("reportsPanelHtml" in app, "reports panel html")

    web = (ROOT / "oracle_bot/webapp.py").read_text(encoding="utf-8")
    ok("parse-report" in web, "server parse-report")
    ok("demo-report" in web, "server demo-report")

    sw = (BP / "sw.js").read_text(encoding="utf-8")
    ok("bp-survey-v49" in sw, "cache v49")
    ok("reports.js" in sw, "sw caches reports.js")

    # сохранить эталонный JSON для импорта/истории
    out = ROOT / "oracle_bot/static/bestpaints/data/demo-report-sergey.json"
    out.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(out.exists() and out.stat().st_size > 500, f"wrote {out.name}")

    print("ALL PASSED" if not failed else f"{failed} FAILURES")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
