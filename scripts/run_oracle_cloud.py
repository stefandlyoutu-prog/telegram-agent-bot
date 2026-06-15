#!/usr/bin/env python3
"""Оракул в облаке: Mini App + webhook (Render free tier)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Облачный режим: webhook вместо polling, URL из Render
os.environ.setdefault("ORACLE_CLOUD", "1")


def main() -> None:
    port = int(os.getenv("PORT", "8787"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"m-Oracul cloud: http://{host}:{port}/ (webhook + Mini App)")
    uvicorn.run("oracle_bot.webapp:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
