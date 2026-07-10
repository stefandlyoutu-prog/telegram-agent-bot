#!/usr/bin/env python3
"""Запуск рекламы «осознанность через боль»: админу + все promo-каналы."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from oracle_bot.ads import pain_awareness_admin_report, pain_awareness_channel_v2
from oracle_bot.config import ORACLE_PROMO_CHANNELS


def _token() -> str:
    return (
        os.getenv("ORACLE_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )


def _api(token: str, method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", str(body)))
    return body["result"]


def _send(token: str, chat_id: int | str, text: str) -> None:
    _api(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
    )


def main() -> None:
    token = _token()
    if not token:
        print("FAIL: ORACLE_BOT_TOKEN не задан")
        sys.exit(1)

    admin_raw = os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")[0].strip()
    admin_id = int(admin_raw)

    channels = [c.strip().lstrip("@") for c in ORACLE_PROMO_CHANNELS if c.strip()]
    if not channels:
        channels = ["M_Topgoroskop"]

    print("Отправка отчёта админу…")
    _send(token, admin_id, pain_awareness_admin_report())

    print("Отправка рекламного поста админу…")
    preview = pain_awareness_channel_v2("preview")
    _send(token, admin_id, preview)

    ok = fail = 0
    for ch in channels:
        text = pain_awareness_channel_v2(ch)
        try:
            _api(
                token,
                "sendMessage",
                {
                    "chat_id": f"@{ch}",
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            print(f"OK  @{ch}")
            ok += 1
        except Exception as e:
            print(f"FAIL @{ch}: {e}")
            fail += 1

    print(f"\nГотово: каналы {ok}/{len(channels)}, ошибок {fail}")
    print(f"Ссылка для рекламы: https://t.me/MOracul_bot?start=src_awareness")


if __name__ == "__main__":
    main()
