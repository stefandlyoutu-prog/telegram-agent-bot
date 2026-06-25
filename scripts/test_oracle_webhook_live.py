#!/usr/bin/env python3
"""Smoke: прод moracul отвечает на /ping через webhook (правила №1–8)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BASE = os.getenv("ORACLE_WEBAPP_URL", "https://moracul.onrender.com").rstrip("/")
ADMIN = int((os.getenv("MONEY_ADMIN_IDS") or "0").split(",")[0])


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def main() -> int:
    print("=== Oracle webhook live test ===")
    health = _get(f"{BASE}/health")
    print("health:", health)
    if not health.get("bot_ready"):
        print("FAIL: bot_ready=false")
        return 1
    if health.get("mode") != "webhook_sync":
        print("WARN: expected mode=webhook_sync, got", health.get("mode"))

    uid = int(time.time())
    payload = {
        "update_id": uid,
        "message": {
            "message_id": uid,
            "date": uid,
            "chat": {"id": ADMIN, "type": "private"},
            "from": {"id": ADMIN, "is_bot": False, "first_name": "QA"},
            "text": "/ping",
            "entities": [{"offset": 0, "length": 5, "type": "bot_command"}],
        },
    }
    t0 = time.time()
    resp = _post(f"{BASE}/webhook", payload)
    elapsed = time.time() - t0
    print(f"webhook: {resp} in {elapsed:.2f}s")
    if not resp.get("ok"):
        print("FAIL: webhook not ok")
        return 1
    if elapsed < 0.3:
        print("WARN: webhook too fast — feed_update may not have run")
    print("OK: check Telegram for pong from @MOracul_bot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
