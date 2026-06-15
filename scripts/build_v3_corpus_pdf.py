#!/usr/bin/env python3
"""PDF-превью корпуса v3 (без 3MF)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.hybrid_v3_figure8_corpus import build_v3_corpus_pdf, default_figure8_spec

    out = Path("/Users/polzovatel/Downloads/figure8-corpus-v3-preview.pdf")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser().resolve()
    spec = default_figure8_spec()
    data = build_v3_corpus_pdf(spec)
    out.write_bytes(data)
    print(f"OK: {out} ({len(data)//1024} KB) spec={spec.to_dict()}")


if __name__ == "__main__":
    main()
