"""
Re-register all dwg_* kits in data/reference_models/library_index.json.

  - removes any stale dwg_* entries whose folder no longer exists,
  - re-scans data/reference_models/dwg_*/manifest.json,
  - infers category + keywords from the title,
  - sets max_part_dim_mm from bbox_mm,
  - leaves every other kit unchanged.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference_models"
INDEX = REF / "library_index.json"


def _category_from_title(t: str) -> str:
    s = t.lower()
    if any(w in s for w in ("компрессор", "kompressor", "atlas", "kopko",
                              "копко", "atlas copko")):
        return "compressor_reference"
    if any(w in s for w in ("задвижк", "zadvizhk", "затвор", "клапан",
                              "valve", "ду50", "ду100", "ду150", "du100")):
        return "valve_reference"
    if any(w in s for w in ("вентилятор", "ventilyator", "fan ")):
        return "fan_reference"
    if any(w in s for w in ("компонент", "danfoss", "данфосс", "болт",
                              "гайка", "шайб", "профил")):
        return "fastener_reference"
    if any(w in s for w in ("мебель", "furniture", "стул", "стол", "shkaf",
                              "shkaf", "офисн")):
        return "furniture_reference"
    if any(w in s for w in ("дерев", "tree", "derev")):
        return "tree_reference"
    if any(w in s for w in ("человек", "людей", "лиц", "chelovek", "human",
                              "people", "figur")):
        return "human_figure_reference"
    if any(w in s for w in ("авто", "автомобил", "vehicle", "грузовик",
                              "kenworth", "тягач", "tyagach", "kamaz",
                              "военн")):
        return "vehicle_reference"
    if any(w in s for w in ("самолет", "самолёт", "plane", "космич")):
        return "aircraft_reference"
    if any(w in s for w in ("шашк", "damas", "шахмат", "chess")):
        return "boardgame_reference"
    if any(w in s for w in ("pelco", "cctv", "видеонаблюд", "kamera",
                              "камер")):
        return "cctv_reference"
    if any(w in s for w in ("экзотическ", "техник", "tekhnik")):
        return "industrial_reference"
    if any(w in s for w in ("архитектор", "архитектур", "блок", "двер",
                              "окн", "fasad", "interior",
                              "ландшафт", "маф")):
        return "architecture_reference"
    if any(w in s for w in ("организ", "бокс", "лоток", "ящик", "polkа",
                              "exhibidor", "cajita", "gabetero", "bandeja")):
        return "container_reference"
    if any(w in s for w in ("цок", "бункер", "tsok", "хранилищ")):
        return "industrial_reference"
    if any(w in s for w in ("чаша", "генуя", "сантех", "papel", "porta")):
        return "plumbing_reference"
    return "dwg_reference"


def _keywords_from_title(t: str) -> list[str]:
    tokens = re.findall(r"[А-Яа-яA-Za-z0-9]{3,}", t)
    stop = {
        "Acad", "DWG", "формат", "файл", "файлы", "масштаб", "модель",
        "разные", "разных",
    }
    out: list[str] = []
    for tok in tokens:
        if len(out) >= 8:
            break
        if tok in stop or tok.lower() in {"the", "and", "for"}:
            continue
        out.append(tok.lower())
    return out


def main() -> int:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    kits = idx["kits"]

    # 1) Drop any dwg_* entry whose folder is gone OR which has a colliding
    #    old slug we replaced.
    kept: list[dict] = []
    dropped = 0
    for k in kits:
        if not k["slug"].startswith("dwg_"):
            kept.append(k)
            continue
        if (REF / k["slug"]).is_dir():
            kept.append(k)
        else:
            dropped += 1
    print(f"  dropped {dropped} stale dwg_ entries")

    existing_slugs = {k["slug"] for k in kept}

    # 2) Add every dwg_*/manifest.json that is not already present.
    added = 0
    for d in sorted(REF.glob("dwg_*")):
        if not d.is_dir():
            continue
        if d.name in existing_slugs:
            # Already present — refresh maxdim/category if needed
            mm = d / "manifest.json"
            if not mm.exists():
                continue
            m = json.loads(mm.read_text(encoding="utf-8"))
            bbox = m.get("bbox_mm") or []
            maxdim = max(bbox) if bbox else None
            title = m.get("title", d.name)
            for k in kept:
                if k["slug"] == d.name:
                    k["max_part_dim_mm"] = maxdim
                    k["category"] = _category_from_title(title)
                    k["keywords"] = _keywords_from_title(title)
                    k["sample_parts"] = ["extracted_mesh.stl"]
                    k["stl_count"] = 1
                    k["bytes_zip"] = (
                        (d / "extracted_mesh.stl").stat().st_size
                        if (d / "extracted_mesh.stl").exists()
                        else 0
                    )
                    k["top_tokens"] = k["keywords"][:5]
                    k["split_style"] = "extracted_mesh"
                    break
            continue
        mm = d / "manifest.json"
        if not mm.exists():
            continue
        m = json.loads(mm.read_text(encoding="utf-8"))
        bbox = m.get("bbox_mm") or []
        maxdim = max(bbox) if bbox else None
        title = m.get("title", d.name)
        size = (
            (d / "extracted_mesh.stl").stat().st_size
            if (d / "extracted_mesh.stl").exists()
            else 0
        )
        keywords = _keywords_from_title(title)
        kept.append({
            "slug": d.name,
            "category": _category_from_title(title),
            "stl_count": 1,
            "scad_count": 0,
            "bytes_zip": size,
            "max_part_dim_mm": maxdim,
            "top_tokens": keywords[:5],
            "keywords": keywords,
            "sample_parts": ["extracted_mesh.stl"],
            "has_gear_tokens": False,
            "has_wheel_tokens": "авто" in title.lower() or "vehicle" in title.lower() or "kenworth" in title.lower(),
            "has_wing_tokens": "самолет" in title.lower() or "plane" in title.lower(),
            "split_style": "extracted_mesh",
        })
        added += 1

    idx["kits"] = kept
    print(f"  added {added} new dwg_ entries")
    print(f"  total kits: {len(kept)}")

    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"  wrote {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
