#!/usr/bin/env python3
"""Сарай v2: без резки (1/1.5/2 м) + IKEA PDF."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.dacha_shed_v2_nocut import DEFAULT_SHED_NOCUT, build_shed_v2_archive

    out = Path("/Users/polzovatel/Downloads/dacha-shed-3x4-v2-nocut")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser()
    zip_path = build_shed_v2_archive(out, DEFAULT_SHED_NOCUT)
    sc = DEFAULT_SHED_NOCUT.stick_counts()
    print(f"OK folder: {out}")
    print(f"OK zip:    {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    print(f"Sticks: 200cm×{sc[2000]} 150cm×{sc[1500]} 100cm×{sc[1000]}")
    print(f"IKEA PDF:  {out / 'instrukciya-IKEA.pdf'}")


if __name__ == "__main__":
    main()
