"""Трубка «8» (лемниската), разрез z=0, подставка отдельно."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np
import trimesh

# Сегменты shapely buffer → видимые грани на боковой стенке в слайсере
_PATH_BUFFER_RES = 112
_SEAM_BUFFER_RES = 96
# Зазор у центра «8»: петли не смыкаются; мосты через ±X разводят потоки (режим dual)
_CROSS_LOBE_EPS = 0.15
# Для полости «∞» — дуги почти до центра (иначе канал рвётся у перекрёстка)
_VOID_LOBE_EPS = 0.028
# v9: один замкнутый канал «∞» — в перекрёстке верхняя/нижняя ветка (z)
_CROSS_PLAN_RADIUS_FACTOR = 0.22


def fig8_centerline(lemniscate_a: float, n: int = 160, *, lobe_y_scale: float = 0.72) -> np.ndarray:
    """«8» (лемниската): x=A·sin(t), y=A·lobe_y_scale·sin(2t) — как две петли в storyboard."""
    pts: List[List[float]] = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        x = lemniscate_a * math.sin(t)
        y = lemniscate_a * lobe_y_scale * math.sin(2.0 * t)
        pts.append([x, y, 0.0])
    return np.asarray(pts, dtype=np.float64)


def fig8_lobes(
    lemniscate_a: float,
    n: int = 80,
    t_eps: float = _CROSS_LOBE_EPS,
    *,
    lobe_y_scale: float = 0.72,
) -> Tuple[np.ndarray, np.ndarray]:
    """Две петли «8» без склейки через центр."""

    def arc(t0: float, t1: float) -> np.ndarray:
        pts: List[List[float]] = []
        for i in range(n):
            t = t0 + (t1 - t0) * i / (n - 1)
            x = lemniscate_a * math.sin(t)
            y = lemniscate_a * lobe_y_scale * math.sin(2.0 * t)
            pts.append([x, y, 0.0])
        return np.asarray(pts, dtype=np.float64)

    return arc(t_eps, math.pi - t_eps), arc(math.pi + t_eps, 2.0 * math.pi - t_eps)


def _fig8_buffer_polygons(lemniscate_a: float, r_bore: float, r_out: float):
    from shapely.geometry import LineString

    path = fig8_centerline(lemniscate_a)
    line = LineString(path[:, :2])
    outer = line.buffer(r_out, join_style=1, cap_style=2, resolution=_PATH_BUFFER_RES)
    inner = line.buffer(r_bore, join_style=1, cap_style=2, resolution=_PATH_BUFFER_RES)
    return outer, inner


def _bridge_x_mm(lemniscate_a: float, r_bore: float) -> float:
    """X мостов ±bx: далеко от (0,0), иначе в центре получается общая «чаша»."""
    return max(r_bore * 0.82, lemniscate_a * 0.14, 14.0)


def _channel_bridge_midpoints(
    lemniscate_a: float,
    r_bore: float = 20.0,
    t_eps: float = _CROSS_LOBE_EPS,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Точки моста у перекрёстка: разные X → два канала не пересекаются в плане."""
    del t_eps
    bx = _bridge_x_mm(lemniscate_a, r_bore)
    return (bx, 0.0), (-bx, 0.0)


def fig8_lobes_bridged(
    lemniscate_a: float,
    bridge_x: float,
    n: int = 80,
    *,
    lobe_y_scale: float = 0.72,
) -> Tuple[np.ndarray, np.ndarray]:
    """Петли «8» между мостами ±bridge_x (не сходятся в одной точке 0,0)."""
    t_r = math.asin(min(0.999, bridge_x / lemniscate_a))

    def arc(t0: float, t1: float) -> np.ndarray:
        pts: List[List[float]] = []
        for i in range(n):
            t = t0 + (t1 - t0) * i / (n - 1)
            x = lemniscate_a * math.sin(t)
            y = lemniscate_a * lobe_y_scale * math.sin(2.0 * t)
            pts.append([x, y, 0.0])
        return np.asarray(pts, dtype=np.float64)

    l0 = arc(t_r, math.pi - t_r)
    l1 = arc(math.pi + t_r, 2.0 * math.pi - t_r)
    return l0, l1


def _channel_2d_polygon(lobe_pts: np.ndarray, bridge_mid: Tuple[float, float], r_bore: float):
    """Одна петля «8» + дуга-мост через перекрёсток (замкнутый контур для циркуляции)."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    arc = LineString(lobe_pts[:, :2])
    e0 = tuple(lobe_pts[0, :2])
    e1 = tuple(lobe_pts[-1, :2])
    bridge = LineString([e0, bridge_mid, e1])
    kw = dict(join_style=1, cap_style=2, resolution=_PATH_BUFFER_RES)
    merged = unary_union([arc.buffer(r_bore, **kw), bridge.buffer(r_bore, **kw)])
    if merged.is_empty:
        raise ValueError("empty channel polygon")
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)
    return merged


def _dual_channel_void_polygon(lemniscate_a: float, r_bore: float):
    """Два изолированных канала (без общей полости в центре)."""
    from shapely.ops import unary_union

    l0, l1 = fig8_lobes(lemniscate_a)
    mid_a, mid_b = _channel_bridge_midpoints(lemniscate_a, r_bore)
    ch0 = _channel_2d_polygon(l0, mid_a, r_bore)
    ch1 = _channel_2d_polygon(l1, mid_b, r_bore)
    if ch0.intersection(ch1).area > 0.5:
        raise ValueError("channels must not overlap in plan")
    return unary_union([ch0, ch1])


def _extrude_void_2d(poly, height: float, z0: float = 0.0) -> trimesh.Trimesh:
    """Выдавить полость; MultiPolygon → несколько призм."""
    from shapely.geometry import Polygon

    if poly.is_empty:
        raise ValueError("empty void polygon")
    polys = [poly] if poly.geom_type == "Polygon" else [g for g in poly.geoms if isinstance(g, Polygon) and g.area > 1.0]
    if not polys:
        raise ValueError("no void polygons to extrude")
    parts: List[trimesh.Trimesh] = []
    for p in polys:
        slab = trimesh.creation.extrude_polygon(p, height=height)
        if z0 != 0.0:
            slab.apply_translation([0.0, 0.0, z0])
        parts.append(slab)
    return parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)


def path_footprint_mm(path: np.ndarray, r_outer: float) -> Tuple[float, float]:
    return (
        float(path[:, 0].max() - path[:, 0].min()) + 2.0 * r_outer,
        float(path[:, 1].max() - path[:, 1].min()) + 2.0 * r_outer,
    )


def _path_tangents(path: np.ndarray) -> List[np.ndarray]:
    n = len(path)
    out: List[np.ndarray] = []
    for i in range(n):
        if i == 0:
            t = path[1] - path[0]
        elif i == n - 1:
            t = path[-1] - path[-2]
        else:
            t = path[i + 1] - path[i - 1]
        t[2] = 0.0
        ln = float(np.linalg.norm(t))
        out.append(t / ln if ln > 1e-9 else np.array([1.0, 0.0, 0.0]))
    return out


def _finalize(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if hasattr(mesh, "remove_degenerate_faces"):
        mesh.remove_degenerate_faces()
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_winding(mesh)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    return mesh


def _union_all(parts: List[trimesh.Trimesh]) -> trimesh.Trimesh:
    if not parts:
        raise ValueError("empty parts")
    if len(parts) == 1:
        return _finalize(parts[0])
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.union(parts, **kw)
            if out is not None and len(out.vertices) > 0:
                return _finalize(out)
        except Exception:
            continue
    out = parts[0]
    for piece in parts[1:]:
        out = _union(out, piece)
    return out


def _union(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.union([a, b], **kw)
            if out is not None and len(out.vertices) > 0:
                return _finalize(out)
        except Exception:
            continue
    return _finalize(trimesh.util.concatenate([a, b]))


def _subtract(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.difference([a, b], **kw)
            if out is not None and len(out.vertices) > 0:
                return _finalize(out)
        except Exception:
            continue
    return a


def _trimesh_to_manifold(mesh: trimesh.Trimesh):
    import manifold3d as m3d

    return m3d.Manifold(
        m3d.Mesh(
            vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
        )
    )


def _manifold_to_trimesh(manifold) -> trimesh.Trimesh:
    mesh = manifold.to_mesh()
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vert_properties[:, :3], dtype=np.float64),
        faces=np.asarray(mesh.tri_verts, dtype=np.int64),
        process=False,
    )


def _clip_manifold_z(manifold, z_min: float, z_max: float):
    import manifold3d as m3d

    extent_z = z_max - z_min
    box = m3d.Manifold.cube((420.0, 420.0, extent_z + 0.02), True)
    box = box.translate((0.0, 0.0, (z_max + z_min) * 0.5))
    return m3d.Manifold.batch_boolean([manifold, box], m3d.OpType.Intersect)


def _build_pipe_manifold(path: np.ndarray, radius: float, sections: int = 24):
    """Круглая труба вдоль 3D-пути (manifold3d, watertight)."""
    import manifold3d as m3d

    parts = []
    for p in path:
        sph = m3d.Manifold.sphere(radius, sections)
        sph = sph.translate((float(p[0]), float(p[1]), float(p[2])))
        parts.append(sph)
    for i in range(len(path)):
        p0 = path[i]
        p1 = path[(i + 1) % len(path)]
        seg = p1 - p0
        length = float(np.linalg.norm(seg))
        if length < 1e-4:
            continue
        cyl = trimesh.creation.cylinder(
            radius=radius, height=length + radius * 0.04, sections=sections
        )
        cyl.apply_transform(
            trimesh.geometry.align_vectors([0.0, 0.0, 1.0], seg / length, False)
        )
        cyl.apply_translation((p0 + p1) * 0.5)
        parts.append(_trimesh_to_manifold(cyl))
    return m3d.Manifold.batch_boolean(parts, m3d.OpType.Add)


def _build_tube_corpus_half_manifold(
    *,
    lemniscate_a: float,
    r_bore: float,
    wall: float,
    half_h: float,
    upper: bool,
) -> trimesh.Trimesh:
    """Половинка корпуса-трубки «8» (v15, без hub).

    Канал = один замкнутый путь лемнискаты с over/under через центр
    (z = z0·tanh(scale·sin(t))). Над z=0 — одна диагональ через центр,
    под z=0 — другая (перпендикулярная). Hub нет — каналы НЕ перекрыты.
    """
    import manifold3d as m3d

    path = fig8_overunder_path_3d(
        lemniscate_a, half_h=half_h, n=400, lobe_y_scale=0.72, ramp_scale=6.0
    )
    r_out = r_bore + wall
    outer_pipe = _build_pipe_manifold(path, r_out, sections=32)
    inner_pipe = _build_pipe_manifold(path, r_bore, sections=32)

    tube = m3d.Manifold.batch_boolean([outer_pipe, inner_pipe], m3d.OpType.Subtract)

    if upper:
        half = _clip_manifold_z(tube, 0.0, half_h + 0.02)
    else:
        half = _clip_manifold_z(tube, -half_h - 0.02, 0.0)

    tm = _manifold_to_trimesh(half)
    # Убираем вырожденные плоские "тела" (vol≈0) от clip — они мусор для slicer
    parts = tm.split()
    real = [p for p in parts if p.volume > 1.0]
    if len(real) == 1:
        return real[0]
    if len(real) > 1:
        return trimesh.util.concatenate(real)
    return tm


def _intersect(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.intersection([a, b], **kw)
            if out is not None and len(out.vertices) > 0:
                return _finalize(out)
        except Exception:
            continue
    return a


def _path_z_at_xy(
    x: float,
    y: float,
    *,
    upper_branch: bool,
    lemniscate_a: float,
    r_bore: float,
    half_h: float,
    cross_plan_r: float,
) -> float:
    z_lane = half_h * 0.28
    z_upper = half_h * 0.5
    z_lower = -half_h * 0.5
    d = math.hypot(x, y)
    if d >= cross_plan_r:
        return z_upper if upper_branch else z_lower
    w = (1.0 - d / cross_plan_r) ** 1.2
    if upper_branch:
        return z_upper + z_lane * w
    return z_lower - z_lane * w


def _path_interp3(
    a: np.ndarray, b: np.ndarray, steps: int
) -> List[np.ndarray]:
    out: List[np.ndarray] = []
    for i in range(1, steps + 1):
        t = i / steps
        out.append((1.0 - t) * a + t * b)
    return out


def fig8_closed_bridge_path_3d(
    lemniscate_a: float,
    *,
    n_lobe: int = 72,
    r_bore: float = 20.0,
    half_h: float = 40.0,
) -> np.ndarray:
    """Замкнутый контур «∞» без самопересечения: две петли + мосты ±X (нет «чаши» в 0,0)."""
    cross_r = _crossing_disk_radius(lemniscate_a, r_bore)
    bx = _bridge_x_mm(lemniscate_a, r_bore)
    l0, l1 = fig8_lobes_bridged(lemniscate_a, bx, n=n_lobe, lobe_y_scale=0.72)
    mid_a, mid_b = _channel_bridge_midpoints(lemniscate_a, r_bore)

    def zpt(x: float, y: float, upper: bool) -> float:
        return _path_z_at_xy(
            x,
            y,
            upper_branch=upper,
            lemniscate_a=lemniscate_a,
            r_bore=r_bore,
            half_h=half_h,
            cross_plan_r=cross_r,
        )

    def lift(p2, upper: bool) -> np.ndarray:
        return np.array([p2[0], p2[1], zpt(float(p2[0]), float(p2[1]), upper)], dtype=np.float64)

    ma = np.array([mid_a[0], mid_a[1], zpt(mid_a[0], mid_a[1], True)], dtype=np.float64)
    mb = np.array([mid_b[0], mid_b[1], zpt(mid_b[0], mid_b[1], False)], dtype=np.float64)

    def bridge_via_x(
        from_pt: np.ndarray, to_pt: np.ndarray, bx_target: float, upper: bool, steps: int = 10
    ) -> List[np.ndarray]:
        """Мост по X=±bx, без диагонали через (0,0) — иначе задевает центральный остров."""
        z_from = float(from_pt[2])
        z_to = float(to_pt[2])
        knee = np.array([bx_target, float(from_pt[1]), z_from], dtype=np.float64)
        corner = np.array([bx_target, 0.0, (z_from + z_to) * 0.5], dtype=np.float64)
        out: List[np.ndarray] = []
        out.extend(_path_interp3(from_pt, knee, max(3, steps // 2)))
        out.extend(_path_interp3(knee, corner, max(3, steps // 2)))
        out.extend(_path_interp3(corner, to_pt, max(3, steps // 2)))
        return out

    pts: List[np.ndarray] = []
    for p in l0:
        pts.append(lift(p, True))
    pts.extend(bridge_via_x(pts[-1], lift(l1[0], False), mid_a[0], True))
    for p in l1[1:]:
        pts.append(lift(p, False))
    pts.extend(bridge_via_x(pts[-1], lift(l0[0], True), mid_b[0], False))
    return np.asarray(pts, dtype=np.float64)


def fig8_infinity_path_3d(
    lemniscate_a: float,
    *,
    n: int = 200,
    r_bore: float = 20.0,
    half_h: float = 40.0,
    cross_plan_r: float | None = None,
) -> np.ndarray:
    """Совместимость: контур с мостами (не лемниската через (0,0))."""
    del cross_plan_r
    return fig8_closed_bridge_path_3d(
        lemniscate_a, n_lobe=max(48, n // 3), r_bore=r_bore, half_h=half_h
    )


def fig8_overunder_path_3d(
    lemniscate_a: float,
    *,
    half_h: float = 40.0,
    n: int = 400,
    lobe_y_scale: float = 0.72,
    ramp_scale: float = 6.0,
) -> np.ndarray:
    """Замкнутый 3D-путь лемнискаты с over/under через центр.

    x = A·sin(t), y = A·k·sin(2t), z = z0·tanh(scale·sin(t))

    На полу-обходе t∈(0,π) z≈+z0, на t∈(π,2π) z≈-z0. Узкий переход
    проходит точно через (0,0,0). Касательные около t=0 и t=π направлены
    по диагоналям NE и NW соответственно — поэтому два прохода канала
    в плане пересекаются **под перпендикулярными углами**, а по Z разнесены.
    """
    z0 = half_h * 0.5
    t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    x = lemniscate_a * np.sin(t)
    y = lemniscate_a * lobe_y_scale * np.sin(2.0 * t)
    z = z0 * np.tanh(ramp_scale * np.sin(t))
    return np.column_stack([x, y, z]).astype(np.float64)


def _tube_mesh_along_path(path: np.ndarray, radius: float, sections: int = 16) -> trimesh.Trimesh:
    """Труба вдоль замкнутой ломаной: цилиндры + сферы в каждом узле (watertight union)."""
    parts: List[trimesh.Trimesh] = []
    for p in path:
        sp = trimesh.creation.icosphere(subdivisions=2, radius=radius * 1.02)
        sp.apply_translation(p)
        parts.append(sp)
    for i in range(len(path) - 1):
        p0 = path[i]
        p1 = path[i + 1]
        seg = p1 - p0
        length = float(np.linalg.norm(seg))
        if length < 1e-5:
            continue
        direction = seg / length
        cyl = trimesh.creation.cylinder(radius=radius, height=length, sections=sections)
        transform = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], direction, False)
        cyl.apply_transform(transform)
        mid = (p0 + p1) * 0.5
        cyl.apply_translation(mid)
        parts.append(cyl)
    # замыкание контура
    p0, p1 = path[-1], path[0]
    seg = p1 - p0
    length = float(np.linalg.norm(seg))
    if length > 1e-5:
        direction = seg / length
        cyl = trimesh.creation.cylinder(radius=radius, height=length, sections=sections)
        transform = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], direction, False)
        cyl.apply_transform(transform)
        cyl.apply_translation((p0 + p1) * 0.5)
        parts.append(cyl)
    out = parts[0]
    for m in parts[1:]:
        out = _union(out, m)
    return out


def _shapely_polys(geom) -> List:
    """Разбить shapely-геометрию на список Polygon."""
    from shapely.geometry import Polygon

    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return [g for g in geom.geoms if isinstance(g, Polygon) and g.area > 1.0]
    return []


def _extrude_watertight(poly, height: float, z0: float = 0.0) -> trimesh.Trimesh:
    """Выдавить полигон → watertight призма."""
    import trimesh.repair as _rep

    mesh = trimesh.creation.extrude_polygon(poly, height=height)
    _rep.fix_normals(mesh)
    _rep.fix_winding(mesh)
    if z0 != 0.0:
        mesh.apply_translation([0.0, 0.0, z0])
    return mesh


def _lane_footprint_2d(lobe_pts: np.ndarray, r_bore: float):
    """План одной ветки «8» (дуга без горизонтального моста ±X)."""
    from shapely.geometry import LineString

    line = LineString(lobe_pts[:, :2])
    return line.buffer(r_bore, join_style=1, cap_style=2, resolution=_PATH_BUFFER_RES)


def _crossing_disk_radius(lemniscate_a: float, r_bore: float) -> float:
    return max(r_bore * 1.85, lemniscate_a * _CROSS_PLAN_RADIUS_FACTOR)


_SEAM_VOID_OVERLAP_MM = 0.35


def _add_crossing_void_slabs(
    parts: List[trimesh.Trimesh],
    inside_polys,
    *,
    upper: bool,
    half_h: float,
    z_lane: float,
    own_branch: bool,
    seam_overlap: float,
) -> None:
    """Полость в перекрёстке: на z=0 — стенка; своя ветка от шва, чужая — верхний/нижний ярус."""
    from shapely.geometry import Polygon as _SPoly

    for poly in _shapely_polys(inside_polys):
        if not isinstance(poly, _SPoly):
            continue
        if own_branch:
            tier_h = half_h - seam_overlap
            if upper:
                parts.append(_extrude_watertight(poly, tier_h, z0=seam_overlap))
            else:
                parts.append(_extrude_watertight(poly, tier_h, z0=-half_h))
        else:
            tier_h = half_h - z_lane
            if upper:
                parts.append(_extrude_watertight(poly, tier_h, z0=z_lane))
            else:
                parts.append(_extrude_watertight(poly, tier_h, z0=-half_h))


def _build_infinity_void_half(
    *,
    lemniscate_a: float,
    r_bore: float,
    half_h: float,
    upper: bool,
) -> trimesh.Trimesh:
    """Полость половинки «∞»: две ветки, over/under в центре, один замкнутый контур в сборке.

    Вне перекрёстка: «своя» ветка на всю высоту половинки; чужая — только ярус в центре.
    На шве z=0 — узкий стык-колодец.
    """
    from shapely.geometry import Point

    l0, l1 = fig8_lobes(lemniscate_a, t_eps=_VOID_LOBE_EPS)
    fp0 = _lane_footprint_2d(l0, r_bore)
    fp1 = _lane_footprint_2d(l1, r_bore)
    cross_r = _crossing_disk_radius(lemniscate_a, r_bore)
    cross_disk = Point(0.0, 0.0).buffer(cross_r, resolution=64)
    z_lane = half_h * 0.36
    overlap = _SEAM_VOID_OVERLAP_MM

    own_fp = fp0 if upper else fp1
    other_fp = fp1 if upper else fp0

    parts: List[trimesh.Trimesh] = []
    own_out = own_fp.difference(cross_disk)
    own_in = own_fp.intersection(cross_disk)
    other_in = other_fp.intersection(cross_disk)

    for poly in _shapely_polys(own_out):
        if upper:
            parts.append(_extrude_watertight(poly, half_h, z0=0.0))
        else:
            parts.append(_extrude_watertight(poly, half_h, z0=-half_h))

    _add_crossing_void_slabs(
        parts,
        own_in,
        upper=upper,
        half_h=half_h,
        z_lane=z_lane,
        own_branch=True,
        seam_overlap=overlap,
    )
    _add_crossing_void_slabs(
        parts,
        other_in,
        upper=upper,
        half_h=half_h,
        z_lane=z_lane,
        own_branch=False,
        seam_overlap=overlap,
    )

    conn_r = r_bore * 0.34
    conn = Point(0.0, 0.0).buffer(conn_r, resolution=32)
    seam_h = z_lane + overlap
    if upper:
        parts.append(_extrude_watertight(conn, seam_h, z0=-overlap))
    else:
        parts.append(_extrude_watertight(conn, seam_h, z0=-seam_h))

    if not parts:
        raise ValueError("infinity void empty")
    return _union_all(parts) if len(parts) > 1 else _finalize(parts[0])


def verify_figure8_dimensions(
    mesh_lower: trimesh.Trimesh,
    mesh_upper: trimesh.Trimesh,
    *,
    half_h: float,
    channel_diameter_mm: float,
) -> Tuple[bool, str]:
    """Высота половинки ≥ half_h, канал ≥ channel_diameter_mm."""
    for name, m in (("02", mesh_lower), ("03", mesh_upper)):
        h = float(m.bounds[1][2] - m.bounds[0][2])
        if h + 0.5 < half_h:
            return False, f"{name}: высота {h:.1f} < {half_h:.1f} мм"
    if channel_diameter_mm < 40.0:
        return False, f"канал Ø{channel_diameter_mm:.1f} < 40 мм"
    return True, "ok"


def verify_lanes_no_plan_crossing(
    mesh_lower: trimesh.Trimesh,
    mesh_upper: trimesh.Trimesh,
    *,
    lemniscate_a: float,
    r_bore: float,
    half_h: float = 40.0,
) -> Tuple[bool, str]:
    """В центре «8» на одной высоте z не открыты обе ветки сразу (нет слияния потоков)."""
    from shapely.geometry import Point

    bx = _bridge_x_mm(lemniscate_a, r_bore)
    l0, l1 = fig8_lobes_bridged(lemniscate_a, bx)
    fp0 = _lane_footprint_2d(l0, r_bore)
    fp1 = _lane_footprint_2d(l1, r_bore)
    cross_r = _crossing_disk_radius(lemniscate_a, r_bore)
    cross = Point(0.0, 0.0).buffer(cross_r, resolution=48)
    overlap = fp0.intersection(fp1).intersection(cross)
    if overlap.is_empty:
        return True, "ok"

    assembled = _union_all([mesh_lower, mesh_upper])
    conn_r = r_bore * 0.32

    samples = []
    if overlap.geom_type == "Polygon":
        samples.append(overlap.representative_point())
    else:
        for g in overlap.geoms:
            if g.area > 0.5:
                samples.append(g.representative_point())

    cross_r_hub = _crossing_disk_radius(lemniscate_a, r_bore)
    hub_r = min(cross_r_hub * 0.42, r_bore * 0.95)
    for pt in samples[:12]:
        x, y = float(pt.x), float(pt.y)
        if math.hypot(x, y) < max(conn_r, hub_r) * 1.1:
            continue
        # Смешивание = обе ветки открыты на одной высоте z (не over/under)
        z_test = (half_h * 0.22, 0.0, -half_h * 0.22)
        void_at = [not assembled.contains([[x, y, zt]])[0] for zt in z_test]
        if void_at[0] and void_at[1] and void_at[2]:
            return False, f"слияние потоков в ({x:.1f},{y:.1f})"
        if void_at[1] and math.hypot(x, y) < cross_r * 0.85:
            return False, f"общая полость на z=0 в ({x:.1f},{y:.1f})"

    return True, "ok"


def verify_figure8_channel(
    mesh_lower: trimesh.Trimesh,
    mesh_upper: trimesh.Trimesh,
    *,
    lemniscate_a: float,
    r_bore: float,
    half_h: float = 40.0,
) -> Tuple[bool, str]:
    """Проверка: один замкнутый контур «∞», ветки разведены по Z в центре."""
    assembled = _union_all([mesh_lower, mesh_upper])
    path3d = fig8_infinity_path_3d(
        lemniscate_a, r_bore=r_bore, half_h=half_h, n=180
    )

    blocked = 0
    z_probe = max(2.5, r_bore * 0.12)
    for pt in path3d:
        x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
        if not assembled.contains([[x, y, z]])[0]:
            continue
        open_near = False
        for dz in (-z_probe, 0.0, z_probe):
            if not assembled.contains([[x, y, z + dz]])[0]:
                open_near = True
                break
        if not open_near:
            blocked += 1
    if blocked > max(4, len(path3d) * 0.06):
        return False, f"траектория канала заблокирована ({blocked}/{len(path3d)})"

    ok_sep, msg_sep = verify_lanes_no_plan_crossing(
        mesh_lower, mesh_upper, lemniscate_a=lemniscate_a, r_bore=r_bore, half_h=half_h
    )
    if not ok_sep:
        return False, msg_sep

    cl = fig8_centerline(lemniscate_a, n=120)
    ix_l = int(np.argmin(cl[:, 0]))
    ix_r = int(np.argmax(cl[:, 0]))
    left = cl[ix_l]
    right = cl[ix_r]
    bx = _bridge_x_mm(lemniscate_a, r_bore)
    probes = [
        (float(left[0]), float(left[1]), -half_h * 0.5),
        (float(right[0]), float(right[1]), half_h * 0.5),
        (bx, 0.0, half_h * 0.5),
        (-bx, 0.0, -half_h * 0.5),
    ]
    for x, y, z in probes:
        if assembled.contains([[x, y, z]])[0]:
            return False, f"проба канала заблокирована ({x:.0f},{y:.0f},z={z:.1f})"

    # В центре «8» — остров (хотя бы одна половинка; union mesh может врать contains)
    for zc in (-0.5, 0.0, 0.5):
        in_lo = mesh_lower.contains([[0.0, 0.0, zc]])[0]
        in_up = mesh_upper.contains([[0.0, 0.0, zc]])[0]
        if not (in_lo or in_up):
            return False, f"в центре (0,0) нет стенки z={zc:.1f} — смешивание потоков"

    return True, "ok"


def count_non_manifold_edges(mesh: trimesh.Trimesh) -> int:
    """Сколько рёбер имеют != 2 смежных грани (Bambu: 'non-manifold edges')."""
    from collections import Counter

    if len(mesh.faces) == 0:
        return 0
    edges = np.sort(mesh.edges, axis=1)
    counts = Counter(map(tuple, edges))
    return sum(1 for c in counts.values() if c != 2)


def verify_figure8_part_mesh(
    mesh: trimesh.Trimesh,
    *,
    part_name: str,
    half_h: float,
    min_stl_bytes: int = 100_000,
) -> Tuple[bool, str]:
    """Финальная деталь для ZIP: watertight, без non-manifold, корректные размеры."""
    stl_len = len(mesh.export(file_type="stl"))
    if stl_len < min_stl_bytes:
        return False, f"{part_name}: STL слишком мал ({stl_len} B)"
    if mesh.volume < 10_000.0:
        return False, f"{part_name}: объём {mesh.volume:.0f} мм³"
    h = float(mesh.bounds[1][2] - mesh.bounds[0][2])
    if h + 0.5 < half_h:
        return False, f"{part_name}: высота {h:.1f} < {half_h:.1f} мм"
    if len(mesh.vertices) < 1000:
        return False, f"{part_name}: слишком мало вершин ({len(mesh.vertices)})"
    nm = count_non_manifold_edges(mesh)
    if nm > 0:
        return False, f"{part_name}: {nm} non-manifold edges (slicer откажется)"
    if not mesh.is_watertight:
        return False, f"{part_name}: mesh не watertight"
    # Проверка через 3MF roundtrip (формат, который Bambu использует нативно
    # и который сохраняет shared vertices, в отличие от STL).
    import io as _io
    m3f_bytes = mesh.export(file_type="3mf")
    reloaded = trimesh.load(_io.BytesIO(m3f_bytes), file_type="3mf", process=False)
    if hasattr(reloaded, "geometry"):
        reloaded = list(reloaded.geometry.values())[0]
    nm_reload = count_non_manifold_edges(reloaded)
    if nm_reload > 0:
        return False, f"{part_name}: после 3MF roundtrip {nm_reload} non-manifold edges"
    if not reloaded.is_watertight:
        return False, f"{part_name}: после 3MF roundtrip не watertight"
    return True, "ok"


def build_figure8_tube_shell(
    *,
    lemniscate_a: float,
    r_bore: float,
    wall: float,
    half_h: float,
    upper: bool,
    channel_mode: str = "infinity",
) -> trimesh.Trimesh:
    """Половинка корпуса-трубки «∞»: Ø2·r_bore, стенка wall, шов z=0, over/under."""
    import trimesh.repair as _rep

    if half_h < 40.0:
        raise ValueError("half_h must be >= 40 mm")
    if r_bore < 20.0:
        raise ValueError("r_bore must be >= 20 mm (channel width >= 40 mm)")

    if channel_mode == "infinity":
        return _build_tube_corpus_half_manifold(
            lemniscate_a=lemniscate_a,
            r_bore=r_bore,
            wall=wall,
            half_h=half_h,
            upper=upper,
        )

    r_plan = r_bore + wall
    outer, bore_blob = _fig8_buffer_polygons(lemniscate_a, r_bore, r_plan)

    solid = trimesh.creation.extrude_polygon(outer, height=half_h)
    _rep.fix_normals(solid)
    _rep.fix_winding(solid)
    if not upper:
        solid.apply_translation([0.0, 0.0, -half_h])

    if channel_mode == "dual":
        inner = _dual_channel_void_polygon(lemniscate_a, r_bore)
        void = _extrude_void_2d(inner, half_h, z0=0.0 if upper else -half_h)
    elif channel_mode == "connected":
        void = _extrude_watertight(bore_blob, half_h)
        if not upper:
            void.apply_translation([0.0, 0.0, -half_h])
    else:
        void = _build_infinity_void_half(
            lemniscate_a=lemniscate_a, r_bore=r_bore, half_h=half_h, upper=upper
        )

    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.difference([solid, void], **kw)
            if out is not None and out.volume > 1.0:
                return _finalize(out)
        except Exception:
            continue
    raise RuntimeError("build_figure8_tube_shell: boolean difference failed")


def _outward_normal(tangent: np.ndarray, point_xy: np.ndarray) -> np.ndarray:
    t = tangent / (np.linalg.norm(tangent) + 1e-9)
    n = np.array([-t[1], t[0], 0.0])
    if np.linalg.norm(n) < 1e-9:
        n = np.array([0.0, 1.0, 0.0])
    n = n / np.linalg.norm(n)
    if np.dot(n[:2], point_xy[:2]) < 0:
        n = -n
    return n


def add_fill_gate(
    mesh: trimesh.Trimesh,
    *,
    x: float,
    y: float,
    tangent: np.ndarray,
    r_bore: float,
    r_out: float,
    wall: float,
    neck_id: float,
    neck_od: float,
    height: float,
    upper: bool = True,
) -> trimesh.Trimesh:
    """Вертикальная горловина снаружи: шахта вверх, отверстие в канал, внутри «8» гладко."""
    out_n = _outward_normal(tangent, np.array([x, y, 0.0]))
    base = np.array([x, y, 0.0]) + out_n * r_out
    bx, by = float(base[0]), float(base[1])

    # Сквозной порт через стенку (горизонтально по нормали наружу)
    port = trimesh.creation.box(extents=[neck_id, wall + 1.0, r_bore * 1.4])
    port_mat = trimesh.geometry.align_vectors([0.0, 1.0, 0.0], out_n, False)
    port.apply_transform(port_mat)
    port_z = -r_bore * 0.55 if upper else r_bore * 0.55
    port.apply_translation([bx, by, port_z])
    mesh = _subtract(mesh, port)

    # Вертикальная шахта (+Z), основание на шве z=0
    chimney_outer = trimesh.creation.cylinder(radius=neck_od / 2.0, height=height, sections=24)
    chimney_bore = trimesh.creation.cylinder(radius=neck_id / 2.0, height=height + 2.0, sections=24)
    chimney_bore.apply_translation([0.0, 0.0, -1.0])
    chimney = _subtract(chimney_outer, chimney_bore)
    chimney.apply_translation([bx, by, height / 2.0])
    return _union(mesh, chimney)


def path_tangent_at(path: np.ndarray, x: float, y: float) -> np.ndarray:
    i = int(np.argmin((path[:, 0] - x) ** 2 + (path[:, 1] - y) ** 2))
    return np.asarray(_path_tangents(path)[i], dtype=np.float64)


def _seam_face_ring_2d(lemniscate_a: float, r_bore: float, r_outer: float, lip_t: float):
    """Кольцо шипа/паза на плоскости шва: стенка трубки чуть уменьшенная.

    Используем bore_blob (буфер лемнискаты по r_bore) — это гарантированно
    совпадает с профилем канала который вычтен при build_figure8_tube_shell.
    Кольцо = outer.buffer(-0.5).difference(bore_blob.buffer(0.45)) — одно тело
    или несколько (outer ring + inner lobe areas), объединяем в один mesh через
    _union_all в вызывающем коде.
    """
    outer, bore_blob = _fig8_buffer_polygons(lemniscate_a, r_bore, r_outer)
    ring = outer.buffer(-0.45).difference(bore_blob.buffer(0.45))
    if ring.is_empty:
        return []
    from shapely.geometry import Polygon
    if ring.geom_type == "Polygon":
        return [ring]
    # Возвращаем только наибольший полигон (внешнее кольцо трубки).
    # Мелкие фрагменты — это центры петель из «дыр» в bore_blob;
    # включать их нельзя — при вычитании из 03 это разрежет тело на части.
    polys = [g for g in ring.geoms if isinstance(g, Polygon) and g.area > 3.0]
    if not polys:
        return []
    return [max(polys, key=lambda g: g.area)]


def add_seam_tongue_groove(
    mesh: trimesh.Trimesh,
    path: np.ndarray,
    r_bore: float,
    r_outer: float,
    *,
    lemniscate_a: float,
    upper: bool,
    lip_h: float = 2.4,
    lip_t: float = 3.2,
    clearance: float = 0.28,
) -> trimesh.Trimesh:
    """Шип (02) / паз (03) по всему кольцу шва — держит и центрирует; M3 — основная сила."""
    z_lip_floor = 0.35 if upper else 0.0

    ring_polys = _seam_face_ring_2d(lemniscate_a, r_bore, r_outer, lip_t)
    if not ring_polys:
        return mesh

    import trimesh.repair as _rep
    lip_parts: List[trimesh.Trimesh] = []
    for poly in ring_polys:
        if upper:
            h = lip_h + clearance
            part = trimesh.creation.extrude_polygon(poly, height=h)
            _rep.fix_normals(part); _rep.fix_winding(part)
            part.apply_translation([0.0, 0.0, z_lip_floor])
        else:
            part = trimesh.creation.extrude_polygon(poly, height=lip_h)
            _rep.fix_normals(part); _rep.fix_winding(part)
        lip_parts.append(part)

    lip_solid = _union_all(lip_parts)
    if upper:
        result = _subtract(mesh, lip_solid)
        if result is None or len(result.vertices) < 100:
            return mesh
        if result.volume < mesh.volume * 0.5:
            return mesh
        return _finalize(result)
    return _union(mesh, lip_solid)


def _piezo_corner_frame(
    lemniscate_a: float, r_bore: float, r_outer: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Угол «8» (левый низ): точка на оси, контакт с наружным контуром, нормали."""
    path = fig8_centerline(lemniscate_a)
    tangents = _path_tangents(path)
    outer, _ = _fig8_buffer_polygons(lemniscate_a, r_bore, r_outer)
    coords = np.array(outer.exterior.coords)
    mask = coords[:, 0] < -12.0
    idx = int(np.argmin(coords[mask, 1]))
    contact = np.asarray(coords[mask][idx], dtype=np.float64)
    i = int(np.argmin(np.sum((path[:, :2] - contact) ** 2, axis=1)))
    p = path[i]
    tang = np.asarray(tangents[i], dtype=np.float64)
    out_n = _outward_normal(tang, p)
    return p, contact, tang, out_n


def piezo_floor_corner(
    lemniscate_a: float,
    r_bore: float,
    r_outer: float,
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """Центр гнезда: в стенке у наружного угла, открыто в канал (как у увлажнителя)."""
    p, contact, tang, out_n = _piezo_corner_frame(lemniscate_a, r_bore, r_outer)
    inward = -out_n / (np.linalg.norm(out_n) + 1e-9)
    wall_span = float(np.linalg.norm(contact[:2] - p[:2]))
    if wall_span < 1e-3:
        wall_span = r_outer - r_bore
    # середина стенки + чуть в канал — диск Ø20 не влезает в 4 мм стенки без босса
    center = contact[:2] - inward[:2] * (wall_span * 0.55)
    return float(center[0]), float(center[1]), tang, out_n


def piezo_corner_on_outer(lemniscate_a: float, r_bore: float, r_outer: float) -> Tuple[float, float, np.ndarray, np.ndarray]:
    return piezo_floor_corner(lemniscate_a, r_bore, r_outer)


def add_piezo_pocket(
    mesh: trimesh.Trimesh,
    *,
    lemniscate_a: float,
    r_bore: float,
    r_outer: float,
    gasket_od_mm: float,
    pocket_depth_mm: float,
    wall_mm: float,
    ceramic_od_mm: float = 16.4,
    shelf_mm: float = 0.35,
) -> trimesh.Trimesh:
    """Гнездо Ø20 у наружного угла: босс выступает наружу, врастает в стенку трубки."""
    p, contact, _, out_n = _piezo_corner_frame(lemniscate_a, r_bore, r_outer)
    gasket_r = gasket_od_mm / 2.0 + 0.15
    depth = pocket_depth_mm
    floor_z = -r_bore + 0.25

    # Босс: ось — наружу из стенки, центр смещён ВНУТРЬ стенки на 40% высоты
    # → босс перекрывается с телом трубки на 40%·boss_h → _union работает
    boss_r = gasket_r + 2.2
    boss_h = max(8.0, gasket_r * 2.0 + 2.0)
    boss = trimesh.creation.cylinder(radius=boss_r, height=boss_h, sections=48)
    mat = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], out_n, False)
    boss.apply_transform(mat)
    # Центр: от точки на внешней стенке смещаем на (boss_h*0.5 - wall_overlap) наружу
    wall_overlap = wall_mm * 1.1
    shift = boss_h * 0.5 - wall_overlap
    cx = float(contact[0]) + float(out_n[0]) * shift
    cy = float(contact[1]) + float(out_n[1]) * shift
    boss.apply_translation([cx, cy, floor_z + depth * 0.4])
    mesh = _union(mesh, boss)

    # Гнездо вдоль оси босса (глубоко в центре — не от угла трубки)
    # Ось выдавливания совпадает с out_n — тот же mat
    pocket = trimesh.creation.cylinder(radius=gasket_r, height=depth, sections=48)
    pocket.apply_transform(mat)
    # Центр гнезда: на лицевой стороне босса (снаружи)
    face_shift = shift + boss_h * 0.5 - depth * 0.5
    px = float(contact[0]) + float(out_n[0]) * face_shift
    py = float(contact[1]) + float(out_n[1]) * face_shift
    pocket.apply_translation([px, py, floor_z + depth * 0.4])
    out = _subtract(mesh, pocket)

    if ceramic_od_mm > 0 and shelf_mm > 0:
        inner_r = ceramic_od_mm / 2.0 + 0.1
        inner_depth = depth + shelf_mm
        inner_pocket = trimesh.creation.cylinder(radius=inner_r, height=inner_depth, sections=36)
        inner_pocket.apply_transform(mat)
        iface_shift = shift + boss_h * 0.5 - inner_depth * 0.5
        ipx = float(contact[0]) + float(out_n[0]) * iface_shift
        ipy = float(contact[1]) + float(out_n[1]) * iface_shift
        inner_pocket.apply_translation([ipx, ipy, floor_z + depth * 0.4])
        out = _subtract(out, inner_pocket)

    return out


def add_clip_features(
    mesh: trimesh.Trimesh,
    clips: Sequence[Tuple[float, float]],
    *,
    upper: bool,
    tab_w: float = 10.0,
    tab_h: float = 5.0,
    tab_t: float = 3.0,
) -> trimesh.Trimesh:
    out = mesh
    for cx, cy in clips:
        sign = 1.0 if cx >= 0 else -1.0
        if upper:
            tab = trimesh.creation.box(extents=[tab_w, tab_h, tab_t])
            tab.apply_translation([cx + sign * (tab_w / 2.0 + 2.0), cy, tab_t / 2.0])
            out = _union(out, tab)
        else:
            slot = trimesh.creation.box(extents=[tab_w + 1.0, tab_h + 1.0, tab_t + 1.0])
            slot.apply_translation([cx + sign * (tab_w / 2.0 + 2.0), cy, tab_t / 2.0])
            out = _subtract(out, slot)
    return out


def add_screw_holes(mesh: trimesh.Trimesh, xy: List[Tuple[float, float]], r: float, depth: float) -> trimesh.Trimesh:
    out = mesh
    for sx, sy in xy:
        hole = trimesh.creation.cylinder(radius=r, height=depth + 6.0, sections=12)
        hole.apply_translation([sx, sy, depth / 2.0 - 3.0])
        out = _subtract(out, hole)
    return out


def build_fill_cap(
    x: float,
    y: float,
    z: float,
    slide_w: float,
    neck_id: float,
    outward: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """Задвижка: пробка в вертикальную шахту + ручка."""
    plug = trimesh.creation.cylinder(radius=neck_id / 2.0 - 0.35, height=3.0, sections=20)
    plate = trimesh.creation.box(extents=[slide_w, 14.0, 1.2])
    handle = trimesh.creation.box(extents=[slide_w + 8.0, 10.0, 1.0])
    handle.apply_translation([0.0, 0.0, 1.1])
    plug.apply_translation([0.0, 0.0, 1.5])
    body = trimesh.util.concatenate([plate, handle, plug])
    body.apply_translation([x, y, z])
    return _finalize(body)


def contour_u_leg_specs(
    path: np.ndarray,
    r_outer: float,
    *,
    lemniscate_a: float,
    r_bore: float = 8.0,
) -> List[dict]:
    """4 точки U-ножек на внешнем контуре «8»."""
    outer, _ = _fig8_buffer_polygons(lemniscate_a, r_bore, r_outer)
    coords = np.array(outer.exterior.coords)
    tangents = _path_tangents(path)
    picks = [
        int(np.argmin(coords[:, 1])),
        int(np.argmax(coords[:, 1])),
        int(np.argmin(coords[:, 0])),
        int(np.argmax(coords[:, 0])),
    ]
    specs: List[dict] = []
    for idx in picks:
        contact = coords[idx, :2]
        i = int(np.argmin(np.sum((path[:, :2] - contact) ** 2, axis=1)))
        p = path[i]
        tang = np.asarray(tangents[i], dtype=np.float64)
        delta = contact - p[:2]
        ln = float(np.linalg.norm(delta))
        out_n = np.array([delta[0] / ln, delta[1] / ln, 0.0]) if ln > 1e-6 else _outward_normal(tang, p)
        specs.append(
            {
                "contact_xy": (float(contact[0]), float(contact[1])),
                "tangent": tang,
                "outward": out_n,
            }
        )
    return specs


# совместимость для PDF / spec
def outer_cradle_specs(path, r_outer, *, lemniscate_a=None, r_bore=8.0, **_) -> List[dict]:
    la = lemniscate_a if lemniscate_a is not None else float(np.max(np.abs(path[:, 0])))
    return contour_u_leg_specs(path, r_outer, lemniscate_a=la, r_bore=r_bore)


def cradle_centers(path: np.ndarray, r_outer: float, outward_mm: float = 10.0) -> List[Tuple[float, float]]:
    la = float(np.max(np.abs(path[:, 0])))
    return [s["contact_xy"] for s in contour_u_leg_specs(path, r_outer, lemniscate_a=la)]


def stand_footprint_mm(lemniscate_a: float, r_bore: float, r_outer: float, margin: float = 10.0) -> Tuple[float, float]:
    outer, _ = _fig8_buffer_polygons(lemniscate_a, r_bore, r_outer)
    b = outer.bounds
    pad = 5.0 + margin  # толщина U-ножки + запас
    return (b[2] - b[0]) + 2.0 * pad, (b[3] - b[1]) + 2.0 * pad


def _oriented_box(
    center_xy: Tuple[float, float],
    z_center: float,
    tangent: np.ndarray,
    outward: np.ndarray,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
) -> trimesh.Trimesh:
    t = tangent / (np.linalg.norm(tangent) + 1e-9)
    o = outward / (np.linalg.norm(outward) + 1e-9)
    z = np.array([0.0, 0.0, 1.0])
    rot = np.eye(4)
    rot[:3, 0] = t
    rot[:3, 1] = o
    rot[:3, 2] = z
    box = trimesh.creation.box(extents=[width_mm, depth_mm, height_mm])
    box.apply_transform(rot)
    box.apply_translation([center_xy[0], center_xy[1], z_center])
    return box


def _build_u_leg(
    contact: np.ndarray,
    tangent: np.ndarray,
    outward: np.ndarray,
    *,
    r_outer: float,
    clearance_mm: float,
    base_mm: float,
    leg_mm: float,
    span_mm: float,
    wall_mm: float,
) -> trimesh.Trimesh:
    """U-ножка: сращена с плитой (z=0), паз по радиусу «8»."""
    gro_r = r_outer + clearance_mm
    t = tangent / (np.linalg.norm(tangent) + 1e-9)
    o = outward / (np.linalg.norm(outward) + 1e-9)
    total_h = base_mm + leg_mm
    inner_gap = clearance_mm
    block_c = contact + o[:2] * (inner_gap + wall_mm * 0.5)

    leg = _oriented_box(
        (float(block_c[0]), float(block_c[1])),
        total_h / 2.0,
        t,
        o,
        span_mm,
        wall_mm,
        total_h,
    )

    cyl = trimesh.creation.cylinder(radius=gro_r, height=span_mm + 6.0, sections=26)
    cmat = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], t, False)
    cyl.apply_transform(cmat)
    cyl_c = contact + o[:2] * gro_r
    cyl_z = base_mm + leg_mm - gro_r * 0.25
    cyl.apply_translation([float(cyl_c[0]), float(cyl_c[1]), cyl_z])
    return _subtract(leg, cyl)


def build_stand_mesh(
    *,
    lemniscate_a: float,
    r_outer: float,
    footprint_x: float,
    footprint_y: float,
    base_mm: float = 4.0,
    pillar_mm: float = 16.0,
    groove_r: float | None = None,
    r_bore: float = 8.0,
) -> trimesh.Trimesh:
    """Плита + 4 U-ножки по контуру «8» (нижняя половина опирается в пазы)."""
    path = fig8_centerline(lemniscate_a)
    clearance = 0.35
    leg_mm = max(r_outer + 1.5, pillar_mm - base_mm) if pillar_mm > base_mm else r_outer + 1.5
    span_mm = 26.0
    wall_mm = 5.5

    base = trimesh.creation.box(extents=[footprint_x, footprint_y, base_mm])
    base.apply_translation([0.0, 0.0, base_mm / 2.0])
    parts: List[trimesh.Trimesh] = [base]

    for spec in contour_u_leg_specs(path, r_outer, lemniscate_a=lemniscate_a, r_bore=r_bore):
        contact = np.array([spec["contact_xy"][0], spec["contact_xy"][1]])
        parts.append(
            _build_u_leg(
                contact,
                spec["tangent"],
                spec["outward"],
                r_outer=r_outer,
                clearance_mm=clearance,
                base_mm=base_mm,
                leg_mm=leg_mm,
                span_mm=span_mm,
                wall_mm=wall_mm,
            )
        )

    return _finalize(_union(base, trimesh.util.concatenate(parts[1:])) if len(parts) > 1 else _finalize(base))
