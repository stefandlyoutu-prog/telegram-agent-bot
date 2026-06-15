#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from bot.services.dacha_products_proposal import PRODUCTS, TUBE, write_proposal

    out = Path("/Users/polzovatel/Downloads/dacha-products-proposal.pdf")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser()
    write_proposal(out)
    print(f"OK: {out} ({out.stat().st_size // 1024} KB)")
    print(f"Труба: {TUBE.sticks}×{TUBE.length_cm}см = {TUBE.price_rub:.0f}₽ → {TUBE.rub_per_stick:.0f}₽/хлыст")
    for p in PRODUCTS:
        print(f"  {p.id}: себест {p.cogs():.0f}₽ → продажа {p.sell_rub[0]:.0f}-{p.sell_rub[1]:.0f}₽")


if __name__ == "__main__":
    main()
