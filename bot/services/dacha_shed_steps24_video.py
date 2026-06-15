"""
Короткое видео: только шаги 2–4 (блок → опора → обвязка → стойки).
Медленно, с 2D-схемой угла из PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

from bot.services.dacha_shed_parts_ru import part_name

VIDEO_W, VIDEO_H = 1280, 720
CAPTION_H = 96
FPS = 8.0


@dataclass
class Step24Scene:
    step: str
    caption: str
    hold: int = 40          # кадров (~5 с при 8 fps)
    corner_2d: bool = False
    show_blocks: bool = False
    show_feet: bool = False
    show_frame: bool = False
    show_posts: bool = False
    posts_count: int = 6    # 0..6 появляются по одной на шаге 4
    elev: float = 22
    azim: float = -42


def _scenes() -> List[Step24Scene]:
    opora = part_name("foot_base")
    ugol_stoyka = part_name("corner_post")
    return [
        Step24Scene(
            "Введение",
            "Шаги 2–4 — самое важное. Смотрите до конца: угол показан дважды — сбоку и в 3D.",
            hold=32,
        ),
        Step24Scene(
            "Шаг 2",
            "6 бетонных блоков: 4 угла + середина передней и задней стены. Блок ровно, уровень.",
            show_blocks=True,
            elev=34, azim=-48, hold=40,
        ),
        Step24Scene(
            "Шаг 2",
            f"На каждый блок — «{opora}» + анкер М8. Гнездо пустое — сюда позже стойка.",
            show_blocks=True, show_feet=True,
            elev=28, azim=-38, hold=44,
        ),
        Step24Scene(
            "Главное!",
            "Вид СБОКУ у угла — как в PDF. Запомните: обвязка НЕ в опору.",
            corner_2d=True, hold=56,
        ),
        Step24Scene(
            "Шаг 3",
            f"Нижняя обвязка 3×3 м на ЗЕМЛЕ. Углы рамы — над блоками. В «{opora}» НЕ вставляется!",
            show_blocks=True, show_feet=True, show_frame=True,
            elev=26, azim=-40, hold=48,
        ),
        Step24Scene(
            "Шаг 3",
            "Вдоль передней стены: коричневая рама на земле, оранжевые опоры ВЫШЕ — в них войдёт стойка.",
            show_blocks=True, show_feet=True, show_frame=True,
            elev=7, azim=-90, hold=44,
        ),
        Step24Scene(
            "Шаг 3",
            "Проверьте диагонали квадрата — должны быть равны (±5 мм). Потом совместите углы над блоками.",
            show_blocks=True, show_feet=True, show_frame=True,
            elev=55, azim=-90, hold=36,
        ),
        Step24Scene(
            "Шаг 4 — стойка 1",
            f"Первая стойка 200 см: нижний конец — в гнездо «{opora}».",
            show_blocks=True, show_feet=True, show_frame=True,
            show_posts=True, posts_count=1,
            elev=12, azim=-88, hold=40,
        ),
        Step24Scene(
            "Шаг 4 — стойка 1",
            f"Та же палка проходит через «{ugol_stoyka}» на обвязке. Затяните М5, проверьте уровень.",
            show_blocks=True, show_feet=True, show_frame=True,
            show_posts=True, posts_count=1,
            corner_2d=True, hold=48,
        ),
        Step24Scene(
            "Шаг 4 — все стойки",
            "Так же — ещё 5 стоек: 4 угла + середина перед/зад. На 150 см спереди — правый косяк двери.",
            show_blocks=True, show_feet=True, show_frame=True,
            show_posts=True, posts_count=6,
            elev=14, azim=-52, hold=48,
        ),
        Step24Scene(
            "Готово (шаги 2–4)",
            "Дальше: раскосы (шаг 5), верхняя обвязка (6), крыша (7–9). См. PDF-инструкцию.",
            show_blocks=True, show_feet=True, show_frame=True,
            show_posts=True, posts_count=6,
            elev=18, azim=-35, hold=40,
        ),
    ]


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _caption_bar(img, step: str, caption: str):
    from PIL import Image, ImageDraw

    draw_h = VIDEO_H - CAPTION_H
    scale = min(VIDEO_W / img.width, draw_h / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    src = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), "#ffffff")
    canvas.paste(src, ((VIDEO_W - nw) // 2, (draw_h - nh) // 2))
    d = ImageDraw.Draw(canvas)
    d.line([(0, draw_h), (VIDEO_W, draw_h)], fill="#ccc", width=2)
    d.rounded_rectangle([(14, draw_h + 10), (200, draw_h + 54)], radius=8,
                        fill="#ffebee", outline="#b71c1c", width=2)
    d.text((107, draw_h + 32), step, fill="#b71c1c", font=_font(22, True), anchor="mm")
    # перенос длинного текста — две строки если длинный
    if len(caption) > 72:
        mid = caption.rfind(" ", 0, len(caption) // 2 + 20)
        if mid < 20:
            mid = len(caption) // 2
        d.text((VIDEO_W // 2 + 40, draw_h + 26), caption[:mid].strip(),
               fill="#222", font=_font(19), anchor="mm")
        d.text((VIDEO_W // 2 + 40, draw_h + 52), caption[mid:].strip(),
               fill="#222", font=_font(19), anchor="mm")
    else:
        d.text((VIDEO_W // 2 + 40, draw_h + 32), caption,
               fill="#222", font=_font(20), anchor="mm")
    return canvas


def _render_3d_partial(
    spec: "ShedV3StableSpec",
    scene: Step24Scene,
):
    import matplotlib.pyplot as plt
    from PIL import Image

    from bot.services.dacha_shed_interior_video import draw_shed_3d

    fig = plt.figure(figsize=(12.8, 6.4))
    fig.patch.set_facecolor("#ffffff")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#f8f8f8")
    ax.set_proj_type("persp", focal_length=0.2)
    ax.grid(False)
    ax.set_axis_off()

    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0

    # частичные стойки: рисуем все, но через new_part trick — проще нарисовать все posts
    # и обрезать визуально через posts_count — переопределим draw с лимитом
    _draw_partial(spec, ax, scene)

    ax.set_xlim(0, L)
    ax.set_ylim(0, D)
    ax.set_zlim(0, fh + 0.3)
    ax.view_init(elev=scene.elev, azim=scene.azim)
    ax.set_box_aspect([L, D, fh + 0.3])

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor="#ffffff", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _draw_partial(spec, ax, scene: Step24Scene):
    """draw_shed_3d с ограничением числа стоек."""
    from bot.services.dacha_shed_interior_video import (
        BLOCK_H, FOOT_TOP, FRAME_Z, PROFILE, _post_xy, _wall_top, _box3, _beam3,
    )
    import numpy as np

    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    hw = PROFILE / 2
    posts = _post_xy(spec)

    ax.plot_surface(
        np.array([[0, L], [0, L]]),
        np.array([[0, 0], [D, D]]),
        np.zeros((2, 2)),
        color="#e8e8e8", alpha=0.45, zorder=0,
    )

    if scene.show_blocks:
        for px, py in posts:
            _box3(ax, px, py, 0, BLOCK_H, 0.09, "#8e8e8e")

    if scene.show_feet:
        for px, py in posts:
            _box3(ax, px, py, BLOCK_H, FOOT_TOP, 0.055, "#e07000", zorder=4)

    if scene.show_frame:
        inset = 0.028
        for x0, y0, x1, y1 in [
            (inset, 0, L - inset, 0), (L, inset, L, D - inset),
            (L - inset, D, inset, D), (0, D, 0, inset),
        ]:
            _beam3(ax, (x0, y0, FRAME_Z), (x1, y1, FRAME_Z), hw * 2, "#6b4520")
        corners = {(0.0, 0.0), (L, 0.0), (L, D), (0.0, D)}
        for px, py in corners:
            _box3(ax, px, py, FRAME_Z, FRAME_Z + hw * 6, 0.034, "#ff9800", zorder=6)

    if scene.show_posts:
        n = scene.posts_count
        for i, (px, py) in enumerate(posts):
            if i >= n:
                break
            h = _wall_top(spec, py)
            _beam3(ax, (px, py, FRAME_Z), (px, py, h), hw * 2.2, "#cc4400")


def _render_2d_corner():
    import matplotlib.pyplot as plt
    from PIL import Image
    from bot.services.dacha_shed_assembly_anim import _draw_corner_explainer

    fig, ax = plt.subplots(figsize=(12.8, 6.4))
    fig.patch.set_facecolor("#ffffff")
    ax.axis("off")
    _draw_corner_explainer(ax)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120, facecolor="#ffffff", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _render_scene(spec: "ShedV3StableSpec", scene: Step24Scene):
    if scene.corner_2d and not scene.show_posts:
        img = _render_2d_corner()
    elif scene.corner_2d and scene.show_posts:
        # split: 3d small + 2d — for step 4 with corner, use 2d only (clearer)
        img = _render_2d_corner()
    elif scene.show_blocks or scene.show_feet or scene.show_frame or scene.show_posts:
        img = _render_3d_partial(spec, scene)
    else:
        import matplotlib.pyplot as plt
        from PIL import Image
        fig, ax = plt.subplots(figsize=(12.8, 6.4))
        fig.patch.set_facecolor("#ffffff")
        ax.axis("off")
        ax.text(0.5, 0.55, "Хозблок 3×3 «Стабл»", ha="center", fontsize=28, fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.42, "Шаги 2 – 4", ha="center", fontsize=22, color="#b71c1c", transform=ax.transAxes)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=110, facecolor="#ffffff")
        plt.close(fig)
        buf.seek(0)
        img = Image.open(buf).convert("RGB")
    return _caption_bar(img, scene.step, scene.caption)


def build_steps24_video(
    spec: "ShedV3StableSpec",
    path: Path,
    *,
    fps: float = FPS,
) -> Path:
    from PIL import Image

    frames: List[Image.Image] = []
    for sc in _scenes():
        img = _render_scene(spec, sc)
        frames.extend([img.copy()] * sc.hold)

    path.parent.mkdir(parents=True, exist_ok=True)
    import imageio
    with imageio.get_writer(str(path), fps=fps, codec="libx264", macro_block_size=1) as w:
        for f in frames:
            w.append_data(np.array(f))
    return path
