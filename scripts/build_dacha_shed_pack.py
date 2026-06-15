#!/usr/bin/env python3
"""Сборка архива сарая 3×4 односкат в Downloads."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.dacha_shed_kit import DEFAULT_SHED, build_shed_archive

    out = Path("/Users/polzovatel/Downloads/dacha-shed-3x4-v1")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser()
    zip_path = build_shed_archive(out, DEFAULT_SHED)
    print(f"OK folder: {out}")
    print(f"OK zip:    {zip_path} ({zip_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
