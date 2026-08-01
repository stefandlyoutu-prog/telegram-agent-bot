#!/usr/bin/env python3
"""Создаёт тестовую историю: замерщик Морозов Степан + данные бланка/DOCX.

1) Пишет полный survey JSON (для localStorage / ручного импорта).
2) Опционально гоняет живой Vision/LLM по фото+docx (LIVE=1).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle_bot.bestpaints_reports import (  # noqa: E402
    GOLDEN_SERGEY_CHERNY_RUCHEY,
    extract_docx_text,
    normalize_report,
    parse_report_bundle,
)


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def survey_from_report(data: dict) -> dict:
    data = normalize_report(data)
    c = data["client"]
    binfo = data["building"]
    site = data["site"]
    mextra = data["measure"]
    walls = []
    for w in data["walls"]:
        has_lh = w.get("length") is not None and w.get("height") is not None
        walls.append(
            {
                "id": _uid(),
                "label": w["label"],
                "shape": w.get("shape") or ("custom" if w.get("areaManual") and not has_lh else "rect"),
                "length": "" if w.get("length") is None else str(w["length"]),
                "height": "" if w.get("height") is None else str(w["height"]),
                "ridge": "" if w.get("ridge") is None else str(w["ridge"]),
                "height2": "",
                "areaManual": "" if w.get("areaManual") is None else str(w["areaManual"]),
                "zone": w.get("zone") or "facade",
                "material": binfo.get("material") or "block",
                "condition": "",
                "coatingWant": "",
                "note": w.get("note") or "из отчёта",
                "photos": [],
                "flags": {},
                "endsOn": bool(w.get("endsLength") or w.get("endsCount")),
                "endsLength": "" if w.get("endsLength") is None else str(w["endsLength"]),
                "endsCount": "" if w.get("endsCount") is None else str(w["endsCount"]),
                "endsDepth": "0.2",
                "soffitArea": "" if w.get("soffitArea") is None else str(w["soffitArea"]),
                "ceilingArea": "" if w.get("ceilingArea") is None else str(w["ceilingArea"]),
                "trimLength": "" if w.get("trimLength") is None else str(w["trimLength"]),
                "doborLength": "" if w.get("doborLength") is None else str(w["doborLength"]),
                "gutterLength": "" if w.get("gutterLength") is None else str(w["gutterLength"]),
                "sillLength": "" if w.get("sillLength") is None else str(w["sillLength"]),
                "attention": {},
            }
        )
    bid = _uid()
    now = datetime.now(timezone.utc).isoformat()
    layout = mextra.get("layoutLength") or sum((w.get("layoutLength") or 0) for w in data["walls"])
    return {
        "id": f"srv_demo_{_uid()}",
        "title": binfo.get("name") or c.get("address") or "Сергей · Чёрный Ручей",
        "createdAt": now,
        "updatedAt": now,
        "client": {
            "name": c.get("name") or "",
            "phone": c.get("phone") or "",
            "email": "",
            "address": c.get("address") or "",
            "surveyor": c.get("surveyor") or "Морозов Степан",
        },
        "buildings": [
            {
                "id": bid,
                "name": binfo.get("name") or "Дом блок-хаус",
                "kind": "house",
                "roofType": "gable",
                "zones": {"facade": True, "interior": False},
                "material": binfo.get("material") or "block",
                "materialSize": binfo.get("materialSize") or "",
                "houseType": binfo.get("houseType") or "film",
                "condition": binfo.get("condition") or "normal",
                "humidity": "",
                "colors": binfo.get("colors") or "Adler",
                "oldCoatingNote": binfo.get("oldCoatingNote") or "",
                "removalDifficulty": binfo.get("removalDifficulty") or "normal",
                "fenceBothSides": False,
                "plinthSkip": False,
                "tech": {
                    "techId": 4,
                    "paintId": "",
                    "paintIdInterior": "",
                    "scope": "facade",
                    "colorSameOrDarker": True,
                    "compatibilityTest": False,
                    "techIdInterior": 4,
                },
                "previewColor": "#c4a35a",
                "photos": [],
                "dims": {
                    "length": "",
                    "width": "",
                    "heightRidge": "" if binfo.get("heightRidge") is None else str(binfo["heightRidge"]),
                    "heightGable": "",
                },
                "measure": {
                    "walls": walls,
                    "openings": [],
                    "wallsArea": 0,
                    "openingsArea": mextra.get("openingsArea") or "",
                    "facadeArea": 0,
                    "interiorArea": 0,
                    "endsLength": "",
                    "soffitArea": "",
                    "fasciaArea": "",
                    "ceilingArea": "",
                    "trimLength": "",
                    "doborLength": "",
                    "layoutLength": "" if layout is None else str(layout),
                    "gutterLength": "",
                    "sillLength": "",
                    "roundCoef": 1,
                    "paintSides": 1,
                    "notes": mextra.get("notes") or data.get("notes") or "",
                },
            }
        ],
        "activeBuildingId": bid,
        "attention": data.get("attention") or {},
        "site": {
            "startWhen": site.get("startWhen") or "",
            "workHours": site.get("workHours") or "",
            "powerKw": "",
            "powerFrom": site.get("powerFrom") or "",
            "powerOk": "yes",
            "generator": False,
            "housing": site.get("housing") or "need",
            "toilet": site.get("toilet") or "yes",
            "shower": site.get("shower") or "none",
            "water": site.get("water") or "yes",
            "shop": "",
            "scaffold": "none",
            "maxHeight": "" if binfo.get("heightRidge") is None else str(binfo["heightRidge"]),
            "accessNote": "",
            "occupancy": "empty",
            "clientFurniture": "yes",
            "notes": site.get("notes") or data.get("notes") or "",
        },
        "extras": {"qty": data.get("extrasQty") or {}},
        "estimate": {
            "discountPct": 0,
            "payments": {"advance": 10, "second": 40, "third": 40, "final": 10},
            "customLines": [],
        },
        "contract": {
            "objectName": binfo.get("name") or "",
            "number": "",
            "date": "",
            "workDays": "",
            "startDate": "",
            "managerName": "",
            "managerPhone": "",
            "surveyorPhone": "",
            "passport": "",
            "passportIssued": "",
            "passportCode": "",
            "registration": "",
        },
        "_demo": "morozov_stepan_sergey_cherny_ruchey",
    }


async def live_parse() -> dict | None:
    img = Path(
        "/Users/polzovatel/.cursor/projects/Users-polzovatel-Projects-telegram-agent-bot/assets/"
        "IMG_20260731_170141-4eff0d2b-0457-4efd-9f1c-4f10657f1308.png"
    )
    docx = Path("/Users/polzovatel/Downloads/Отчёт.docx")
    images = [img.read_bytes()] if img.exists() else []
    texts = []
    if docx.exists():
        texts.append(extract_docx_text(docx.read_bytes()))
    if not images and not texts:
        print("LIVE skip: no files")
        return None
    hint = "замерщик Морозов Степан. Это бланк отчёта по замеру + DOCX-заметки."
    print(f"LIVE parse: images={len(images)} texts={len(texts)}…")
    return await parse_report_bundle(images=images, texts=texts, hint=hint)


def main() -> int:
    out_dir = ROOT / "oracle_bot/static/bestpaints/data"
    out_dir.mkdir(parents=True, exist_ok=True)

    golden = normalize_report(GOLDEN_SERGEY_CHERNY_RUCHEY)
    survey = survey_from_report(golden)
    survey_path = out_dir / "demo-survey-morozov-stepan.json"
    survey_path.write_text(json.dumps(survey, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", survey_path)

    report_path = out_dir / "demo-report-sergey.json"
    report_path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", report_path)

    # CRM seed locally if module available
    try:
        from oracle_bot import bestpaints_crm as crm

        obj = crm.create_object(
            {
                "client_name": survey["client"]["name"],
                "client_phone": survey["client"]["phone"],
                "address": survey["client"]["address"],
                "title": survey["title"],
                "surveyor_name": "Морозов Степан",
                "notes": "Демо-история из бланка + Отчёт.docx",
            }
        )
        print("CRM object", obj.get("id"), obj.get("status"))
    except Exception as e:
        print("CRM seed skip:", e)

    if os.getenv("LIVE") == "1":
        try:
            live = asyncio.run(live_parse())
        except Exception as e:
            print("LIVE fail (using golden survey):", e)
            live = None
        if live:
            live_path = out_dir / "live-report-sergey.json"
            live_path.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
            print("LIVE confidence", live.get("confidence"), "walls", len(live.get("walls") or []))
            print("Wrote", live_path)
            g_areas = sorted(w.get("areaManual") or 0 for w in golden["walls"])
            l_areas = sorted(w.get("areaManual") or 0 for w in (live.get("walls") or []))
            print("golden areas", g_areas)
            print("live areas", l_areas)
            print("live client", live.get("client"))
    else:
        print("Set LIVE=1 to run Vision/LLM on blank+docx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
