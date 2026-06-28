"""Робокасса: формирование ссылки на оплату и проверка подписи колбэков.

Документация: https://docs.robokassa.ru/

Поток:
  1. Бот создаёт инвойс (storage.create_invoice) → получает InvId.
  2. build_payment_url(...) формирует ссылку → пользователь платит картой/СБП.
  3. Робокасса дёргает ResultURL (сервер-сервер) с подписью по Password#2 →
     check_result_signature → выдаём доступ (идемпотентно) → отвечаем "OK{InvId}".
  4. Пользователя редиректит на SuccessURL (подпись по Password#1) — показываем
     страницу «вернитесь в бот».
"""

from __future__ import annotations

import hashlib
from typing import Mapping
from urllib.parse import urlencode

from oracle_bot.config import (
    ROBOKASSA_HASH,
    ROBOKASSA_LOGIN,
    ROBOKASSA_PASSWORD1,
    ROBOKASSA_PASSWORD2,
    ROBOKASSA_TEST,
)

PAYMENT_HOST = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _hasher(algo: str):
    return {
        "md5": hashlib.md5,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }.get((algo or "md5").lower(), hashlib.md5)


def format_sum(amount_rub: int | float) -> str:
    """Сумма для Робокассы. Целые рубли — без копеек, иначе 2 знака."""
    if float(amount_rub).is_integer():
        return str(int(amount_rub))
    return f"{float(amount_rub):.2f}"


def _shp_tail(shp: Mapping[str, str] | None) -> str:
    """Доп. параметры Shp_* в подписи: отсортированы, в виде :key=value."""
    if not shp:
        return ""
    parts = [f"{key}={shp[key]}" for key in sorted(shp)]
    return (":" + ":".join(parts)) if parts else ""


def _signature(parts: list[str], shp: Mapping[str, str] | None) -> str:
    raw = ":".join(parts) + _shp_tail(shp)
    return _hasher(ROBOKASSA_HASH)(raw.encode("utf-8")).hexdigest()


def build_payment_url(
    *,
    inv_id: int,
    out_sum: int | float,
    description: str,
    shp: Mapping[str, str] | None = None,
    email: str | None = None,
) -> str:
    """Ссылка на страницу оплаты Робокассы."""
    out = format_sum(out_sum)
    signature = _signature([ROBOKASSA_LOGIN, out, str(inv_id), ROBOKASSA_PASSWORD1], shp)
    params: dict[str, str] = {
        "MerchantLogin": ROBOKASSA_LOGIN,
        "OutSum": out,
        "InvId": str(inv_id),
        "Description": description[:100],
        "SignatureValue": signature,
        "Culture": "ru",
        "Encoding": "utf-8",
    }
    if email:
        params["Email"] = email
    if ROBOKASSA_TEST:
        params["IsTest"] = "1"
    if shp:
        for key in sorted(shp):
            params[key] = shp[key]
    return f"{PAYMENT_HOST}?{urlencode(params)}"


def _extract_shp(data: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in data.items() if k.lower().startswith("shp_")}


def check_result_signature(data: Mapping[str, str]) -> bool:
    """Проверка подписи ResultURL (Password#2). data — query/form Робокассы."""
    out_sum = data.get("OutSum") or data.get("out_summ") or ""
    inv_id = data.get("InvId") or data.get("inv_id") or ""
    got = (data.get("SignatureValue") or "").lower()
    if not (out_sum and inv_id and got):
        return False
    expected = _signature([out_sum, str(inv_id), ROBOKASSA_PASSWORD2], _extract_shp(data))
    return got == expected.lower()


def check_success_signature(data: Mapping[str, str]) -> bool:
    """Проверка подписи SuccessURL (Password#1)."""
    out_sum = data.get("OutSum") or data.get("out_summ") or ""
    inv_id = data.get("InvId") or data.get("inv_id") or ""
    got = (data.get("SignatureValue") or "").lower()
    if not (out_sum and inv_id and got):
        return False
    expected = _signature([out_sum, str(inv_id), ROBOKASSA_PASSWORD1], _extract_shp(data))
    return got == expected.lower()
