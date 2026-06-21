#!/usr/bin/env python3
"""Заполнить очередь постов каналов на неделю (5 постов/день × каналы)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from oracle_bot.channel_queue import seed_week_queue
from oracle_bot import storage as db


def main() -> None:
    p = argparse.ArgumentParser(description="Seed channel post queue for a week")
    p.add_argument("--days", type=int, default=7, help="Days ahead (default 7)")
    p.add_argument("--start", type=str, default="", help="Start date YYYY-MM-DD (default today)")
    p.add_argument("--no-replace", action="store_true", help="Keep existing pending posts")
    p.add_argument("--dry-run", action="store_true", help="Show plan size only")
    args = p.parse_args()

    db.init_db()
    start = date.fromisoformat(args.start) if args.start else date.today()

    if args.dry_run:
        from oracle_bot.promo import build_week_plan

        plan = build_week_plan(start_day=start, days=args.days)
        promo = sum(1 for r in plan if r["kind"] == "promo")
        print(json.dumps({"posts": len(plan), "promo_slots": promo, "start": start.isoformat()}, ensure_ascii=False))
        return

    result = seed_week_queue(
        start_day=start,
        days=args.days,
        replace_pending=not args.no_replace,
    )
    summary = db.channel_queue_summary()
    print(json.dumps({**result, "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
