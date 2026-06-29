#!/usr/bin/env python3
"""Транскрибация видео курса numerologyHVD → oracle_bot/exclusive_hvd/transcripts/."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path.home() / "Downloads" / "numerologyHVD"
OUT_DIR = ROOT / "oracle_bot" / "exclusive_hvd" / "transcripts"


def _setup_ffmpeg_path() -> None:
    import os

    import imageio_ffmpeg

    bin_dir = OUT_DIR / "_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_link = bin_dir / "ffmpeg"
    src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_link.exists():
        try:
            ffmpeg_link.symlink_to(src)
        except OSError:
            import shutil

            shutil.copy2(src, ffmpeg_link)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video: Path, wav: Path) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(video),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def transcribe(wav: Path, model_name: str) -> dict:
    _setup_ffmpeg_path()
    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(str(wav), language="ru", fp16=False)
    return result


def process_one(video: Path, model_name: str, force: bool) -> Path:
    stem = video.stem
    out_txt = OUT_DIR / f"{stem}.txt"
    out_json = OUT_DIR / f"{stem}.json"
    if out_txt.exists() and not force:
        print(f"skip {video.name}")
        return out_txt

    wav = OUT_DIR / "_audio" / f"{stem}.wav"
    print(f"audio {video.name} …")
    extract_audio(video, wav)
    print(f"whisper {video.name} ({model_name}) …")
    result = transcribe(wav, model_name)
    text = (result.get("text") or "").strip()
    out_txt.write_text(text + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        wav.unlink()
    except OSError:
        pass
    print(f"done {out_txt.name} ({len(text)} chars)")
    return out_txt


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    p.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    p.add_argument("--force", action="store_true")
    p.add_argument("--only", help="substring filter for filenames")
    args = p.parse_args()

    if not args.src.is_dir():
        print(f"Папка не найдена: {args.src}", file=sys.stderr)
        return 1

    videos = sorted(args.src.glob("*.mp4"), key=lambda x: x.stat().st_size)
    if args.only:
        videos = [v for v in videos if args.only.lower() in v.name.lower()]
    if not videos:
        print("Нет mp4", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _setup_ffmpeg_path()
    for v in videos:
        try:
            process_one(v, args.model, args.force)
        except Exception as e:
            print(f"ERR {v.name}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
