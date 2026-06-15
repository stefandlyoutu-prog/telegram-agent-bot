#!/usr/bin/env python3
"""Запуск локального дашборда «Центр доходов»."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Дашборд бизнес-идей")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Не открывать браузер")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    if not args.no_open:
        webbrowser.open(url)

    print(f"Центр доходов: {url}")
    uvicorn.run(
        "business_dashboard.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
