#!/usr/bin/env python3
"""Запуск акции «бесплатный день» на проде: полный доступ + рассылка всем."""

from __future__ import annotations

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


def main() -> None:
    admin_id = int(os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")[0])
    base = os.getenv("ORACLE_WEBAPP_URL", "https://moracul.onrender.com").strip().rstrip("/")
    url = f"{base}/api/admin/free-day-start"
    payload = json.dumps({"user_id": admin_id}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = json.load(r)
        print("OK free-day-start:", json.dumps(body, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:500]
        print(f"FAIL HTTP {e.code}: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
