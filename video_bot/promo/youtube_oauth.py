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


def get_access_token() -> str:
    """Действующий access-token (кэш с запасом 60 сек)."""
    now = time.time()
    if _cache.get("token") and float(_cache.get("exp", 0)) > now + 60:
        return str(_cache["token"])
    import requests

    resp = requests.post(
        _TOKEN_URL,
        data={
            "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
            "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip(),
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube token refresh failed: {data}")
    _cache["token"] = data["access_token"]
    _cache["exp"] = now + float(data.get("expires_in", 3500))
    return str(_cache["token"])
