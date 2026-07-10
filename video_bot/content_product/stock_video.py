"""Stock-видео: Pexels / Pixabay API + fallback."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from video_bot.broll import ensure_stock_cache, image_to_motion_clip
from video_bot.content_product.broll_strict import (
    TOPIC_TEMPLATES,
    query_allowed,
    queries_for_scene,
    video_meta_allowed,
)
from video_bot.content_product.frame_fit import blur_fit_overlay, pad_fit_chain
from video_bot.content_product.media_wikimedia import (
    photo_to_static_clip,
    resolve_chernobyl_media,
)
from video_bot.generate import FPS, H, W

# .env проекта (PEXELS_API_KEY, PIXABAY_API_KEY)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[2].parent / "m-money-hub" / ".env")

logger = logging.getLogger(__name__)

FFMPEG = None

# Один публичный клип Pixabay (fallback без API)
_FALLBACK_MP4 = "https://cdn.pixabay.com/video/2020/05/25/40130-424930032_large.mp4"

# ID клипов, которые не используем (лица / неподходящий контент)
BLOCKLIST_PEXELS_IDS: set[int] = {
    6115070,
    8360178,
    12909800,
    7308301,
}

# Запросы с «лицами» — понижаем приоритет
_FACE_HINTS = ("portrait", "face", "smiling", "woman", "man", "people", "girl", "boy", "child")


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _api_get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def search_pexels_video(query: str, cache_dir: Path, *, pick: int = 0, topic_key: str | None = None) -> Path | None:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        logger.debug("PEXELS_API_KEY не задан")
        return None
    if topic_key and not query_allowed(topic_key, query):
        return None
    q = urllib.parse.quote(query)
    page = 1 + (pick // 8)
    url = (
        f"https://api.pexels.com/videos/search?query={q}"
        f"&per_page=15&orientation=portrait&page={page}"
    )
    try:
        data = _api_get(url, headers={"Authorization": key, "User-Agent": "M-ContentFactory/1.0"})
    except Exception as e:
        logger.warning("Pexels search %s: %s", query, e)
        return None

    videos = data.get("videos") or []
    if topic_key:
        videos = [v for v in videos if video_meta_allowed(topic_key, v)]

    def score(v: dict) -> tuple:
        vid = int(v.get("id") or 0)
        dur = int(v.get("duration") or 99)
        url_l = (v.get("url") or "").lower()
        face_penalty = 1 if any(h in url_l for h in _FACE_HINTS) else 0
        blocked = 1 if vid in BLOCKLIST_PEXELS_IDS else 0
        dur_penalty = 0 if 4 <= dur <= 22 else 1
        return (blocked, face_penalty, dur_penalty, abs(dur - 12))

    videos = sorted(videos, key=score)
    if not videos:
        return None
    vid = videos[pick % len(videos)]
    if int(vid.get("id") or 0) in BLOCKLIST_PEXELS_IDS:
        return None

    files = sorted(
        vid.get("video_files") or [],
        key=lambda f: (f.get("height") or 0),
        reverse=True,
    )
    for f in files:
        link = f.get("link")
        h = f.get("height") or 0
        if not link or h < 720 or h > 2200:
            continue
        dest = cache_dir / f"pexels_{vid.get('id', 0)}_{pick}.mp4"
        if dest.exists() and dest.stat().st_size > 50_000:
            return dest
        try:
            return _download(link, dest)
        except Exception as e:
            logger.warning("Pexels download: %s", e)
    return None


def search_pixabay_video(query: str, cache_dir: Path) -> Path | None:
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    q = urllib.parse.quote(query)
    url = f"https://pixabay.com/api/videos/?key={key}&q={q}&per_page=5&safesearch=true"
    try:
        data = _api_get(url)
    except Exception as e:
        logger.warning("Pixabay search %s: %s", query, e)
        return None
    for hit in data.get("hits") or []:
        vids = hit.get("videos") or {}
        for quality in ("large", "medium", "small"):
            info = vids.get(quality) or {}
            link = info.get("url")
            if not link:
                continue
            dest = cache_dir / f"pixabay_{hit.get('id', 0)}_{quality}.mp4"
            if dest.exists() and dest.stat().st_size > 50_000:
                return dest
            try:
                return _download(link, dest)
            except Exception as e:
                logger.warning("Pixabay download: %s", e)
    return None


def ensure_fallback_video(cache_dir: Path) -> Path:
    dest = cache_dir / "fallback_stock.mp4"
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    return _download(_FALLBACK_MP4, dest)


# Кэш query+pick → локальный файл
_query_cache: dict[str, Path] = {}


def _pexels_key(path: Path) -> str:
    m = re.search(r"pexels_(\d+)_", path.name)
    if m:
        return f"pexels:{m.group(1)}"
    return f"pexels:file:{path.name}"


def resolve_broll(
    query: str,
    cache_dir: Path,
    *,
    prefer_video: bool = True,
    photo_paths: list[Path] | None = None,
    photo_idx: int = 0,
    pick: int = 0,
    topic_key: str | None = None,
    strict: bool = False,
    registry=None,
) -> tuple[Path, str]:
    """Вернуть (путь, тип 'video'|'photo'). Без повторов при registry."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    if prefer_video:
        for attempt in range(20):
            pick_i = pick + attempt
            cache_key = f"{topic_key or ''}::{query}::{pick_i}"
            if cache_key in _query_cache and _query_cache[cache_key].exists():
                got = _query_cache[cache_key]
            else:
                got = search_pexels_video(query, cache_dir, pick=pick_i, topic_key=topic_key)
                if not got and not strict:
                    got = search_pixabay_video(query, cache_dir)
                if not got and not strict:
                    got = ensure_fallback_video(cache_dir)
                if got:
                    _query_cache[cache_key] = got
            if not got:
                break
            key = _pexels_key(got)
            if registry and registry.is_used(key):
                continue
            if registry:
                registry.must_claim(key)
            return got, "video"
        if strict:
            raise RuntimeError(f"Нет уникального видео по запросу: {query!r} (topic={topic_key})")
        fb = ensure_fallback_video(cache_dir)
        return fb, "video"

    photos = photo_paths or ensure_stock_cache(cache_dir / "photos")
    for attempt in range(max(len(photos), 1) * 2):
        idx = (photo_idx + attempt) % max(len(photos), 1)
        p = photos[idx] if photos else ensure_stock_cache(cache_dir / "photos")[0]
        key = f"stock_photo:{p.name}"
        if registry and registry.is_used(key):
            continue
        if registry:
            registry.must_claim(key)
        return p, "photo"
    # Все фото «заняты» — синтетический кадр, но ролик не падает
    from video_bot.broll import _synthetic_photo

    syn = _synthetic_photo(cache_dir / "photos")
    return syn, "photo"


def trim_video_native(
    src: Path,
    duration_sec: float,
    out: Path,
    *,
    start_offset: float = 0.0,
    hands_focus: bool = False,
) -> Path:
    """Реальное видео: blur-fit 9:16, без обрезки объекта."""
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.8, duration_sec)
    post = f"fps={FPS},format=yuv420p"
    fc = f"[0:v]{blur_fit_overlay(post)}"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-ss",
            str(start_offset),
            "-i",
            str(src),
            "-filter_complex",
            fc,
            "-t",
            f"{dur:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def trim_vertical_clip(
    src: Path,
    duration_sec: float,
    out: Path,
    *,
    start_offset: float = 0.0,
    hands_focus: bool = False,
) -> Path:
    """Кроп 9:16 + лёгкий зум."""
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.8, duration_sec)
    crop = f"crop={W}:{H}" if not hands_focus else f"crop={W}:{H}:0:ih/5"
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"{crop},"
        f"zoompan=z='min(zoom+0.0012,1.1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={int(dur * FPS)}:s={W}x{H}:fps={FPS},"
        f"eq=saturation=1.15:brightness=0.02,"
        f"vignette=PI/6"
    )
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-ss",
            str(start_offset),
            "-i",
            str(src),
            "-vf",
            vf,
            "-t",
            f"{dur:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def build_scene_visual(
    scene_query: str,
    duration_sec: float,
    work_dir: Path,
    scene_id: int,
    *,
    photo_paths: list[Path],
    photo_start: int,
    topic_key: str | None = None,
    strict: bool = False,
    registry=None,
) -> Path:
    """Сцена: video B-roll; strict — только тема, без fallback и без zoompan."""
    from video_bot.broll import concat_video_clips

    work_dir.mkdir(parents=True, exist_ok=True)
    cut = min(1.8, max(1.0, duration_sec / 3))
    n = max(2, min(4, int(duration_sec / cut)))
    durs: list[float] = []
    rem = duration_sec
    for i in range(n):
        d = cut if i < n - 1 else rem
        durs.append(max(0.85, d))
        rem -= d
    if rem > 0.15:
        durs[-1] += rem

    if topic_key and topic_key in TOPIC_TEMPLATES:
        alt_queries = queries_for_scene(topic_key, scene_query, scene_id, 0)
    else:
        alt_queries = [scene_query, f"{scene_query} b roll", f"{scene_query} close up"]

    parts: list[Path] = []
    offset = 0.0
    hands = "hand" in scene_query.lower() or "finger" in scene_query.lower()
    for j, d in enumerate(durs):
        q = alt_queries[j % len(alt_queries)]
        src, kind = resolve_broll(
            q,
            work_dir / "stock_cache",
            prefer_video=True,
            pick=scene_id * 3 + j,
            topic_key=topic_key,
            strict=strict,
            registry=registry,
        )
        clip = work_dir / f"s{scene_id}_v{j}.mp4"
        if kind == "video":
            trim_video_native(src, d, clip, start_offset=offset, hands_focus=hands)
            offset += d * 0.7
        elif strict:
            photo_to_static_clip(src, d, clip)
        else:
            image_to_motion_clip(src, d, clip, zoom_in=(j % 2 == 0))
        parts.append(clip)

    merged = work_dir / f"scene_{scene_id}_vis.mp4"
    return concat_video_clips(parts, merged)


def build_scene_visual_wikimedia(
    scene_query: str,
    duration_sec: float,
    work_dir: Path,
    scene_id: int,
    *,
    registry=None,
) -> Path:
    """Документальная сцена: только реальные фото/видео Wikimedia Commons."""
    from video_bot.broll import concat_video_clips

    work_dir.mkdir(parents=True, exist_ok=True)
    cache = work_dir / "wikimedia_cache"
    cut = min(2.2, max(1.2, duration_sec / 2))
    n = max(1, min(3, int(duration_sec / cut)))
    durs: list[float] = []
    rem = duration_sec
    for i in range(n):
        d = cut if i < n - 1 else rem
        durs.append(max(0.9, d))
        rem -= d
    if rem > 0.1:
        durs[-1] += rem

    parts: list[Path] = []
    offset = 0.0
    for j, d in enumerate(durs):
        src, kind, _key = resolve_chernobyl_media(
            scene_query, cache, pick=scene_id * 3 + j, registry=registry
        )
        clip = work_dir / f"wm_s{scene_id}_v{j}.mp4"
        if kind == "video":
            trim_video_native(src, d, clip, start_offset=offset)
            offset += d * 0.5
        else:
            photo_to_static_clip(src, d, clip)
        parts.append(clip)

    merged = work_dir / f"scene_{scene_id}_vis.mp4"
    return concat_video_clips(parts, merged)
