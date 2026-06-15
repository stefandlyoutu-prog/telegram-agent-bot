#!/usr/bin/env python3
"""Сарай v5 Stable: 3×3, без резки, инструкция + 3D-видео + GIF-сборка."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = Path("/Users/polzovatel/Downloads/dacha-shed-v5-stable")


def main() -> None:
    from bot.services.dacha_shed_v3_stable import DEFAULT_SHED_V3, build_shed_v3_archive

    out = DEFAULT_OUT
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).expanduser()
    zip_path = build_shed_v3_archive(out, DEFAULT_SHED_V3)
    sc = DEFAULT_SHED_V3.stick_counts()
    gif = out / "instrukcii" / "sborka-animaciya.gif"
    vid = out / "instrukcii" / "sborka-video.mp4"
    vid3d = out / "instrukcii" / "sborka-3d.mp4"
    pdf = out / "instrukcii" / "instrukciya-poshagovaya.pdf"
    print(f"OK folder: {out}")
    print(f"OK zip:    {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    print(f"Sticks: 200cm×{sc[2000]} 150cm×{sc[1500]} 100cm×{sc[1000]}")
    print(f"Braces: {DEFAULT_SHED_V3.brace_count}  Posts: {DEFAULT_SHED_V3.post_count}")
    print(f"PDF:  {pdf}  ({'есть' if pdf.is_file() else 'НЕТ'})")
    print(f"GIF:  {gif}  ({'есть' if gif.is_file() else 'НЕТ'})")
    print(f"Video MP4: {vid}  ({'есть' if vid.is_file() else 'НЕТ'})")
    print(f"3D MP4:    {vid3d}  ({'есть' if vid3d.is_file() else 'НЕТ'})")
    if zip_path.is_file():
        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if "sborka-animaciya" in n or "sborka-video" in n or "instrukciya-poshagovaya" in n]
            print("В ZIP:", *names, sep="\n  ")


if __name__ == "__main__":
    main()
