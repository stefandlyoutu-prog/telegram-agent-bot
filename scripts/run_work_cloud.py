#!/usr/bin/env python3
"""Работа онлайн: webhook на Render."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WORK_CLOUD", "1")


def main() -> None:
    port = int(os.getenv("PORT", "8790"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Work Online cloud: http://{host}:{port}/")
    uvicorn.run("work_bot.webapp:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
