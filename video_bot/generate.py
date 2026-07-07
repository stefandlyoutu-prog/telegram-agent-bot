"""Генерация видео: lyrics / статья → MP4 (PIL + imageio-ffmpeg)."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Sequence

W, H = 1080, 1920
FPS = 24


def _font(size: int = 48):
    from PIL import ImageFont

    for name in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_bg(frame_i: int, total: int) -> tuple[int, int, int]:
    t = frame_i / max(1, total)
    r = int(15 + 40 * math.sin(t * math.pi))
    g = int(10 + 30 * math.cos(t * math.pi * 0.7))
    b = int(45 + 50 * t)
    return (r, g, b)


def _draw_centered_text(draw, text: str, y: int, font, fill=(255, 255, 255)) -> None:
    from PIL import ImageDraw

    if not isinstance(draw, ImageDraw.ImageDraw):
        return
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)


def build_lyrics_video(
    *,
    title: str,
    lyrics: str,
    out_path: Path,
    sec_per_line: float = 3.0,
) -> Path:
    import numpy as np
    from PIL import Image, ImageDraw
    import imageio

    lines = [ln.strip() for ln in lyrics.splitlines() if ln.strip()]
    if not lines:
        lines = ["(пусто)"]
    title_font = _font(56)
    line_font = _font(44)
    small_font = _font(32)
    frames: list = []
    total_frames = int(len(lines) * sec_per_line * FPS) + FPS * 2
    fi = 0
    for idx, line in enumerate(lines):
        chunk_frames = int(sec_per_line * FPS)
        wrapped = textwrap.wrap(line, width=22) or [line]
        for _ in range(chunk_frames):
            img = Image.new("RGB", (W, H), _gradient_bg(fi, total_frames))
            draw = ImageDraw.Draw(img)
            _draw_centered_text(draw, title[:60], 120, title_font, fill=(255, 220, 100))
            start_y = H // 2 - len(wrapped) * 28
            for j, wl in enumerate(wrapped):
                _draw_centered_text(draw, wl, start_y + j * 56, line_font)
            if idx + 1 < len(lines):
                nxt = textwrap.wrap(lines[idx + 1], width=22)
                if nxt:
                    _draw_centered_text(
                        draw, nxt[0][:40] + "…", H - 200, small_font, fill=(180, 180, 200)
                    )
            frames.append(np.array(img))
            fi += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(out_path), frames, fps=FPS, codec="libx264", quality=8)
    return out_path


def build_article_video(
    *,
    title: str,
    body: str,
    out_path: Path,
    sec_per_slide: float = 5.0,
) -> Path:
    import numpy as np
    from PIL import Image, ImageDraw
    import imageio

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = textwrap.wrap(body, width=400) or [body[:400]]
    slides: list[str] = [title]
    for p in paragraphs:
        slides.extend(textwrap.wrap(p, width=38) or [p[:80]])
    title_font = _font(52)
    body_font = _font(40)
    frames: list = []
    total = int(len(slides) * sec_per_slide * FPS)
    fi = 0
    for slide in slides:
        wrapped = textwrap.wrap(slide, width=24) if len(slide) > 30 else [slide]
        for _ in range(int(sec_per_slide * FPS)):
            img = Image.new("RGB", (W, H), _gradient_bg(fi, total))
            draw = ImageDraw.Draw(img)
            font = title_font if slide == title else body_font
            start_y = 280
            for j, wl in enumerate(wrapped[:8]):
                _draw_centered_text(draw, wl, start_y + j * 52, font)
            frames.append(np.array(img))
            fi += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(out_path), frames, fps=FPS, codec="libx264", quality=8)
    return out_path
