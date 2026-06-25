from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ORACLE_BOT_TOKEN = os.getenv("ORACLE_BOT_TOKEN", "").strip()
ORACLE_BOT_USERNAME = os.getenv("ORACLE_BOT_USERNAME", "MOracul_bot").strip()
ORACLE_PREMIUM_STARS = int(os.getenv("ORACLE_PREMIUM_STARS", "99"))
ORACLE_DEEP_STARS = int(os.getenv("ORACLE_DEEP_STARS", "29"))
ORACLE_FREE_PER_DAY = int(os.getenv("ORACLE_FREE_PER_DAY", "2"))
# paywall: stars (по умолчанию после эксперимента) | referral
ORACLE_PAYWALL_MODE = os.getenv("ORACLE_PAYWALL_MODE", "stars").strip().lower()
# До этой даты (YYYY-MM-DD) — referral вместо Stars (3-дневный тест)
ORACLE_PAYWALL_EXPERIMENT_UNTIL = os.getenv(
    "ORACLE_PAYWALL_EXPERIMENT_UNTIL", "2026-06-24"
).strip()
ORACLE_LLM_MODEL = os.getenv("ORACLE_LLM_MODEL", "gpt-5.4-mini").strip()
# Рефералка: бонусных чтений за приглашённого / welcome новичку
ORACLE_REFERRAL_BONUS = int(os.getenv("ORACLE_REFERRAL_BONUS", "2"))
ORACLE_REFERRAL_WELCOME = int(os.getenv("ORACLE_REFERRAL_WELCOME", "1"))
ORACLE_REFERRAL_UNLIMITED_AT = int(os.getenv("ORACLE_REFERRAL_UNLIMITED_AT", "10"))
ORACLE_PREMIUM_PRICE_RUB = int(os.getenv("ORACLE_PREMIUM_PRICE_RUB", "299"))
ORACLE_PUSH_ENABLED = os.getenv("ORACLE_PUSH_ENABLED", "1") not in {"0", "false", "False"}
ORACLE_PUSH_INTERVAL_SEC = int(os.getenv("ORACLE_PUSH_INTERVAL_SEC", "120"))
ORACLE_DAILY_REPORT = os.getenv("ORACLE_DAILY_REPORT", "1") not in {"0", "false", "False"}
ORACLE_DAILY_REPORT_HOUR_MSK = int(os.getenv("ORACLE_DAILY_REPORT_HOUR_MSK", "9"))
ORACLE_CHANNEL_POSTS_ENABLED = os.getenv("ORACLE_CHANNEL_POSTS_ENABLED", "1") not in {
    "0",
    "false",
    "False",
}
ORACLE_CHANNEL_POST_INTERVAL_SEC = int(os.getenv("ORACLE_CHANNEL_POST_INTERVAL_SEC", "90"))
ORACLE_WEBAPP_URL = os.getenv("ORACLE_WEBAPP_URL", "").strip().rstrip("/")
if not ORACLE_WEBAPP_URL:
    ORACLE_WEBAPP_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
ORACLE_COACH_SEPARATE = os.getenv("ORACLE_COACH_SEPARATE", "0") not in {"1", "true", "True"}

ORACLE_ADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv(
        "MONEY_ADMIN_IDS",
        os.getenv("ORACLE_ADMIN_IDS", "5845195049"),
    ).split(",")
    if x.strip().isdigit()
}

ORACLE_PROMO_CHANNELS: tuple[str, ...] = tuple(
    x.strip().lstrip("@")
    for x in os.getenv(
        "ORACLE_PROMO_CHANNELS",
        "M_Topgoroskop,signsvishe,auragirlss",
    ).split(",")
    if x.strip()
)


def cloud_webapp_url() -> str:
    """HTTPS URL Mini App: явный ORACLE_WEBAPP_URL или Render."""
    if ORACLE_WEBAPP_URL:
        return ORACLE_WEBAPP_URL
    base = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    return base


def oferta_url() -> str:
    explicit = os.getenv("ORACLE_OFERTA_URL", "").strip()
    if explicit:
        return explicit
    base = cloud_webapp_url()
    return f"{base}/oferta" if base else "https://moracul.onrender.com/oferta"


LOCK_MARKER = "---LOCK---"
