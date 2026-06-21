from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

WORK_BOT_TOKEN = (
    os.getenv("WORK_BOT_TOKEN", "").strip()
    or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
)
WORK_BOT_USERNAME = os.getenv("WORK_BOT_USERNAME", "MoRoZovGPTchat_bot").strip()

# Доля исполнителя от вашей комиссии (1 к 10)
WORKER_SHARE = float(os.getenv("WORKER_SHARE", "0.1"))

# Минимальный вывод
MIN_WITHDRAWAL_RUB = int(os.getenv("MIN_WITHDRAWAL_RUB", "5000"))

WORK_ADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv(
        "MONEY_ADMIN_IDS",
        os.getenv("WORK_ADMIN_IDS", "5845195049"),
    ).split(",")
    if x.strip().isdigit()
}

WORK_DB_PATH = Path(
    os.getenv("WORK_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "work_bot.db"))
)

WORK_PUSH_ENABLED = os.getenv("WORK_PUSH_ENABLED", "1") not in {"0", "false", "False"}
WORK_PUSH_INTERVAL_SEC = int(os.getenv("WORK_PUSH_INTERVAL_SEC", "300"))

ORACLE_BOT_USERNAME = os.getenv("ORACLE_BOT_USERNAME", "MOracul_bot").strip()
