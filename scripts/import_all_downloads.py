#!/usr/bin/env python3
"""Import every ZIP/RAR/7z from ~/Downloads into data/reference_models/."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference_models"
DOWNLOADS = Path.home() / "Downloads"


def slug_from_name(name: str) -> str:
    base = Path(name).stem.lower()
    base = re.sub(r"20\d{6,}[-_]?\d*", "", base)
    base = re.sub(r"[^a-z0-9]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return (base[:72] or "unnamed_kit").strip("_")


def import_archive(path: Path) -> dict:
    slug = slug_from_name(path.name)
    out = REF / slug
    if out.exists() and (out / "manifest.json").is_file():
        try:
            prev = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            if prev.get("source_zip") == str(path) and prev.get("stl_count", 0) > 0:
                return {**prev, "status": "skipped_existing"}
        except Exception:
            pass
    out.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(out)
    else:
        return {"slug": slug, "status": "unsupported_ext", "source": str(path)}
    stls = list(out.rglob("*.stl"))
    scad = list(out.rglob("*.scad"))
    manifest = {
        "slug": slug,
        "status": "ok",
        "source_zip": str(path),
        "bytes": path.stat().st_size,
        "stl_count": len(stls),
        "scad_count": len(scad),
        "sample_files": [str(p.relative_to(out)) for p in sorted(stls)[:16]],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    archives = sorted(
        [
            p
            for p in DOWNLOADS.iterdir()
            if p.is_file() and p.suffix.lower() in {".zip", ".rar", ".7z"}
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    results = [import_archive(p) for p in archives]
    summary = {
        "total_archives": len(archives),
        "imported": sum(1 for r in results if r.get("status") == "ok"),
        "skipped": sum(1 for r in results if r.get("status") == "skipped_existing"),
        "unsupported": sum(1 for r in results if r.get("status") == "unsupported_ext"),
        "results": results,
    }
    (REF / "import_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
