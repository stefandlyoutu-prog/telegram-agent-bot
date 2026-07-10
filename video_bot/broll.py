"""B-roll: фото Pexels → движение (Ken Burns) + склейка клипов."""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

from video_bot.generate import FPS, H, W

FFMPEG = None

# Объекты без лиц: ноутбук, деньги, клавиатура, свечи, карты
STOCK_PHOTOS: list[str] = [
    "https://images.pexels.com/photos/590022/pexels-photo-590022.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/4968384/pexels-photo-4968384.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/607812/pexels-photo-607812.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/7943977/pexels-photo-7943977.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/4475707/pexels-photo-4475707.jpeg?auto=compress&w=1200",
    # Pixabay CDN — запасной источник, если Pexels недоступен
    "https://cdn.pixabay.com/photo/2016/11/29/08/41/keyboard-1869208_1280.jpg",
    "https://cdn.pixabay.com/photo/2017/07/10/23/45/crystal-249201_1280.jpg",
    "https://cdn.pixabay.com/photo/2015/09/05/22/33/office-925806_1280.jpg",
]


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _synthetic_photo(cache_dir: Path) -> Path:
    """Градиент через ffmpeg — последний fallback, если CDN недоступны."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / "fallback_synthetic.jpg"
    if dest.exists() and dest.stat().st_size > 5000:
        return dest
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1a1030:s={W}x{H}:d=1",
            "-vf",
            "geq=r='40+20*sin(X/80)':g='30+15*sin(Y/60)':b='80+30*sin((X+Y)/100)'",
            "-frames:v",
            "1",
            str(dest),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    # минимальный JPEG-заголовок через однотонный кадр
    subprocess.run(
        [_ffmpeg(), "-y", "-f", "lavfi", "-i", f"color=c=0x2a1848:s={W}x{H}:d=1", "-frames:v", "1", str(dest)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return dest


def ensure_stock_cache(cache_dir: Path) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, url in enumerate(STOCK_PHOTOS):
        dest = cache_dir / f"stock_{i:02d}.jpg"
        if not dest.exists() or dest.stat().st_size < 1000:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = resp.read()
                if len(data) > 1000:
                    dest.write_bytes(data)
            except Exception:
                continue
        if dest.exists() and dest.stat().st_size > 1000:
            paths.append(dest)
    if not paths:
        paths.append(_synthetic_photo(cache_dir))
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
        timeout=120,
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
