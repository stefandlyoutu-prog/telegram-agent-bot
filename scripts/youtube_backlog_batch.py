#!/usr/bin/env python3
"""Догон YouTube из oracle_plan: рендер + заливка следующих N planned.

Учитывает дневную квоту YouTube Data API (~6 uploads / 10k units).
Повторяйте скрипт ежедневно или через LaunchAgent.

Пример:
  .venv/bin/python scripts/youtube_backlog_batch.py --limit 4 --no-llm
  .venv/bin/python scripts/youtube_backlog_batch.py --limit 4 --upload-only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from video_bot.promo import oracle_promo as op  # noqa: E402
from video_bot.promo.distribute import post_youtube  # noqa: E402


def _out_dir(d: str) -> Path:
    return ROOT / "data" / "video_bot" / "promo" / "out" / d


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=4, help="сколько роликов за прогон")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--upload-only", action="store_true", help="только уже rendered")
    p.add_argument("--include-future", action="store_true", help="брать будущие даты (по умолчанию да)")
    args = p.parse_args()

    os.environ.setdefault("VIDEO_TTS_ENGINE", "edge")
    os.environ.setdefault("VIDEO_TTS_POLISH", "0")

    plan = op.load_plan()
    items = [
        i
        for i in plan
        if i.platform == "youtube"
        and i.status in ({"rendered"} if args.upload_only else {"planned", "rendered"})
    ]
    items.sort(key=lambda i: (i.date, i.slot))
    if args.limit:
        items = items[: max(0, args.limit)]
    if not items:
        print("Нечего делать (нет planned/rendered YouTube).")
        return

    print(f"Batch YouTube: {len(items)} шт. (limit={args.limit})", flush=True)
    posted = failed = 0

    async def render_one(i: op.PromoItem) -> None:
        out = _out_dir(i.date)
        path = await op.render_item(i, out, use_llm=not args.no_llm)
        i.status = "rendered"
        i.file = str(path)
        op.save_plan(plan)
        print(f"  render OK {i.source} → {path.name}", flush=True)

    for i in items:
        if i.status == "planned" and not args.upload_only:
            try:
                asyncio.run(render_one(i))
            except Exception as e:  # noqa: BLE001
                i.status = "failed"
                i.note = str(e)[:200]
                op.save_plan(plan)
                failed += 1
                print(f"  render FAIL {i.source}: {e}", flush=True)
                continue

        if i.status != "rendered" or not i.file or not Path(i.file).exists():
            print(f"  SKIP {i.source}: нет файла", flush=True)
            continue

        try:
            res = post_youtube(i)
        except Exception as e:  # noqa: BLE001
            i.status = "failed"
            i.note = str(e)[:200]
            op.save_plan(plan)
            failed += 1
            print(f"  upload EXC {i.source}: {e}", flush=True)
            if "quota" in str(e).lower() or "rateLimit" in str(e):
                print("STOP: YouTube quota/rate limit", flush=True)
                break
            continue

        i.status = res.status
        i.note = (res.url or res.error or "")[:200]
        op.save_plan(plan)
        print(f"  upload {res.status} {i.source} {res.url or res.error}", flush=True)
        if res.ok:
            posted += 1
        else:
            failed += 1
            err = (res.error or "").lower()
            if "quota" in err or "ratelimit" in err or "uploadlimit" in err:
                print("STOP: YouTube quota/rate limit", flush=True)
                break

    left = sum(1 for x in plan if x.platform == "youtube" and x.status in {"planned", "rendered", "failed"})
    print(f"DONE posted={posted} failed={failed} youtube_left={left} today={date.today()}", flush=True)
    raise SystemExit(1 if failed and not posted else 0)


if __name__ == "__main__":
    main()
