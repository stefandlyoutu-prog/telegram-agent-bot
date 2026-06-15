#!/usr/bin/env python3
"""Проверка корпуса «8»: shell + финальные STL (с шип-пазом)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from bot.services.figure8_tube_mesh import (
        build_figure8_tube_shell,
        verify_figure8_channel,
        verify_figure8_dimensions,
        verify_figure8_part_mesh,
    )
    from bot.services.hybrid_v3_figure8_corpus import Figure8CorpusSpec, build_v3_part_mesh

    spec = Figure8CorpusSpec()
    la, rb, wall, hh = (
        spec.lemniscate_a_mm,
        spec.tube_bore_radius_mm,
        spec.wall_mm,
        spec.half_height_mm,
    )

    lower = build_figure8_tube_shell(
        lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=False
    )
    upper = build_figure8_tube_shell(
        lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=True
    )

    for label, ok, msg in [
        ("dimensions", *verify_figure8_dimensions(
            lower, upper, half_h=hh, channel_diameter_mm=spec.channel_diameter_mm
        )),
        ("channel", *verify_figure8_channel(
            lower, upper, lemniscate_a=la, r_bore=rb, half_h=hh
        )),
    ]:
        if not ok:
            print(f"FAIL {label}: {msg}")
            return 1

    for pid in ("fig8_body_lower", "fig8_body_upper"):
        mesh = build_v3_part_mesh(pid, spec)
        ok, msg = verify_figure8_part_mesh(mesh, part_name=pid, half_h=hh)
        if not ok:
            print(f"FAIL part {pid}: {msg}")
            return 1
        stl_len = len(mesh.export(file_type="stl"))
        print(f"OK {pid}: vol={mesh.volume:.0f} stl={stl_len // 1024}KB verts={len(mesh.vertices)}")

    print("OK figure8 corpus (shell + parts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
