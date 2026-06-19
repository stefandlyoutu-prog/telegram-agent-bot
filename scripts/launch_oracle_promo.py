#!/usr/bin/env python3
"""Запуск промо @MOracul_bot: профиль бота, прогрев, пост в канал, рассылка."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from oracle_bot.config import ORACLE_PROMO_CHANNELS
from oracle_bot.promo import post_for_channel, post_launch_broadcast, warmup_post_for_channel


def _token() -> str:
    return (
        os.getenv("ORACLE_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", str(body)))
    return body["result"]


def setup_bot_profile(token: str) -> None:
    _api(
        token,
        "setMyDescription",
        {
            "description": (
                "🔮 m-Oracul — Таро, гороскоп на сегодня, совместимость, ладонь по фото. "
                "15+ разделов. Бесплатно каждый день · Premium через Telegram Stars."
            )
        },
    )
    _api(
        token,
        "setMyShortDescription",
        {"short_description": "Гадания и советы · бесплатно + Stars"},
    )
    _api(
        token,
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Меню оракула"},
                {"command": "premium", "description": "Premium 30 дней"},
                {"command": "ref", "description": "Пригласить друга"},
            ]
        },
    )
    print("OK  bot profile updated")


def post_channel(token: str, username: str, text: str, *, pin: bool = False) -> int:
    u = username.strip().lstrip("@")
    msg = _api(
        token,
        "sendMessage",
        {
            "chat_id": f"@{u}",
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
    )
    mid = int(msg["message_id"])
    if pin:
        _api(token, "pinChatMessage", {"chat_id": f"@{u}", "message_id": mid, "disable_notification": True})
    print(f"OK  posted to @{u} message_id={mid}")
    return mid


def check_channel(token: str, username: str) -> dict:
    u = username.strip().lstrip("@")
    me = int(_api(token, "getMe")["id"])
    member = _api(token, "getChatMember", {"chat_id": f"@{u}", "user_id": me})
    status = member.get("status", "")
    is_admin = status in ("administrator", "creator")
    return {
        "username": u,
        "status": status,
        "can_post": bool(member.get("can_post_messages", is_admin)),
    }


def launch_on_render(base_url: str, admin_id: int) -> dict:
    url = base_url.rstrip("/") + "/api/admin/launch-promo"
    payload = json.dumps(
        {
            "user_id": admin_id,
            "channels": [],
            "broadcast": True,
            "channel_posts": 1,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main() -> None:
    p = argparse.ArgumentParser(description="Promo launch for @MOracul_bot")
    p.add_argument("--warmup", action="store_true", help="Post warmup (no bot link)")
    p.add_argument("--warmup-day", type=int, default=1, help="Warmup day 1-3")
    p.add_argument("--promo", action="store_true", help="Post channel promo with deep-links")
    p.add_argument("--channel-only", action="store_true", help="Only post to TG channel (promo)")
    p.add_argument("--pin", action="store_true", help="Pin promo post")
    p.add_argument("--render", action="store_true", help="Call Render /api/admin/launch-promo")
    p.add_argument("--skip-profile", action="store_true")
    p.add_argument("--delay", type=float, default=2.0, help="Pause between channel posts")
    args = p.parse_args()

    token = _token()
    if not token:
        print("FAIL ORACLE_BOT_TOKEN missing", file=sys.stderr)
        sys.exit(1)

    admin_id = int(os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")[0])
    channels = list(ORACLE_PROMO_CHANNELS) or ["M_Topgoroskop"]
    render_url = os.getenv("ORACLE_WEBAPP_URL", "https://moracul.onrender.com").strip()

    if not args.skip_profile:
        setup_bot_profile(token)

    do_warmup = args.warmup or (not args.promo and not args.render and not args.channel_only)
    do_promo = args.promo or args.channel_only

    if do_warmup:
        print(f"=== Warmup day {args.warmup_day} ===")
        for ch in channels:
            try:
                st = check_channel(token, ch)
                if not st["can_post"]:
                    print(f"SKIP warmup @{st['username']}")
                    continue
                text = warmup_post_for_channel(st["username"], day=args.warmup_day)
                post_channel(token, st["username"], text)
                time.sleep(args.delay)
            except Exception as e:
                print(f"FAIL warmup @{ch}: {e}")

    if do_promo:
        print("=== Promo (deep-links) ===")
        for ch in channels:
            try:
                st = check_channel(token, ch)
                if not st["can_post"]:
                    print(f"SKIP promo @{st['username']}")
                    continue
                text = post_for_channel(st["username"])
                post_channel(token, st["username"], text, pin=args.pin)
                time.sleep(args.delay)
            except Exception as e:
                print(f"FAIL promo @{ch}: {e}")

    if args.render:
        try:
            result = launch_on_render(render_url, admin_id)
            print("OK  render launch-promo:", json.dumps(result, ensure_ascii=False)[:500])
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"WARN render launch: HTTP {e.code} {body}")
        except Exception as e:
            print(f"WARN render launch: {e}")

    if not do_warmup and not do_promo and not args.render:
        print("Использование:")
        print("  python3 scripts/launch_oracle_promo.py --warmup          # прогрев без ссылки")
        print("  python3 scripts/launch_oracle_promo.py --promo --pin     # реклама + закреп")
        print("  python3 scripts/launch_oracle_promo.py --warmup --promo  # прогрев и реклама")


if __name__ == "__main__":
    main()
