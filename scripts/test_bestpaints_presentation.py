#!/usr/bin/env python3
"""Smoke-тест чертежей + презентационного PDF BestPaints."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle_bot.bestpaints_drawings import normalize_parse

BP = Path(__file__).resolve().parents[1] / "oracle_bot/static/bestpaints"
failed = 0

def ok(c, m):
    global failed
    print(("OK" if c else "FAIL"), m)
    if not c:
        failed += 1

r = normalize_parse({
    "confidence": 0.85,
    "drawingType": "elevation",
    "walls": [
        {"label": "Главный фасад", "length": 10, "height": 3, "shape": "rect"},
        {"label": "Торцы", "length": 6, "height": 3, "ridge": 4.5, "shape": "gable"},
    ],
    "openings": [{"wallLabel": "Главный фасад", "label": "Окно", "width": 1.5, "height": 1.4}],
})
ok(len(r["walls"]) == 2, "2 walls")
ok(len(r["openings"]) == 1, "1 opening")

report = (BP / "js/report.js").read_text(encoding="utf-8")
for needle in ["Почему это решение", "Из чего складывается цена по сторонам", "Обоснование цены", "ГАРАНТИЯ", "pitchForPaint"]:
    ok(needle in report, f"report has {needle}")

app = (BP / "js/app.js").read_text(encoding="utf-8")
ok("bindDrawingsPanel" in app, "drawings bound")
ok("/bestpaints/api/parse-drawing" in (BP / "js/drawings.js").read_text(encoding="utf-8"), "client API path")
ok("parse-drawing" in Path(__file__).resolve().parents[1].joinpath("oracle_bot/webapp.py").read_text(encoding="utf-8"), "server route")
ok("bp-survey-v43" in (BP / "sw.js").read_text(encoding="utf-8"), "cache v43")

print("ALL PASSED" if not failed else f"{failed} FAILURES")
sys.exit(1 if failed else 0)
