#!/usr/bin/env python3
"""Сборка комплекта шпалеры для дачи: PDF, 3MF, STL, Avito."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.dacha_trellis_kit import DEFAULT_SPEC, build_kit_pack

    out = Path("/Users/polzovatel/Downloads/dacha-trellis-solnechnogorsk-v2")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser().resolve()

    folder = build_kit_pack(out, DEFAULT_SPEC)
    spec = DEFAULT_SPEC
    print(f"OK: {folder}")
    print(f"  PDF: shpalera-tomat-2-instrukciya.pdf")
    print(f"  3MF: connectors-plate-1-of-2.3mf + connectors-plate-2-of-2.3mf")
    print(f"  профиль: {spec.total_profile_mm()/1000:.1f} м на комплект")
    print(f"  коннекторы: {spec.connector_counts()}")


if __name__ == "__main__":
    main()
