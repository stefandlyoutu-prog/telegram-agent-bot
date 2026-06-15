#!/usr/bin/env python3
"""
Out-of-process CAD kit builder.

OpenCASCADE (via CadQuery) can segfault on degenerate geometry.  This worker
runs the kernel in its own process so a crash can never take down the bot —
the parent reads the return code and treats a signal death as a build failure.

Usage:
    python scripts/cad_worker.py '<json-payload>'

Payload:
    {"zip_path": "...", "specs": [{"name","generator","params"}], "material": "petg"}

Prints a single JSON line: {"ok": bool, "counts": {...}, "error": str|None}.
"""
from __future__ import annotations

# CRITICAL: import the OCCT kernel (OCP/CadQuery) *before* numpy/trimesh.
# OCP bundles its own native runtime (TBB/BLAS); if numpy/trimesh load their
# copies first, OCCT boolean/fillet ops segfault intermittently.  Importing it
# here first makes the whole worker process stable.
try:
    import cadquery as _cadquery_preload  # noqa: F401
except Exception:
    _cadquery_preload = None

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "no payload"}))
        return 1
    try:
        payload = json.loads(sys.argv[1])
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"bad payload: {exc}"}))
        return 1

    try:
        from bot.services.cad_kernel import build_kit_zip_from_specs

        counts = build_kit_zip_from_specs(
            payload["zip_path"],
            payload["specs"],
            material=payload.get("material", "petg"),
        )
        print(json.dumps({"ok": True, "counts": counts, "error": None}))
        return 0
    except Exception as exc:
        import traceback

        print(json.dumps({
            "ok": False,
            "counts": {},
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-400:],
        }))
        return 0


if __name__ == "__main__":
    sys.exit(main())
