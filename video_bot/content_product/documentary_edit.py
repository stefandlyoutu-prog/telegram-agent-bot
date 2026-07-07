"""Монтаж репортажа: быстрые склейки, Ken Burns, цветокор, кроссфейды."""

from __future__ import annotations

import subprocess
from pathlib import Path

from video_bot.content_product.frame_fit import blur_fit_overlay, pad_fit_chain
from video_bot.content_product.media_wikimedia import resolve_chernobyl_media
from video_bot.generate import FPS, H, W

FFMPEG = None

# Холодный «документальный» грейд (BBC / Netflix shorts)
_DOC_GRADE = (
    "eq=saturation=0.68:brightness=-0.04:contrast=1.12:gamma=0.92,"
    "colorbalance=rs=-0.03:gs=-0.01:bs=0.07,"
    "vignette=angle=PI/4.5"
)

CUT_SEC = 2.0
XFADE_SEC = 0.28


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _pan_mode(idx: int) -> tuple[bool, str]:
    """zoom_in, pan: left|right|up|down|center"""
    modes = [
        (True, "right"),
        (False, "left"),
        (True, "up"),
        (False, "down"),
        (True, "center"),
    ]
    return modes[idx % len(modes)]


def photo_to_documentary_clip(
    image: Path,
    duration_sec: float,
    out_mp4: Path,
    *,
    cut_idx: int = 0,
) -> Path:
    """Архивное фото: медленный Ken Burns + документальный грейд."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.9, duration_sec)
    frames = max(1, int(dur * FPS))
    zoom_in, pan = _pan_mode(cut_idx)
    if zoom_in:
        z_expr = f"1.0+0.10*on/{frames}"
    else:
        z_expr = f"1.10-0.10*on/{frames}"
    if pan == "right":
        x_expr = f"iw/2-(iw/zoom/2)+20*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pan == "left":
        x_expr = f"iw/2-(iw/zoom/2)-20*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pan == "up":
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)-15*on/{frames}"
    elif pan == "down":
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)+15*on/{frames}"
    else:
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    fade_out = max(0.1, dur - XFADE_SEC)
    motion = (
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={W}x{H}:fps={FPS}"
    )
    post = (
        f"{_DOC_GRADE},"
        f"fade=t=in:st=0:d={XFADE_SEC:.2f},"
        f"fade=t=out:st={fade_out:.2f}:d={XFADE_SEC:.2f},"
        f"format=yuv420p"
    )
    vf = f"{pad_fit_chain(motion)},{post}"
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
            f"{dur:.3f}",
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


def video_to_documentary_clip(
    src: Path,
    duration_sec: float,
    out_mp4: Path,
    *,
    start_offset: float = 0.0,
) -> Path:
    """Реальное видео + грейд + мягкие fade."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.9, duration_sec)
    fade_out = max(0.1, dur - XFADE_SEC)
    post = (
        f"fps={FPS},"
        f"{_DOC_GRADE},"
        f"fade=t=in:st=0:d={XFADE_SEC:.2f},"
        f"fade=t=out:st={fade_out:.2f}:d={XFADE_SEC:.2f},"
        f"format=yuv420p"
    )
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
            str(out_mp4),
        ],
        check=True,
        capture_output=True,
    )
    return out_mp4


def _cut_durations(total_sec: float) -> list[float]:
    """2–2.5 сек на кадр — как в вертикальных репортажах."""
    n = max(2, int(total_sec / CUT_SEC + 0.45))
    base = total_sec / n
    durs = [base] * n
    drift = total_sec - sum(durs)
    if durs:
        durs[-1] += drift
    return [max(0.95, d) for d in durs]


def build_documentary_scene(
    scene_query: str,
    duration_sec: float,
    work_dir: Path,
    scene_id: int,
    *,
    registry,
) -> Path:
    """Сцена репортажа: уникальные кадры, быстрый монтаж."""
    from video_bot.broll import concat_video_clips

    work_dir.mkdir(parents=True, exist_ok=True)
    cache = work_dir / "wikimedia_cache"
    durs = _cut_durations(duration_sec)

    parts: list[Path] = []
    offset = 0.0
    for j, d in enumerate(durs):
        pick = scene_id * 7 + j
        src, kind, key = resolve_chernobyl_media(
            scene_query, cache, pick=pick, registry=registry
        )
        clip = work_dir / f"doc_s{scene_id}_c{j}.mp4"
        if kind == "video":
            video_to_documentary_clip(src, d, clip, start_offset=offset)
            offset += d * 0.45
        else:
            photo_to_documentary_clip(src, d, clip, cut_idx=scene_id * 3 + j)
        parts.append(clip)

    merged = work_dir / f"scene_{scene_id}_vis.mp4"
    return concat_video_clips(parts, merged)
