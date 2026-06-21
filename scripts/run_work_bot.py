#!/usr/bin/env python3
"""Локальный запуск @WorkOnline bot (polling)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from work_bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
