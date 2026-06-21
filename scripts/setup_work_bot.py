#!/usr/bin/env python3
"""Профиль бота «Работа онлайн» в BotFather."""

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


def _api(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", str(body)))
    return body["result"]


def main() -> None:
    token = os.getenv("WORK_BOT_TOKEN", "").strip()
    if not token:
        print("FAIL: WORK_BOT_TOKEN не задан", file=sys.stderr)
        sys.exit(1)
    _api(
        token,
        "setMyDescription",
        {
            "description": (
                "💼 Задания онлайн: установки, подписки, рефералы.\n"
                "Выполняешь → сдаёшь отчёт → деньги на баланс.\n"
                "Вывод от 5 000 ₽."
            )
        },
    )
    _api(
        token,
        "setMyShortDescription",
        {"short_description": "Задания онлайн · выплаты за отчёты"},
    )
    _api(
        token,
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Начать / меню"},
                {"command": "balance", "description": "Баланс"},
                {"command": "help", "description": "Как работает"},
            ]
        },
    )
    me = _api(token, "getMe", {})
    print(f"OK @{me.get('username')} profile updated")


if __name__ == "__main__":
    main()
