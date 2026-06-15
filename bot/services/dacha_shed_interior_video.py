"""
Подробное видео сборки изнутри.

Камера — в центре сарая на уровне глаз (1.6 м), смотрит к каждой стене.
Чередуются:
  - Широкие виды изнутри (как строится, как стоит)
  - Крупные планы стыков (блок+опора, стойка+рама, раскос, верхний угол, стропило)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

from bot.services.dacha_shed_parts_ru import part_name

# ═══════════════════════════════════════════════════════
#  Физические константы (метры)
# ═══════════════════════════════════════════════════════
BLOCK_H  = 0.14
FOOT_H   = 0.08
FOOT_TOP = BLOCK_H + FOOT_H   # 0.22 — гнездо стойки
FRAME_Z  = 0.04               # обвязка на ЗЕМЛЕ (не на блоках, не в опоре)
PROFILE  = 0.022
EYE_H    = 1.60

VIDEO_W, VIDEO_H = 1280, 720
CAPTION_H = 88


# ═══════════════════════════════════════════════════════
#  Примитивы для mplot3d
# ═══════════════════════════════════════════════════════

def _line3(ax, p0, p1, **kw):
    ax.plot3D([p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]], **kw)


def _box3(ax, cx, cy, z0, z1, hw, color, alpha=1.0, zorder=2):
    """Вертикальный столбик (для блока / опоры)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    faces = [
        [(cx-hw, cy-hw, z0), (cx+hw, cy-hw, z0), (cx+hw, cy-hw, z1), (cx-hw, cy-hw, z1)],
        [(cx-hw, cy+hw, z0), (cx+hw, cy+hw, z0), (cx+hw, cy+hw, z1), (cx-hw, cy+hw, z1)],
        [(cx-hw, cy-hw, z0), (cx-hw, cy+hw, z0), (cx-hw, cy+hw, z1), (cx-hw, cy-hw, z1)],
        [(cx+hw, cy-hw, z0), (cx+hw, cy+hw, z0), (cx+hw, cy+hw, z1), (cx+hw, cy-hw, z1)],
        [(cx-hw, cy-hw, z1), (cx+hw, cy-hw, z1), (cx+hw, cy+hw, z1), (cx-hw, cy+hw, z1)],
    ]
    col = Poly3DCollection(faces, alpha=alpha, zorder=zorder)
    col.set_facecolor(color)
    col.set_edgecolor("#00000033")
    ax.add_collection3d(col)


def _beam3(ax, p0, p1, hw, color, alpha=1.0):
    """Квадратный профиль по оси (p0→p1)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    p0, p1 = np.array(p0, float), np.array(p1, float)
    axis = p1 - p0
    length = np.linalg.norm(axis)
    if length < 1e-6:
        return
    ax_v = axis / length
    # перпендикуляр
    ref = np.array([0, 0, 1.0])
    if abs(np.dot(ax_v, ref)) > 0.9:
        ref = np.array([1.0, 0, 0])
    u = np.cross(ax_v, ref); u /= np.linalg.norm(u)
    v = np.cross(ax_v, u)
    corners_2d = [(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)]
    faces = []
    c0 = [p0 + u*a + v*b for a, b in corners_2d]
    c1 = [p1 + u*a + v*b for a, b in corners_2d]
    n = len(c0)
    for i in range(n):
        j = (i + 1) % n
        faces.append([c0[i], c0[j], c1[j], c1[i]])
    faces.append(c0)
    faces.append(c1)
    col = Poly3DCollection(faces, alpha=alpha)
    col.set_facecolor(color)
    col.set_edgecolor("#00000022")
    ax.add_collection3d(col)


# ═══════════════════════════════════════════════════════
#  Рисование структуры
# ═══════════════════════════════════════════════════════

def _post_xy(spec: "ShedV3StableSpec"):
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    return [(x, y) for x in (0.0, L/2, L) for y in (0.0, D)]


def _wall_top(spec: "ShedV3StableSpec", y: float) -> float:
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    D  = spec.depth_mm / 1000.0
    return fh + (bh - fh) * (y / D)


def draw_shed_3d(ax, spec: "ShedV3StableSpec",
                 *,
                 show_blocks=True, show_feet=True, show_frame=True,
                 show_posts=True, show_braces=False, show_top=False,
                 show_door=False, show_rafters=False, show_purlins=False,
                 new_part: Optional[str] = None):
    """
    new_part — тип детали, добавляемой в этом шаге.
    Все остальные части рисуются приглушённо; новая — ярко.
    """
    L  = spec.length_mm / 1000.0
    D  = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0

    hw = PROFILE / 2

    # цвета: DIM = предыдущие шаги, FULL = текущий новый шаг
    def color(part: str, full: str, dim: str, alpha_dim=0.45):
        if new_part is None or new_part == part:
            return full, 1.0
        return dim, alpha_dim

    C_CONC,   a_conc   = color("block",  "#8e8e8e", "#c0c0c0")
    C_FOOT,   a_foot   = color("foot",   "#e07000", "#f5bb6a")
    C_FRAME,  a_frame  = color("frame",  "#6b4520", "#b89070")
    C_POST,   a_post   = color("post",   "#cc4400", "#f08060")
    C_CONN,   a_conn   = color("post",   "#ff9800", "#f5bb6a")   # corner_post
    C_BRACE,  a_brace  = color("brace",  "#8b5500", "#c4986a")
    C_TOP,    a_top    = color("top",    "#6b4520", "#b89070")
    C_RAFTER, a_rafter = color("rafter", "#b07820", "#d4a860")
    C_DOOR,   a_door   = color("door",   "#3e2010", "#9e7050")

    posts = _post_xy(spec)

    # земля
    ax.plot_surface(
        np.array([[0, L], [0, L]]),
        np.array([[0, 0], [D, D]]),
        np.zeros((2, 2)),
        color="#e8e8e8", alpha=0.4, zorder=0
    )

    # блоки — ВНУТРИ периметра рамы, не снаружи, поэтому рама не проходит сквозь
    if show_blocks:
        for px, py in posts:
            _box3(ax, px, py, 0, BLOCK_H, 0.09, C_CONC, alpha=a_conc)

    # опоры (выше рамы, поверх блоков)
    if show_feet:
        for px, py in posts:
            _box3(ax, px, py, BLOCK_H, FOOT_TOP, 0.055, C_FOOT, alpha=a_foot, zorder=4)

    # нижняя обвязка — на земле (ниже блоков и опор)
    if show_frame:
        inset = 0.028
        sides = [
            (inset, 0, L - inset, 0), (L, inset, L, D - inset),
            (L - inset, D, inset, D), (0, D, 0, inset),
        ]
        for x0, y0, x1, y1 in sides:
            _beam3(ax, (x0, y0, FRAME_Z), (x1, y1, FRAME_Z), hw * 2, C_FRAME, alpha=a_frame)
        for px, py in ((0, 0), (L, 0), (L, D), (0, D)):
            _box3(ax, px, py, FRAME_Z, FRAME_Z + hw * 6, 0.034, C_CONN, alpha=a_conn, zorder=6)

    # стойки — низ в гнезде опоры (FOOT_TOP), проходят через corner_post на раме
    if show_posts:
        for px, py in posts:
            h = _wall_top(spec, py)
            _beam3(ax, (px, py, FRAME_Z), (px, py, h), hw * 2, C_POST, alpha=a_post)

    # раскосы
    if show_braces:
        z_lo = FRAME_Z + 0.30
        for yw, zt in ((0.0, fh), (D, bh)):
            _beam3(ax, (0, yw, z_lo), (L, yw, zt - 0.20), hw * 1.5, C_BRACE, alpha=a_brace)
            _beam3(ax, (L, yw, z_lo), (0, yw, zt - 0.20), hw * 1.5, C_BRACE, alpha=a_brace)
        for xw in (0.0, L):
            zt = (fh + bh) * 0.5
            _beam3(ax, (xw, 0, z_lo), (xw, D, zt - 0.20), hw * 1.5, C_BRACE, alpha=a_brace)
            _beam3(ax, (xw, D, z_lo), (xw, 0, zt - 0.20), hw * 1.5, C_BRACE, alpha=a_brace)

    # верхняя обвязка
    if show_top:
        sides_3d = [(0,0,L,0), (L,0,L,D), (L,D,0,D), (0,D,0,0)]
        for x0,y0,x1,y1 in sides_3d:
            _beam3(ax, (x0,y0,_wall_top(spec,y0)), (x1,y1,_wall_top(spec,y1)), hw*2, C_TOP, alpha=a_top)

    # дверной проём
    if show_door:
        dx0 = spec.door_offset_left_mm / 1000.0
        dx1 = dx0 + spec.door_width_mm / 1000.0
        dh  = spec.door_height_mm / 1000.0
        _beam3(ax, (dx0, 0, 0), (dx0, 0, dh), hw*2, C_DOOR, alpha=a_door)
        _beam3(ax, (dx1, 0, 0), (dx1, 0, dh), hw*2, C_DOOR, alpha=a_door)
        _beam3(ax, (dx0, 0, dh), (dx1, 0, dh), hw*2, C_DOOR, alpha=a_door)

    # стропила
    if show_rafters:
        n = spec.rafter_count_n
        xs = [L * i / (n-1) for i in range(n)] if n > 1 else [0, L]
        for rx in xs:
            _beam3(ax, (rx, 0, fh), (rx, D, bh), hw*2, C_RAFTER, alpha=a_rafter)

    # прогоны
    if show_purlins:
        for frac in (0.33, 0.67):
            y = D * frac
            z = _wall_top(spec, y) + 0.06
            _beam3(ax, (0, y, z), (L, y, z), hw*1.5, C_TOP, alpha=a_top)


# ═══════════════════════════════════════════════════════
#  Крупный план стыка (отдельная фигура)
# ═══════════════════════════════════════════════════════

def draw_joint_detail(ax, spec: "ShedV3StableSpec", joint: str) -> bool:
    """Крупный план стыка. Возвращает False если нужна 2D-фигура (не 3D ax)."""
    if joint == "corner_base":
        return False  # рисуется отдельно в 2D

    hw  = PROFILE / 2 * 2.5
    C_CONC  = "#8e8e8e"
    C_FOOT  = "#e07000"
    C_FRAME = "#6b4520"
    C_POST  = "#cc4400"
    C_CONN  = "#ff9800"

    if joint == "brace_top":
        # стойка
        _beam3(ax, (0, 0, 0), (0, 0, 1.1), hw, C_POST)
        # раскос снизу к вершине
        _beam3(ax, (0, 0, 0.75), (0.85, 0, 0.18), hw*0.9, "#8b5500", alpha=0.95)
        # brace_45 коннектор
        _box3(ax, 0, 0, 0.73, 0.77+hw*5, 0.036, C_CONN)
        ax.text(0.08, 0.04, 0.85, "стойка", color=C_POST,  fontsize=11, fontweight="bold")
        ax.text(0.12, 0.04, 0.55, part_name("brace_45"), color=C_CONN, fontsize=11, fontweight="bold")
        ax.text(0.35, 0.04, 0.35, "раскос ← угол 45°", color="#8b5500", fontsize=11, fontweight="bold")
        ax.set_xlim(-0.15, 1.05)
        ax.set_ylim(-0.3, 0.3)
        ax.set_zlim(0.1, 1.25)
        ax.view_init(elev=18, azim=-35)

    elif joint == "top_corner":
        # стойка
        _beam3(ax, (0, 0, 0), (0, 0, 0.75), hw, C_POST)
        # две обвязки в разные стороны
        _beam3(ax, (0, 0, 0.75), (0.85, 0, 0.75), hw, C_FRAME)
        _beam3(ax, (0, 0, 0.75), (0, 0.75, 0.75), hw, C_FRAME)
        # corner_90 коннектор
        _box3(ax, 0, 0, 0.74, 0.76+hw*5, 0.04, C_CONN)
        ax.text(0.08, 0.05, 0.88, part_name("corner_90"), color=C_CONN,  fontsize=11, fontweight="bold")
        ax.text(0.35, 0.05, 0.80, "обвязка →", color=C_FRAME, fontsize=11, fontweight="bold")
        ax.text(0.05, 0.35, 0.80, "обвязка ↗", color=C_FRAME, fontsize=11, fontweight="bold")
        ax.text(0.05, 0.05, 0.45, "стойка", color=C_POST,  fontsize=11, fontweight="bold")
        ax.set_xlim(-0.15, 1.0)
        ax.set_ylim(-0.15, 0.9)
        ax.set_zlim(0.25, 1.0)
        ax.view_init(elev=28, azim=-28)

    elif joint == "rafter_seat":
        # верхняя обвязка
        _beam3(ax, (-0.45, 0, 0.75), (0.5, 0, 0.75), hw, C_FRAME)
        # стропило — наклонное
        _beam3(ax, (0, 0, 0.75), (0, 0.95, 0.40), hw, "#b07820")
        # rafter_seat коннектор
        _box3(ax, 0, 0, 0.74, 0.78+hw*5, 0.04, C_CONN)
        ax.text(-0.38, 0.04, 0.80, "обвязка", color=C_FRAME,    fontsize=11, fontweight="bold")
        ax.text(0.07,  0.04, 0.90, part_name("rafter_seat"), color=C_CONN, fontsize=11, fontweight="bold")
        ax.text(0.05,  0.55, 0.52, "стропило", color="#b07820",  fontsize=11, fontweight="bold")
        ax.set_xlim(-0.6, 0.6)
        ax.set_ylim(-0.2, 1.1)
        ax.set_zlim(0.45, 1.05)
        ax.view_init(elev=22, azim=-42)

    ax.set_facecolor("#ffffff")
    ax.grid(False)
    ax.set_axis_off()
    return True


# ═══════════════════════════════════════════════════════
#  Сценарий
# ═══════════════════════════════════════════════════════

@dataclass
class Scene:
    step_label: str
    caption: str
    show_blocks:  bool = False
    show_feet:    bool = False
    show_frame:   bool = False
    show_posts:   bool = False
    show_braces:  bool = False
    show_top:     bool = False
    show_door:    bool = False
    show_rafters: bool = False
    show_purlins: bool = False
    new_part: Optional[str] = None    # что добавлено в этом шаге
    elev: float = 18
    azim: float = -40
    detail_joint: Optional[str] = None
    hold: int = 24   # кадров паузы (24 при 10 fps = 2.4 сек)


def _make_scenes(spec: "ShedV3StableSpec") -> List[Scene]:
    fh = spec.front_height_mm / 1000.0
    opora = part_name("foot_base")
    ugol_stoyka = part_name("corner_post")
    krep_raskos = part_name("brace_45")
    ugol_90 = part_name("corner_90")
    derzhatel_strop = part_name("rafter_seat")

    s: List[Scene] = []

    # ── Шаг 1: блоки ──────────────────────────────────────
    s.append(Scene("Шаг 1 — Фундамент",
                   "6 бетонных блоков: 4 угла + центр передней и задней стены",
                   show_blocks=True, new_part="block",
                   elev=32, azim=-50, hold=28))

    # ── СТЫК #1: блок + опора + стойка (крупный план) ─────
    s.append(Scene("Стык — Угол (вид сбоку)",
                   f"Стойка в «{opora}» на блоке. Обвязка на земле. Одна палка через «{ugol_stoyka}».",
                   detail_joint="corner_base", hold=36))

    # ── Шаг 2: опоры ──────────────────────────────────────
    s.append(Scene(f"Шаг 2 — {opora}",
                   f"Оранжевые опоры крепятся анкером М8 к каждому блоку",
                   show_blocks=True, show_feet=True, new_part="foot",
                   elev=24, azim=-30, hold=28))

    # ── Шаг 3а: обвязка сверху ─────────────────────────────
    s.append(Scene("Шаг 3 — Нижняя обвязка",
                   "Квадрат 3×3 м кладут на ЗЕМЛЮ. Углы рамы — над блоками. В опору НЕ вставляется!",
                   show_blocks=True, show_feet=True, show_frame=True, new_part="frame",
                   elev=26, azim=-42, hold=30))

    s.append(Scene("Шаг 3 — Вдоль передней стены",
                   "Рама на земле (коричневая). Опоры на блоках ВЫШЕ рамы — в них войдёт стойка.",
                   show_blocks=True, show_feet=True, show_frame=True,
                   elev=8, azim=-90, hold=28))

    # ── Шаг 4а: ставим стойки ─────────────────────────────
    s.append(Scene("Шаг 4 — Стойки 200 см",
                   f"Нижний конец стойки — в «{opora}». Через «{ugol_stoyka}» — крепим к раме.",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, new_part="post",
                   elev=10, azim=-88, hold=30))

    # ── Шаг 4б: вид изнутри угла ──────────────────────────
    s.append(Scene("Шаг 4 — Вид изнутри",
                   "Стоим внутри: шесть стоек стоят, рама внизу, опоры выходят наружу вниз",
                   show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
                   elev=14, azim=-52, hold=28))

    # ── Шаг 4в: вид снизу-вверх ───────────────────────────
    s.append(Scene("Шаг 4 — Смотрим вверх",
                   "Стойки уходят вверх. Левая сторона (фасад) — 200 см, правая (зад) — 150 см",
                   show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
                   elev=5, azim=180, hold=26))

    # ── СТЫК #2: раскос ───────────────────────────────────
    s.append(Scene(f"Стык — {krep_raskos}",
                   f"Раскос крепится к стойке «{krep_raskos}» вверху и внизу",
                   detail_joint="brace_top", hold=36))

    # ── Шаг 5а: раскосы ───────────────────────────────────
    s.append(Scene("Шаг 5 — Раскосы крест-накрест",
                   "По 2 раскоса на каждую из 4 стен (фасад, зад, лево, право). Итого 8 шт.",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, new_part="brace",
                   elev=14, azim=-58, hold=28))

    # ── Шаг 5б: изнутри на фасад ──────────────────────────
    s.append(Scene("Шаг 5 — Фасад изнутри",
                   "Передняя стена: крест из раскосов не даёт стойкам складываться",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True,
                   elev=7, azim=-90, hold=26))

    # ── СТЫК #3: верхний угол ─────────────────────────────
    s.append(Scene(f"Стык — {ugol_90}",
                   f"Вершина стойки + две верхних обвязки = угол. «{ugol_90}»",
                   detail_joint="top_corner", hold=36))

    # ── Шаг 6а: верхняя обвязка ───────────────────────────
    s.append(Scene("Шаг 6 — Верхняя обвязка",
                   "Верхняя рама: спереди высота 200 см, сзади 150 см → уклон крыши 14°",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, show_top=True, new_part="top",
                   elev=22, azim=-42, hold=28))

    # ── Шаг 6б: смотрим вверх внутри ──────────────────────
    s.append(Scene("Шаг 6 — Смотрим вверх изнутри",
                   "Видно уклон: левые (фасадные) стойки длиннее правых (задних)",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, show_top=True,
                   elev=38, azim=178, hold=28))

    # ── Шаг 7: дверь ──────────────────────────────────────
    s.append(Scene("Шаг 7 — Дверной проём",
                   "Два профиля 200 см + горизонталь сверху. Проём 100 см от левого угла",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, show_top=True,
                   show_door=True, new_part="door",
                   elev=10, azim=-88, hold=28))

    # ── СТЫК #4: стропило ─────────────────────────────────
    s.append(Scene(f"Стык — {derzhatel_strop}",
                   f"Стропило ложится в паз «{derzhatel_strop}» на верхней обвязке",
                   detail_joint="rafter_seat", hold=36))

    # ── Шаг 8: стропила ───────────────────────────────────
    s.append(Scene("Шаг 8 — Стропила",
                   "4 стропила 150 см, наклонены вдоль уклона от фасада к задней стене",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, show_top=True,
                   show_door=True, show_rafters=True, new_part="rafter",
                   elev=38, azim=165, hold=28))

    # ── Шаг 9: прогоны ────────────────────────────────────
    s.append(Scene("Шаг 9 — Обрешётка",
                   "2 прогона поперёк стропил — на них ляжет профлист крыши",
                   show_blocks=True, show_feet=True, show_frame=True,
                   show_posts=True, show_braces=True, show_top=True,
                   show_door=True, show_rafters=True, show_purlins=True,
                   new_part="rafter",  # общий цвет
                   elev=42, azim=160, hold=28))

    # ── Финал: плавный облёт ──────────────────────────────
    for azim in range(-55, 100, 12):
        s.append(Scene("Готово! Каркас собран.",
                       "Осталось обшить стены и крышу профлистом",
                       show_blocks=True, show_feet=True, show_frame=True,
                       show_posts=True, show_braces=True, show_top=True,
                       show_door=True, show_rafters=True, show_purlins=True,
                       elev=20, azim=float(azim), hold=3))

    return s


# ═══════════════════════════════════════════════════════
#  Рендер одной сцены → PIL Image
# ═══════════════════════════════════════════════════════

def _render_scene(spec: "ShedV3StableSpec", scene: Scene) -> "Image":
    import matplotlib.pyplot as plt
    from PIL import Image, ImageDraw, ImageFont

    from bot.services.dacha_shed_assembly_anim import _draw_corner_explainer

    fig = plt.figure(figsize=(12.8, 6.3))
    fig.patch.set_facecolor("#ffffff")

    if scene.detail_joint == "corner_base":
        ax = fig.add_subplot(111)
        ax.axis("off")
        _draw_corner_explainer(ax)
    else:
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor("#f8f8f8")
        ax.set_proj_type("persp", focal_length=0.18)
        ax.grid(False)
        ax.set_axis_off()

        L = spec.length_mm / 1000.0
        D = spec.depth_mm / 1000.0
        fh = spec.front_height_mm / 1000.0

        if scene.detail_joint:
            draw_joint_detail(ax, spec, scene.detail_joint)
        else:
            draw_shed_3d(
                ax, spec,
                show_blocks=scene.show_blocks,
                show_feet=scene.show_feet,
                show_frame=scene.show_frame,
                show_posts=scene.show_posts,
                show_braces=scene.show_braces,
                show_top=scene.show_top,
                show_door=scene.show_door,
                show_rafters=scene.show_rafters,
                show_purlins=scene.show_purlins,
                new_part=scene.new_part,
            )
            ax.set_xlim(0, L)
            ax.set_ylim(0, D)
            ax.set_zlim(0, fh + 0.4)
            ax.view_init(elev=scene.elev, azim=scene.azim)
            ax.set_box_aspect([L, D, fh + 0.4])

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=108, facecolor="#ffffff", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    src = Image.open(buf).convert("RGB")
    draw_h = VIDEO_H - CAPTION_H
    scale = min(VIDEO_W / src.width, draw_h / src.height)
    nw, nh = int(src.width * scale), int(src.height * scale)
    src = src.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), "#ffffff")
    canvas.paste(src, ((VIDEO_W - nw) // 2, (draw_h - nh) // 2))

    # подписи
    d = ImageDraw.Draw(canvas)
    d.line([(0, draw_h), (VIDEO_W, draw_h)], fill="#e0e0e0", width=2)

    def _font(size, bold=False):
        for p in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]:
            try:
                from PIL import ImageFont
                return ImageFont.truetype(p, size)
            except OSError:
                pass
        from PIL import ImageFont
        return ImageFont.load_default()

    # плашка с шагом
    is_detail = scene.detail_joint is not None
    tag_color = "#1565c0" if is_detail else "#b71c1c"
    tag_bg    = "#e3f2fd" if is_detail else "#ffebee"
    tw = 220
    d.rounded_rectangle([(12, draw_h+10), (12+tw, draw_h+52)],
                         radius=8, fill=tag_bg, outline=tag_color, width=2)
    label = scene.step_label
    d.text((12 + tw//2, draw_h+31), label,
           fill=tag_color, font=_font(20, True), anchor="mm")

    d.text((VIDEO_W//2 + tw//4, draw_h+31), scene.caption,
           fill="#222222", font=_font(21), anchor="mm")

    return canvas


# ═══════════════════════════════════════════════════════
#  Сборка видео
# ═══════════════════════════════════════════════════════

def build_interior_video(
    spec: "ShedV3StableSpec",
    path: Path,
    *,
    fps: float = 10.0,
) -> Path:
    from PIL import Image

    scenes = _make_scenes(spec)
    frames: List[Image.Image] = []

    total = len(scenes)
    for i, scene in enumerate(scenes):
        print(f"  {i+1}/{total}: {scene.step_label} — {scene.caption[:40]}")
        img = _render_scene(spec, scene)
        frames.extend([img.copy()] * scene.hold)

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".mp4":
        import imageio
        with imageio.get_writer(str(path), fps=fps, codec="libx264",
                                macro_block_size=1) as writer:
            for f in frames:
                writer.append_data(np.array(f))
        return path

    dur = int(1000 / fps)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=dur, loop=0, optimize=True)
    return path
