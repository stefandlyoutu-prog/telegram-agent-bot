from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[1].parent / "m-money-hub" / ".env")

VIDEO_BOT_TOKEN = os.getenv("MONEY_BOT_TOKEN_2", os.getenv("WORK_BOT_TOKEN_2", "")).strip()
VIDEO_BOT_USERNAME = os.getenv("MONEY_BOT_USERNAME_2", "M_twotest_bot").strip().lstrip("@")
VIDEO_DATA_DIR = Path(
    os.getenv("VIDEO_BOT_DATA", str(Path(__file__).resolve().parents[1] / "data" / "video_bot"))
)
VIDEO_ADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")
    if x.strip().isdigit()
}
