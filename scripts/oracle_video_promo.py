#!/usr/bin/env python3
"""Автопостинг рекламных роликов @MOracul_bot.

Один логин — план на месяц — N роликов в день — трафик в Telegram — атрибуция.

Команды:
  plan     — составить план на месяц (сколько роликов в день по площадкам)
  list     — показать ролики к выпуску (на сегодня или дату)
  render   — сгенерировать ролики к выпуску в data/video_bot/promo/out/<дата>/
  post-tg  — выложить готовые ролики в Telegram-канал (мгновенный трафик)
  report   — атрибуция: какой источник качает подписчиков/оплаты (локальная БД)

Примеры:
  python3 scripts/oracle_video_promo.py plan --days 30 --tiktok 2 --youtube 2 --telegram 1
  python3 scripts/oracle_video_promo.py render --limit 5
  python3 scripts/oracle_video_promo.py post-tg --channel @M_Topgoroskop
  python3 scripts/oracle_video_promo.py report --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from video_bot.promo import oracle_promo as op  # noqa: E402


def _out_dir(day: date) -> Path:
    from video_bot.config import VIDEO_DATA_DIR

    return VIDEO_DATA_DIR / "promo" / "out" / day.isoformat()


# ───────────────────────── plan ─────────────────────────
def cmd_plan(args: argparse.Namespace) -> None:
    per_day: dict[str, int] = {}
    for platform in op.PLATFORMS:
        n = getattr(args, platform, 0)
        if n:
            per_day[platform] = n
    if not per_day:
        per_day = {"tiktok": 2, "youtube": 2, "telegram": 1}
    items = op.build_month_plan(date.today(), per_day, days=args.days)
    path = op.save_plan(items)
    by_plat: dict[str, int] = {}
    for i in items:
        by_plat[i.platform] = by_plat.get(i.platform, 0) + 1
    print(f"OK  план на {args.days} дн.: {len(items)} роликов")
    for p, n in by_plat.items():
        print(f"    {p}: {n} ({per_day[p]}/день)")
    print(f"    сохранён: {path}")
    print("    пример метки:", items[0].source, "→", items[0].link)


# ───────────────────────── list ─────────────────────────
def cmd_list(args: argparse.Namespace) -> None:
    plan = op.load_plan()
    if not plan:
        print("План пуст. Сначала: plan")
        return
    on = date.fromisoformat(args.date) if args.date else date.today()
    due = op.due_items(plan, on)
    print(f"К выпуску на {on.isoformat()}: {len(due)}")
    for i in due[: args.limit or len(due)]:
        print(f"  [{i.status}] {i.platform} #{i.slot} · {i.source} · {i.topic}")


# ───────────────────────── render ─────────────────────────
def cmd_render(args: argparse.Namespace) -> None:
    plan = op.load_plan()
    if not plan:
        print("План пуст. Сначала: plan")
        return
    on = date.fromisoformat(args.date) if args.date else date.today()
    due = [i for i in op.due_items(plan, on) if i.status == "planned"]
    if args.limit:
        due = due[: args.limit]
    if not due:
        print("Нечего рендерить.")
        return
    out = _out_dir(on)
    print(f"Рендер {len(due)} роликов → {out}")

    async def _run() -> None:
        for i in due:
            try:
                path = await op.render_item(i, out, use_llm=not args.no_llm)
                i.status = "rendered"
                i.file = str(path)
                print(f"  OK  {i.source} → {path.name}")
            except Exception as e:  # noqa: BLE001
                i.status = "failed"
                i.note = str(e)[:200]
                print(f"  FAIL {i.source}: {e}")
            op.save_plan(plan)

    asyncio.run(_run())
    print("Готово. Дальше: post-tg или загрузи файлы на площадки.")


# ───────────────────────── post-tg ─────────────────────────
def _tg_api(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", str(body)))
    return body["result"]


def cmd_post_tg(args: argparse.Namespace) -> None:
    token = os.getenv("ORACLE_BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("FAIL ORACLE_BOT_TOKEN не задан", file=sys.stderr)
        sys.exit(1)
    channel = (args.channel or "").lstrip("@")
    if not channel:
        try:
            from oracle_bot.config import ORACLE_PROMO_CHANNELS

            channel = (list(ORACLE_PROMO_CHANNELS) or ["M_Topgoroskop"])[0].lstrip("@")
        except Exception:
            channel = "M_Topgoroskop"
    plan = op.load_plan()
    ready = [i for i in plan if i.status == "rendered" and i.platform in {"telegram", "tiktok", "youtube"} and i.file and Path(i.file).exists()]
    if args.limit:
        ready = ready[: args.limit]
    if not ready:
        print("Нет готовых роликов. Сначала: render")
        return
    import urllib.request as _u

    for i in ready:
        caption = (
            f"🔮 {i.topic}\n\n"
            f"Узнай свой расклад бесплатно прямо сейчас:\n{i.link}"
        )
        # multipart upload через requests, иначе Bot API
        try:
            import requests  # type: ignore

            with open(i.file, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": f"@{channel}", "caption": caption, "parse_mode": "HTML"},
                    files={"video": f},
                    timeout=300,
                )
            ok = resp.json().get("ok")
            if not ok:
                raise RuntimeError(resp.text[:200])
            i.status = "posted"
            print(f"  OK  @{channel} ← {Path(i.file).name} ({i.source})")
        except Exception as e:  # noqa: BLE001
            i.note = str(e)[:200]
            print(f"  FAIL {i.source}: {e}")
        op.save_plan(plan)


# ───────────────────────── report ─────────────────────────
def cmd_report(args: argparse.Namespace) -> None:
    try:
        from oracle_bot import storage as db

        rows = db.signups_by_source(args.days)
    except Exception as e:  # noqa: BLE001
        print(f"Локальная БД недоступна ({e}).")
        print("Используй команду /sources в самом боте — она читает прод-базу на Render.")
        return
    if not rows:
        print("Нет данных. На проде смотри /sources в боте @MOracul_bot.")
        return
    print(f"Откуда трафик (локально, за {args.days} дн.):")
    for r in rows[:30]:
        print(f"  {r['source']:>16}  чел.={r['users']:<5} оплат={r['payers']:<4} {int(r.get('rub') or 0)}₽")


def main() -> None:
    p = argparse.ArgumentParser(description="Автопостинг роликов @MOracul_bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("plan", help="составить план на месяц")
    sp.add_argument("--days", type=int, default=30)
    for platform in op.PLATFORMS:
        sp.add_argument(f"--{platform}", type=int, default=0, help=f"роликов в день: {platform}")
    sp.set_defaults(func=cmd_plan)

    sl = sub.add_parser("list", help="ролики к выпуску")
    sl.add_argument("--date")
    sl.add_argument("--limit", type=int, default=0)
    sl.set_defaults(func=cmd_list)

    sr = sub.add_parser("render", help="сгенерировать ролики")
    sr.add_argument("--date")
    sr.add_argument("--limit", type=int, default=0)
    sr.add_argument("--no-llm", action="store_true", help="без Gemini (fallback-сценарий)")
    sr.set_defaults(func=cmd_render)

    spt = sub.add_parser("post-tg", help="выложить готовые ролики в Telegram-канал")
    spt.add_argument("--channel")
    spt.add_argument("--limit", type=int, default=0)
    spt.set_defaults(func=cmd_post_tg)

    srep = sub.add_parser("report", help="атрибуция трафика")
    srep.add_argument("--days", type=int, default=30)
    srep.set_defaults(func=cmd_report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
