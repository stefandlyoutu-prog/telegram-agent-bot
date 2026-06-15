#!/usr/bin/env python3
"""Mini App m-Oracul (нужен HTTPS для Telegram — ngrok / Render)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    args = p.parse_args()
    print(f"m-Oracul WebApp: http://{args.host}:{args.port}/")
    print("Для Telegram задай ORACLE_WEBAPP_URL=https://... в .env")
    uvicorn.run("oracle_bot.webapp:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
