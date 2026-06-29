"""Загрузка готовых роликов на площадки: Telegram, YouTube, VK, TikTok.

Каждая площадка деградирует «мягко»: если доступа нет — ролик остаётся в папке
со статусом `manual` (выложишь руками), а не падает весь конвейер.

Ссылка-метка (item.link) идёт в описание ролика → переход в Оракул и атрибуция /sources.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from video_bot.promo.oracle_promo import PromoItem


@dataclass
class UploadResult:
    ok: bool
    platform: str
    status: str  # posted | manual | failed
    url: str = ""
    error: str = ""


def _caption(item: PromoItem, *, with_link: bool = True) -> str:
    base = f"🔮 {item.topic}"
    if with_link:
        base += f"\n\nБесплатный расклад: {item.link}"
    return base


# ───────────────────────── Telegram ─────────────────────────
def post_telegram(item: PromoItem, *, channel: str = "") -> UploadResult:
    token = os.getenv("ORACLE_BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return UploadResult(False, "telegram", "manual", error="ORACLE_BOT_TOKEN не задан")
    ch = (channel or "").lstrip("@")
    if not ch:
        try:
            from oracle_bot.config import ORACLE_PROMO_CHANNELS

            ch = (list(ORACLE_PROMO_CHANNELS) or ["M_Topgoroskop"])[0].lstrip("@")
        except Exception:
            ch = "M_Topgoroskop"
    import requests

    try:
        with open(item.file, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendVideo",
                data={"chat_id": f"@{ch}", "caption": _caption(item), "parse_mode": "HTML"},
                files={"video": f},
                timeout=300,
            )
        body = r.json()
        if not body.get("ok"):
            return UploadResult(False, "telegram", "failed", error=str(body)[:200])
        return UploadResult(True, "telegram", "posted", url=f"https://t.me/{ch}")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "telegram", "failed", error=str(e)[:200])


# ───────────────────────── YouTube Shorts ─────────────────────────
def post_youtube(item: PromoItem) -> UploadResult:
    from video_bot.promo.youtube_oauth import get_access_token, youtube_configured

    if not youtube_configured():
        return UploadResult(False, "youtube", "manual", error="YOUTUBE_* не настроены (см. youtube_authorize.py)")
    import json

    import requests

    try:
        token = get_access_token()
        title = f"{item.topic} #shorts"[:95]
        meta = {
            "snippet": {
                "title": title,
                "description": f"{item.topic}\n\nБесплатный расклад таро и гороскоп: {item.link}\n#shorts #таро #гороскоп",
                "tags": ["таро", "гороскоп", "оракул", "shorts"],
                "categoryId": "24",
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        size = Path(item.file).stat().st_size
        init = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            },
            data=json.dumps(meta),
            timeout=60,
        )
        upload_url = init.headers.get("Location")
        if not upload_url:
            return UploadResult(False, "youtube", "failed", error=f"init {init.status_code}: {init.text[:200]}")
        with open(item.file, "rb") as f:
            up = requests.put(
                upload_url,
                headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                data=f,
                timeout=600,
            )
        data = up.json()
        vid = data.get("id")
        if not vid:
            return UploadResult(False, "youtube", "failed", error=str(data)[:200])
        return UploadResult(True, "youtube", "posted", url=f"https://youtube.com/shorts/{vid}")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "youtube", "failed", error=str(e)[:200])


# ───────────────────────── VK (видео в сообществе) ─────────────────────────
def post_vk(item: PromoItem) -> UploadResult:
    token = os.getenv("VK_TOKEN", "").strip()
    if not token:
        return UploadResult(False, "vk", "manual", error="VK_TOKEN не задан")
    group_id = os.getenv("VK_GROUP_ID", "").strip()
    api_v = os.getenv("VK_API_VERSION", "5.199").strip()
    import requests

    try:
        params = {
            "access_token": token,
            "v": api_v,
            "name": item.topic[:128],
            "description": f"{item.topic}\n\nБесплатный расклад: {item.link}",
            "wallpost": 1,
        }
        if group_id:
            params["group_id"] = group_id.lstrip("-")
        save = requests.get("https://api.vk.com/method/video.save", params=params, timeout=30).json()
        if "error" in save:
            return UploadResult(False, "vk", "failed", error=str(save["error"])[:200])
        upload_url = save["response"]["upload_url"]
        with open(item.file, "rb") as f:
            up = requests.post(upload_url, files={"video_file": f}, timeout=600).json()
        owner = up.get("owner_id")
        vid = up.get("video_id")
        if not vid:
            return UploadResult(False, "vk", "failed", error=str(up)[:200])
        return UploadResult(True, "vk", "posted", url=f"https://vk.com/video{owner}_{vid}")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "vk", "failed", error=str(e)[:200])


# ───────────────────────── TikTok (API требует одобрения dev-приложения) ─────────────────────────
def post_tiktok(item: PromoItem) -> UploadResult:
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        # Файл остаётся в папке — выкладываешь вручную, ссылка-метка уже в плане
        return UploadResult(
            False, "tiktok", "manual",
            error="TikTok Content Posting API требует одобренного dev-приложения; ролик в папке для ручной загрузки",
        )
    import requests

    try:
        size = Path(item.file).stat().st_size
        init = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={
                "post_info": {"title": _caption(item, with_link=False)[:150], "privacy_level": "PUBLIC_TO_EVERYONE"},
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            },
            timeout=60,
        ).json()
        upload_url = (init.get("data") or {}).get("upload_url")
        if not upload_url:
            return UploadResult(False, "tiktok", "failed", error=str(init)[:200])
        with open(item.file, "rb") as f:
            requests.put(
                upload_url,
                headers={"Content-Range": f"bytes 0-{size-1}/{size}", "Content-Type": "video/mp4"},
                data=f,
                timeout=600,
            )
        return UploadResult(True, "tiktok", "posted", url="https://www.tiktok.com/")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "tiktok", "failed", error=str(e)[:200])


_DISPATCH = {
    "telegram": post_telegram,
    "youtube": post_youtube,
    "shorts": post_youtube,
    "vk": post_vk,
    "tiktok": post_tiktok,
}


def distribute(item: PromoItem, *, channel: str = "") -> UploadResult:
    """Выложить ролик на свою площадку. Неизвестная/ненастроенная → manual."""
    fn = _DISPATCH.get(item.platform)
    if fn is None:
        return UploadResult(False, item.platform, "manual", error="нет загрузчика для площадки")
    if item.platform == "telegram":
        return post_telegram(item, channel=channel)
    return fn(item)
