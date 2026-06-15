#!/usr/bin/env python3
"""Настройка интеграций через API (без логина на сайты)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import os

from business_dashboard.storage import init_db, set_user_asset, update_idea_fields, update_status


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def setup_oracle_bot() -> dict:
    token = os.getenv("ORACLE_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "ORACLE_BOT_TOKEN missing"}

    me = _api(token, "getMe")
    username = me.get("result", {}).get("username", "")

    _api(
        token,
        "setMyDescription",
        {
            "description": (
                "🔮 m-Oracul — расклады Таро, совместимость по датам, "
                "хиромантия по фото ладони и советы по отношениям. "
                "Премиум — Telegram Stars."
            )
        },
    )
    _api(
        token,
        "setMyShortDescription",
        {"short_description": "Гадания и советы · Stars-подписка"},
    )
    _api(
        token,
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Меню оракула"},
                {"command": "premium", "description": "Премиум 30 дней"},
            ]
        },
    )

    stars_ok = False
    try:
        inv = _api(
            token,
            "createInvoiceLink",
            {
                "title": "Оракул Премиум",
                "description": "Безлимит 30 дней",
                "payload": "premium_30d",
                "currency": "XTR",
                "prices": [{"label": "30 дней", "amount": 99}],
            },
        )
        stars_ok = inv.get("ok", False)
    except urllib.error.HTTPError:
        stars_ok = False

    init_db()
    for key, note in {
        "email": "morozov.stepan.dme@yandex.ru",
        "samozanyatost": "Мой налог",
        "botfather": f"@{username}",
        "yandex_partner": "browser + distribution",
    }.items():
        set_user_asset(key, True, note=note)
    if stars_ok:
        set_user_asset("telegram_stars", True, note="XTR invoice OK")

    bot_link = f"https://t.me/{username}" if username else ""
    update_status("oracle-platform", "running")
    update_idea_fields(
        "oracle-platform",
        note=f"Бот {bot_link} · Stars={'да' if stars_ok else 'нет'}",
        action_required="Продвижение: Shorts/TG-канал → @MOracul_bot",
    )
    update_status("yandex-browser-partner", "connected")
    update_status("yandex-distribution", "connected")

    return {
        "ok": True,
        "username": username,
        "stars": stars_ok,
        "bot_link": bot_link,
    }


def main() -> None:
    admin = os.getenv("MONEY_ADMIN_IDS", "")
    print("=== Setup integrations ===")
    print(f"MONEY_ADMIN_IDS: {admin or '(не задан)'}")
    result = setup_oracle_bot()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        sys.exit(1)
    print("\nЗапуск: python3 scripts/run_oracle_bot.py")


if __name__ == "__main__":
    main()
