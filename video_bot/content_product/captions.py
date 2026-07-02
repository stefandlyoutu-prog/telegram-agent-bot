"""Субтитры в стиле Hormozi / TikTok faceless."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_bot.generate import W, H

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_BOLD, size)
    except OSError:
        from video_bot.generate import _font as gf

        return gf(size)


def render_kinetic_caption(
    lines: list[str],
    highlight: str,
    path: Path,
    *,
    stage: str = "proof",
) -> Path:
    """
    Крупный текст по центру экрана (не внизу).
    Акцентное слово — жёлтым, остальное — белое, жирная обводка.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = []
    for ln in lines[:2]:
        raw_lines.extend(textwrap.wrap(ln.strip(), width=14) or [ln.strip()])
    raw_lines = [x for x in raw_lines if x][:2]
    if not raw_lines:
        raw_lines = ["СМОТРИ"]

    hook = stage == "hook"
    fs = 78 if hook else 68
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(fs)
    sub_font = _font(42)

    # лёгкий градиент снизу (не коробка)
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(H - 520, H):
        alpha = int(140 * (y - (H - 520)) / 520)
        gd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, grad)
    draw = ImageDraw.Draw(img)

    block_h = len(raw_lines) * (fs + 18)
    y0 = int(H * 0.38) - block_h // 2

    hi_up = highlight.upper().strip()

    for i, line in enumerate(raw_lines):
        y = y0 + i * (fs + 18)
        words = line.split()
        # если highlight в строке — подсветим
        if hi_up and hi_up in line.upper():
            _draw_stroked_center(draw, line, y, font, fill=(255, 220, 50))
        else:
            _draw_stroked_center(draw, line, y, font, fill=(255, 255, 255))

    # бейдж стадии (hook/cta)
    if stage in ("hook", "cta"):
        # без эмодзи: PIL-шрифт не содержит эмодзи-глифов, вместо них рисуется «□»
        badge = "СМОТРИ ДО КОНЦА" if stage == "hook" else "ССЫЛКА В ОПИСАНИИ"
        _draw_stroked_center(draw, badge, H - 180, sub_font, fill=(255, 200, 80))

    img.save(path)
    return path


def render_documentary_caption(
    lines: list[str],
    highlight: str,
    path: Path,
    *,
    stage: str = "proof",
) -> Path:
    """Кинематографичные титры: дата сверху, факт снизу — без «продающих» бейджей."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # верхняя плашка (дата / hook)
    top_bar = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    td = ImageDraw.Draw(top_bar)
    for y in range(120):
        a = int(160 * (1 - y / 120))
        td.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    img.paste(top_bar, (0, 0), top_bar)
    draw = ImageDraw.Draw(img)

    # нижняя плашка
    bar_h = 280
    bar = Image.new("RGBA", (W, bar_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for y in range(bar_h):
        alpha = int(200 * y / bar_h)
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img.paste(bar, (0, H - bar_h), bar)
    draw = ImageDraw.Draw(img)

    date_font = _font(44)
    main_font = _font(62 if stage == "hook" else 56)
    hi_font = _font(72 if stage == "hook" else 64)

    line_top = (lines[0] if lines else "").strip()[:28]
    line_bot = (lines[1] if len(lines) > 1 else highlight).strip()[:24]
    hi_up = highlight.upper().strip()

    if line_top:
        _draw_stroked_center(draw, line_top, 52, date_font, fill=(200, 200, 210))

    y_main = H - bar_h + 70
    if hi_up and hi_up in line_bot.upper():
        _draw_stroked_center(draw, line_bot, y_main, hi_font, fill=(255, 210, 80))
    else:
        _draw_stroked_center(draw, line_bot or hi_up, y_main, main_font, fill=(245, 245, 245))

    # тонкая красная линия — акцент репортажа
    draw.line([(80, H - bar_h + 18), (W - 80, H - bar_h + 18)], fill=(180, 40, 40, 200), width=3)

    img.save(path)
    return path


def _draw_stroked_center(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill) -> None:
    for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, 3), (-3, 3), (3, -3)):
        draw.text((W // 2 + dx, y + dy), text, font=font, fill=(0, 0, 0, 230), anchor="ma")
    draw.text((W // 2, y), text, font=font, fill=fill, anchor="ma")
