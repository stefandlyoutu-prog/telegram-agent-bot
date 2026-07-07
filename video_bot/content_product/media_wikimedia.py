"""Реальные фото/видео с Wikimedia Commons (документальные проекты)."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

UA = "ContentFactoryBot/1.0 (telegram-agent-bot; documentary/educational)"
_API_PAUSE_SEC = 0.4

FFMPEG = None


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _api(params: dict) -> dict:
    base = "https://commons.wikimedia.org/w/api.php"
    q = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            time.sleep(_API_PAUSE_SEC)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                wait = 2.0 * (attempt + 1)
                logger.warning("Wikimedia 429, пауза %.1fs", wait)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Wikimedia API: исчерпаны повторы")


def search_files(query: str, *, limit: int = 10) -> list[str]:
    data = _api(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "srlimit": str(limit),
        }
    )
    return [h["title"] for h in data.get("query", {}).get("search", [])]


def file_url(title: str) -> tuple[str, str] | None:
    """title: File:Name.jpg → (url, mime)."""
    data = _api(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
        }
    )
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            continue
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url")
        mime = info.get("mime") or ""
        if url:
            return url, mime
    return None


def download_file(title: str, dest: Path) -> Path:
    got = file_url(title)
    if not got:
        raise FileNotFoundError(title)
    url, _mime = got
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            time.sleep(_API_PAUSE_SEC)
            with urllib.request.urlopen(req, timeout=180) as resp:
                dest.write_bytes(resp.read())
            return dest
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                wait = 3.0 * (attempt + 1)
                logger.warning("Wikimedia download 429, пауза %.1fs", wait)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Wikimedia download: исчерпаны повторы для {title}")


def ensure_mp4(src: Path, out_mp4: Path) -> Path:
    """webm/ogv/jpg → mp4 для монтажа."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("use photo_to_clip for images")
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out_mp4),
        ],
        check=True,
        capture_output=True,
    )
    return out_mp4


def photo_to_static_clip(
    image: Path,
    duration_sec: float,
    out_mp4: Path,
    *,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Реальное фото — pad fit, без обрезки."""
    from video_bot.content_product.frame_fit import pad_fit_chain

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf = f"{pad_fit_chain('format=yuv420p')}"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-vf",
            vf,
            "-t",
            f"{duration_sec:.2f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out_mp4),
        ],
        check=True,
        capture_output=True,
    )
    return out_mp4


# Проверенные файлы Commons — реальные кадры Чернобыля/Припяти (HQ)
CHERNOBYL_MEDIA: list[dict] = [
    {"file": "File:IAEA 02790015 (5613115146).jpg", "kind": "photo", "tags": ("aes", "plant", "1986", "hook", "disaster")},
    {"file": "File:Chernobyl Reactor 4 - Where Disaster Occurred - Chernobyl Exclusion Zone - Northern Ukraine - 01 (27099656425).jpg", "kind": "photo", "tags": ("reactor", "block4", "explosion", "disaster", "aes")},
    {"file": "File:Chernobyl Reactor 4 - Where Disaster Occurred - Chernobyl Exclusion Zone - Northern Ukraine - 03 (27031434071).jpg", "kind": "photo", "tags": ("reactor", "block4", "explosion")},
    {"file": "File:Chernobyl reactor 4.jpg", "kind": "photo", "tags": ("reactor", "block4", "aes")},
    {"file": "File:Chernobyl - power plant - reactor 4 02.jpg", "kind": "photo", "tags": ("reactor", "block4", "aes")},
    {"file": "File:Chernobyl Power Station aerial view.jpg", "kind": "photo", "tags": ("aes", "aerial", "plant", "today")},
    {"file": "File:Chernobyl NPP Site Panorama with NSC Construction - June 2013.jpg", "kind": "photo", "tags": ("aes", "plant", "today", "hook")},
    {"file": "File:Aerial view of Pripyat.jpg", "kind": "photo", "tags": ("pripyat", "aerial", "city", "evacuation", "abandoned")},
    {"file": "File:Pripyat (02710024).jpg", "kind": "photo", "tags": ("pripyat", "city", "abandoned")},
    {"file": "File:Abandoned buildings in Pripyat (02710148).jpg", "kind": "photo", "tags": ("pripyat", "abandoned", "city")},
    {"file": "File:Pripyat - ferris wheel.jpg", "kind": "photo", "tags": ("pripyat", "abandoned", "evacuation", "city")},
    {"file": "File:Sign at Entrance to Chernobyl Exclusion Zone - Northern Ukraine (26825581640).jpg", "kind": "photo", "tags": ("radiation", "sign", "zone")},
    {"file": "File:Chernobyl - radioactivity sign 01.jpg", "kind": "photo", "tags": ("radiation", "sign", "zone")},
    {"file": "File:Chernobyl Sarcophagus model.jpg", "kind": "photo", "tags": ("sarcophagus", "confinement", "today")},
    {"file": "File:Chernobyl-4 and the Memorial 2009-001.jpg", "kind": "photo", "tags": ("memorial", "liquidators", "reactor")},
    {"file": "File:Radioactive vehicles near the Yanov train station, Pripyat.webm", "kind": "video", "tags": ("pripyat", "radiation", "video", "vehicles", "abandoned")},
    {"file": "File:Radioactive Young Pioneer camp nestled in Chernobyl's \"Red Forest\".webm", "kind": "video", "tags": ("red forest", "video", "radiation", "forest")},
]


def _kind_from_title(title: str) -> str:
    low = title.lower()
    if low.endswith((".webm", ".ogv", ".mpeg", ".mp4", ".mov")):
        return "video"
    return "photo"


def _extra_wikimedia(tag_l: str, registry, limit: int = 15) -> list[dict]:
    """Доп. кадры с Commons, если исчерпан локальный пул."""
    import time

    queries = [
        "Chernobyl nuclear",
        "Pripyat abandoned",
        "Chernobyl reactor 4",
        "Chernobyl exclusion zone",
    ]
    tag_word = tag_l.split()[0] if tag_l else ""
    found: list[dict] = []
    seen: set[str] = {m["file"] for m in CHERNOBYL_MEDIA}
    for q in queries:
        query = f"{q} {tag_word}".strip()
        try:
            time.sleep(0.6)
            titles = search_files(query, limit=12)
        except Exception:
            continue
        for title in titles:
            low = title.lower()
            if low.endswith((".svg", ".png", ".gif")):
                continue
            if title in seen or registry.is_used(title):
                continue
            seen.add(title)
            found.append({"file": title, "kind": _kind_from_title(title), "tags": ()})
            if len(found) >= limit:
                return found
    return found


def resolve_chernobyl_media(
    tag: str,
    cache_dir: Path,
    pick: int = 0,
    *,
    registry=None,
    used: set[str] | None = None,
) -> tuple[Path, str, str]:
    """Подбор реального медиа. Возвращает (path, kind, key). Без повторов в ролике."""
    from video_bot.content_product.media_registry import MediaRegistry

    cache_dir.mkdir(parents=True, exist_ok=True)
    if registry is None:
        registry = MediaRegistry()
        if used:
            for k in used:
                registry.claim(k)

    tag_l = tag.lower()
    videos = [m for m in CHERNOBYL_MEDIA if m["kind"] == "video" and any(t in tag_l for t in m["tags"])]
    photos = [m for m in CHERNOBYL_MEDIA if m["kind"] == "photo" and any(t in tag_l for t in m["tags"])]
    if "video" in tag_l and videos:
        pool = videos
    else:
        pool = videos + photos if videos else (photos or CHERNOBYL_MEDIA)

    fresh = [m for m in pool if not registry.is_used(m["file"])]
    if not fresh:
        fresh = [m for m in CHERNOBYL_MEDIA if not registry.is_used(m["file"])]
    if not fresh:
        fresh = _extra_wikimedia(tag_l, registry)
    if not fresh:
        raise RuntimeError(
            f"Нет уникального медиа для «{tag}»: в ролике уже {len(registry)} кадров, повторы запрещены"
        )

    item = fresh[pick % len(fresh)]
    registry.must_claim(item["file"])

    safe = re.sub(r"[^\w.-]+", "_", item["file"].replace("File:", ""))[:80]
    ext = ".webm" if item["kind"] == "video" else ".jpg"
    raw = cache_dir / f"{safe}{ext}"
    if not raw.exists() or raw.stat().st_size < 1000:
        try:
            download_file(item["file"], raw)
        except Exception as e:
            registry.release(item["file"])
            alt = [m for m in fresh if m["file"] != item["file"] and not registry.is_used(m["file"])]
            if not alt:
                raise RuntimeError(f"Не удалось скачать медиа {item['file']}: {e}") from e
            item = alt[0]
            registry.must_claim(item["file"])
            safe = re.sub(r"[^\w.-]+", "_", item["file"].replace("File:", ""))[:80]
            ext = ".webm" if item["kind"] == "video" else ".jpg"
            raw = cache_dir / f"{safe}{ext}"
            download_file(item["file"], raw)
    if item["kind"] == "video":
        mp4 = cache_dir / f"{safe}.mp4"
        if not mp4.exists() or mp4.stat().st_size < 1000:
            ensure_mp4(raw, mp4)
        return mp4, "video", item["file"]
    return raw, "photo", item["file"]
