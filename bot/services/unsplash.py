"""Unsplash API — стоковый фон для карточек Авито (https://unsplash.com/developers)."""

import logging
import re
from typing import Optional, Tuple

import aiohttp

from bot.config import UNSPLASH_ACCESS_KEY, UNSPLASH_ENABLED, UNSPLASH_TIMEOUT_SEC

logger = logging.getLogger(__name__)

API_BASE = "https://api.unsplash.com"


class UnsplashError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
        "Accept-Version": "v1",
    }


def build_search_query(user_request: str, vision_facts: str) -> str:
    """Короткий англоязычный запрос для поиска фона под товар."""
    text = f"{user_request}\n{vision_facts}".lower()

    if "ксеноморф" in text or "alien" in text or "чужой" in text:
        return "alien collectible figurine product photography white background"
    if "iphone" in text or "смартфон" in text or "телефон" in text:
        return "smartphone product photography minimal studio"
    if "кроссовк" in text or "обув" in text or "sneaker" in text:
        return "sneakers product photography clean background"
    if "одежд" in text or "футболк" in text or "куртк" in text:
        return "clothing apparel product flat lay studio"
    if "мебел" in text or "стол" in text or "стул" in text:
        return "furniture product interior catalog photo"
    if "игруш" in text or "фигурк" in text or "collectible" in text:
        return "collectible toy figurine product photography"

    words: list[str] = []
    for line in vision_facts.splitlines():
        t = line.strip().lstrip("•-* ").strip()
        if not t or len(t) < 4:
            continue
        if re.search(r"метод:|размер:|ocr:|фон,|обстановк", t, re.I):
            continue
        latin = re.findall(r"[a-zA-Z]{3,}", t)
        if latin:
            words.extend(latin[:3])
        else:
            words.append(t.split()[0][:24])
        if len(words) >= 4:
            break

    base = " ".join(words[:4]).strip()
    if base:
        return f"{base} product photography studio background"
    return "minimal product photography white studio background"


async def _trigger_download(session: aiohttp.ClientSession, download_location: str) -> None:
    from bot.services.http_client import proxy_for_request

    if not download_location:
        return
    try:
        async with session.get(
            download_location,
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
            proxy=proxy_for_request(False),
        ) as resp:
            await resp.read()
    except Exception as e:
        logger.debug("Unsplash download ping: %s", e)


async def fetch_random_photo(query: str) -> Tuple[bytes, str, str, str]:
    """
    Случайное фото по запросу.
    Returns: (image_bytes, mime, photo_id, photographer_name)
    """
    if not UNSPLASH_ACCESS_KEY:
        raise UnsplashError("ключ не задан")
    params = {
        "query": query[:120],
        "orientation": "squarish",
        "content_filter": "high",
        "w": 1200,
        "h": 1200,
    }
    url = f"{API_BASE}/photos/random"
    from bot.services.http_client import proxy_for_request, session_kwargs

    async with aiohttp.ClientSession(**session_kwargs(False)) as session:
        async with session.get(
            url,
            headers=_headers(),
            params=params,
            timeout=aiohttp.ClientTimeout(total=UNSPLASH_TIMEOUT_SEC),
            proxy=proxy_for_request(False),
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise UnsplashError(f"HTTP {resp.status}: {data}")
        urls = data.get("urls") or {}
        img_url = urls.get("regular") or urls.get("small")
        if not img_url:
            raise UnsplashError("нет URL изображения")
        download_loc = (data.get("links") or {}).get("download_location") or ""
        photo_id = data.get("id") or ""
        user = data.get("user") or {}
        photographer = user.get("name") or user.get("username") or "Unsplash"

        await _trigger_download(session, download_loc)

        async with session.get(
            img_url,
            timeout=aiohttp.ClientTimeout(total=UNSPLASH_TIMEOUT_SEC),
            proxy=proxy_for_request(False),
        ) as img_resp:
            if img_resp.status != 200:
                raise UnsplashError(f"скачивание: {img_resp.status}")
            raw = await img_resp.read()
            ctype = img_resp.headers.get("Content-Type", "image/jpeg")
            mime = ctype.split(";")[0].strip() or "image/jpeg"
            return raw, mime, photo_id, photographer


async def check_api() -> str:
    if not UNSPLASH_ENABLED:
        return "выключен"
    if not UNSPLASH_ACCESS_KEY:
        return "ключ не задан"
    try:
        _, _, pid, name = await fetch_random_photo("product studio")
        return f"OK · фото {pid} · {name}"
    except Exception as e:
        return str(e)[:100]


async def make_unsplash_studio_card(
    image_data: bytes,
    copy,
    user_request: str,
    vision_facts: str,
) -> Tuple[bytes, str]:
    from bot.services.avito_card import render_studio_card_with_background
    from bot.services.image_output import format_method_label

    query = build_search_query(user_request, vision_facts)
    bg_bytes, _, photo_id, photographer = await fetch_random_photo(query)
    method = "unsplash/studio-bg"
    label = format_method_label(method)
    if photo_id:
        label = f"{label} · {photographer}"
    data, mime = render_studio_card_with_background(
        image_data, copy, bg_bytes, method_label=label
    )
    logger.info("Unsplash card: query=%r photo=%s", query, photo_id)
    return data, mime
