#!/usr/bin/env python3
"""Запуск @MOracul_bot (Оракул)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oracle_bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
