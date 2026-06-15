#!/usr/bin/env python3
"""Ночной отчёт — добавить в cron: 0 0 * * * python3 scripts/close_day_report.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from business_dashboard.daily import close_day_report
from business_dashboard.storage import init_db, rollover_day_if_needed


def main() -> None:
    init_db()
    rollover_day_if_needed()
    report = close_day_report()
    print(f"Отчёт {report['report_date']}: план {report['expected_total']:.0f} → факт {report['actual_total']:.0f} ₽")
    print(report["gap_reason"])


if __name__ == "__main__":
    main()
