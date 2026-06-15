#!/usr/bin/env python3
"""Build searchable index from data/reference_models/*."""

from __future__ import annotations

import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference_models"
OUT = REF / "library_index.json"

CATEGORY_RULES: List[Tuple[str, str]] = [
    (r"airliner|boeing|747|fuselage|airplane|extra.?300|fokker|gzumwalt|turboprop|rc.?plane", "rc_aircraft"),
    (r"drone|quadcopter|hexacopter|fpv|multicopter|voyager|xpander|geprc|imura|landing.?leg", "drone_fpv"),
    (r"tank|truck|semi|jeep|willys|vehicle|chassis|wheel|gear(?!box)", "vehicle_rc"),
    (r"robot|gripper|claw|manipulator|spider|scara|arm", "robot_mechanism"),
    (r"planetarium|gearbox|gear|iris|planetary|mechanical", "mechanical_gear"),
    (r"castle|city|tower|eiffel|house|brick|riesenrad|ferris|rotating.?city|manhattan", "architecture_miniature"),
    (r"kit.?card|card.?kit", "kit_card"),
    (r"gauntlet|articulated|flexi|print.?in.?place", "articulated_wearable"),
    (r"pegboard|peg.?board|tool.?holder|spool|filament|bobine|extruder", "printer_accessory"),
    (r"basket|crate|box|container|wipes", "functional_container"),
    (r"deadpool|yoda|stitch|charizard|character|bust|pokemon", "character_sculpt"),
    (r"train|track|rail", "train_system"),
    (r"catapult|minecraft|game", "toy_mechanism"),
    (r"wind|eolienne|mill", "kinetic_decor"),
    (r"display|stand|gantry", "display_stand"),
]


def stl_bbox(path: Path) -> Optional[Tuple[float, float, float]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 84:
        return None
    if data[:5] == b"solid":
        return None
    n = struct.unpack_from("<I", data, 80)[0]
    if n <= 0 or 84 + n * 50 > len(data):
        return None
    xs, ys, zs = [], [], []
    off = 84
    for _ in range(min(n, 8000)):
        vals = struct.unpack_from("<12f", data, off)
        xs.extend(vals[0::3])
        ys.extend(vals[1::3])
        zs.extend(vals[2::3])
        off += 50
    if not xs:
        return None
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2]


def categorize(slug: str, names: str) -> str:
    blob = f"{slug} {names}"
    for pat, cat in CATEGORY_RULES:
        if re.search(pat, blob, re.I):
            return cat
    return "general_kit"


def analyze_kit(slug_dir: Path) -> Dict[str, Any]:
    slug = slug_dir.name
    stls = sorted(slug_dir.rglob("*.stl"))
    names = " ".join(p.stem for p in stls[:80])
    bboxes = [stl_bbox(p) for p in stls[:40]]
    bboxes = [b for b in bboxes if b]
    part_tokens = Counter()
    for p in stls:
        for t in tokenize(p.stem):
            part_tokens[t] += 1
    max_dim = 0.0
    if bboxes:
        max_dim = max(max(b) for b in bboxes)
    manifest_path = slug_dir / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    category = categorize(slug, names)
    keywords = sorted(set(tokenize(slug) + [t for t, _ in part_tokens.most_common(24)]))
    return {
        "slug": slug,
        "category": category,
        "stl_count": len(stls),
        "scad_count": len(list(slug_dir.rglob("*.scad"))),
        "bytes_zip": manifest.get("bytes"),
        "max_part_dim_mm": round(max_dim, 2) if max_dim else None,
        "top_tokens": [t for t, _ in part_tokens.most_common(12)],
        "keywords": keywords[:32],
        "sample_parts": [p.name for p in stls[:8]],
        "has_gear_tokens": bool(re.search(r"gear|pinion|planet|axle|bearing", names, re.I)),
        "has_wheel_tokens": bool(re.search(r"wheel|tire|tyre|rim", names, re.I)),
        "has_wing_tokens": bool(re.search(r"wing|fuselage|aileron|stabil", names, re.I)),
        "split_style": (
            "high_part_count"
            if len(stls) >= 20
            else "medium_split"
            if len(stls) >= 6
            else "low_part_count"
            if len(stls) >= 2
            else "single_body"
        ),
    }


def main() -> None:
    kits = []
    for d in sorted(REF.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if d.name in {"incraft3d"}:
            continue
        if not list(d.rglob("*.stl")) and not (d / "manifest.json").is_file():
            continue
        kits.append(analyze_kit(d))
    by_cat: Dict[str, int] = Counter(k["category"] for k in kits)
    index = {
        "kit_count": len(kits),
        "total_stl": sum(k["stl_count"] for k in kits),
        "categories": dict(by_cat),
        "kits": kits,
    }
    OUT.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"kit_count": len(kits), "categories": dict(by_cat)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
