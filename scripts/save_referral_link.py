#!/usr/bin/env python3
"""Сохранить реф. ссылку в дашборд: python3 scripts/save_referral_link.py SLUG 'https://...'"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_dashboard.storage import init_db, update_idea_fields, update_status


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: save_referral_link.py <slug> <url> [note extra]")
        sys.exit(1)
    slug, url = sys.argv[1], sys.argv[2]
    extra = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
    init_db()
    note = f"Реф. ссылка: {url}"
    if extra:
        note += f" · {extra}"
    update_idea_fields(slug, note=note, action_required="Модерация / размещение ссылки")
    update_status(slug, "connected")
    print(f"OK {slug} -> {url}")


if __name__ == "__main__":
    main()
