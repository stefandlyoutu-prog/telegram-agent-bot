from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ORACLE_BOT_TOKEN = os.getenv("ORACLE_BOT_TOKEN", "").strip()
ORACLE_BOT_USERNAME = os.getenv("ORACLE_BOT_USERNAME", "MOracul_bot").strip()
ORACLE_PREMIUM_STARS = int(os.getenv("ORACLE_PREMIUM_STARS", "99"))
ORACLE_DEEP_STARS = int(os.getenv("ORACLE_DEEP_STARS", "29"))
# Оплата звёздами выключена по умолчанию — приём только в рублях (Робокасса).
# Чтобы вернуть Stars, выстави ORACLE_STARS_ENABLED=1
ORACLE_STARS_ENABLED = os.getenv("ORACLE_STARS_ENABLED", "0").strip() in {"1", "true", "True"}
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
ORACLE_FREE_DAY_REPORT = os.getenv("ORACLE_FREE_DAY_REPORT", "1") not in {
    "0",
    "false",
    "False",
}
ORACLE_FREE_DAY_REPORT_HOUR_MSK = int(os.getenv("ORACLE_FREE_DAY_REPORT_HOUR_MSK", "0"))
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

# Реквизиты исполнителя (самозанятый) — на сайте и в боте
ORACLE_SELFEMPLOYED_NAME = os.getenv(
    "ORACLE_SELFEMPLOYED_NAME", "Морозов Степан Юрьевич"
).strip()
ORACLE_SELFEMPLOYED_INN = os.getenv("ORACLE_SELFEMPLOYED_INN", "615108112390").strip()


def self_employed_requisites_plain() -> str:
    return (
        f"Самозанятый: {ORACLE_SELFEMPLOYED_NAME}\n"
        f"ИНН: {ORACLE_SELFEMPLOYED_INN}"
    )


def self_employed_requisites_html() -> str:
    return (
        f"Самозанятый: <b>{ORACLE_SELFEMPLOYED_NAME}</b>\n"
        f"ИНН: <b>{ORACLE_SELFEMPLOYED_INN}</b>"
    )


# ───────────────────────── Робокасса (оплата картой/СБП в рублях) ─────────────
ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN", "").strip()
ROBOKASSA_PASSWORD1 = os.getenv("ROBOKASSA_PASSWORD1", "").strip()
ROBOKASSA_PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2", "").strip()
# 1 = тестовый режим Робокассы (без реальных списаний)
ROBOKASSA_TEST = os.getenv("ROBOKASSA_TEST", "0").strip() in {"1", "true", "True"}
# Алгоритм подписи: md5 (по умолчанию), sha256, sha512 — как в настройках магазина
ROBOKASSA_HASH = os.getenv("ROBOKASSA_HASH", "md5").strip().lower()
# Тариф продолжения в рублях (премиум — ORACLE_PREMIUM_PRICE_RUB выше)
ORACLE_DEEP_PRICE_RUB = int(os.getenv("ORACLE_DEEP_PRICE_RUB", "99"))


def robokassa_configured() -> bool:
    return bool(ROBOKASSA_LOGIN and ROBOKASSA_PASSWORD1 and ROBOKASSA_PASSWORD2)


def public_base_url() -> str:
    """Публичный HTTPS-адрес сервиса (для Robokassa Result/Success URL)."""
    base = (
        os.getenv("ORACLE_WEBHOOK_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or ORACLE_WEBAPP_URL
    )
    return base.rstrip("/")


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
