#!/usr/bin/env python3
"""Собрать полный ZIP v1+v2 для гибридного генератора."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> None:
    from bot.services.hybrid_generator import build_hybrid_generator_print_pack

    out = Path("/Users/polzovatel/Downloads/hybrid-generator-full-pack.zip")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser().resolve()

    data, name, n_parts, has_3mf = await build_hybrid_generator_print_pack(
        {"printer": "Bambu Lab P2S", "material": "PETG", "nozzle_mm": 0.4},
        frames=None,
    )
    out.write_bytes(data)
    print(f"OK: {out} ({len(data)//1024} KB, {n_parts} parts, 3mf={has_3mf})")


if __name__ == "__main__":
    asyncio.run(main())
