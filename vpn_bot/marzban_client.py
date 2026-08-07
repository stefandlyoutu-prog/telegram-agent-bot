"""Асинхронный клиент REST API панели Marzban (Xray VLESS/Reality нода).

Документация: https://github.com/Gozargah/Marzban (см. /docs на самой панели).

Поток:
  1. POST /api/admin/token (form: username/password) → access_token (JWT).
  2. Токен кешируем и переиспользуем, при 401 — логинимся заново.
  3. create_user/get_user/modify_user/delete_user — управление ключами.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from vpn_bot.config import MARZBAN_BASE_URL, MARZBAN_INBOUNDS, MARZBAN_PASSWORD, MARZBAN_USERNAME

logger = logging.getLogger(__name__)


class MarzbanError(RuntimeError):
    pass


class MarzbanClient:
    def __init__(
        self,
        base_url: str = MARZBAN_BASE_URL,
        username: str = MARZBAN_USERNAME,
        password: str = MARZBAN_PASSWORD,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _login(self) -> str:
        # verify=False: панель часто на self-signed сертификате (IP без домена).
        async with httpx.AsyncClient(timeout=20, verify=False) as client:
            resp = await client.post(
                f"{self._base_url}/api/admin/token",
                data={
                    "username": self._username,
                    "password": self._password,
                    "grant_type": "password",
                },
            )
        if resp.status_code != 200:
            raise MarzbanError(f"Marzban login failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        self._token = data["access_token"]
        # Токен обычно живёт 24ч (JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440) — обновим через 20ч.
        self._token_expires_at = time.time() + 20 * 3600
        return self._token

    async def _auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        if force_refresh or not self._token or time.time() >= self._token_expires_at:
            await self._login()
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.request(
                method, f"{self._base_url}{path}", headers=headers, **kwargs
            )
        if resp.status_code == 401:
            headers = await self._auth_headers(force_refresh=True)
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                resp = await client.request(
                    method, f"{self._base_url}{path}", headers=headers, **kwargs
                )
        return resp

    async def get_user(self, marzban_username: str) -> Optional[dict[str, Any]]:
        resp = await self._request("GET", f"/api/user/{marzban_username}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise MarzbanError(f"get_user {marzban_username}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def create_user(
        self,
        marzban_username: str,
        *,
        expire_ts: int = 0,
        data_limit_bytes: int = 0,
        note: str = "",
    ) -> dict[str, Any]:
        payload = {
            "username": marzban_username,
            "proxies": {"vless": {}},
            "inbounds": {"vless": list(MARZBAN_INBOUNDS)},
            "expire": expire_ts,
            "data_limit": data_limit_bytes,
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
            "note": note,
        }
        resp = await self._request("POST", "/api/user", json=payload)
        if resp.status_code not in (200, 201):
            raise MarzbanError(f"create_user {marzban_username}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def modify_user(self, marzban_username: str, **fields: Any) -> dict[str, Any]:
        resp = await self._request("PUT", f"/api/user/{marzban_username}", json=fields)
        if resp.status_code != 200:
            raise MarzbanError(f"modify_user {marzban_username}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def delete_user(self, marzban_username: str) -> None:
        resp = await self._request("DELETE", f"/api/user/{marzban_username}")
        if resp.status_code not in (200, 204, 404):
            raise MarzbanError(f"delete_user {marzban_username}: {resp.status_code} {resp.text[:300]}")

    async def ensure_active_user(
        self,
        marzban_username: str,
        *,
        extend_expire_ts: int,
        data_limit_bytes: int = 0,
        note: str = "",
    ) -> dict[str, Any]:
        """Создаёт пользователя или продлевает существующего до extend_expire_ts.

        Если у пользователя уже стоит более позднее expire (напр. не сгоревший
        предыдущий период) — продление суммируется с остатком, а не перетирается.
        """
        existing = await self.get_user(marzban_username)
        if existing is None:
            return await self.create_user(
                marzban_username,
                expire_ts=extend_expire_ts,
                data_limit_bytes=data_limit_bytes,
                note=note,
            )
        current_expire = int(existing.get("expire") or 0)
        now = int(time.time())
        base = current_expire if current_expire > now else now
        added_days = extend_expire_ts - now
        new_expire = base + added_days if added_days > 0 else extend_expire_ts
        return await self.modify_user(
            marzban_username,
            expire=new_expire,
            status="active",
            data_limit=data_limit_bytes,
        )

    @staticmethod
    def subscription_url(user_obj: dict[str, Any]) -> str:
        """Абсолютная подписочная ссылка (Marzban отдаёт относительный путь)."""
        sub = user_obj.get("subscription_url") or ""
        if sub.startswith("http"):
            return sub
        return f"{MARZBAN_BASE_URL}{sub}"
