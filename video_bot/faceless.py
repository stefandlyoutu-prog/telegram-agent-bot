"""Faceless Shorts: B-roll + kinetic captions + нейро-озвучка (контент-ферма)."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from video_bot.batch_factory import Slide, _audio_duration_sec, concat_audio, mux_video_audio
from video_bot.broll import concat_video_clips, ensure_stock_cache, image_to_motion_clip
from video_bot.generate import W, H, _font
from video_bot.tts import DEFAULT_VOICE, synthesize_speech

FFMPEG = None
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _caption_font(size: int = 56):
    try:
        return ImageFont.truetype(FONT_BOLD, size)
    except OSError:
        return _font(size)


def render_caption_png(text: str, path: Path, *, hook: bool = False) -> Path:
    """Кинетический субтитр: жёлтый/белый текст с обводкой (стиль TikTok)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = text.replace("\\n", "\n").split("\n")
    flat: list[str] = []
    for ln in lines:
        flat.extend(textwrap.wrap(ln.strip(), width=18) or [ln.strip()])
    flat = [x for x in flat if x][:4]
    if not flat:
        flat = ["…"]

    img = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # полупрозрачная плашка
    draw.rounded_rectangle((40, 20, W - 40, 400), radius=24, fill=(0, 0, 0, 150))
    fs = 62 if hook else 52
    font = _caption_font(fs)
    y = 50
    for i, line in enumerate(flat):
        fill = (255, 230, 60) if (hook and i == 0) else (255, 255, 255)
        # обводка
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)):
            draw.text((W // 2 + dx, y + dy), line, font=font, fill=(0, 0, 0, 255), anchor="ma")
        draw.text((W // 2, y), line, font=font, fill=fill, anchor="ma")
        y += fs + 14
    img.save(path)
    return path


def overlay_caption_on_video(video: Path, caption_png: Path, out: Path) -> Path:
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
            f"[0:v][1:v]overlay=0:{H - 460}:format=auto,format=yuv420p",
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


def build_scene_broll(
    duration_sec: float,
    stock_paths: list[Path],
    start_idx: int,
    work_dir: Path,
    scene_id: int,
) -> Path:
    """2–3 быстрых кадра за сцену (смена каждые ~1.2–1.8 с — retention)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    cut = min(1.6, max(1.1, duration_sec / 3))
    n_cuts = max(2, min(4, int(duration_sec / cut)))
    seg_durs: list[float] = []
    rem = duration_sec
    for i in range(n_cuts):
        d = cut if i < n_cuts - 1 else rem
        seg_durs.append(max(0.9, d))
        rem -= d
    if rem > 0.2:
        seg_durs[-1] += rem

    parts: list[Path] = []
    for j, d in enumerate(seg_durs):
        img = stock_paths[(start_idx + j) % len(stock_paths)]
        clip = work_dir / f"scene_{scene_id}_cut_{j}.mp4"
        image_to_motion_clip(img, d, clip, zoom_in=(j % 2 == 0))
        parts.append(clip)
    merged = work_dir / f"scene_{scene_id}_raw.mp4"
    return concat_video_clips(parts, merged)


def build_faceless_video(
    slide_defs: Sequence[Slide],
    out_path: Path,
    *,
    work_dir: Path | None = None,
    min_duration_sec: float = 0,
    voice: str = DEFAULT_VOICE,
    subtitle: str = "",
) -> Path:
    wd = work_dir or out_path.parent / "_faceless_tmp"
    wd.mkdir(parents=True, exist_ok=True)
    cache = wd / "stock"
    stock = ensure_stock_cache(cache)

    # Озвучка по сценам → естественные паузы
    audio_parts: list[Path] = []
    durations: list[float] = []
    for i, sd in enumerate(slide_defs):
        mp3 = wd / f"v_{i}.mp3"
        synthesize_speech(sd.voice or sd.on_screen, mp3, voice=voice, rate="+4%")
        audio_parts.append(mp3)
        durations.append(max(2.0, _audio_duration_sec(mp3) + 0.15))

    full_audio = wd / "voice.mp3"
    concat_audio(audio_parts, full_audio, gap_sec=0.12)

    scene_videos: list[Path] = []
    stock_i = 0
    for i, (sd, dur) in enumerate(zip(slide_defs, durations)):
        raw = build_scene_broll(dur, stock, stock_i, wd, i)
        stock_i += 3
        cap = render_caption_png(sd.on_screen.replace("\n", " "), wd / f"cap_{i}.png", hook=(i == 0))
        capped = wd / f"scene_{i}.mp4"
        overlay_caption_on_video(raw, cap, capped)
        scene_videos.append(capped)

    silent = wd / "visual.mp4"
    concat_video_clips(scene_videos, silent)
    mux_video_audio(silent, full_audio, out_path, min_duration_sec=min_duration_sec)
    return out_path
