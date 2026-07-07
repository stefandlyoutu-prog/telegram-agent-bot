"""B-roll: фото Pexels → движение (Ken Burns) + склейка клипов."""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

from video_bot.generate import FPS, H, W

FFMPEG = None

# Только объекты: ноутбук, деньги, клавиатура — без портретов людей
STOCK_PHOTOS: list[str] = [
    "https://images.pexels.com/photos/590022/pexels-photo-590022.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/4968384/pexels-photo-4968384.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/607812/pexels-photo-607812.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/7943977/pexels-photo-7943977.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/4475707/pexels-photo-4475707.jpeg?auto=compress&w=1200",
]


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def ensure_stock_cache(cache_dir: Path) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, url in enumerate(STOCK_PHOTOS):
        dest = cache_dir / f"stock_{i:02d}.jpg"
        if not dest.exists() or dest.stat().st_size < 1000:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    dest.write_bytes(resp.read())
            except Exception:
                continue
        if dest.exists() and dest.stat().st_size > 1000:
            paths.append(dest)
    if not paths:
        raise RuntimeError("Не удалось скачать stock-фото для B-roll")
    return paths


def image_to_motion_clip(
    image: Path,
    duration_sec: float,
    out_mp4: Path,
    *,
    zoom_in: bool = True,
) -> Path:
    """Ken Burns: плавный зум + лёгкий pan — как в faceless Shorts."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(duration_sec * FPS))
    if zoom_in:
        z_expr = f"1+0.12*on/{frames}"
    else:
        z_expr = f"1.12-0.12*on/{frames}"
    vf = (
        f"scale=1300:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={W}x{H}:fps={FPS},"
        f"eq=brightness=0.03:saturation=1.15,"
        f"vignette=PI/5"
    )
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
            f"{duration_sec:.3f}",
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


def concat_video_clips(clips: list[Path], out_mp4: Path) -> Path:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    lst = out_mp4.with_suffix(".txt")
    lst.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            str(out_mp4),
        ],
        check=True,
        capture_output=True,
    )
    lst.unlink(missing_ok=True)
    return out_mp4
