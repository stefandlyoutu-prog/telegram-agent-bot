#!/usr/bin/env python3
"""Код верификации Яндекс Дистрибуции в описание @MOracul_bot."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CODE = os.getenv("YANDEX_DIST_VERIFY_CODE", "gx2owa73p6vuq49y").strip()
TOKEN = os.getenv("ORACLE_BOT_TOKEN", "").strip()


def api(method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> None:
    if not TOKEN:
        print("ORACLE_BOT_TOKEN missing")
        sys.exit(1)
    desc = (
        f"🔮 m-Oracul — Таро, совместимость, ладонь, советы. "
        f"Премиум: Stars. {CODE}"
    )
    short = f"Оракул · {CODE}"
    r1 = api("setMyDescription", {"description": desc})
    r2 = api("setMyShortDescription", {"short_description": short[:120]})
    print("setMyDescription:", r1.get("ok"), r1.get("description", r1))
    print("setMyShortDescription:", r2.get("ok"))
    print("\nТеперь на distribution.yandex.ru нажми жёлтую кнопку «Подтвердить».")


if __name__ == "__main__":
    main()
