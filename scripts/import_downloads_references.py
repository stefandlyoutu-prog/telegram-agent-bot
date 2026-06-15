#!/usr/bin/env python3
"""Import reference ZIPs from ~/Downloads into data/reference_models/."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference_models"
DOWNLOADS = Path.home() / "Downloads"

IMPORTS = [
    ("boeing-747sp-1200-model_files.zip", "clerx_boeing_747sp_printables_zip"),
    ("WILLYS_JEEP_original_style.zip", "vehicle_willys_jeep_kit"),
    ("EGG_ROLL_BASKET.zip", "perforated_egg_basket"),
    ("stackable_crate.zip", "modular_stackable_crate"),
    ("Wall_Fixing.zip", "wall_mount_fixing"),
    ("Key_Holder.zip", "wall_mount_key_holder"),
    ("Ender_3_V2_Tool_Holder.zip", "printer_tool_holder_ender3"),
    ("Pegstr_Pegboard_Wizard.zip", "pegboard_ecosystem"),
    ("Star_Destroyer_Kit_Card.zip", "vehicle_star_destroyer_kit"),
    ("Halloween_Stitch.zip", "character_stitch_kit"),
    ("Baby_Yoda_Free_Sample.zip", "character_baby_yoda"),
    ("Charizard_Pokemon_.zip", "character_charizard"),
    ("Deadpool_Bust.zip", "character_deadpool_bust"),
    ("Starter_Plant_Grower.zip", "seed_starter_kit"),
    ("Mechanical_Planetarium.zip", "mechanical_planetarium"),
    ("zx82net_Ultimate_Parametric_Rugged_Box_Snap_Closure.zip", "hinged_snap_box"),
]


def import_zip(zip_name: str, slug: str) -> dict:
    src = DOWNLOADS / zip_name
    out = REF / slug
    if not src.is_file():
        return {"slug": slug, "status": "missing", "source": str(src)}
    out.mkdir(parents=True, exist_ok=True)
    stl_before = list(out.rglob("*.stl"))
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(out)
    stls = list(out.rglob("*.stl"))
    manifest = {
        "slug": slug,
        "status": "ok",
        "source_zip": str(src),
        "bytes": src.stat().st_size,
        "stl_count": len(stls),
        "sample_files": [str(p.relative_to(out)) for p in sorted(stls)[:12]],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    results = [import_zip(name, slug) for name, slug in IMPORTS]
    summary = {
        "imported": sum(1 for r in results if r.get("status") == "ok"),
        "missing": sum(1 for r in results if r.get("status") == "missing"),
        "results": results,
    }
    (REF / "import_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
