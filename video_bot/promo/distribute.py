"""Загрузка готовых роликов на площадки: Telegram, YouTube, VK, TikTok.

Каждая площадка деградирует «мягко»: если доступа нет — ролик остаётся в папке
со статусом `manual` (выложишь руками), а не падает весь конвейер.

Ссылка-метка (item.link) идёт в описание ролика → переход в Оракул и атрибуция /sources.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from video_bot.promo.oracle_promo import PromoItem

logger = logging.getLogger(__name__)


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
        # YouTube с 2023 не делает ссылки кликабельными в Shorts (описание и
        # комментарии). Основной путь перехода теперь — QR-код и хендл "TG: ОРАКУЛ БОТ",
        # впечатанные прямо в кадр видео (см. captions.py/assembler.py). Ссылка
        # текстом и в шапке канала — запасной вариант для тех, кто читает описание.
        meta = {
            "snippet": {
                "title": title,
                "description": (
                    f"{item.topic}\n\n"
                    f"🔮 Наведи камеру на QR в конце видео — попадёшь прямо в бота\n"
                    f"Или в Telegram найди: MOracul_bot\n"
                    f"Кликабельная ссылка — в шапке канала.\n"
                    f"{item.link}\n"
                    f"#shorts #таро #гороскоп"
                ),
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
        _yt_comment_link(token, vid, item)
        return UploadResult(True, "youtube", "posted", url=f"https://youtube.com/shorts/{vid}")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "youtube", "failed", error=str(e)[:200])


def _yt_comment_link(token: str, video_id: str, item: PromoItem) -> None:
    """Первый комментарий с кликабельной ссылкой (в Shorts описание не кликается)."""
    import requests

    try:
        r = requests.post(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            # В Shorts ссылки в комментариях НЕ кликабельны (политика
                            # YouTube) — даём QR (в видео) + имя для поиска + ссылку текстом.
                            "textOriginal": (
                                "🔮 QR в конце видео → сразу в бота. Либо в Telegram набери MOracul_bot\n"
                                f"Или скопируй ссылку: {item.link}\n"
                                "Кликабельная ссылка — в шапке канала."
                            )
                        }
                    },
                }
            },
            timeout=30,
        )
        if r.status_code not in (200, 201):
            logger.warning("yt comment %s: %s", r.status_code, r.text[:150])
    except Exception as e:  # noqa: BLE001
        logger.warning("yt comment: %s", e)


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


# ───────────────────────── TikTok / Instagram (upload-post.com) ─────────────────────────
def uploadpost_platforms() -> list[str]:
    """Площадки автопостинга через upload-post (env UPLOAD_POST_PLATFORMS, через запятую)."""
    raw = os.getenv("UPLOAD_POST_PLATFORMS", "tiktok").strip()
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def post_uploadpost(item: PromoItem, *, platforms: list[str] | None = None,
                    scheduled_iso: str = "") -> UploadResult:
    """Автопостинг через upload-post.com (одним запросом на несколько площадок).

    scheduled_iso — ISO-8601 время отложенной публикации (интерпретируется
    в Europe/Moscow); пусто = опубликовать сразу.
    """
    from video_bot.promo.tiktok_guard import tiktok_posting_disabled

    api_key = os.getenv("UPLOAD_POST_API_KEY", "").strip()
    profile = os.getenv("UPLOAD_POST_USER", "oracle").strip()
    plats = list(platforms or uploadpost_platforms())
    if tiktok_posting_disabled() and "tiktok" in plats:
        plats = [p for p in plats if p != "tiktok"]
        if not plats:
            return UploadResult(
                False, "tiktok", "manual",
                error="TikTok временно заблокирован (spam_risk); Instagram — отдельно",
            )
    import requests

    caption_base = f"🔮 {item.topic}"
    if "instagram" in plats:
        caption = (
            f"{caption_base}\n\n"
            "2 сценария судьбы на 2 месяца — бесплатно 👇\n"
            "https://t.me/MOracul_bot?start=src_instagram\n\n"
            "#таро #гороскоп #эзотерика #предсказания"
        )[:2100]
    else:
        caption = _caption(item, with_link=False)[:2000] + " Бот — в шапке профиля"
    data: list[tuple[str, str]] = [
        ("user", profile),
        ("title", caption[:2100]),
        ("post_mode", "DIRECT_POST"),        # tiktok
        ("media_type", "REELS"),             # instagram
        ("async_upload", "true"),
    ]
    data += [("platform[]", p) for p in plats]
    if scheduled_iso:
        data += [("scheduled_date", scheduled_iso), ("timezone", "Europe/Moscow")]
    label = "+".join(plats)
    try:
        with open(item.file, "rb") as f:
            r = requests.post(
                "https://api.upload-post.com/api/upload",
                headers={"Authorization": f"Apikey {api_key}"},
                data=data,
                files={"video": (Path(item.file).name, f, "video/mp4")},
                timeout=900,
            )
        resp = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code in (200, 202):
            url = ""
            try:
                results = resp.get("results") or {}
                for plat in plats:
                    url = (results.get(plat) or {}).get("url", "")
                    if url:
                        break
            except AttributeError:
                pass
            status = "scheduled" if scheduled_iso else "posted"
            fallback_urls = {"tiktok": "https://www.tiktok.com/", "instagram": "https://instagram.com/moracul_taro"}
            return UploadResult(True, label, status, url=url or fallback_urls.get(plats[0] if plats else "", ""))
        err_text = f"upload-post {r.status_code}: {str(resp)[:200]}"
        from video_bot.promo.tiktok_guard import note_uploadpost_errors

        note_uploadpost_errors([err_text])
        return UploadResult(False, label, "failed", error=err_text)
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, label, "failed", error=str(e)[:200])


def post_tiktok(item: PromoItem, *, scheduled_iso: str = "") -> UploadResult:
    if os.getenv("UPLOAD_POST_API_KEY", "").strip():
        return post_uploadpost(item, scheduled_iso=scheduled_iso)
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        # Файл остаётся в папке — выкладываешь вручную, ссылка-метка уже в плане
        return UploadResult(
            False, "tiktok", "manual",
            error="Автопостинг не настроен (UPLOAD_POST_API_KEY пуст); ролик в папке для ручной загрузки",
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
