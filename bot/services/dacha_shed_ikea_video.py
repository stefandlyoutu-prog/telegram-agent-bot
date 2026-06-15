"""
Видео-сборка в стиле IKEA: белый фон, детали появляются по одной.
Физика: блок(z=0..0.14) → опора(z=0.14..0.22) → обвязка(z=0.04) → стойка(z=0..full_h)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

from bot.services.dacha_shed_parts_ru import part_name

from bot.services.dacha_shed_blueprints import (
    _draw_line_iso,
    _post_positions,
    _rafter_xs,
    _wall_top_z,
    iso_xy,
)

# ─── физические высоты ────────────────────────────────────────────────────────
GROUND_Z   = 0.0    # поверхность земли
BLOCK_H    = 0.14   # высота бетонного блока
FOOT_H     = 0.08   # высота пластиковой опоры
FOOT_TOP   = BLOCK_H + FOOT_H   # 0.22 — верх опоры (куда входит стойка снизу)
FRAME_Z    = 0.04   # нижняя обвязка лежит на земле

VIDEO_W, VIDEO_H = 1280, 720
CAPTION_H  = 90


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


@dataclass
class PartAnim:
    alpha: float = 0.0
    slide: float = 1.0   # 1=сверху, 0=на месте


@dataclass
class AnimState:
    parts: Dict[str, PartAnim] = field(default_factory=dict)
    caption: str = ""
    step_label: str = ""

    def p(self, key: str) -> PartAnim:
        if key not in self.parts:
            self.parts[key] = PartAnim()
        return self.parts[key]


def _lerp_state(a: AnimState, b: AnimState, t: float, new_keys) -> AnimState:
    t_eased = _ease_out(t)
    keys = set(a.parts) | set(b.parts)
    out = AnimState(
        caption=b.caption if t > 0.5 else a.caption,
        step_label=b.step_label,
    )
    for k in keys:
        pa = a.parts.get(k, PartAnim())
        pb = b.parts.get(k, PartAnim())
        if k in new_keys:
            # новая деталь: прилетает сверху
            out.parts[k] = PartAnim(alpha=t_eased, slide=1.0 - t_eased)
        else:
            out.parts[k] = PartAnim(
                alpha=pa.alpha + (pb.alpha - pa.alpha) * t_eased,
                slide=pa.slide + (pb.slide - pa.slide) * t_eased,
            )
    return out


# ─── ключевые состояния ───────────────────────────────────────────────────────

def _key_states(spec: "ShedV3StableSpec") -> List[AnimState]:
    states: List[AnimState] = []

    def snap(caption: str, step: str, visible: List[str]) -> AnimState:
        s = AnimState(caption=caption, step_label=step)
        for k in visible:
            s.p(k).alpha = 1.0
            s.p(k).slide = 0.0
        return s

    opora = part_name("foot_base")
    ugol_stoyka = part_name("corner_post")

    vis: List[str] = []

    states.append(AnimState(caption="Хозблок 3×3 м — пошаговая сборка", step_label=""))

    # шаг 1 — блоки
    for i in range(6):
        vis.append(f"block_{i}")
    states.append(snap("Бетонные блоки — 6 точек под фундамент", "Шаг 1", list(vis)))

    # шаг 2 — опоры на блоки
    for i in range(6):
        vis.append(f"foot_{i}")
    states.append(snap("Оранжевая опора крепится на блок анкером М8", "Шаг 2", list(vis)))

    # шаг 3 — нижняя обвязка
    for i in range(4):
        vis.append(f"base_{i}")
    states.append(snap("Нижняя обвязка — квадрат 3×3 м кладут на ЗЕМЛЮ", "Шаг 3", list(vis)))
    states.append(snap("Углы рамы над блоками. Обвязка вокруг блоков — в опору НЕ вставляется!", "Шаг 3", list(vis)))

    # шаг 4 — стойки
    for i in range(6):
        vis.append(f"post_{i}")
    states.append(snap(f"Стойки 200 см: низ в «{opora}», та же палка через «{ugol_stoyka}» на раме", "Шаг 4", list(vis)))

    # шаг 5 — раскосы
    for w in range(4):
        vis.append(f"brace_{w}")
    states.append(snap("Раскосы крест-накрест — без них каркас шатается", "Шаг 5", list(vis)))

    # шаг 6 — верхняя обвязка
    for i in range(4):
        vis.append(f"top_{i}")
    states.append(snap("Верхняя обвязка: спереди выше (200 см), сзади ниже (150 см)", "Шаг 6", list(vis)))

    # шаг 7 — дверь
    vis.append("door")
    states.append(snap("Дверной проём на фасаде — 100 см ширина", "Шаг 7", list(vis)))

    # шаг 8 — стропила
    for i in range(spec.rafter_count_n):
        vis.append(f"rafter_{i}")
    states.append(snap("Стропила крыши — четыре палки 150 см", "Шаг 8", list(vis)))

    # шаг 9 — прогоны
    for i in range(2):
        vis.append(f"purlin_{i}")
    states.append(snap("Обрешётка — под профлист, вдоль крыши", "Шаг 9", list(vis)))

    states.append(snap("Каркас готов. Крепите профлист.", "Готово!", list(vis)))
    return states


# ─── рисование одного кадра ──────────────────────────────────────────────────

def _slide_z(slide: float) -> float:
    """Смещение вверх при вылете детали (1 → из воздуха, 0 → на месте)."""
    return slide * 0.6


def _set_view(ax, spec: "ShedV3StableSpec") -> None:
    """Фиксированный ракурс: каркас крупно, снизу-спереди."""
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0

    # крайние точки в iso
    xs, ys = [], []
    for vx, vy, vz in [(0,0,0),(L,0,0),(0,D,0),(L,D,0),(0,0,fh),(L,0,fh),(0,D,fh),(L,D,fh)]:
        ix, iy = iso_xy(vx, vy, vz)
        xs.append(ix); ys.append(iy)

    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    rng = max(max(xs)-min(xs), max(ys)-min(ys))
    m = rng * 0.22  # поля
    ax.set_xlim(cx - rng/2 - m, cx + rng/2 + m)
    ax.set_ylim(cy - rng/2 - m * 0.5, cy + rng/2 + m * 1.6)
    ax.set_aspect("equal")


def draw_ikea_frame(ax, spec: "ShedV3StableSpec", state: AnimState) -> None:
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    posts = _post_positions(spec)

    C_BLOCK  = "#b0b0b0"   # бетон
    C_FOOT   = "#ff8c00"   # опора (оранжевая)
    C_FRAME  = "#7a5230"   # обвязка/прогон (тёмно-коричневый)
    C_POST   = "#e65100"   # стойка
    C_BRACE  = "#a0620a"   # раскос
    C_RAFTER = "#c9963a"   # стропила
    C_DOOR   = "#5d3015"   # дверь

    def get(key: str) -> PartAnim:
        return state.parts.get(key, PartAnim())

    def post_full_h(x: float, y: float) -> float:
        """Высота стойки от земли."""
        if y < 0.05:
            return fh
        if y > D - 0.05:
            return bh
        return _wall_top_z(spec, y)

    # ── земля: тонкая горизонтальная плоскость
    gpts = [iso_xy(x, y, GROUND_Z) for x, y in [(0,0),(L,0),(L,D),(0,D)]]
    gxs = [p[0] for p in gpts] + [gpts[0][0]]
    gys = [p[1] for p in gpts] + [gpts[0][1]]
    ax.fill(gxs, gys, color="#f0f0f0", ec="#d0d0d0", lw=0.8, zorder=0)

    # ── бетонные блоки
    for i, (px, py, _) in enumerate(posts):
        a = get(f"block_{i}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        # рисуем блок как заштрихованный ромб
        bw = 0.16  # полуширина блока
        corners = [(px-bw, py, GROUND_Z+dz), (px+bw, py, GROUND_Z+dz),
                   (px+bw, py, BLOCK_H+dz),  (px-bw, py, BLOCK_H+dz)]
        pts2d = [iso_xy(c[0], c[1], c[2]) for c in corners]
        ax.fill([p[0] for p in pts2d]+[pts2d[0][0]],
                [p[1] for p in pts2d]+[pts2d[0][1]],
                color=C_BLOCK, ec="#808080", lw=1.0, alpha=a.alpha, zorder=2)
        # верхняя грань
        top_pts = [iso_xy(px-bw, py-bw, BLOCK_H+dz), iso_xy(px+bw, py-bw, BLOCK_H+dz),
                   iso_xy(px+bw, py+bw, BLOCK_H+dz), iso_xy(px-bw, py+bw, BLOCK_H+dz)]
        ax.fill([p[0] for p in top_pts]+[top_pts[0][0]],
                [p[1] for p in top_pts]+[top_pts[0][1]],
                color="#c8c8c8", ec="#808080", lw=0.8, alpha=a.alpha, zorder=3)

    # ── опоры (оранжевые скобы на блоках)
    for i, (px, py, _) in enumerate(posts):
        a = get(f"foot_{i}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        fw = 0.06
        fp = [(px-fw, py, BLOCK_H+dz), (px+fw, py, BLOCK_H+dz),
              (px+fw, py, FOOT_TOP+dz), (px-fw, py, FOOT_TOP+dz)]
        fp2d = [iso_xy(c[0], c[1], c[2]) for c in fp]
        ax.fill([p[0] for p in fp2d]+[fp2d[0][0]],
                [p[1] for p in fp2d]+[fp2d[0][1]],
                color=C_FOOT, ec="#c45000", lw=1.2, alpha=a.alpha, zorder=4)

    # ── нижняя обвязка (лежит на земле)
    sides = [((0,0),(L,0)), ((L,0),(L,D)), ((L,D),(0,D)), ((0,D),(0,0))]
    for i, ((x0,y0),(x1,y1)) in enumerate(sides):
        a = get(f"base_{i}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        _draw_line_iso(ax, (x0, y0, FRAME_Z+dz), (x1, y1, FRAME_Z+dz),
                       color=C_FRAME, lw=7, alpha=a.alpha, zorder=5)

    # ── стойки — низ в гнезде опоры, проходят через corner_post на раме
    for i, (px, py, _) in enumerate(posts):
        a = get(f"post_{i}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        h = post_full_h(px, py)
        _draw_line_iso(ax, (px, py, FOOT_TOP+dz), (px, py, h+dz),
                       color=C_POST, lw=7, alpha=a.alpha, zorder=6)
        if a.alpha > 0.7:
            # corner_post на уровне обвязки
            cx2, cy2 = iso_xy(px, py, FRAME_Z + dz)
            ax.plot(cx2, cy2, "s", color="#ff9800", ms=8, zorder=7, alpha=a.alpha)

    # ── раскосы (крест по фасадным стенам)
    brace_walls = [(0.0, fh), (D, bh), (0.0, fh), (D, bh)]
    for wi in range(4):
        a = get(f"brace_{wi}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        y_wall = 0.0 if wi < 2 else D
        zt = fh if y_wall < 0.1 else bh
        _draw_line_iso(ax, (0, y_wall, FRAME_Z+0.25+dz), (L, y_wall, zt-0.18+dz),
                       color=C_BRACE, lw=3.5, alpha=a.alpha*0.9, zorder=5)
        _draw_line_iso(ax, (L, y_wall, FRAME_Z+0.25+dz), (0, y_wall, zt-0.18+dz),
                       color=C_BRACE, lw=3.5, alpha=a.alpha*0.9, zorder=5)

    # ── верхняя обвязка
    for i, ((x0,y0),(x1,y1)) in enumerate(sides):
        a = get(f"top_{i}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        z0 = _wall_top_z(spec, y0) + dz
        z1 = _wall_top_z(spec, y1) + dz
        _draw_line_iso(ax, (x0, y0, z0), (x1, y1, z1),
                       color=C_FRAME, lw=7, alpha=a.alpha, zorder=7)

    # ── дверной проём
    a = get("door")
    if a.alpha > 0:
        dz = _slide_z(a.slide)
        dx0 = spec.door_offset_left_mm / 1000.0
        dx1 = dx0 + spec.door_width_mm / 1000.0
        dh  = spec.door_height_mm / 1000.0
        for sx, ex in [(dx0, dx0), (dx1, dx1)]:
            _draw_line_iso(ax, (sx, 0, GROUND_Z+dz), (ex, 0, dh+dz),
                           color=C_DOOR, lw=4.5, alpha=a.alpha, zorder=8)
        _draw_line_iso(ax, (dx0, 0, dh+dz), (dx1, 0, dh+dz),
                       color=C_DOOR, lw=4.5, alpha=a.alpha, zorder=8)

    # ── стропила
    for ri, rx in enumerate(_rafter_xs(spec)):
        a = get(f"rafter_{ri}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        zf = _wall_top_z(spec, 0.0)
        zb = _wall_top_z(spec, D)
        _draw_line_iso(ax, (rx, 0, zf+dz), (rx, D, zb+dz),
                       color=C_RAFTER, lw=5, alpha=a.alpha, zorder=8)

    # ── прогоны
    for pi, frac in enumerate((0.33, 0.67)):
        a = get(f"purlin_{pi}")
        if a.alpha <= 0:
            continue
        dz = _slide_z(a.slide)
        y = D * frac
        z = _wall_top_z(spec, y) + 0.05
        _draw_line_iso(ax, (0, y, z+dz), (L, y, z+dz),
                       color=C_FRAME, lw=4.5, alpha=a.alpha, zorder=9)

    _set_view(ax, spec)


# ─── рендер одного кадра в PIL Image ─────────────────────────────────────────

def _render_pil(spec: "ShedV3StableSpec", state: AnimState) -> "Image":
    import matplotlib.pyplot as plt
    from PIL import Image, ImageDraw, ImageFont

    fig, ax = plt.subplots(figsize=(12.8, 6.6))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    draw_ikea_frame(ax, spec, state)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor="#ffffff")
    plt.close(fig)
    buf.seek(0)

    src = Image.open(buf).convert("RGB")
    draw_area_h = VIDEO_H - CAPTION_H
    scale = min(VIDEO_W / src.width, draw_area_h / src.height)
    nw, nh = int(src.width * scale), int(src.height * scale)
    src = src.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), "#ffffff")
    canvas.paste(src, ((VIDEO_W - nw) // 2, (draw_area_h - nh) // 2))

    # нижняя полоса с текстом
    d = ImageDraw.Draw(canvas)
    d.line([(0, draw_area_h), (VIDEO_W, draw_area_h)], fill="#e0e0e0", width=2)

    def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
        names = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for n in names:
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                pass
        return ImageFont.load_default()

    if state.step_label:
        d.text((VIDEO_W // 2, draw_area_h + 22), state.step_label,
               fill="#111111", font=font(28, True), anchor="mm")
    if state.caption:
        d.text((VIDEO_W // 2, draw_area_h + 60), state.caption,
               fill="#444444", font=font(21), anchor="mm")

    return canvas


# ─── сборка видео ─────────────────────────────────────────────────────────────

def build_ikea_assembly_video(
    spec: "ShedV3StableSpec",
    path: Path,
    *,
    frames_per_step: int = 10,
    hold_frames: int = 7,
    fps: float = 12.0,
) -> Path:
    from PIL import Image

    key_states = _key_states(spec)
    frames: List[Image.Image] = []

    def hold(st: AnimState, n: int) -> None:
        img = _render_pil(spec, st)
        frames.extend([img.copy()] * n)

    def transition(a: AnimState, b: AnimState) -> None:
        new_keys = {k for k, pb in b.parts.items()
                    if pb.alpha > a.parts.get(k, PartAnim()).alpha}
        for i in range(frames_per_step):
            t = (i + 1) / frames_per_step
            st = _lerp_state(a, b, t, new_keys)
            frames.append(_render_pil(spec, st))

    hold(key_states[0], hold_frames * 2)
    prev = key_states[0]
    for nxt in key_states[1:]:
        transition(prev, nxt)
        hold(nxt, hold_frames)
        prev = nxt
    hold(prev, hold_frames * 3)

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".mp4":
        import imageio
        import numpy as np
        with imageio.get_writer(str(path), fps=fps, codec="libx264",
                                macro_block_size=1) as writer:
            for f in frames:
                writer.append_data(np.array(f))
        return path

    # GIF fallback
    dur = int(1000 / fps)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=dur, loop=0, optimize=True)
    return path
