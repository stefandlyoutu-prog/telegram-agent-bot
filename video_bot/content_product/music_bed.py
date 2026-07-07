"""Фоновая музыка под задачу: тихо, но слышно."""

from __future__ import annotations

import logging
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG = None

# Royalty-free (Archive.org / открытые лицензии)
MUSIC_PROFILES: dict[str, dict] = {
    "mystical": {
        "url": "https://archive.org/download/dark-ambient-3/dark%20ambient%203.mp3",
        "volume": 0.22,
        "fade_in": 2.0,
        "fade_out": 3.0,
    },
    "documentary": {
        "url": "https://archive.org/download/dark-ambient-3/dark%20ambient%203.mp3",
        "volume": 0.20,
        "fade_in": 1.5,
        "fade_out": 2.5,
    },
    "corporate": {
        "url": "https://archive.org/download/everything_is_gonna_be_alright/everything_is_gonna_be_alright.mp3",
        "volume": 0.16,
        "fade_in": 1.0,
        "fade_out": 2.0,
    },
    "uplifting": {
        "url": "https://archive.org/download/everything_is_gonna_be_alright/everything_is_gonna_be_alright.mp3",
        "volume": 0.18,
        "fade_in": 0.8,
        "fade_out": 1.5,
    },
}


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def ensure_music(profile: str, cache_dir: Path) -> Path | None:
    cfg = MUSIC_PROFILES.get(profile)
    if not cfg:
        logger.warning("Неизвестный music profile: %s", profile)
        return None
    dest = cache_dir / f"music_{profile}.mp3"
    try:
        return _download(cfg["url"], dest)
    except Exception as e:
        logger.warning("Музыка %s: %s", profile, e)
        return None


def mix_voice_and_music(
    voice_mp3: Path,
    music_mp3: Path,
    out_mp3: Path,
    *,
    duration_sec: float,
    music_volume: float = 0.22,
    fade_in: float = 1.5,
    fade_out: float = 2.5,
) -> Path:
    """Голос + фон. Музыка тише голоса (~20%)."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    dur = max(1.0, duration_sec)
    fo = min(fade_out, dur * 0.15)
    fi = min(fade_in, dur * 0.1)
    fade_out_start = max(0, dur - fo)
    # loop music, fade, mix
    fc = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{dur:.2f},"
        f"afade=t=in:st=0:d={fi:.2f},"
        f"afade=t=out:st={fade_out_start:.2f}:d={fo:.2f},"
        f"volume={music_volume:.3f}[bg];"
        f"[0:a]volume=1.0[voice];"
        f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(voice_mp3),
            "-i",
            str(music_mp3),
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(out_mp3),
        ],
        check=True,
        capture_output=True,
    )
    return out_mp3
