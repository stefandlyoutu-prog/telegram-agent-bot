#!/usr/bin/env python3
"""Precompute geometry_profile.json for all reference kits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.services.reference_geometry import build_geometry_profile

REF = Path(__file__).resolve().parents[1] / "data" / "reference_models"


def main() -> None:
    ok = skip = fail = 0
    for d in sorted(REF.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        prof = build_geometry_profile(d.name, force=True)
        if prof and prof.get("part_count", 0) >= 1:
            ok += 1
        elif list(d.rglob("*.stl")):
            fail += 1
        else:
            skip += 1
    print(json.dumps({"profiles_built": ok, "failed": fail, "skipped_no_stl": skip}, indent=2))


if __name__ == "__main__":
    main()
