#!/usr/bin/env python3
"""ZIP v3: OpenSCAD/STL/3MF + PDF для корпуса «восьмёрки»."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> None:
    from bot.services.hybrid_v3_figure8_corpus import V4_PACK_FILENAME, build_v3_print_pack, default_figure8_spec

    out = Path.home() / "Downloads" / V4_PACK_FILENAME
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser().resolve()
    spec = default_figure8_spec()
    data, filename, n_parts, has_3mf = await build_v3_print_pack()
    out.write_bytes(data)
    print(f"OK: {out} ({len(data)//1024} KB) parts={n_parts} 3mf={has_3mf} spec={spec.to_dict()}")


if __name__ == "__main__":
    asyncio.run(main())
