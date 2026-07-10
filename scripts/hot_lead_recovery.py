#!/usr/bin/env python3
"""Срочный дожим горячих лидов через prod API или локально."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def _local(limit: int) -> dict:
    from aiogram import Bot
    from oracle_bot.hot_recovery import run_hot_recovery

    token = os.environ.get("ORACLE_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("ORACLE_BOT_TOKEN не задан")
    bot = Bot(token)
    try:
        return await run_hot_recovery(bot, limit=limit)
    finally:
        await bot.session.close()


def _via_api(base: str, admin_id: int, limit: int) -> dict:
    import urllib.parse
    import urllib.request

    q = urllib.parse.urlencode({"user_id": admin_id, "limit": limit})
    url = f"{base.rstrip('/')}/api/admin/hot-recovery?{q}"
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        import json

        return json.loads(resp.read().decode())


def main() -> None:
    p = argparse.ArgumentParser(description="Hot lead recovery blast")
    p.add_argument("--local", action="store_true", help="Локально через BOT_TOKEN + SQLite")
    p.add_argument("--api", default=os.environ.get("ORACLE_SITE_URL", "https://moracul.ru"))
    p.add_argument("--admin-id", type=int, default=int(os.environ.get("MONEY_ADMIN_IDS", "5845195049").split(",")[0]))
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()
    _load_env()

    if args.local:
        result = asyncio.run(_local(args.limit))
    else:
        result = _via_api(args.api, args.admin_id, args.limit)
    print(result)


if __name__ == "__main__":
    main()
