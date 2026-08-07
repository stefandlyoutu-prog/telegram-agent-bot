"""Робокасса для VPN-бота: ссылка на оплату + проверка подписи колбэков.

Логика идентична oracle_bot/robokassa.py, но со своими реквизитами
(VPN_ROBOKASSA_*), т.к. это может быть отдельный магазин в личном кабинете.
"""

from __future__ import annotations

import hashlib
from typing import Mapping
from urllib.parse import urlencode

from vpn_bot.config import (
    VPN_ROBOKASSA_HASH,
    VPN_ROBOKASSA_LOGIN,
    VPN_ROBOKASSA_PASSWORD1,
    VPN_ROBOKASSA_PASSWORD2,
    VPN_ROBOKASSA_TEST,
    VPN_ROBOKASSA_TEST_PASSWORD1,
    VPN_ROBOKASSA_TEST_PASSWORD2,
)

PAYMENT_HOST = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _pw1() -> str:
    if VPN_ROBOKASSA_TEST and VPN_ROBOKASSA_TEST_PASSWORD1:
        return VPN_ROBOKASSA_TEST_PASSWORD1
    return VPN_ROBOKASSA_PASSWORD1


def _pw2() -> str:
    if VPN_ROBOKASSA_TEST and VPN_ROBOKASSA_TEST_PASSWORD2:
        return VPN_ROBOKASSA_TEST_PASSWORD2
    return VPN_ROBOKASSA_PASSWORD2


def _hasher(algo: str):
    return {
        "md5": hashlib.md5,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }.get((algo or "md5").lower(), hashlib.md5)


def format_sum(amount_rub: int | float) -> str:
    if float(amount_rub).is_integer():
        return str(int(amount_rub))
    return f"{float(amount_rub):.2f}"


def _shp_tail(shp: Mapping[str, str] | None) -> str:
    if not shp:
        return ""
    parts = [f"{key}={shp[key]}" for key in sorted(shp)]
    return (":" + ":".join(parts)) if parts else ""


def _signature(parts: list[str], shp: Mapping[str, str] | None) -> str:
    raw = ":".join(parts) + _shp_tail(shp)
    return _hasher(VPN_ROBOKASSA_HASH)(raw.encode("utf-8")).hexdigest()


def build_payment_url(
    *,
    inv_id: int,
    out_sum: int | float,
    description: str,
    shp: Mapping[str, str] | None = None,
    email: str | None = None,
) -> str:
    out = format_sum(out_sum)
    signature = _signature([VPN_ROBOKASSA_LOGIN, out, str(inv_id), _pw1()], shp)
    params: dict[str, str] = {
        "MerchantLogin": VPN_ROBOKASSA_LOGIN,
        "OutSum": out,
        "InvId": str(inv_id),
        "Description": description[:100],
        "SignatureValue": signature,
        "Culture": "ru",
        "Encoding": "utf-8",
    }
    if email:
        params["Email"] = email
    if VPN_ROBOKASSA_TEST:
        params["IsTest"] = "1"
    if shp:
        for key in sorted(shp):
            params[key] = shp[key]
    return f"{PAYMENT_HOST}?{urlencode(params)}"


def _extract_shp(data: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in data.items() if k.lower().startswith("shp_")}


def check_result_signature(data: Mapping[str, str]) -> bool:
    out_sum = data.get("OutSum") or data.get("out_summ") or ""
    inv_id = data.get("InvId") or data.get("inv_id") or ""
    got = (data.get("SignatureValue") or "").lower()
    if not (out_sum and inv_id and got):
        return False
    expected = _signature([out_sum, str(inv_id), _pw2()], _extract_shp(data))
    return got == expected.lower()


def check_success_signature(data: Mapping[str, str]) -> bool:
    out_sum = data.get("OutSum") or data.get("out_summ") or ""
    inv_id = data.get("InvId") or data.get("inv_id") or ""
    got = (data.get("SignatureValue") or "").lower()
    if not (out_sum and inv_id and got):
        return False
    expected = _signature([out_sum, str(inv_id), _pw1()], _extract_shp(data))
    return got == expected.lower()
