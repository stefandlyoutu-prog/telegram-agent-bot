"""YouTube OAuth через refresh-token (без тяжёлых google-зависимостей, только requests).

Один раз: scripts/youtube_authorize.py → получаешь YOUTUBE_REFRESH_TOKEN.
Дальше: get_access_token() сам обновляет короткий access-token из refresh.
"""

from __future__ import annotations

import os
import time

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_cache: dict[str, float | str] = {}


def youtube_configured() -> bool:
    return bool(
        os.getenv("YOUTUBE_CLIENT_ID", "").strip()
        and os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
        and os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    )


def get_access_token(refresh_token: str | None = None) -> str:
    """Действующий access-token (кэш с запасом 60 сек).

    refresh_token — опционально для доп. аккаунта; иначе берём YOUTUBE_REFRESH_TOKEN.
    """
    rt = (refresh_token or "").strip() or os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    cache_key = f"token:{rt[-12:]}" if rt else "token"
    exp_key = f"exp:{rt[-12:]}" if rt else "exp"
    now = time.time()
    if _cache.get(cache_key) and float(_cache.get(exp_key, 0)) > now + 60:
        return str(_cache[cache_key])
    import requests

    resp = requests.post(
        _TOKEN_URL,
        data={
            "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
            "refresh_token": rt,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube token refresh failed: {data}")
    _cache[cache_key] = data["access_token"]
    _cache[exp_key] = now + float(data.get("expires_in", 3500))
    return str(_cache[cache_key])
