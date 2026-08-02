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
from typing import Any

from video_bot.promo.oracle_promo import PromoItem

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    ok: bool
    platform: str
    status: str  # posted | manual | failed
    url: str = ""
    error: str = ""


def _promo_setting(key: str, default: str = "") -> str:
    """Настройки из кабинета ReelDesk (Выводы → Настройки публикации).
    Best-effort: если кабинет/БД недоступны — тихо падаем на default,
    чтобы движок постинга никогда не ломался из-за настроек."""
    try:
        from video_studio import storage as _vstore

        return _vstore.get_setting(key, default)
    except Exception:  # noqa: BLE001
        return default


def _cta_hard() -> bool:
    return _promo_setting("cta_style", "normal") == "hard"


def _site_url() -> str:
    return (_promo_setting("site_url", "https://moracul.ru") or "https://moracul.ru").rstrip("/")


def _comment_hook_line() -> str:
    if _promo_setting("comment_hook_enabled", "1") != "1":
        return ""
    return "Напиши свой знак в комментариях — отвечу картой 👇"


def _birthday_day(item: PromoItem) -> int | None:
    """Число из служебной метки [birth-day:N] ежедневной серии."""
    import re

    m = re.search(r"\[birth-day:(\d{1,2})\]", item.note or "")
    if not m:
        return None
    day = int(m.group(1))
    return day if 1 <= day <= 31 else None


def _first_comment(item: PromoItem, platform: str = "birthday") -> str:
    day = _birthday_day(item)
    if day:
        from video_bot.promo.birthday_series import first_comment

        return first_comment(day, platform)
    # TikTok: ссылка в первом комменте, не в title (меньше shadowban).
    if platform == "tiktok" or item.platform == "tiktok":
        link = (item.link or "https://t.me/MOracul_bot?start=src_tiktok").strip()
        return f"Бесплатный расклад → {link}"
    return ""


def _caption(item: PromoItem, *, with_link: bool = True) -> str:
    site = _site_url()
    hook = _comment_hook_line()
    if with_link and _cta_hard():
        parts = [f"👉 {item.link}", "Жми — расклад бесплатно!", f"Сайт: {site}", "", f"🔮 {item.topic}"]
        if hook:
            parts.append(hook)
        return "\n".join(parts)
    base = f"🔮 {item.topic}"
    if with_link:
        base += f"\n\nБесплатный расклад: {item.link}\nСайт: {site}"
    if hook:
        base += f"\n{hook}"
    return base


def _fill_tpl(tpl: str, item: PromoItem, *, link: str) -> str:
    site = _site_url()
    text = (
        tpl.replace("{topic}", item.topic)
        .replace("{link}", link)
        .replace("{site}", site)
    )
    hook = _comment_hook_line()
    if hook and hook not in text and _promo_setting("comment_hook_enabled", "1") == "1":
        text = text.rstrip() + "\n\n" + hook
    if site and site not in text and "{site}" not in tpl:
        text = text.rstrip() + f"\nСайт: {site}"
    return text


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


# ───────────────────────── YouTube Shorts / long-form ─────────────────────────
def post_youtube(item: PromoItem, *, account: dict[str, Any] | None = None, content_type: str = "shorts") -> UploadResult:
    """content_type: "shorts" (по умолчанию, вертикальные до 60с) | "video" (обычный
    ролик — тот же исходник, только без #shorts-хвоста и /shorts/-ссылки; реальный
    горизонтальный/длинный монтаж — отдельная доработка рендер-движка, здесь только
    переключатель метаданных публикации)."""
    from video_bot.promo.youtube_oauth import get_access_token, youtube_configured

    rt = (account or {}).get("refresh_token", "").strip() if account is not None else ""
    if account is not None and not rt:
        return UploadResult(False, "youtube", "manual", error="Доп. аккаунт не авторизован — нажмите «Подключить» в кабинете")
    if account is None and not youtube_configured():
        return UploadResult(False, "youtube", "manual", error="YOUTUBE_* не настроены (см. youtube_authorize.py)")
    import json

    import requests

    is_short = content_type != "video"
    hard = _cta_hard()
    try:
        token = get_access_token(rt)
        title = (f"{item.topic} #shorts" if is_short else item.topic)[:95]
        # YouTube с 2023 не делает ссылки кликабельными в Shorts (описание и
        # комментарии). Основной путь перехода теперь — QR-код и хендл "TG: ОРАКУЛ БОТ",
        # впечатанные прямо в кадр видео (см. captions.py/assembler.py). Ссылка
        # текстом и в шапке канала — запасной вариант для тех, кто читает описание.
        if hard:
            description = (
                f"👉 ЖМИ: {item.link}\n"
                f"Бесплатный расклад за 10 секунд в Telegram (MOracul_bot)\n\n"
                f"{item.topic}\n\n"
                f"🔮 Или наведи камеру на QR в конце видео.\n"
            )
        else:
            description = (
                f"{item.topic}\n\n"
                f"🔮 Наведи камеру на QR в конце видео — попадёшь прямо в бота\n"
                f"Или в Telegram найди: MOracul_bot\n"
                f"Кликабельная ссылка — в шапке канала.\n"
                f"{item.link}\n"
            )
        description += "#shorts #таро #гороскоп" if is_short else "#таро #гороскоп"
        meta = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["таро", "гороскоп", "оракул"] + (["shorts"] if is_short else []),
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
        url = f"https://youtube.com/shorts/{vid}" if is_short else f"https://youtube.com/watch?v={vid}"
        return UploadResult(True, "youtube", "posted", url=url)
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "youtube", "failed", error=str(e)[:200])


def _yt_comment_link(token: str, video_id: str, item: PromoItem) -> None:
    """Первый комментарий с кликабельной ссылкой (в Shorts описание не кликается)."""
    import requests

    birthday = _first_comment(item, "youtube")
    custom = _promo_setting("youtube_comment_template", "").strip()
    if birthday:
        text = birthday
    elif custom:
        text = custom.replace("{link}", item.link).replace("{topic}", item.topic)
    elif _cta_hard():
        text = (
            f"👉 Забери свой бесплатный расклад: {item.link}\n"
            "Или набери в Telegram: MOracul_bot"
        )
    else:
        text = (
            "🔮 QR в конце видео → сразу в бота. Либо в Telegram набери MOracul_bot\n"
            f"Или скопируй ссылку: {item.link}\n"
            "Кликабельная ссылка — в шапке канала."
        )
    try:
        r = requests.post(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": text}},
                }
            },
            timeout=30,
        )
        if r.status_code not in (200, 201):
            logger.warning("yt comment %s: %s", r.status_code, r.text[:150])
    except Exception as e:  # noqa: BLE001
        logger.warning("yt comment: %s", e)


# ───────────────────────── VK (видео в сообществе) ─────────────────────────
def post_vk(item: PromoItem, *, account: dict[str, Any] | None = None) -> UploadResult:
    if account is not None:
        token = (account.get("access_token") or "").strip()
        if not token:
            return UploadResult(False, "vk", "manual", error="Доп. VK-аккаунт без токена — вставьте в кабинете")
        group_id = (account.get("group_id") or "").strip()
    else:
        token = os.getenv("VK_TOKEN", "").strip()
        if not token:
            return UploadResult(False, "vk", "manual", error="VK_TOKEN не задан")
        # vk_target=personal (по умолчанию) → личная стена владельца токена (group_id
        # пуст); vk_target=group → стена сообщества из vk_target_group_id.
        if _promo_setting("vk_target", "personal") == "group":
            group_id = _promo_setting("vk_target_group_id", "").strip() or os.getenv("VK_GROUP_ID", "").strip()
        else:
            group_id = ""
    api_v = os.getenv("VK_API_VERSION", "5.199").strip()
    import requests

    try:
        description = (
            f"👉 {item.link}\nБесплатный расклад — жми!\n\n{item.topic}"
            if _cta_hard()
            else f"{item.topic}\n\nБесплатный расклад: {item.link}"
        )
        params = {
            "access_token": token,
            "v": api_v,
            "name": item.topic[:128],
            "description": description,
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
        first_comment = _first_comment(item, "vk")
        if first_comment:
            try:
                requests.post(
                    "https://api.vk.com/method/video.createComment",
                    data={
                        "access_token": token,
                        "v": api_v,
                        "owner_id": owner,
                        "video_id": vid,
                        "message": first_comment,
                    },
                    timeout=30,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("vk first comment: %s", e)
        return UploadResult(True, "vk", "posted", url=f"https://vk.com/video{owner}_{vid}")
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, "vk", "failed", error=str(e)[:200])


# ───────────────────────── TikTok / Instagram (upload-post.com) ─────────────────────────
def uploadpost_platforms() -> list[str]:
    """Площадки автопостинга через upload-post (env UPLOAD_POST_PLATFORMS, через запятую).

    Instagram по умолчанию вырезан: аккаунт moracul_taro отключён Meta (19.07.2026).
    Вернуть: UPLOAD_POST_PLATFORMS=tiktok,instagram + BIRTHDAY_SKIP_INSTAGRAM=0.
    """
    raw = os.getenv("UPLOAD_POST_PLATFORMS", "tiktok").strip()
    plats = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if os.getenv("UPLOAD_POST_SKIP_INSTAGRAM", "1").strip().lower() in ("1", "true", "yes"):
        plats = [p for p in plats if p != "instagram"]
    return plats


def post_uploadpost(item: PromoItem, *, platforms: list[str] | None = None,
                    scheduled_iso: str = "", account: dict[str, Any] | None = None,
                    media_type: str = "") -> UploadResult:
    """Автопостинг через upload-post.com (одним запросом на несколько площадок).

    scheduled_iso — ISO-8601 время отложенной публикации (интерпретируется
    в Europe/Moscow); пусто = опубликовать сразу.
    account — доп. аккаунт из channel_accounts (свой upload-post профиль вместо
    общего UPLOAD_POST_USER).
    media_type — "REELS" (по умолчанию) | "IMAGE" для Instagram-постов лентой;
    сам контент (картинка/карусель вместо видео) — доработка рендер-движка,
    здесь только переключатель поля upload-post API.
    """
    from video_bot.promo.tiktok_guard import tiktok_posting_disabled

    api_key = os.getenv("UPLOAD_POST_API_KEY", "").strip()
    if account is not None:
        profile = (account.get("profile") or account.get("upload_post_profile") or "").strip()
        if not profile:
            return UploadResult(False, "uploadpost", "manual", error="Доп. аккаунт не подключён к upload-post — нажмите «Подключить»")
    else:
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
    ig_tpl = _promo_setting("instagram_caption_template", "").strip()
    generic_tpl = _promo_setting("generic_caption_template", "").strip()
    site = _site_url()
    birth_day = _birthday_day(item)
    _tt_tags = (
        "#таро #гороскоп #эзотерика #предсказания #знакизодиака",
        "#таро #любовь #расклад #гороскоп #эзотерика",
        "#гороскоп #знакизодиака #таро #судьба #предсказание",
        "#таро #раскладтаро #эзотерика #мистика #гадание",
        "#гороскопнасегодня #таро #знакизодиака #вселенная #эзотерика",
        "#датарождения #нумерология #характер #самопознание #таро",
    )
    tag_i = abs(hash(item.source or item.topic)) % len(_tt_tags)
    if birth_day:
        caption = (
            f"🔢 {item.topic}\n\n"
            "Сохрани, чтобы не забыть. Знаешь именинника с этим числом — отправь ему.\n"
            "Какое число разобрать следующим? Пиши в комментариях.\n\n"
            f"Бот в шапке · {site}\n"
            f"{_tt_tags[birth_day % len(_tt_tags)]}"
        )[:2100]
    elif "tiktok" in plats and "instagram" not in plats:
        # TikTok: хук + хэштеги, без t.me в title (ссылка — first_comment / шапка).
        hook = _comment_hook_line() or "Напиши свой знак в комментариях — отвечу картой 👇"
        caption = (
            f"{caption_base}\n\n"
            f"{hook}\n"
            f"Бот в шапке профиля · {site}\n\n"
            f"{_tt_tags[tag_i]}"
        )[:2100]
    elif "instagram" in plats:
        if ig_tpl:
            caption = _fill_tpl(ig_tpl, item, link="https://t.me/MOracul_bot?start=src_instagram")[:2100]
        else:
            hook = _comment_hook_line()
            caption = (
                f"{caption_base}\n\n"
                "2 сценария судьбы на 2 месяца — бесплатно 👇\n"
                "https://t.me/MOracul_bot?start=src_instagram\n"
                f"Сайт: {site}\n"
                + (f"{hook}\n" if hook else "")
                + "\n#таро #гороскоп #эзотерика #предсказания"
            )[:2100]
    elif generic_tpl:
        caption = _fill_tpl(generic_tpl, item, link=item.link)[:2100]
    else:
        caption = _caption(item, with_link=False)[:2000] + f"\nБот — в шапке · сайт {site}"
    data: list[tuple[str, str]] = [
        ("user", profile),
        ("title", caption[:2100]),
        ("post_mode", "DIRECT_POST"),                 # tiktok
        ("media_type", media_type or "REELS"),        # instagram: REELS | IMAGE | STORIES
        ("async_upload", "true"),
    ]
    data += [("platform[]", p) for p in plats]
    if scheduled_iso:
        data += [("scheduled_date", scheduled_iso), ("timezone", "Europe/Moscow")]
    first_comment = _first_comment(item, plats[0] if len(plats) == 1 else "birthday")
    if first_comment:
        data.append(("first_comment", first_comment))
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
            # После успешного Reel — опционально Stories (кадр + CTA)
            if (
                "instagram" in plats
                and (media_type or "REELS") == "REELS"
                and _promo_setting("instagram_stories_enabled", "1") == "1"
                and not scheduled_iso
            ):
                try:
                    post_instagram_story_frame(item, profile=profile, api_key=api_key)
                except Exception as e:  # noqa: BLE001
                    logger.warning("instagram stories skip: %s", e)
            return UploadResult(True, label, status, url=url or fallback_urls.get(plats[0] if plats else "", ""))
        err_text = f"upload-post {r.status_code}: {str(resp)[:200]}"
        from video_bot.promo.tiktok_guard import note_uploadpost_errors

        note_uploadpost_errors([err_text])
        return UploadResult(False, label, "failed", error=err_text)
    except Exception as e:  # noqa: BLE001
        return UploadResult(False, label, "failed", error=str(e)[:200])


def post_instagram_story_frame(item: PromoItem, *, profile: str, api_key: str) -> UploadResult:
    """Stories: первый кадр ролика + текст CTA (сайт/бот). Upload-post media_type=STORIES."""
    import subprocess
    import tempfile

    import requests

    site = _site_url()
    tmp = Path(tempfile.mkdtemp(prefix="ig_story_"))
    frame = tmp / "story.jpg"
    # Кадр на ~1с — типичная «заставка» ролика
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", "1", "-i", str(item.file),
            "-frames:v", "1", "-q:v", "2", str(frame),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if not frame.exists() or frame.stat().st_size < 1000:
        return UploadResult(False, "instagram_stories", "failed", error="не удалось вырезать кадр")
    caption = f"🔮 {item.topic}\nСайт {site}\nБот: t.me/MOracul_bot"[:500]
    data = [
        ("user", profile),
        ("title", caption),
        ("media_type", "STORIES"),
        ("platform[]", "instagram"),
        ("async_upload", "true"),
    ]
    with open(frame, "rb") as f:
        r = requests.post(
            "https://api.upload-post.com/api/upload",
            headers={"Authorization": f"Apikey {api_key}"},
            data=data,
            files={"photo": (frame.name, f, "image/jpeg")},
            timeout=300,
        )
    ok = r.status_code in (200, 202)
    return UploadResult(ok, "instagram_stories", "posted" if ok else "failed", error="" if ok else str(r.text)[:160])


def post_tiktok(
    item: PromoItem, *, scheduled_iso: str = "", account: dict[str, Any] | None = None, media_type: str = "",
) -> UploadResult:
    if account is not None or os.getenv("UPLOAD_POST_API_KEY", "").strip():
        return post_uploadpost(item, scheduled_iso=scheduled_iso, account=account, media_type=media_type)
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


def distribute(
    item: PromoItem,
    *,
    channel: str = "",
    account: dict[str, Any] | None = None,
    content_type: str | None = None,
    media_type: str = "",
) -> UploadResult:
    """Выложить ролик на свою площадку. Неизвестная/ненастроенная → manual.

    account — конкретный аккаунт из channel_accounts (см. video_studio.storage);
    None = основной/глобальный (текущее поведение, без изменений). Позволяет
    раннеру постить один и тот же слот в разные аккаунты одной площадки.

    content_type — если явно не передан вызывающим кодом, берём настройку
    youtube_content_type из кабинета (shorts | video | mixed; mixed = каждое
    5-е видео уходит как обычный ролик, остальные — Shorts)."""
    fn = _DISPATCH.get(item.platform)
    if fn is None:
        return UploadResult(False, item.platform, "manual", error="нет загрузчика для площадки")
    if item.platform == "telegram":
        return post_telegram(item, channel=channel)
    if item.platform in ("youtube", "shorts"):
        if content_type is None:
            setting = _promo_setting("youtube_content_type", "shorts")
            if setting == "mixed":
                content_type = "video" if (abs(hash(item.file)) % 5 == 0) else "shorts"
            else:
                content_type = setting
        return post_youtube(item, account=account, content_type=content_type)
    if item.platform == "vk":
        return post_vk(item, account=account)
    if item.platform == "tiktok":
        return post_tiktok(item, account=account, media_type=media_type)
    return fn(item)
