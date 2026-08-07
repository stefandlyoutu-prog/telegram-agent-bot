"""Настройки VPN-бота: токен, тарифы, доступ к панели Marzban, Робокасса."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

VPN_BOT_TOKEN = os.getenv("VPN_BOT_TOKEN", "").strip()
VPN_BOT_USERNAME = os.getenv("VPN_BOT_USERNAME", "").strip()

VPN_ADMIN_IDS: set[int] = {
    int(x.strip())
    for raw in (os.getenv("MONEY_ADMIN_IDS", ""), os.getenv("VPN_ADMIN_IDS", ""))
    for x in raw.split(",")
    if x.strip().isdigit()
}

VPN_DB_PATH = os.getenv("VPN_DB_PATH", "").strip() or str(
    Path(__file__).resolve().parents[1] / "data" / "vpn_bot.db"
)

# ── Брендинг (аналог «Sirius VPN бот» / новости / помощь) ──
VPN_BRAND_NAME = os.getenv("VPN_BRAND_NAME", "Наш VPN").strip()
VPN_NEWS_CHANNEL = os.getenv("VPN_NEWS_CHANNEL", "").strip().lstrip("@")
VPN_HELP_CONTACT = os.getenv("VPN_HELP_CONTACT", "").strip().lstrip("@")

# ── Панель Marzban (Xray VLESS+Reality нода) ──
MARZBAN_BASE_URL = os.getenv("MARZBAN_BASE_URL", "").strip().rstrip("/")
MARZBAN_USERNAME = os.getenv("MARZBAN_USERNAME", "").strip()
MARZBAN_PASSWORD = os.getenv("MARZBAN_PASSWORD", "").strip()
# Тег(и) инбаунда(ов), которые выдаём новым пользователям, через запятую.
# Смотри в дашборде Marzban → Node Settings → Inbounds (напр. "VLESS TCP REALITY").
MARZBAN_INBOUNDS: tuple[str, ...] = tuple(
    x.strip() for x in os.getenv("MARZBAN_INBOUNDS", "VLESS TCP REALITY").split(",") if x.strip()
)


def marzban_configured() -> bool:
    return bool(MARZBAN_BASE_URL and MARZBAN_USERNAME and MARZBAN_PASSWORD)


# ── Тарифы ──
# Формат VPN_TARIFFS: JSON-список [{"id":"m1","days":30,"price_rub":199,"title":"1 месяц"}, ...]
# Если не задан — используются тарифы по умолчанию ниже.
_DEFAULT_TARIFFS = [
    {"id": "m1", "title": "1 месяц", "days": 30, "price_rub": 199},
    {"id": "m3", "title": "3 месяца", "days": 90, "price_rub": 499},
    {"id": "m12", "title": "12 месяцев", "days": 365, "price_rub": 1499},
]


def _load_tariffs() -> list[dict]:
    raw = os.getenv("VPN_TARIFFS", "").strip()
    if not raw:
        return _DEFAULT_TARIFFS
    try:
        data = json.loads(raw)
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return _DEFAULT_TARIFFS


VPN_TARIFFS: list[dict] = _load_tariffs()


def get_tariff(tariff_id: str) -> dict | None:
    for t in VPN_TARIFFS:
        if t["id"] == tariff_id:
            return t
    return None


VPN_TRIAL_DAYS = int(os.getenv("VPN_TRIAL_DAYS", "3"))
VPN_TRIAL_ENABLED = os.getenv("VPN_TRIAL_ENABLED", "1") not in {"0", "false", "False"}

# Лимит трафика на пользователя в байтах (0 = безлимит). По умолчанию безлимит.
VPN_DATA_LIMIT_BYTES = int(os.getenv("VPN_DATA_LIMIT_BYTES", "0"))

# ── Робокасса (своя, может отличаться от oracle_bot) ──
VPN_ROBOKASSA_LOGIN = os.getenv("VPN_ROBOKASSA_LOGIN", "").strip()
VPN_ROBOKASSA_PASSWORD1 = os.getenv("VPN_ROBOKASSA_PASSWORD1", "").strip()
VPN_ROBOKASSA_PASSWORD2 = os.getenv("VPN_ROBOKASSA_PASSWORD2", "").strip()
VPN_ROBOKASSA_TEST_PASSWORD1 = os.getenv("VPN_ROBOKASSA_TEST_PASSWORD1", "").strip()
VPN_ROBOKASSA_TEST_PASSWORD2 = os.getenv("VPN_ROBOKASSA_TEST_PASSWORD2", "").strip()
VPN_ROBOKASSA_TEST = os.getenv("VPN_ROBOKASSA_TEST", "1").strip() in {"1", "true", "True"}
VPN_ROBOKASSA_HASH = os.getenv("VPN_ROBOKASSA_HASH", "md5").strip().lower()


def robokassa_configured() -> bool:
    return bool(
        VPN_ROBOKASSA_LOGIN and VPN_ROBOKASSA_PASSWORD1 and VPN_ROBOKASSA_PASSWORD2
    )


def public_base_url() -> str:
    """Публичный HTTPS-адрес бота (для Robokassa Result/Success URL)."""
    base = (
        os.getenv("ORACLE_WEBHOOK_URL", "").strip()
        or os.getenv("VPN_WEBHOOK_URL", "").strip()
        or os.getenv("ORACLE_WEBAPP_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )
    return base.rstrip("/")
