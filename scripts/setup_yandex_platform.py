#!/usr/bin/env python3
"""Площадка для Яндекс Дистрибуции (Telegraph) + обновление дашборда."""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_dashboard.storage import init_db, update_idea_fields, update_status

PLATFORM_URL = os.getenv("YANDEX_PLATFORM_URL", "https://t.me/M_Topgoroskop").strip()
PLATFORM_USERNAME = os.getenv("YANDEX_PLATFORM_USERNAME", "M_Topgoroskop").strip()
VERIFY_CODE = "gx2owa73p6vuq49y"
DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "yandex_platform.json"


def main() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(
            {
                "platform_url": PLATFORM_URL,
                "verify_code": VERIFY_CODE,
                "platform_type": "telegram_channel",
                "bot": "https://t.me/MOracul_bot",
                "note": "Код gx2owa73p6vuq49y — в описание канала @M_Topgoroskop",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    init_db()
    update_idea_fields(
        "yandex-browser-partner",
        note=f"Площадка: {PLATFORM_URL} · код на странице · бот @MOracul_bot",
        action_required="Код в описании @M_Topgoroskop → Подтвердить в Дистрибуции",
    )
    update_status("yandex-browser-partner", "connected")
    print(PLATFORM_URL)
    print("OK dashboard +", DATA_FILE)


if __name__ == "__main__":
    main()
