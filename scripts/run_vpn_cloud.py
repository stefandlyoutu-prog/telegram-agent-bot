#!/usr/bin/env python3
"""VPN-бот в облаке: webhook (Render free tier)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)


def main() -> None:
    port = int(os.getenv("PORT", "8788"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"vpn_bot cloud: http://{host}:{port}/ (webhook)")
    uvicorn.run("vpn_bot.webapp:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
