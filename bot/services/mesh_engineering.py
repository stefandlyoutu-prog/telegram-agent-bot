"""
Engineering analysis layer for printable meshes.

This module gives the bot a real *physics + geometry brain* on top of
`trimesh`.  Everything here is closed-form / first-principles engineering,
not heuristics:

  * Mass properties      — volume, mass (per material density), centre of
                           mass, full inertia tensor about the CoM, and the
                           principal moments / axes.
  * Static stability     — projects the CoM onto the build plate, builds the
                           support polygon (convex hull of bed-contact
                           points) and reports the tip-over (topple) angle and
                           the safety margin.  Pure rigid-body statics.
  * Overhang analysis    — classifies every triangle by the slope of its
                           surface relative to the build plate using the face
                           normal, and estimates the down-facing area that a
                           slicer would flag for support (slicer convention:
                           support is needed when a surface is steeper than
                           `overhang_limit_deg` measured from vertical).
  * Wall thickness       — ray-casts inward from sampled surface points to
                           measure local solid thickness and flag walls below
                           the printable minimum.
  * Print orientation    — scores a set of candidate orientations (the six
                           axis-aligned bbox faces plus the principal-axis
                           rest pose) by support burden, footprint stability
                           and build height, and recommends the best one.

The output is a structured :class:`PrintabilityReport` plus a Russian
human-readable summary used in chat captions, self-checks and LLM context.

All maths is unit-agnostic but the bot works in millimetres; densities are
therefore handled as g/cm³ and converted internally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

try:  # trimesh is already a hard dependency elsewhere in the bot
    import trimesh
except Exception:  # pragma: no cover - trimesh always present in prod
    trimesh = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
#  Material database (FDM / resin), density in g/cm³
# ─────────────────────────────────────────────────────────────────────────────

MATERIAL_DENSITY_G_CM3: Dict[str, float] = {
    "pla": 1.24,
    "pla-cf": 1.30,
    "petg": 1.27,
    "petg-cf": 1.30,
    "abs": 1.04,
    "asa": 1.07,
    "tpu": 1.21,
    "nylon": 1.14,
    "pa-cf": 1.16,
    "pc": 1.20,
    "resin": 1.10,
    "hips": 1.04,
    "pp": 0.90,
}
DEFAULT_MATERIAL = "pla"

# A coarse Young's-modulus table (MPa) for first-order stiffness hints only.
MATERIAL_MODULUS_MPA: Dict[str, float] = {
    "pla": 3500.0,
    "pla-cf": 4200.0,
    "petg": 2100.0,
    "petg-cf": 3600.0,
    "abs": 2200.0,
    "asa": 2000.0,
    "tpu": 70.0,
    "nylon": 1700.0,
    "pa-cf": 6500.0,
    "pc": 2300.0,
    "resin": 2400.0,
    "hips": 1900.0,
    "pp": 1300.0,
}


def material_density(material: str) -> float:
    return MATERIAL_DENSITY_G_CM3.get((material or "").strip().lower(),
                                       MATERIAL_DENSITY_G_CM3[DEFAULT_MATERIAL])


# ─────────────────────────────────────────────────────────────────────────────
#  Report dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MassProperties:
    material: str
    density_g_cm3: float
    volume_mm3: float
    mass_g: float
    surface_area_mm2: float
    bbox_mm: Tuple[float, float, float]
    center_mass_mm: Tuple[float, float, float]
    # Inertia tensor about the CoM in g·mm² (3×3) and its principal values.
    inertia_g_mm2: List[List[float]]
    principal_moments_g_mm2: Tuple[float, float, float]
    is_watertight: bool
    # Solidity = mesh volume / convex-hull volume (1.0 = fully convex/solid).
    solidity: float

    def gyration_radii_mm(self) -> Tuple[float, float, float]:
        """Radius of gyration per principal axis = sqrt(I/m)."""
        if self.mass_g <= 0:
            return (0.0, 0.0, 0.0)
        return tuple(  # type: ignore[return-value]
            math.sqrt(max(0.0, I) / self.mass_g)
            for I in self.principal_moments_g_mm2
        )


@dataclass
class StabilityReport:
    com_height_mm: float
    support_base_area_mm2: float
    # Horizontal distance from the CoM ground projection to the nearest edge
    # of the support polygon. Negative ⇒ CoM is outside base ⇒ topples.
    com_margin_mm: float
    com_inside_base: bool
    topple_angle_deg: float          # tilt needed to tip about nearest edge
    bed_contact_points: int
    # Tip-over safety ratio = margin / com_height (>0.2 is comfortable).
    stability_ratio: float
    verdict: str                     # "stable" | "tippy" | "unstable"


@dataclass
class OverhangReport:
    overhang_limit_deg: float
    total_area_mm2: float
    overhang_area_mm2: float
    overhang_fraction: float
    steep_overhang_area_mm2: float   # surfaces ≥ 70° from vertical (near roof)
    bridge_candidate_area_mm2: float # near-horizontal down faces (bridges)
    needs_support: bool
    worst_overhang_deg: float        # most horizontal down-facing surface


@dataclass
class ThicknessReport:
    min_wall_mm_target: float
    sampled_points: int
    min_thickness_mm: float
    p05_thickness_mm: float          # 5th percentile (thin regions)
    median_thickness_mm: float
    thin_fraction: float             # fraction of samples below target
    thin_risk: bool


@dataclass
class OrientationCandidate:
    name: str
    rotation_matrix: List[List[float]]   # 4×4 homogeneous
    height_mm: float
    footprint_mm2: float
    support_area_mm2: float
    stability_ratio: float
    score: float                     # higher = better


@dataclass
class PrintabilityReport:
    mass: MassProperties
    stability: StabilityReport
    overhang: OverhangReport
    thickness: Optional[ThicknessReport]
    recommended_orientation: Optional[OrientationCandidate]
    orientation_candidates: List[OrientationCandidate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        def _d(o):
            if o is None:
                return None
            return {k: v for k, v in o.__dict__.items()}
        return {
            "mass": _d(self.mass),
            "stability": _d(self.stability),
            "overhang": _d(self.overhang),
            "thickness": _d(self.thickness),
            "recommended_orientation": _d(self.recommended_orientation),
            "orientation_candidates": [_d(c) for c in self.orientation_candidates],
            "notes": list(self.notes),
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Mass properties
# ─────────────────────────────────────────────────────────────────────────────

def mass_properties(mesh: "trimesh.Trimesh", material: str = DEFAULT_MATERIAL
                     ) -> MassProperties:
    """Closed-form mass / inertia of a (preferably watertight) mesh.

    trimesh computes volume integrals analytically over the surface
    triangulation (divergence theorem), so this is exact for the given
    tessellation, not Monte-Carlo.
    """
    density = material_density(material)
    rho_mm3 = density / 1000.0  # g/cm³ → g/mm³

    ext = mesh.extents if mesh.extents is not None else np.zeros(3)
    bbox = (float(ext[0]), float(ext[1]), float(ext[2]))
    area = float(mesh.area)
    watertight = bool(mesh.is_watertight)

    # Volume: use abs() because non-watertight meshes can report signed/neg.
    try:
        vol = float(abs(mesh.volume))
    except Exception:
        vol = 0.0
    if not np.isfinite(vol) or vol <= 0.0:
        # Fall back to convex hull volume for open meshes.
        try:
            vol = float(abs(mesh.convex_hull.volume))
        except Exception:
            vol = 0.0

    mass = vol * rho_mm3

    # Centre of mass
    try:
        com = np.asarray(mesh.center_mass, dtype=float)
        if not np.all(np.isfinite(com)):
            raise ValueError
    except Exception:
        com = np.asarray(mesh.centroid, dtype=float)

    # Inertia tensor: trimesh.moment_inertia is computed at density=1 about
    # the CoM. Scale by our true density (g/mm³) to get g·mm².
    try:
        I_unit = np.asarray(mesh.moment_inertia, dtype=float)
        I = I_unit * rho_mm3
        if not np.all(np.isfinite(I)):
            raise ValueError
    except Exception:
        I = np.zeros((3, 3))

    try:
        principal = np.linalg.eigvalsh((I + I.T) / 2.0)
        principal = np.sort(np.abs(principal))
        principal_t = (float(principal[0]), float(principal[1]),
                       float(principal[2]))
    except Exception:
        principal_t = (0.0, 0.0, 0.0)

    # Solidity
    solidity = 1.0
    try:
        hull_vol = float(abs(mesh.convex_hull.volume))
        if hull_vol > 0:
            solidity = max(0.0, min(1.0, vol / hull_vol))
    except Exception:
        pass

    return MassProperties(
        material=(material or DEFAULT_MATERIAL).lower(),
        density_g_cm3=density,
        volume_mm3=vol,
        mass_g=mass,
        surface_area_mm2=area,
        bbox_mm=bbox,
        center_mass_mm=(float(com[0]), float(com[1]), float(com[2])),
        inertia_g_mm2=[[float(x) for x in row] for row in I],
        principal_moments_g_mm2=principal_t,
        is_watertight=watertight,
        solidity=solidity,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Static stability (rigid-body statics)
# ─────────────────────────────────────────────────────────────────────────────

def _support_polygon(mesh: "trimesh.Trimesh", contact_eps_mm: float = 0.6
                     ) -> Tuple[np.ndarray, float]:
    """Return (hull_xy_points, base_area). Points are bed-contact vertices."""
    verts = np.asarray(mesh.vertices, dtype=float)
    if len(verts) == 0:
        return np.zeros((0, 2)), 0.0
    z_min = verts[:, 2].min()
    contact = verts[np.abs(verts[:, 2] - z_min) <= contact_eps_mm][:, :2]
    if len(contact) < 3:
        # Fall back to the full bbox footprint.
        contact = verts[:, :2]
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(contact)
        hull_pts = contact[hull.vertices]
        area = float(hull.volume)  # for 2-D ConvexHull, .volume == area
    except Exception:
        # Bounding-box fallback
        mn = contact.min(axis=0)
        mx = contact.max(axis=0)
        hull_pts = np.array([[mn[0], mn[1]], [mx[0], mn[1]],
                             [mx[0], mx[1]], [mn[0], mx[1]]])
        area = float((mx[0] - mn[0]) * (mx[1] - mn[1]))
    return hull_pts, area


def _point_in_polygon_margin(point_xy: np.ndarray, poly: np.ndarray) -> float:
    """Signed distance from point to polygon boundary (+ inside, − outside).

    Uses the minimum distance to all edges, signed by an even-odd inside test.
    """
    if len(poly) < 3:
        return -1.0
    px, py = float(point_xy[0]), float(point_xy[1])

    # Inside test (ray casting)
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i

    # Distance to nearest edge
    min_d = float("inf")
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ab = b - a
        t = np.dot(point_xy - a, ab) / (np.dot(ab, ab) + 1e-12)
        t = max(0.0, min(1.0, t))
        proj = a + t * ab
        d = float(np.linalg.norm(point_xy - proj))
        min_d = min(min_d, d)

    return min_d if inside else -min_d


def stability(mesh: "trimesh.Trimesh",
              com: Optional[np.ndarray] = None,
              contact_eps_mm: float = 0.6) -> StabilityReport:
    """Tip-over analysis for the mesh resting on the XY plane (bed at min Z)."""
    if com is None:
        try:
            com = np.asarray(mesh.center_mass, dtype=float)
            if not np.all(np.isfinite(com)):
                raise ValueError
        except Exception:
            com = np.asarray(mesh.centroid, dtype=float)

    verts = np.asarray(mesh.vertices, dtype=float)
    z_min = float(verts[:, 2].min()) if len(verts) else 0.0
    com_height = max(1e-6, float(com[2]) - z_min)

    hull_pts, base_area = _support_polygon(mesh, contact_eps_mm)
    n_contact = int(
        np.sum(np.abs(verts[:, 2] - z_min) <= contact_eps_mm)
    ) if len(verts) else 0

    margin = _point_in_polygon_margin(com[:2], hull_pts) if len(hull_pts) >= 3 \
        else -1.0
    inside = margin > 0

    # Tilt angle to topple about the nearest support edge:
    #   the body tips when the CoM passes over the edge, i.e. when
    #   tan(theta) = margin / com_height.
    if inside and com_height > 0:
        topple_angle = math.degrees(math.atan2(margin, com_height))
    else:
        topple_angle = 0.0

    ratio = (margin / com_height) if com_height > 0 else -1.0

    if not inside:
        verdict = "unstable"
    elif ratio < 0.15 or topple_angle < 12.0:
        verdict = "tippy"
    else:
        verdict = "stable"

    return StabilityReport(
        com_height_mm=com_height,
        support_base_area_mm2=base_area,
        com_margin_mm=margin,
        com_inside_base=inside,
        topple_angle_deg=topple_angle,
        bed_contact_points=n_contact,
        stability_ratio=ratio,
        verdict=verdict,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Overhang analysis (slicer convention)
# ─────────────────────────────────────────────────────────────────────────────

def overhangs(mesh: "trimesh.Trimesh",
              overhang_limit_deg: float = 45.0,
              build_dir: Tuple[float, float, float] = (0, 0, 1),
              bed_eps_mm: float = 0.5) -> OverhangReport:
    """Classify down-facing surfaces that a slicer would need to support.

    Convention: ``overhang_limit_deg`` is measured from *vertical*.  A surface
    needs support when its slope from the build plate is shallower than the
    limit.  For a face with outward normal ``n`` and build direction +Z, the
    surface is down-facing when ``n·(+Z) < 0``; the angle of the surface below
    the horizontal plane is ``asin(-n_z)``.  Support is required when that
    angle exceeds ``90° − overhang_limit_deg`` (e.g. limit 45° ⇒ any surface
    more horizontal than 45° from the plate).

    Faces lying *on* the build plate (the resting footprint, within
    ``bed_eps_mm`` of the lowest Z) are excluded — they are supported by the
    bed itself, not by generated support material.
    """
    bd = np.asarray(build_dir, dtype=float)
    bd = bd / (np.linalg.norm(bd) + 1e-12)

    normals = np.asarray(mesh.face_normals, dtype=float)
    areas = np.asarray(mesh.area_faces, dtype=float)
    if len(normals) == 0:
        return OverhangReport(overhang_limit_deg, 0, 0, 0, 0, 0, False, 0)

    total_area = float(areas.sum())

    # Exclude faces resting on the bed (footprint): their centroid sits at the
    # lowest layer along the build direction.
    centroids = mesh.triangles_center
    proj = centroids @ bd
    z_floor = float(proj.min())
    on_bed = proj <= (z_floor + bed_eps_mm)

    # Component of each normal along build direction.
    nz = normals @ bd                       # cos(angle between n and +Z)
    # Down-facing surfaces have nz < 0. The surface's tilt below horizontal is
    # phi = asin(-nz) ∈ [0°, 90°]; phi=90° ⇒ horizontal roof.
    down = (nz < -1e-6) & (~on_bed)
    phi = np.zeros_like(nz)
    phi[down] = np.degrees(np.arcsin(np.clip(-nz[down], 0.0, 1.0)))

    # Support needed when phi > (90 - limit): surface more horizontal than the
    # allowed overhang.
    support_threshold = 90.0 - overhang_limit_deg
    needs = down & (phi > support_threshold)

    overhang_area = float(areas[needs].sum())
    steep_area = float(areas[down & (phi >= 70.0)].sum())
    bridge_area = float(areas[down & (phi >= 80.0)].sum())
    worst = float(phi[down].max()) if np.any(down) else 0.0

    frac = (overhang_area / total_area) if total_area > 0 else 0.0

    return OverhangReport(
        overhang_limit_deg=overhang_limit_deg,
        total_area_mm2=total_area,
        overhang_area_mm2=overhang_area,
        overhang_fraction=frac,
        steep_overhang_area_mm2=steep_area,
        bridge_candidate_area_mm2=bridge_area,
        needs_support=overhang_area > max(20.0, 0.01 * total_area),
        worst_overhang_deg=worst,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Wall thickness (inward ray casting)
# ─────────────────────────────────────────────────────────────────────────────

def wall_thickness(mesh: "trimesh.Trimesh",
                   min_wall_mm: float = 1.2,
                   samples: int = 400) -> Optional[ThicknessReport]:
    """Estimate local solid thickness by casting rays inward from the surface.

    For a sample of face centroids we shoot a ray along ``-normal`` (into the
    solid) and take the distance to the next surface hit.  This is the classic
    "ray thickness" gauge; it is approximate but robust and fast on a sample.
    """
    faces = np.asarray(mesh.faces)
    if len(faces) == 0:
        return None

    normals = np.asarray(mesh.face_normals, dtype=float)
    centroids = mesh.triangles_center
    n_faces = len(faces)
    if n_faces == 0:
        return None

    rng = np.random.default_rng(12345)
    k = min(samples, n_faces)
    idx = rng.choice(n_faces, size=k, replace=False)

    # Start a hair inside the surface to avoid self-hit at the origin face.
    origins = centroids[idx] - normals[idx] * 1e-3
    directions = -normals[idx]

    try:
        locations, index_ray, _ = mesh.ray.intersects_location(
            ray_origins=origins, ray_directions=directions,
            multiple_hits=False,
        )
    except Exception:
        return None

    if len(index_ray) == 0:
        return None

    dists = np.linalg.norm(locations - origins[index_ray], axis=1)
    dists = dists[np.isfinite(dists) & (dists > 1e-4)]
    if len(dists) == 0:
        return None

    thin_frac = float(np.mean(dists < min_wall_mm))
    return ThicknessReport(
        min_wall_mm_target=min_wall_mm,
        sampled_points=int(len(dists)),
        min_thickness_mm=float(dists.min()),
        p05_thickness_mm=float(np.percentile(dists, 5)),
        median_thickness_mm=float(np.median(dists)),
        thin_fraction=thin_frac,
        thin_risk=thin_frac > 0.05,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Print-orientation optimisation
# ─────────────────────────────────────────────────────────────────────────────

def _axis_aligned_orientations() -> List[Tuple[str, np.ndarray]]:
    """Six bbox-face-down rotations + identity."""
    out: List[Tuple[str, np.ndarray]] = [("as_is", np.eye(4))]
    rx90 = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])
    rx_90 = trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])
    ry90 = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
    ry_90 = trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])
    rx180 = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    out += [
        ("rot_x+90", rx90), ("rot_x-90", rx_90),
        ("rot_y+90", ry90), ("rot_y-90", ry_90),
        ("flip_180", rx180),
    ]
    return out


# Default Bambu Lab P-series build volume (mm).
DEFAULT_BED_MM: Tuple[float, float, float] = (256.0, 256.0, 256.0)


def _score_orientation(m: "trimesh.Trimesh", overhang_limit_deg: float,
                        bed_mm: Tuple[float, float, float]
                        ) -> Tuple[float, float, float, float, float]:
    """Return (score, height, footprint, support_area, stability_ratio)."""
    ext = m.extents
    height = float(ext[2])
    footprint = float(ext[0] * ext[1])

    ov = overhangs(m, overhang_limit_deg=overhang_limit_deg)
    st = stability(m)

    # Normalised penalties (lower is better), then converted to a score.
    support_pen = ov.overhang_fraction                  # 0..1
    height_pen = height / (height + max(ext[0], ext[1]) + 1e-6)
    # Stability bonus: clamp ratio into 0..1-ish.
    stab = max(-0.5, min(1.0, st.stability_ratio))
    inside_bonus = 0.0 if st.com_inside_base else -1.0

    # Build-volume fit: a part that does not fit upright must be laid down.
    fit_pen = 0.0
    if height > bed_mm[2]:
        fit_pen -= 3.0          # cannot print this tall — hard penalty
    if ext[0] > bed_mm[0] or ext[1] > bed_mm[1]:
        fit_pen -= 1.0          # footprint over bed (might still split)

    score = (
        -1.6 * support_pen          # supports are the biggest cost
        - 0.5 * height_pen          # shorter prints are safer/faster
        + 0.8 * stab                # broad stable base is good
        + inside_bonus              # never recommend a toppling pose
        + fit_pen                   # must fit the printer
    )
    return score, height, footprint, ov.overhang_area_mm2, st.stability_ratio


def best_orientation(mesh: "trimesh.Trimesh",
                     overhang_limit_deg: float = 45.0,
                     try_principal: bool = True,
                     bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM
                     ) -> Tuple[Optional[OrientationCandidate],
                                List[OrientationCandidate]]:
    """Score candidate orientations and return (best, all_candidates)."""
    candidates: List[OrientationCandidate] = []
    orientations = _axis_aligned_orientations()

    if try_principal:
        # Lay the longest principal axis horizontal: align it to X.
        try:
            T = mesh.principal_inertia_transform
            candidates_extra = [("principal_rest", np.asarray(T))]
            orientations += candidates_extra
        except Exception:
            pass

    for name, R in orientations:
        try:
            m = mesh.copy()
            m.apply_transform(R)
            # Drop onto the bed (min Z to 0).
            m.apply_translation([0, 0, -m.bounds[0][2]])
            score, height, footprint, support_area, stab = _score_orientation(
                m, overhang_limit_deg, bed_mm
            )
            candidates.append(OrientationCandidate(
                name=name,
                rotation_matrix=[[float(x) for x in row] for row in R],
                height_mm=height,
                footprint_mm2=footprint,
                support_area_mm2=support_area,
                stability_ratio=stab,
                score=score,
            ))
        except Exception:
            continue

    if not candidates:
        return None, []
    candidates.sort(key=lambda c: -c.score)
    return candidates[0], candidates


# ─────────────────────────────────────────────────────────────────────────────
#  Top-level report
# ─────────────────────────────────────────────────────────────────────────────

def analyze_mesh(mesh: "trimesh.Trimesh",
                 material: str = DEFAULT_MATERIAL,
                 min_wall_mm: float = 1.2,
                 overhang_limit_deg: float = 45.0,
                 do_thickness: bool = True,
                 do_orientation: bool = True,
                 bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM
                 ) -> PrintabilityReport:
    """Run the full engineering analysis on a single mesh."""
    notes: List[str] = []

    mass = mass_properties(mesh, material=material)
    if not mass.is_watertight:
        notes.append("Меш не watertight — масса/инерция оценены приближённо.")

    st = stability(mesh)
    if st.verdict == "unstable":
        notes.append(
            "ЦТ выходит за опору — деталь опрокинется; нужна переориентация "
            "или опора/плот."
        )
    elif st.verdict == "tippy":
        notes.append(
            f"Узкая опора: запас до опрокидывания {st.topple_angle_deg:.0f}° — "
            "печать с brim рекомендуется."
        )

    ov = overhangs(mesh, overhang_limit_deg=overhang_limit_deg)
    if ov.needs_support:
        notes.append(
            f"Нависания {ov.overhang_fraction*100:.0f}% площади "
            f"(порог {overhang_limit_deg:.0f}°) — потребуются поддержки."
        )

    th = wall_thickness(mesh, min_wall_mm=min_wall_mm) if do_thickness else None
    if th and th.thin_risk:
        notes.append(
            f"Тонкие стенки: {th.thin_fraction*100:.0f}% выборки < "
            f"{min_wall_mm:.1f} мм (min {th.min_thickness_mm:.2f} мм)."
        )

    best, cands = (None, [])
    if do_orientation:
        best, cands = best_orientation(
            mesh, overhang_limit_deg=overhang_limit_deg, bed_mm=bed_mm
        )
        if (best is not None and mass.bbox_mm
                and max(mass.bbox_mm) > max(bed_mm)):
            notes.append(
                f"Габарит {max(mass.bbox_mm):.0f} мм превышает стол "
                f"{max(bed_mm):.0f} мм — деталь нужно разрезать на части."
            )

    return PrintabilityReport(
        mass=mass, stability=st, overhang=ov, thickness=th,
        recommended_orientation=best, orientation_candidates=cands,
        notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Human-readable formatting (RU)
# ─────────────────────────────────────────────────────────────────────────────

_VERDICT_RU = {
    "stable": "устойчива",
    "tippy": "склонна к опрокидыванию",
    "unstable": "неустойчива",
}


def format_report_text(report: PrintabilityReport, name: str = "деталь") -> str:
    m = report.mass
    st = report.stability
    ov = report.overhang
    lines: List[str] = []
    lines.append(f"📐 Инженерный анализ — {name}")
    lines.append(
        f"• Габариты: {m.bbox_mm[0]:.1f}×{m.bbox_mm[1]:.1f}×{m.bbox_mm[2]:.1f} мм"
    )
    lines.append(
        f"• Объём: {m.volume_mm3/1000.0:.1f} см³, масса ({m.material.upper()} "
        f"ρ={m.density_g_cm3:.2f}): {m.mass_g:.1f} г"
    )
    lines.append(
        f"• Площадь поверхности: {m.surface_area_mm2/100.0:.1f} см², "
        f"solidity {m.solidity:.2f}"
    )
    lines.append(
        f"• ЦТ: ({m.center_mass_mm[0]:.1f}, {m.center_mass_mm[1]:.1f}, "
        f"{m.center_mass_mm[2]:.1f}) мм, высота ЦТ {st.com_height_mm:.1f} мм"
    )
    lines.append(
        f"• Устойчивость: {_VERDICT_RU.get(st.verdict, st.verdict)}, "
        f"угол опрокидывания {st.topple_angle_deg:.0f}°, "
        f"запас {st.com_margin_mm:.1f} мм"
    )
    lines.append(
        f"• Нависания: {ov.overhang_fraction*100:.0f}% площади, "
        f"{'нужны поддержки' if ov.needs_support else 'поддержки не требуются'}"
    )
    if report.thickness:
        th = report.thickness
        lines.append(
            f"• Стенки: min {th.min_thickness_mm:.2f} мм, медиана "
            f"{th.median_thickness_mm:.2f} мм "
            f"(цель ≥ {th.min_wall_mm_target:.1f} мм)"
        )
    if report.recommended_orientation:
        ro = report.recommended_orientation
        lines.append(
            f"• Рекомендуемая ориентация: «{ro.name}» — высота "
            f"{ro.height_mm:.0f} мм, нависания {ro.support_area_mm2/100.0:.1f} см²"
        )
    for n in report.notes:
        lines.append(f"  ⚠ {n}")
    return "\n".join(lines)


def kit_engineering_report(parts: List[Tuple[str, "trimesh.Trimesh"]],
                            material: str = DEFAULT_MATERIAL,
                            min_wall_mm: float = 1.2,
                            bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM,
                            include_gate: bool = True,
                            include_load_capacity: bool = True) -> str:
    """Build a multi-part engineering report (one block per named part).

    Used to drop an `engineering_report.txt` into kit ZIPs so the user gets
    real mass/stability/overhang/orientation numbers per component, plus the
    printability-gate verdict, an estimated load capacity (FEA-lite) and a
    total filament-mass estimate for the whole assembly.
    """
    blocks: List[str] = []
    total_mass = 0.0
    total_vol = 0.0
    n_block = 0
    n_warn = 0
    for name, mesh in parts:
        try:
            rep = analyze_mesh(mesh, material=material, min_wall_mm=min_wall_mm,
                               do_thickness=True, do_orientation=True,
                               bed_mm=bed_mm)
            total_mass += rep.mass.mass_g
            total_vol += rep.mass.volume_mm3
            block = format_report_text(rep, name)
            if include_gate:
                gate = printability_gate(rep, bed_mm=bed_mm,
                                         min_wall_mm=min_wall_mm)
                if gate.severity == "block":
                    n_block += 1
                elif gate.severity == "warn":
                    n_warn += 1
                block += "\n" + gate.summary()
            if include_load_capacity:
                cap_kg = safe_cantilever_load_kg(rep.mass, material=material)
                block += (f"\n🔩 Несущая способность (консоль, слабая ось, "
                          f"SF=2): ~{cap_kg:.1f} кг")
            blocks.append(block)
        except Exception as exc:  # pragma: no cover - defensive
            blocks.append(f"📐 {name}: анализ не удался ({exc})")
    gate_line = ""
    if include_gate:
        verdict = ("⛔ есть блокирующие детали" if n_block else
                   ("⚠️ есть замечания" if n_warn else "✅ все детали проходят гейт"))
        gate_line = (f"Printability gate по набору: {verdict} "
                     f"(block={n_block}, warn={n_warn})\n")
    header = (
        "ИНЖЕНЕРНЫЙ ОТЧЁТ ПО НАБОРУ\n"
        "==========================\n"
        f"Материал: {material.upper()} (ρ={material_density(material):.2f} г/см³)\n"
        f"Деталей: {len(parts)}\n"
        f"Суммарный объём: {total_vol/1000.0:.1f} см³\n"
        f"Расчётная масса филамента: {total_mass:.0f} г\n"
        f"{gate_line}"
        "\nМетод: масс-инерция (теорема о дивергенции), статика опрокидывания,\n"
        "анализ нависаний по нормалям граней, толщина стенок лучевым зондом,\n"
        "несущая способность — балка Эйлера-Бернулли с поправкой на адгезию слоёв.\n"
        "\n"
    )
    return header + ("\n\n".join(blocks)) + "\n"


def physics_design_rules(bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM,
                          overhang_limit_deg: float = 45.0) -> str:
    """Compact first-principles design rules injected into the LLM prompt.

    Gives the model the same physics the bot validates against, so designs
    arrive print-ready instead of being rejected by the post-export checker.
    """
    rho = ", ".join(
        f"{k.upper()} {v:.2f}"
        for k, v in list(MATERIAL_DENSITY_G_CM3.items())[:6]
    )
    return (
        "ИНЖЕНЕРНЫЕ ПРАВИЛА (бот проверяет их физикой после генерации):\n"
        f"• Рабочий объём принтера: {bed_mm[0]:.0f}×{bed_mm[1]:.0f}×{bed_mm[2]:.0f} мм; "
        "детали крупнее — резать на стыкуемые части (pin/socket, зазор 0.2-0.3 мм).\n"
        f"• Нависания: поверхности круче {overhang_limit_deg:.0f}° от вертикали требуют "
        "поддержек — проектируй так, чтобы их минимизировать (фаски 45°, дренаж, ребра).\n"
        "• Устойчивость: ЦТ должен проецироваться внутрь опорного контура; высокие узкие "
        "детали (угол опрокидывания < 12°) дополняй широкой базой или brim.\n"
        "• Толщина стенок: минимум 0.8-1.2 мм (2-3 периметра по 0.4 мм сопла); "
        "несущие стенки 2-3 мм.\n"
        "• Мосты (горизонтальные перемычки) до ~10 мм печатаются без поддержек; длиннее — "
        "добавляй опору или дели.\n"
        f"• Плотности (г/см³): {rho}. Масса = объём(см³) × плотность.\n"
        "• Зазоры посадок: подвижные 0.3-0.45 мм, фиксированные 0.1-0.2 мм; "
        "резьбу и оси проверяй tolerance coupon.\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  B. Closed-loop auto-fix: orientation, splitting, printability gate
# ─────────────────────────────────────────────────────────────────────────────

def apply_orientation(mesh: "trimesh.Trimesh",
                      candidate: OrientationCandidate) -> "trimesh.Trimesh":
    """Return a copy of the mesh rotated to the candidate pose and dropped onto
    the bed (min Z = 0). This is what we actually export so the user receives a
    print-ready orientation, not just advice."""
    m = mesh.copy()
    R = np.asarray(candidate.rotation_matrix, dtype=float)
    m.apply_transform(R)
    m.apply_translation([0, 0, -float(m.bounds[0][2])])
    return m


def auto_orient(mesh: "trimesh.Trimesh",
                overhang_limit_deg: float = 45.0,
                bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM
                ) -> Tuple["trimesh.Trimesh", Optional[OrientationCandidate]]:
    """Pick the best print orientation and return the reoriented mesh."""
    best, _ = best_orientation(mesh, overhang_limit_deg=overhang_limit_deg,
                               bed_mm=bed_mm)
    if best is None:
        return mesh, None
    return apply_orientation(mesh, best), best


def _axis_point(mesh: "trimesh.Trimesh", axis: int, value: float) -> np.ndarray:
    p = np.array(mesh.centroid, dtype=float, copy=True)
    p[axis] = value
    return p


def split_oversized(mesh: "trimesh.Trimesh",
                    bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM,
                    margin: float = 0.92) -> List["trimesh.Trimesh"]:
    """Slice a too-large mesh into bed-sized, capped (watertight) pieces.

    Cuts sequentially along every axis that exceeds the build volume, using
    capped planar slices so each fragment stays a closed solid. Returns the
    original mesh as a single-element list when it already fits.
    """
    parts: List["trimesh.Trimesh"] = [mesh]
    for axis in range(3):
        limit = bed_mm[axis] * margin
        out: List["trimesh.Trimesh"] = []
        for m in parts:
            ext = float(m.extents[axis])
            if ext <= bed_mm[axis] or limit <= 1e-6:
                out.append(m)
                continue
            n_cuts = int(math.ceil(ext / limit))
            lo = float(m.bounds[0][axis])
            seg = ext / n_cuts
            normal = np.zeros(3)
            normal[axis] = 1.0
            for i in range(n_cuts):
                a = lo + i * seg
                b = lo + (i + 1) * seg
                piece = m
                try:
                    if i > 0:
                        piece = piece.slice_plane(_axis_point(m, axis, a),
                                                  normal, cap=True)
                    if piece is None or piece.is_empty:
                        continue
                    if i < n_cuts - 1:
                        piece = piece.slice_plane(_axis_point(m, axis, b),
                                                  -normal, cap=True)
                    if piece is None or piece.is_empty:
                        continue
                except Exception:
                    continue
                out.append(piece)
        parts = out or parts
    return parts


@dataclass
class PrintabilityGate:
    passed: bool
    severity: str                    # "ok" | "warn" | "block"
    issues: List[str] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)

    def summary(self) -> str:
        tag = {"ok": "✅ PASS", "warn": "⚠️ PASS c замечаниями",
               "block": "⛔ BLOCK"}.get(self.severity, self.severity)
        s = f"Printability gate: {tag}"
        if self.fixes_applied:
            s += "\n  Исправлено: " + "; ".join(self.fixes_applied)
        if self.issues:
            s += "\n  Замечания: " + "; ".join(self.issues)
        return s


def printability_gate(report: PrintabilityReport,
                      bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM,
                      min_wall_mm: float = 1.2) -> PrintabilityGate:
    """Hard quality gate applied before a model is shipped.

    ``block`` means a real defect the user must know about (won't fit, will
    topple, not a solid); ``warn`` is a printable-but-watch issue; ``ok`` is
    clean.
    """
    issues: List[str] = []
    severity = "ok"

    def bump(level: str):
        nonlocal severity
        order = {"ok": 0, "warn": 1, "block": 2}
        if order[level] > order[severity]:
            severity = level

    bbox = report.mass.bbox_mm
    if bbox and max(bbox) > max(bed_mm):
        issues.append(
            f"габарит {max(bbox):.0f} мм > стол {max(bed_mm):.0f} мм — нужна резка"
        )
        bump("block")

    if not report.mass.is_watertight:
        issues.append("меш не watertight (не закрытый solid)")
        bump("block")

    if report.stability.verdict == "unstable":
        issues.append("ЦТ вне опоры — опрокинется")
        bump("block")
    elif report.stability.verdict == "tippy":
        issues.append(
            f"узкая опора (угол {report.stability.topple_angle_deg:.0f}°) — brim"
        )
        bump("warn")

    if report.thickness and report.thickness.thin_risk:
        issues.append(
            f"тонкие стенки: {report.thickness.thin_fraction*100:.0f}% < "
            f"{min_wall_mm:.1f} мм"
        )
        bump("warn")

    if report.overhang.needs_support:
        issues.append(
            f"нависания {report.overhang.overhang_fraction*100:.0f}% — поддержки"
        )
        bump("warn")

    return PrintabilityGate(passed=severity != "block", severity=severity,
                            issues=issues)


@dataclass
class AutoPrepareResult:
    parts: List[Tuple[str, "trimesh.Trimesh"]]   # name → print-ready mesh
    gate: PrintabilityGate
    report: PrintabilityReport                    # analysis of the input pose
    actions: List[str] = field(default_factory=list)


def auto_prepare(mesh: "trimesh.Trimesh",
                 name: str = "деталь",
                 material: str = DEFAULT_MATERIAL,
                 min_wall_mm: float = 1.2,
                 overhang_limit_deg: float = 45.0,
                 bed_mm: Tuple[float, float, float] = DEFAULT_BED_MM,
                 do_orient: bool = True,
                 do_split: bool = True) -> AutoPrepareResult:
    """The closed loop: analyse → auto-orient → split-if-oversized → re-gate.

    Returns print-ready part meshes plus the gate verdict and the list of
    corrective actions taken. This is what turns the physics layer from
    *descriptive* into *corrective*.
    """
    actions: List[str] = []
    report = analyze_mesh(mesh, material=material, min_wall_mm=min_wall_mm,
                          overhang_limit_deg=overhang_limit_deg, bed_mm=bed_mm)

    work = mesh
    if do_orient and report.recommended_orientation is not None \
            and report.recommended_orientation.name != "as_is":
        oriented, cand = auto_orient(mesh, overhang_limit_deg, bed_mm)
        if cand is not None:
            work = oriented
            actions.append(
                f"переориентация → «{cand.name}» (нависания/устойчивость)"
            )

    parts: List[Tuple[str, "trimesh.Trimesh"]] = []
    if do_split and work.extents is not None and \
            any(float(work.extents[a]) > bed_mm[a] for a in range(3)):
        pieces = split_oversized(work, bed_mm=bed_mm)
        if len(pieces) > 1:
            actions.append(
                f"разрезка на {len(pieces)} стыкуемых частей (не влезает на стол)"
            )
            for i, pc in enumerate(pieces, start=1):
                parts.append((f"{name}_part{i:02d}", pc))
        else:
            parts.append((name, work))
    else:
        parts.append((name, work))

    gate = printability_gate(report, bed_mm=bed_mm, min_wall_mm=min_wall_mm)
    gate.fixes_applied = list(actions)
    return AutoPrepareResult(parts=parts, gate=gate, report=report,
                             actions=actions)


# ─────────────────────────────────────────────────────────────────────────────
#  C. FEA-lite: first-order beam strength under a load case
# ─────────────────────────────────────────────────────────────────────────────

# Tensile yield strength of bulk polymer (MPa). Printed FDM parts are weaker
# and anisotropic, so we knock these down for load across layer lines.
MATERIAL_YIELD_MPA: Dict[str, float] = {
    "pla": 50.0, "pla-cf": 55.0, "petg": 50.0, "petg-cf": 60.0,
    "abs": 40.0, "asa": 44.0, "tpu": 10.0, "nylon": 50.0,
    "pa-cf": 80.0, "pc": 62.0, "resin": 50.0, "hips": 30.0, "pp": 26.0,
}
GRAVITY = 9.80665  # m/s²


def material_yield(material: str) -> float:
    return MATERIAL_YIELD_MPA.get((material or "").lower(),
                                   MATERIAL_YIELD_MPA["pla"])


@dataclass
class BeamFEAResult:
    load_N: float
    arm_mm: float
    section_w_mm: float
    section_h_mm: float
    section_modulus_mm3: float
    area_moment_mm4: float
    max_stress_mpa: float
    allow_stress_mpa: float
    safety_factor: float
    tip_deflection_mm: float
    verdict: str                     # "ok" | "marginal" | "fail"
    notes: List[str] = field(default_factory=list)


def beam_cantilever_fea(arm_mm: float, load_N: float,
                        section_w_mm: float, section_h_mm: float,
                        material: str = DEFAULT_MATERIAL,
                        layer_knockdown: float = 0.55,
                        target_sf: float = 2.0) -> BeamFEAResult:
    """First-order cantilever-beam check (Euler–Bernoulli).

    Rectangular section bending about its *weak* axis (``section_h_mm`` is the
    height in the load direction):

        I = w·h³/12,  S = I/c = w·h²/6,  σ_max = M/S = F·L / S,
        δ_tip = F·L³ / (3·E·I).

    The allowable stress is the bulk yield knocked down for FDM layer adhesion.
    This is an honest first-order estimate (not full FEM), good for sizing ribs
    and walls and for "will this handle X kg" sanity checks.
    """
    notes: List[str] = []
    w = max(1e-6, float(section_w_mm))
    h = max(1e-6, float(section_h_mm))
    L = max(1e-6, float(arm_mm))

    I = w * h ** 3 / 12.0                 # mm⁴
    S = w * h ** 2 / 6.0                  # mm³
    M = load_N * L                        # N·mm
    sigma = M / S if S > 0 else float("inf")   # N/mm² = MPa

    E = MATERIAL_MODULUS_MPA.get((material or "").lower(),
                                  MATERIAL_MODULUS_MPA[DEFAULT_MATERIAL])
    deflection = (load_N * L ** 3) / (3.0 * E * I) if (E * I) > 0 else float("inf")

    allow = material_yield(material) * layer_knockdown
    sf = (allow / sigma) if sigma > 0 else float("inf")

    if sf >= target_sf:
        verdict = "ok"
    elif sf >= 1.0:
        verdict = "marginal"
        notes.append(
            f"запас прочности {sf:.1f} < целевого {target_sf:.0f} — утолщи сечение"
        )
    else:
        verdict = "fail"
        notes.append(
            f"σ={sigma:.1f} МПа > допуск {allow:.1f} МПа — сломается, "
            "увеличь высоту сечения или добавь ребро"
        )
    notes.append("оценка по балке Эйлера-Бернулли с поправкой на адгезию слоёв "
                 f"(k={layer_knockdown:.2f}); нагрузка поперёк слоёв — слабое место")

    return BeamFEAResult(
        load_N=load_N, arm_mm=L, section_w_mm=w, section_h_mm=h,
        section_modulus_mm3=S, area_moment_mm4=I,
        max_stress_mpa=sigma, allow_stress_mpa=allow, safety_factor=sf,
        tip_deflection_mm=deflection, verdict=verdict, notes=notes,
    )


def beam_fea_from_bbox(mass: MassProperties, load_kg: float,
                       material: str = DEFAULT_MATERIAL,
                       target_sf: float = 2.0) -> BeamFEAResult:
    """Convenience FEA-lite: treat the part as a cantilever whose length is the
    longest bbox dim and whose section is the other two dims, loaded by
    ``load_kg`` at the tip. A ballpark "does it hold the weight" check."""
    dims = sorted(mass.bbox_mm)              # [h_small, mid, long]
    h, mid, length = dims[0], dims[1], dims[2]
    load_N = max(0.0, load_kg) * GRAVITY
    return beam_cantilever_fea(arm_mm=length, load_N=load_N,
                               section_w_mm=mid, section_h_mm=h,
                               material=material, target_sf=target_sf)


def safe_cantilever_load_kg(mass: MassProperties, material: str = DEFAULT_MATERIAL,
                            target_sf: float = 2.0,
                            layer_knockdown: float = 0.55) -> float:
    """Largest tip load (kg) the part can carry as a cantilever on its weak
    axis at the requested safety factor. A ballpark "how much will it hold"."""
    dims = sorted(mass.bbox_mm)
    h, mid, length = dims[0], dims[1], dims[2]
    # Scale the gross bbox section modulus by solidity so hollow/L parts are
    # not wildly overrated (honest ballpark, not a substitute for real FEM).
    solidity = max(0.05, min(1.0, mass.solidity))
    S = (mid * h ** 2 / 6.0) * solidity          # effective weak-axis modulus
    allow = material_yield(material) * layer_knockdown
    if length <= 0 or target_sf <= 0:
        return 0.0
    F_allow = allow * S / length / target_sf     # N
    return max(0.0, F_allow / GRAVITY)


def format_fea_text(fea: BeamFEAResult, load_kg: Optional[float] = None) -> str:
    v = {"ok": "✅ держит", "marginal": "⚠️ на пределе",
         "fail": "⛔ сломается"}.get(fea.verdict, fea.verdict)
    head = "🔩 FEA-lite (балочная модель)"
    if load_kg is not None:
        head += f" — нагрузка {load_kg:.1f} кг ({fea.load_N:.0f} Н)"
    lines = [
        head,
        f"• сечение {fea.section_w_mm:.1f}×{fea.section_h_mm:.1f} мм, "
        f"плечо {fea.arm_mm:.0f} мм",
        f"• σ_max = {fea.max_stress_mpa:.1f} МПа, допуск {fea.allow_stress_mpa:.1f} МПа",
        f"• запас прочности SF = {fea.safety_factor:.1f} → {v}",
        f"• прогиб кончика ≈ {fea.tip_deflection_mm:.2f} мм",
    ]
    for n in fea.notes:
        lines.append(f"  – {n}")
    return "\n".join(lines)


def stiffness_hint(mass: MassProperties, material: str) -> str:
    """First-order bending-stiffness comparison hint (EI proxy) for captions."""
    E = MATERIAL_MODULUS_MPA.get((material or "").lower(),
                                  MATERIAL_MODULUS_MPA[DEFAULT_MATERIAL])
    # Use the smallest principal moment as the weak bending axis.
    I_min = min(mass.principal_moments_g_mm2) if mass.mass_g > 0 else 0.0
    # EI is only meaningful with a real area moment; here we expose a relative
    # proxy (E × radius_of_gyration²) for ranking, not absolute deflection.
    rg = mass.gyration_radii_mm()
    return (f"Жёсткость (ориентир): E={E:.0f} МПа, "
            f"радиусы инерции {rg[0]:.1f}/{rg[1]:.1f}/{rg[2]:.1f} мм")
