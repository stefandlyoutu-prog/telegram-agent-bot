#!/usr/bin/env python3
"""Полный архив: 4 дачных набора + бизнес-PDF + ZIP."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.dacha_full_pack import build_full_archive

    out = Path("/Users/polzovatel/Downloads/dacha-kits-full-v2")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser()
    zip_path = build_full_archive(out)
    print(f"OK folder: {out}")
    print(f"OK zip:    {zip_path} ({zip_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
