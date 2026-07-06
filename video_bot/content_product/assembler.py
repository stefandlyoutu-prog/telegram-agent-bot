"""Сборка продуктового ролика: воронка → видеоряд → озвучка → субтитры."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from video_bot.batch_factory import _audio_duration_sec, concat_audio, mux_video_audio
from video_bot.broll import concat_video_clips, ensure_stock_cache
from video_bot.content_product.captions import render_documentary_caption, render_kinetic_caption
from video_bot.content_product.documentary_edit import build_documentary_scene
from video_bot.content_product.media_registry import MediaRegistry
from video_bot.content_product.models import VideoScript
from video_bot.content_product.music_bed import MUSIC_PROFILES, ensure_music, mix_voice_and_music
from video_bot.content_product.stock_video import (
    build_scene_visual,
    build_scene_visual_wikimedia,
)
from video_bot.content_product.tts_engine import synthesize_voice_mp3
from video_bot.generate import H, W

FFMPEG = None


def _add_qr_to_last_scene(cap_path: Path, link: str) -> None:
    """Впечатывает QR-код в финальную (CTA) сцену — ссылки в Shorts/Reels не кликабельны,
    а QR можно навести камерой прямо с экрана (в т.ч. со стоп-кадра/скриншота)."""
    if not link:
        return
    try:
        import qrcode
        from PIL import Image

        qr_img = qrcode.make(link, box_size=8, border=2).convert("RGBA")
        size = 340
        qr_img = qr_img.resize((size, size))
        frame = Image.new("RGBA", (size + 28, size + 28), (255, 255, 255, 235))
        frame.paste(qr_img, (14, 14))

        cap = Image.open(cap_path).convert("RGBA")
        x = (cap.width - frame.width) // 2
        y = cap.height - frame.height - 260
        cap.alpha_composite(frame, (x, y))
        cap.save(cap_path)
    except Exception:  # noqa: BLE001
        pass  # QR — бонус, не должен ронять рендер ролика


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _overlay_caption(video: Path, caption_png: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(video),
            "-i",
            str(caption_png),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p",
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


async def build_product_video(
    script: VideoScript,
    out_path: Path,
    *,
    work_dir: Path | None = None,
    min_duration_sec: float = 55.0,
    media_mode: str = "pexels",
    topic_key: str | None = None,
    strict_broll: bool = False,
) -> Path:
    """Полный конвейер контент-продукта.

    media_mode: pexels | wikimedia
    strict_broll: только тема, без fallback и без Ken Burns на видео
    """
    meta = script.meta or {}
    mode = media_mode or meta.get("media") or "pexels"
    style = meta.get("style", "promo")
    tkey = topic_key or meta.get("topic_key")
    music_profile = meta.get("music_profile")
    strict = strict_broll or mode == "wikimedia" or tkey in ("stretch_ceiling", "chernobyl")
    is_documentary = style == "documentary" or mode == "wikimedia"

    wd = work_dir or out_path.parent / "_product_tmp"
    wd.mkdir(parents=True, exist_ok=True)
    photos = ensure_stock_cache(wd / "photos")

    audio_parts: list[Path] = []
    durations: list[float] = []
    for i, sc in enumerate(script.scenes):
        mp3 = wd / f"voice_{i}.mp3"
        await synthesize_voice_mp3(sc.voice, mp3)
        audio_parts.append(mp3)
        durations.append(max(1.8, _audio_duration_sec(mp3) + 0.1))

    voice = wd / "voice_full.mp3"
    concat_audio(audio_parts, voice, gap_sec=0.08)

    total_voice_sec = sum(durations)
    if music_profile:
        prof = MUSIC_PROFILES.get(music_profile, {})
        bed = ensure_music(music_profile, wd / "music_cache")
        if bed:
            mixed = wd / "voice_with_music.mp3"
            mix_voice_and_music(
                voice,
                bed,
                mixed,
                duration_sec=total_voice_sec + 0.5,
                music_volume=float(prof.get("volume", 0.2)),
                fade_in=float(prof.get("fade_in", 1.5)),
                fade_out=float(prof.get("fade_out", 2.5)),
            )
            voice = mixed

    scene_clips: list[Path] = []
    photo_i = 0
    registry = MediaRegistry()
    caption_fn = render_documentary_caption if is_documentary else render_kinetic_caption
    for i, (sc, dur) in enumerate(zip(script.scenes, durations)):
        if is_documentary:
            vis = build_documentary_scene(
                sc.broll_search, dur, wd, i, registry=registry
            )
        elif mode == "wikimedia":
            vis = build_scene_visual_wikimedia(sc.broll_search, dur, wd, i, registry=registry)
        else:
            vis = build_scene_visual(
                sc.broll_search,
                dur,
                wd,
                i,
                photo_paths=photos,
                photo_start=photo_i,
                topic_key=tkey,
                strict=strict,
                registry=registry,
            )
        photo_i += 2
        cap = caption_fn(
            sc.caption_lines,
            sc.highlight,
            wd / f"cap_{i}.png",
            stage=sc.stage,
        )
        if i == len(script.scenes) - 1:
            _add_qr_to_last_scene(cap, script.cta)
        capped = wd / f"scene_{i}.mp4"
        _overlay_caption(vis, cap, capped)
        scene_clips.append(capped)

    visual = wd / "visual.mp4"
    concat_video_clips(scene_clips, visual)
    mux_video_audio(visual, voice, out_path, min_duration_sec=min_duration_sec)
    return out_path


async def build_product_video_async(
    topic: str,
    out_path: Path,
    *,
    use_llm_script: bool = True,
    work_dir: Path | None = None,
    min_duration_sec: float = 55.0,
) -> Path:
    from video_bot.content_product.script_engine import generate_script

    script = await generate_script(topic, use_llm=use_llm_script)
    return await build_product_video(
        script,
        out_path,
        work_dir=work_dir,
        min_duration_sec=min_duration_sec,
    )
