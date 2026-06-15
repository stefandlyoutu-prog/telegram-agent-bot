"""
Общая 3D-геометрия каркаса сарая (метры) — одна правда для всех рендеров.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import trimesh
import trimesh.transformations as tf

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

from bot.services.dacha_shed_interior_video import (
    BLOCK_H,
    FOOT_TOP,
    FRAME_Z,
    PROFILE,
    _post_xy,
    _wall_top,
)

SOCKET_D = 0.028  # глубина гнезда коннектора, м
_MM = 0.001
_CONNECTOR_MM: dict = {}


def _connector(name: str) -> trimesh.Trimesh:
    if name not in _CONNECTOR_MM:
        if name in ("tee_90", "inline_splice", "corner_90", "brace_45"):
            from bot.services.dacha_shed_kit import SHED_CONNECTOR_BUILDERS

            _CONNECTOR_MM[name] = SHED_CONNECTOR_BUILDERS[name]()
        else:
            from bot.services.dacha_trellis_kit import CONNECTOR_BUILDERS

            _CONNECTOR_MM[name] = CONNECTOR_BUILDERS[name]()
    return _CONNECTOR_MM[name].copy()


def beam_mesh(p0, p1, hw: float) -> Optional[trimesh.Trimesh]:
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        return None
    box = trimesh.creation.box([hw * 2, hw * 2, length])
    direction = axis / length
    rot = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], direction)
    box.apply_transform(rot)
    box.apply_translation((p0 + p1) * 0.5)
    return box


def block_mesh(cx: float, cy: float, z0: float, z1: float, hw: float) -> trimesh.Trimesh:
    h = z1 - z0
    box = trimesh.creation.box([hw * 2, hw * 2, max(h, 1e-4)])
    box.apply_translation([cx, cy, z0 + h * 0.5])
    return box


def post_bottom_z() -> float:
    """Низ стойки — от земли, через corner_post и foot_base вверх."""
    return max(0.02, FRAME_Z - SOCKET_D * 0.5)


def place_foot(px: float, py: float) -> trimesh.Trimesh:
    m = _connector("foot_base")
    m.apply_scale(_MM)
    z_min = m.bounds[0, 2]
    m.apply_translation([px, py, BLOCK_H - z_min])
    return m


def _rotate_corner(m: trimesh.Trimesh, px: float, py: float, L: float, D: float) -> None:
    if abs(px - L) < 1e-6 and abs(py) < 1e-6:
        m.apply_transform(tf.rotation_matrix(math.pi, [0, 0, 1]))
    elif abs(px - L) < 1e-6 and abs(py - D) < 1e-6:
        m.apply_transform(tf.rotation_matrix(math.pi, [0, 0, 1]))
    elif abs(px) < 1e-6 and abs(py - D) < 1e-6:
        m.apply_transform(tf.rotation_matrix(math.pi, [1, 0, 0]))


def place_corner_post(px: float, py: float, L: float, D: float) -> trimesh.Trimesh:
    """Уголок для стойки: горизонтальные гнёзда = уровень обвязки."""
    m = _connector("corner_post")
    m.apply_scale(_MM)
    _rotate_corner(m, px, py, L, D)
    m.apply_translation([px, py, FRAME_Z - SOCKET_D * 0.5])
    return m


def place_tee(px: float, py: float, along_x: bool) -> trimesh.Trimesh:
    m = _connector("tee_90")
    m.apply_scale(_MM)
    if not along_x:
        m.apply_transform(tf.rotation_matrix(math.pi / 2, [0, 0, 1]))
    m.apply_translation([px, py, FRAME_Z - SOCKET_D * 0.5])
    return m


def frame_sides(L: float, D: float, inset: float = SOCKET_D) -> List[Tuple[float, float, float, float]]:
    """Стороны обвязки с укорочением под corner_post на углах."""
    i = inset
    return [
        (i, 0, L - i, 0),
        (L, i, L, D - i),
        (L - i, D, i, D),
        (0, D, 0, i),
    ]


def wall_posts(spec: "ShedV3StableSpec", wall: str) -> List[Tuple[float, float]]:
    """Точки стоек на одной стене (для раскосов). wall: front/back/left/right."""
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    if wall == "front":
        return [(x, 0.0) for x in (0.0, L / 2, L)]
    if wall == "back":
        return [(x, D) for x in (0.0, L / 2, L)]
    if wall == "left":
        return [(0.0, y) for y in (0.0, D)]
    return [(L, y) for y in (0.0, D)]


def brace_pairs(wall: str) -> List[Tuple[int, int]]:
    """Индексы стоек для креста на стене."""
    if wall in ("front", "back"):
        return [(0, 2), (2, 0)]
    return [(0, 1), (1, 0)]


def build_shed_meshes(
    spec: "ShedV3StableSpec",
    *,
    show_blocks: bool = False,
    show_feet: bool = False,
    show_frame: bool = False,
    show_posts: bool = False,
    show_braces: bool = False,
    show_top: bool = False,
    show_door: bool = False,
    show_rafters: bool = False,
    show_purlins: bool = False,
) -> List[trimesh.Trimesh]:
    """Возвращает список мешей с metadata in mesh.metadata['color']."""
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    hw = PROFILE / 2.0
    posts = _post_xy(spec)
    corners = {(0.0, 0.0), (L, 0.0), (L, D), (0.0, D)}
    mid_front = (L / 2, 0.0)
    mid_back = (L / 2, D)
    out: List[trimesh.Trimesh] = []

    def add(mesh: Optional[trimesh.Trimesh], color: Tuple[float, float, float]) -> None:
        if mesh is None:
            return
        m = mesh.copy()
        m.metadata["color"] = color
        out.append(m)

    ground = trimesh.creation.box([L + 1.6, D + 1.6, 0.02])
    ground.apply_translation([L * 0.5, D * 0.5, -0.01])
    add(ground, (0.91, 0.91, 0.89))

    if show_blocks:
        for px, py in posts:
            add(block_mesh(px, py, 0.0, BLOCK_H, 0.045), (0.56, 0.56, 0.56))

    if show_feet:
        for px, py in posts:
            add(place_foot(px, py), (0.88, 0.44, 0.0))

    if show_frame:
        for px, py in corners:
            add(place_corner_post(px, py, L, D), (1.0, 0.60, 0.0))
        for px, py in (mid_front, mid_back):
            add(place_tee(px, py, along_x=True), (1.0, 0.60, 0.0))
        for x0, y0, x1, y1 in frame_sides(L, D):
            add(beam_mesh((x0, y0, FRAME_Z), (x1, y1, FRAME_Z), hw), (0.42, 0.27, 0.13))

    if show_posts:
        z0 = post_bottom_z()
        for px, py in posts:
            top = _wall_top(spec, py)
            add(beam_mesh((px, py, z0), (px, py, top), hw), (0.80, 0.27, 0.0))

    if show_braces:
        z_lo = FRAME_Z + 0.30
        walls = (
            ("front", fh),
            ("back", bh),
            ("left", bh),
            ("right", bh),
        )
        for wall, z_hi_wall in walls:
            pts = wall_posts(spec, wall)
            if len(pts) < 2:
                continue
            z_hi = z_hi_wall - 0.20
            if wall in ("left", "right"):
                z_hi = (fh + bh) * 0.5 - 0.15
            for i0, i1 in brace_pairs(wall):
                p0 = pts[i0]
                p1 = pts[i1]
                add(beam_mesh((p0[0], p0[1], z_lo), (p1[0], p1[1], z_hi), hw * 1.2), (0.55, 0.33, 0.0))
                add(beam_mesh((p1[0], p1[1], z_lo), (p0[0], p0[1], z_hi), hw * 1.2), (0.55, 0.33, 0.0))

    if show_top:
        for x0, y0, x1, y1 in frame_sides(L, D, inset=SOCKET_D):
            z0, z1 = _wall_top(spec, y0), _wall_top(spec, y1)
            add(beam_mesh((x0, y0, z0), (x1, y1, z1), hw), (0.42, 0.27, 0.13))
        for px, py in corners:
            m = _connector("corner_90")
            m.apply_scale(_MM)
            _rotate_corner(m, px, py, L, D)
            z = _wall_top(spec, py)
            m.apply_translation([px, py, z - SOCKET_D * 0.5])
            add(m, (1.0, 0.60, 0.0))

    if show_door:
        dx0 = spec.door_offset_left_mm / 1000.0
        dx1 = dx0 + spec.door_width_mm / 1000.0
        dh = spec.door_height_mm / 1000.0
        for p0, p1 in (
            ((dx0, 0, FRAME_Z), (dx0, 0, dh)),
            ((dx1, 0, FRAME_Z), (dx1, 0, dh)),
            ((dx0, 0, dh), (dx1, 0, dh)),
        ):
            add(beam_mesh(p0, p1, hw), (0.24, 0.13, 0.08))

    if show_rafters:
        n = spec.rafter_count_n
        xs = [L * i / (n - 1) for i in range(n)] if n > 1 else [0.0, L]
        for rx in xs:
            add(beam_mesh((rx, 0, fh), (rx, D, bh), hw), (0.69, 0.47, 0.13))

    if show_purlins:
        for frac in (0.33, 0.67):
            y = D * frac
            z = _wall_top(spec, y) + 0.06
            add(beam_mesh((0, y, z), (L, y, z), hw * 1.5), (0.42, 0.27, 0.13))
        girt_z = 1.0
        for x0, y0, x1, y1 in frame_sides(L, D, inset=0.0):
            add(beam_mesh((x0, y0, girt_z), (x1, y1, girt_z), hw * 1.2), (0.42, 0.27, 0.13))

    return out
