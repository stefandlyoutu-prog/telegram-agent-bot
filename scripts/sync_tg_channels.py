#!/usr/bin/env python3
"""Синхронизация прав бота во всех каналах реестра."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_dashboard.storage import init_db
from telegram_channels.storage import sync_all_tg_channels


def main() -> None:
    init_db()
    rows = sync_all_tg_channels()
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
