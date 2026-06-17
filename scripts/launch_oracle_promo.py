#!/usr/bin/env python3
"""Запуск промо @MOracul_bot: профиль бота, пост в канал, рассылка пользователям."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from oracle_bot.promo import all_channel_posts, post_launch_broadcast, pick_channel_post


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
        _api(token, "pinChatMessage", {"chat_id": f"@{u}", "message_id": mid})
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
    p.add_argument("--channel-only", action="store_true", help="Only post to TG channel")
    p.add_argument("--all-posts", action="store_true", help="Post all 5 variants (one per channel run)")
    p.add_argument("--pin", action="store_true", help="Pin channel post")
    p.add_argument("--render", action="store_true", help="Call Render /api/admin/launch-promo")
    p.add_argument("--skip-profile", action="store_true")
    args = p.parse_args()

    token = _token()
    if not token:
        print("FAIL ORACLE_BOT_TOKEN missing", file=sys.stderr)
        sys.exit(1)

    admin_id = int(os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")[0])
    channels_raw = os.getenv("ORACLE_PROMO_CHANNELS", "M_Topgoroskop")
    channels = [x.strip() for x in channels_raw.split(",") if x.strip()]
    render_url = os.getenv("ORACLE_WEBAPP_URL", "https://moracul.onrender.com").strip()

    if not args.skip_profile:
        setup_bot_profile(token)

    for ch in channels:
        try:
            st = check_channel(token, ch)
            print(f"channel @{st['username']}: status={st['status']} can_post={st['can_post']}")
            if not st["can_post"]:
                print(f"SKIP @{st['username']} — добавь @MOracul_bot админом с правом постить")
                continue
        except urllib.error.HTTPError as e:
            print(f"SKIP @{ch}: {e.read().decode()[:200]}")
            continue

        posts = all_channel_posts() if args.all_posts else [pick_channel_post()]
        for i, text in enumerate(posts):
            try:
                post_channel(token, ch, text, pin=args.pin and i == 0)
            except Exception as e:
                print(f"FAIL post @{ch}: {e}")

    if args.render:
        try:
            result = launch_on_render(render_url, admin_id)
            print("OK  render launch-promo:", json.dumps(result, ensure_ascii=False)[:500])
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"WARN render launch: HTTP {e.code} {body}")
            print("     Задеплой m-oracul и повтори: python3 scripts/launch_oracle_promo.py --render")
        except Exception as e:
            print(f"WARN render launch: {e}")

    if not args.channel_only and not args.render:
        print("\nРассылка пользователям — только на сервере (БД на Render):")
        print(f"  python3 scripts/launch_oracle_promo.py --render")
        print("  или в боте: /broadcast " + post_launch_broadcast()[:40].replace("\n", " ") + "…")


if __name__ == "__main__":
    main()
