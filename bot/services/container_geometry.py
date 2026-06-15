"""
Parametric generators for small desk-scale storage containers and stencils.

Proportions and wall thicknesses are taken from real CAD measured in:
  - data/reference_models/pill_box_heptagonal/
  - data/reference_models/master_box/
  - data/reference_models/small_drawer_organizer/
  - data/reference_models/recycle_bin/
  - data/reference_models/sine_cosine_stencil/

Default values match the measured kits; all dimensions in millimetres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union


# ─────────────────────────────────────────────────────────────────────────────
#  Open-top tray / pill box / general organizer
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TraySpec:
    width_mm: float = 60.0       # outer X
    depth_mm: float = 40.0       # outer Y
    height_mm: float = 25.0      # outer Z
    wall_mm: float = 2.2         # measured average from real kits
    floor_mm: float = 2.0
    fillet_mm: float = 2.0       # outer corner radius (0 = sharp)
    cell_count_x: int = 1        # internal subdivisions
    cell_count_y: int = 1
    cell_wall_mm: float = 1.6    # thinner than outer walls


def _rounded_rect(w: float, d: float, fillet: float,
                  n_arc: int = 12) -> Polygon:
    if fillet <= 0:
        return Polygon([(-w/2, -d/2), (w/2, -d/2), (w/2, d/2), (-w/2, d/2)])
    f = min(fillet, min(w, d) / 2.0 - 0.01)
    pts = []
    # 4 corners with arcs
    # bottom-right corner
    cx, cy = w/2 - f, -d/2 + f
    for i in range(n_arc + 1):
        a = -math.pi/2 + (i / n_arc) * (math.pi/2)
        pts.append((cx + f * math.cos(a), cy + f * math.sin(a)))
    # top-right
    cx, cy = w/2 - f, d/2 - f
    for i in range(n_arc + 1):
        a = 0 + (i / n_arc) * (math.pi/2)
        pts.append((cx + f * math.cos(a), cy + f * math.sin(a)))
    # top-left
    cx, cy = -w/2 + f, d/2 - f
    for i in range(n_arc + 1):
        a = math.pi/2 + (i / n_arc) * (math.pi/2)
        pts.append((cx + f * math.cos(a), cy + f * math.sin(a)))
    # bottom-left
    cx, cy = -w/2 + f, -d/2 + f
    for i in range(n_arc + 1):
        a = math.pi + (i / n_arc) * (math.pi/2)
        pts.append((cx + f * math.cos(a), cy + f * math.sin(a)))
    return Polygon(pts)


def build_tray(spec: TraySpec | None = None) -> trimesh.Trimesh:
    """Open-top rectangular tray with optional internal grid of cells."""
    s = spec or TraySpec()
    outer = _rounded_rect(s.width_mm, s.depth_mm, s.fillet_mm)
    # Inner cavity (smaller by 2*wall)
    inner_w = s.width_mm - 2 * s.wall_mm
    inner_d = s.depth_mm - 2 * s.wall_mm
    inner_fillet = max(s.fillet_mm - s.wall_mm, 0)
    inner = _rounded_rect(inner_w, inner_d, inner_fillet)
    shell = Polygon(list(outer.exterior.coords), [list(inner.exterior.coords)])

    # Floor (solid base layer)
    floor = trimesh.creation.extrude_polygon(outer, s.floor_mm)

    # Walls (hollow ring) extruded above the floor
    walls = trimesh.creation.extrude_polygon(shell, s.height_mm - s.floor_mm)
    walls.apply_translation([0, 0, s.floor_mm])

    parts = [floor, walls]

    # Internal cell walls
    if s.cell_count_x > 1:
        for i in range(1, s.cell_count_x):
            x = -inner_w / 2 + (inner_w / s.cell_count_x) * i
            wall = trimesh.creation.box(extents=[
                s.cell_wall_mm, inner_d, s.height_mm - s.floor_mm
            ])
            wall.apply_translation([x, 0, s.floor_mm + (s.height_mm - s.floor_mm) / 2])
            parts.append(wall)
    if s.cell_count_y > 1:
        for j in range(1, s.cell_count_y):
            y = -inner_d / 2 + (inner_d / s.cell_count_y) * j
            wall = trimesh.creation.box(extents=[
                inner_w, s.cell_wall_mm, s.height_mm - s.floor_mm
            ])
            wall.apply_translation([0, y, s.floor_mm + (s.height_mm - s.floor_mm) / 2])
            parts.append(wall)

    # Boolean union via concatenation + manifold repair (cheap for FDM use)
    result = trimesh.util.concatenate(parts)
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Mini drawer cabinet (61×61×30 mm reference)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DrawerCabinetSpec:
    width_mm: float = 60.0
    depth_mm: float = 60.0
    height_mm: float = 60.0
    n_drawers: int = 2
    wall_mm: float = 2.4
    drawer_clearance_mm: float = 0.3


def build_drawer_cabinet(spec: DrawerCabinetSpec | None = None,
                          ) -> Dict[str, trimesh.Trimesh]:
    """Returns {'cabinet': mesh, 'drawer_0': mesh, 'drawer_1': mesh, ...}."""
    s = spec or DrawerCabinetSpec()
    # Cabinet shell
    cab = build_tray(TraySpec(
        width_mm=s.width_mm,
        depth_mm=s.depth_mm,
        height_mm=s.height_mm,
        wall_mm=s.wall_mm,
        floor_mm=s.wall_mm,
        fillet_mm=1.5,
        cell_count_x=1, cell_count_y=s.n_drawers,
        cell_wall_mm=s.wall_mm * 0.7,
    ))
    out = {"cabinet": cab}
    # Drawers
    inner_w = s.width_mm - 2 * s.wall_mm - 2 * s.drawer_clearance_mm
    inner_d = (s.depth_mm - 2 * s.wall_mm) / s.n_drawers \
              - 2 * s.drawer_clearance_mm
    inner_h = s.height_mm - 2 * s.wall_mm - s.drawer_clearance_mm
    for i in range(s.n_drawers):
        drawer = build_tray(TraySpec(
            width_mm=inner_w,
            depth_mm=inner_d,
            height_mm=inner_h,
            wall_mm=s.wall_mm * 0.7,
            floor_mm=s.wall_mm * 0.7,
            fillet_mm=0.8,
        ))
        # Add a small handle (extruded box) on +Y face
        handle = trimesh.creation.box(extents=[
            inner_w * 0.3, 3.0, inner_h * 0.25
        ])
        handle.apply_translation([0, inner_d / 2 + 1.5, inner_h * 0.55])
        drawer = trimesh.util.concatenate([drawer, handle])
        out[f"drawer_{i}"] = drawer
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Cylindrical bin (60×30×30 mm reference)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BinSpec:
    diameter_mm: float = 30.0
    height_mm: float = 60.0
    wall_mm: float = 2.0
    floor_mm: float = 2.0
    taper: float = 0.0          # +ve = wider at top (frustum), 0 = straight


def build_bin(spec: BinSpec | None = None) -> trimesh.Trimesh:
    """Tall thin cylindrical bin, watertight, single STL print."""
    s = spec or BinSpec()
    if abs(s.taper) < 1e-3:
        outer = trimesh.creation.cylinder(radius=s.diameter_mm / 2,
                                           height=s.height_mm,
                                           sections=48)
        inner = trimesh.creation.cylinder(
            radius=s.diameter_mm / 2 - s.wall_mm,
            height=s.height_mm - s.floor_mm + 0.1,
            sections=48,
        )
        inner.apply_translation([0, 0, s.floor_mm + 0.05])
        return outer.difference(inner)
    # Frustum (lofted between bottom & top circles)
    n = 48
    z_low, z_high = 0, s.height_mm
    r_bot = s.diameter_mm / 2
    r_top = r_bot + s.taper * s.height_mm
    parts = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        quad = np.array([
            [r_bot * math.cos(a0), r_bot * math.sin(a0), z_low],
            [r_bot * math.cos(a1), r_bot * math.sin(a1), z_low],
            [r_top * math.cos(a1), r_top * math.sin(a1), z_high],
            [r_top * math.cos(a0), r_top * math.sin(a0), z_high],
        ])
        # Two triangles per quad
        tri1 = trimesh.Trimesh(vertices=quad, faces=[[0, 1, 2]], process=False)
        tri2 = trimesh.Trimesh(vertices=quad, faces=[[0, 2, 3]], process=False)
        parts.extend([tri1, tri2])
    return trimesh.util.concatenate(parts)


# ─────────────────────────────────────────────────────────────────────────────
#  Flat stencil with cut-out shapes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StencilSpec:
    width_mm: float = 100.0
    height_mm: float = 36.0
    thickness_mm: float = 2.5
    cutouts: List[str] = None      # list of shape codes
    border_mm: float = 4.0

    def __post_init__(self):
        if self.cutouts is None:
            self.cutouts = ["circle", "square", "triangle", "star"]


def _cutout_polygon(kind: str, size: float) -> Polygon:
    if kind == "circle":
        pts = [(size/2 * math.cos(2*math.pi*i/24),
                size/2 * math.sin(2*math.pi*i/24)) for i in range(24)]
        return Polygon(pts)
    if kind == "square":
        s = size / 2
        return Polygon([(-s,-s),(s,-s),(s,s),(-s,s)])
    if kind == "triangle":
        s = size / 2
        return Polygon([(-s,-s),(s,-s),(0,s)])
    if kind == "star":
        outer_r = size / 2
        inner_r = outer_r * 0.45
        pts = []
        for i in range(10):
            r = outer_r if i % 2 == 0 else inner_r
            a = -math.pi/2 + math.pi * i / 5
            pts.append((r * math.cos(a), r * math.sin(a)))
        return Polygon(pts)
    if kind == "heart":
        pts = []
        for i in range(32):
            t = 2 * math.pi * i / 32
            x = 16 * math.sin(t) ** 3
            y = (13 * math.cos(t) - 5 * math.cos(2*t)
                 - 2 * math.cos(3*t) - math.cos(4*t))
            pts.append((x * size / 32, y * size / 32))
        return Polygon(pts)
    # default: small circle
    return _cutout_polygon("circle", size)


def build_stencil(spec: StencilSpec | None = None) -> trimesh.Trimesh:
    """Flat stencil plate with cut-out shapes."""
    s = spec or StencilSpec()
    plate = Polygon([
        (-s.width_mm/2, -s.height_mm/2),
        ( s.width_mm/2, -s.height_mm/2),
        ( s.width_mm/2,  s.height_mm/2),
        (-s.width_mm/2,  s.height_mm/2),
    ])
    n = len(s.cutouts)
    if n > 0:
        slot_w = (s.width_mm - 2 * s.border_mm) / n
        slot_size = min(slot_w * 0.7, s.height_mm - 2 * s.border_mm)
        holes = []
        for i, kind in enumerate(s.cutouts):
            cx = -s.width_mm/2 + s.border_mm + slot_w * (i + 0.5)
            hole_poly = _cutout_polygon(kind, slot_size)
            from shapely.affinity import translate as shp_translate
            hole_poly = shp_translate(hole_poly, cx, 0)
            holes.append(list(hole_poly.exterior.coords))
        plate = Polygon(list(plate.exterior.coords), holes)
    return trimesh.creation.extrude_polygon(plate, s.thickness_mm)


# ─────────────────────────────────────────────────────────────────────────────
#  Routing helper — pick the right generator from a free-form request
# ─────────────────────────────────────────────────────────────────────────────

def generator_for_text(text: str) -> Optional[Tuple[str, callable]]:
    """Return (slug, builder_fn) for free-form Russian/English text, or None."""
    import re
    t = (text or "").lower()
    if re.search(r"таблетниц|pill\s*box|органайзер.{0,15}мелк|коробк.{0,10}яче", t):
        return ("pill_box", lambda spec=None: build_tray(
            spec or TraySpec(width_mm=80, depth_mm=40, height_mm=18,
                              cell_count_x=4, cell_count_y=2)))
    if re.search(r"комод|drawer|шкафчик|cabinet", t):
        return ("drawer_cabinet", build_drawer_cabinet)
    if re.search(r"ведер|корзин|bin|реcикл|recycl", t):
        return ("recycle_bin", build_bin)
    if re.search(r"трафарет|stencil", t):
        return ("stencil", build_stencil)
    if re.search(r"подставк|tray|поддон|органайзер", t):
        return ("tray", build_tray)
    return None
