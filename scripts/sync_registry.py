#!/usr/bin/env python3
"""Явная синхронизация title/метаданных из registry (не трогает note/action пользователя)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from business_dashboard.storage import init_db, sync_registry_titles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Обновить title/channel из registry")
    args = parser.parse_args()
    init_db()
    if not args.force:
        print("Добавь --force чтобы обновить метаданные из registry")
        return
    n = sync_registry_titles(force=True)
    print(f"Обновлено записей: {n}")


if __name__ == "__main__":
    main()
