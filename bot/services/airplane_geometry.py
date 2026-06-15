"""
Aerodynamically-correct airplane geometry for 3D printing.

Mathematics sources (all public domain / open):
  - NACA 4-digit airfoil series: Abbott & von Doenhoff, "Theory of Wing Sections", 1959.
  - Fuselage profile: Sears-Haack body (minimum-drag axiom-symmetric body, 1947).
  - Boeing 747 dimensional ratios: FAA TCDS A20WE (public), Jane's All the World's Aircraft.

All geometry produced via closed-form equations, no random elements.
Results are deterministic: same input → same mesh every time.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  NACA 4-digit airfoil
# ─────────────────────────────────────────────────────────────────────────────

def naca4_coords(code: str, n: int = 80) -> Tuple[np.ndarray, np.ndarray]:
    """
    NACA 4-digit airfoil upper/lower surface coordinates.

    Returns two (n, 2) arrays of (x, y) normalized to chord=1.
    x runs from 0 (leading edge) to 1 (trailing edge).
    Uses cosine spacing for accurate leading-edge curvature.

    Example codes: "2412" (Boeing 747 root-ish), "0012" (symmetric, tail),
                   "4412" (Cessna-ish), "2318" (thick root option).
    """
    code = str(code).zfill(4)
    m = int(code[0]) / 100.0   # maximum camber
    p = int(code[1]) / 10.0    # chordwise position of max camber
    t = int(code[2:]) / 100.0  # max thickness fraction of chord

    # Cosine-spaced x stations for dense leading-edge sampling
    beta = np.linspace(0.0, math.pi, n)
    x = (1.0 - np.cos(beta)) / 2.0

    # NACA thickness distribution (Abbott & von Doenhoff eq. 6.1)
    yt = (t / 0.2) * (
        0.2969 * np.sqrt(np.clip(x, 0, 1))
        - 0.1260 * x
        - 0.3516 * x ** 2
        + 0.2843 * x ** 3
        - 0.1015 * x ** 4
    )

    # Mean camber line
    if m < 1e-9 or p < 1e-9:
        yc = np.zeros_like(x)
        dyc_dx = np.zeros_like(x)
    else:
        fwd = x <= p
        yc = np.where(fwd,
                      (m / p ** 2) * (2 * p * x - x ** 2),
                      (m / (1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x ** 2))
        dyc_dx = np.where(fwd,
                          (2 * m / p ** 2) * (p - x),
                          (2 * m / (1 - p) ** 2) * (p - x))

    theta = np.arctan(dyc_dx)
    sin_t, cos_t = np.sin(theta), np.cos(theta)

    upper = np.column_stack([x - yt * sin_t, yc + yt * cos_t])
    lower = np.column_stack([x + yt * sin_t, yc - yt * cos_t])
    return upper, lower


def _airfoil_closed_loop(code: str, chord: float, n: int = 80,
                          min_thickness_mm: float = 1.2) -> np.ndarray:
    """
    Closed 2-D contour (2n-2, 2) in the XZ plane:
    X = chordwise direction, Z = thickness direction.

    Enforces minimum wall thickness for FDM printability.
    Goes TE→upper→LE→lower→TE (counter-clockwise when viewed from +Y span).
    """
    # Enforce minimum printable thickness
    t_code = int(code[2:])
    min_t_frac = min_thickness_mm / chord if chord > 0 else 0
    t_frac = max(t_code / 100.0, min_t_frac * 1.25)
    effective_code = code[:2] + f"{int(round(t_frac * 100)):02d}"
    effective_code = effective_code[:2] + f"{min(int(effective_code[2:]), 30):02d}"

    upper, lower = naca4_coords(effective_code, n)
    # Reverse upper so loop goes TE→LE via upper surface
    pts = np.vstack([upper[::-1], lower[1:]])  # (2n-1, 2)
    pts *= chord
    return pts


# ─────────────────────────────────────────────────────────────────────────────
#  Wing loft
# ─────────────────────────────────────────────────────────────────────────────

def loft_wing_half(
    airfoil: str,
    root_chord: float,
    tip_chord: float,
    span: float,
    le_sweep: float,         # X offset of LE at tip vs root (+ = swept back)
    dihedral_z: float = 0.0, # Z gain from root to tip
    twist_deg: float = -2.0, # washout (tip nose-down, reduces tip stall)
    n_span: int = 28,
    n_chord: int = 64,
    min_thickness_mm: float = 1.2,
) -> "trimesh.Trimesh":
    """
    Loft a wing half using NACA airfoil cross-sections.

    Coordinate system:
      X = chord/length direction (nose of aircraft = +X)
      Y = span direction (tip at +Y)
      Z = lift direction (up = +Z)

    Returns a closed, watertight trimesh suitable for FDM printing.

    Boeing 747 reference values (scale to your chord/span):
      airfoil  = "2318" at root, "2312" at tip (we simplify to one code)
      sweep    = 37.5° at quarter-chord  →  le_sweep ≈ span * tan(37.5°) * 0.75
      taper    = 0.283  (tip/root chord ratio)
      dihedral = 7°     →  dihedral_z ≈ span * tan(7°)
    """
    import trimesh

    # Span stations: cosine bunching gives more sections near root and tip
    # where curvature changes fastest
    t_arr = (1.0 - np.cos(np.linspace(0.0, math.pi, n_span))) / 2.0

    sections_3d: List[np.ndarray] = []

    for t in t_arr:
        chord = root_chord + (tip_chord - root_chord) * t
        chord = max(chord, min_thickness_mm * 4)  # don't let tip vanish

        # 2-D airfoil contour in local XZ plane (X=chord, Z=thickness)
        pts2d = _airfoil_closed_loop(airfoil, chord, n_chord, min_thickness_mm)

        # Washout: rotate section about its own LE (x=0)
        twist_rad = math.radians(twist_deg * t)
        cos_tw = math.cos(twist_rad)
        sin_tw = math.sin(twist_rad)
        px = pts2d[:, 0] * cos_tw - pts2d[:, 1] * sin_tw
        pz = pts2d[:, 0] * sin_tw + pts2d[:, 1] * cos_tw

        # Sweep: shift LE forward/back
        px += le_sweep * t

        # Span and dihedral
        py = span * t
        pz_out = pz + dihedral_z * t

        sections_3d.append(np.column_stack([px, np.full(len(px), py), pz_out]))

    # ── Connect sections into a manifold mesh ──────────────────────────────
    n_pts = len(sections_3d[0])
    verts_list = list(sections_3d)
    verts = np.vstack(verts_list)
    faces: List[List[int]] = []

    for i in range(n_span - 1):
        b0 = i * n_pts
        b1 = (i + 1) * n_pts
        for j in range(n_pts - 1):
            a, b, c, d = b0 + j, b0 + j + 1, b1 + j, b1 + j + 1
            faces += [[a, b, d], [a, d, c]]
        # Close loop (last point → first point)
        a, b, c, d = b0 + n_pts - 1, b0, b1 + n_pts - 1, b1
        faces += [[a, b, d], [a, d, c]]

    # Root cap (flat plate closing the inboard end)
    root_center = sections_3d[0].mean(axis=0)
    rc_idx = len(verts)
    verts = np.vstack([verts, root_center])
    b = 0
    for j in range(n_pts - 1):
        faces.append([rc_idx, b + j + 1, b + j])
    faces.append([rc_idx, b, b + n_pts - 1])

    # Tip cap
    tip_center = sections_3d[-1].mean(axis=0)
    tc_idx = len(verts)
    verts = np.vstack([verts, tip_center])
    b = (n_span - 1) * n_pts
    for j in range(n_pts - 1):
        faces.append([tc_idx, b + j, b + j + 1])
    faces.append([tc_idx, b + n_pts - 1, b])

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces, dtype=np.int32), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  Fuselage body
# ─────────────────────────────────────────────────────────────────────────────

def _sears_haack_radius(x_norm: float) -> float:
    """
    Sears-Haack body radius at normalized position x ∈ [0,1].
    Gives minimum wave drag for a given volume.
    r(x) = r_max * (sin(π*x))^(3/4)     [simplified form]
    """
    return math.sin(math.pi * x_norm) ** 0.75


def fuselage_body(
    length: float,
    max_radius: float,
    nose_fraction: float = 0.12,   # share of length for ogive nose
    tail_fraction: float = 0.22,   # share of length for tail cone
    belly_flatten: float = 0.06,   # fraction to flatten belly for flat-bottom print (unused in revolve)
    n_sections: int = 64,
    n_circ: int = 48,
) -> "trimesh.Trimesh":
    """
    Generate a smooth fuselage body.

    Shape:
      - Nose: Haack ogive (smooth blunt nose, like a 747 or A380)
      - Cabin: parallel constant-radius cylinder
      - Tail: tapered Sears-Haack cone blending to a point

    X axis = nose (+) to tail (-).  Long axis along X.
    Belly is at z=0, spine at z=2*max_radius (before settling on plate).

    belly_flatten: small flat on bottom for stable FDM first layer without a skid.
    """
    import trimesh

    def radius_at_t(t: float) -> float:
        """Radius given t ∈ [0,1]: 0=tail, 1=nose."""
        if t >= 1.0 - nose_fraction:
            t_nose = (t - (1.0 - nose_fraction)) / nose_fraction
            return max_radius * math.sin(math.pi * t_nose / 2.0)
        elif t <= tail_fraction:
            t_tail = t / tail_fraction
            return max_radius * math.sqrt(max(math.sin(math.pi * t_tail / 2.0), 1e-9))
        return max_radius

    # Cosine spacing – dense near nose/tail transitions
    ts = (1.0 - np.cos(np.linspace(0.0, math.pi, n_sections))) / 2.0  # 0=tail … 1=nose

    xs = (ts - 0.5) * length           # -L/2 … +L/2
    radii = np.array([radius_at_t(t) for t in ts])

    # Per-ring angles, shared across all sections (no endpoint → clean wrap)
    angles = np.linspace(0.0, 2 * math.pi, n_circ, endpoint=False)

    # Build all ring vertices at once (no apex collapse needed – min radius is non-zero)
    verts_all = []
    for i in range(n_sections):
        r = radii[i]
        x = xs[i]
        y_arr = r * np.cos(angles)
        z_arr = r * np.sin(angles) + max_radius   # belly at z=0
        x_arr = np.full(n_circ, x)
        verts_all.append(np.column_stack([x_arr, y_arr, z_arr]))

    verts = np.vstack(verts_all)  # shape (n_sections * n_circ, 3)

    # Quads between adjacent rings → 2 triangles each
    # Winding: outward normal → CCW when viewed from outside
    # Ring vertices go CCW when viewed from +X (nose): ↑Y at angle=0, +Z at angle=π/2
    # Going from ring i (larger x/nose) to ring i+1 (smaller x/tail):
    #   outward normal = cross((b-a), (c-a)) must point outward
    faces = []
    for i in range(n_sections - 1):
        b0 = i * n_circ
        b1 = (i + 1) * n_circ
        for j in range(n_circ):
            j1 = (j + 1) % n_circ
            # vertices of quad: a=b0+j, b=b0+j1, c=b1+j, d=b1+j1
            a, b, c, d = b0 + j, b0 + j1, b1 + j, b1 + j1
            # Two triangles with consistent CCW winding (outward normals)
            faces += [[a, c, b], [b, c, d]]

    # Nose cap: fan from nose apex (ring 0 = nose end at xs[-1]=+L/2)
    # Nose is at index n_sections-1 (ts=1 = nose)
    nose_ring_base = (n_sections - 1) * n_circ
    nose_apex = np.array([xs[-1], 0.0, max_radius])  # on axis
    nose_apex_idx = len(verts)
    verts = np.vstack([verts, nose_apex])
    for j in range(n_circ):
        j1 = (j + 1) % n_circ
        faces.append([nose_apex_idx, nose_ring_base + j, nose_ring_base + j1])

    # Tail cap: fan from tail apex (ring 0 = tail end at xs[0]=-L/2)
    tail_ring_base = 0
    tail_apex = np.array([xs[0], 0.0, max_radius])
    tail_apex_idx = len(verts)
    verts = np.vstack([verts, tail_apex])
    for j in range(n_circ):
        j1 = (j + 1) % n_circ
        faces.append([tail_apex_idx, tail_ring_base + j1, tail_ring_base + j])

    mesh = trimesh.Trimesh(
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        process=False,     # keep topology exact; don't merge/split
    )
    trimesh.repair.fix_normals(mesh)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  Engine nacelle
# ─────────────────────────────────────────────────────────────────────────────

def engine_nacelle(
    length: float,
    intake_radius: float,
    max_radius: float,
    exit_radius: float,
    lip_frac: float = 0.08,     # share of length for intake lip bulge
    n_sections: int = 32,
    n_circ: int = 32,
    min_wall_mm: float = 1.0,
) -> "trimesh.Trimesh":
    """
    Turbofan nacelle (outer shell only, solid for FDM).

    Profile (longitudinal cross-section):
      - Intake lip: gentle bulge that flares out smoothly (NACA cowling style)
      - Max radius section: widest point at ~30% of length
      - Aft: smooth taper to nozzle exit radius

    X axis = forward (+) to back (-).  Centred at X=0.
    """
    import trimesh

    x_front = length / 2
    x_back = -length / 2
    x_max_r = x_front - length * 0.30  # max radius station

    def nacelle_radius(x: float) -> float:
        t = (x - x_back) / length  # 0 at back, 1 at front
        if t >= 1.0 - lip_frac:
            # Intake lip: smooth flare
            t_lip = (t - (1.0 - lip_frac)) / lip_frac
            r = intake_radius + (max_radius - intake_radius) * math.sin(math.pi * t_lip / 2)
        elif t >= (x_max_r - x_back) / length:
            # Forward section: linear fan from max_r to intake
            t_fwd = (t - (x_max_r - x_back) / length) / (1.0 - lip_frac - (x_max_r - x_back) / length)
            r = max_radius - (max_radius - intake_radius) * t_fwd * 0.18
        else:
            # Aft section: taper from max_r to exit_r
            t_aft = t / ((x_max_r - x_back) / length)
            r = exit_radius + (max_radius - exit_radius) * math.sqrt(t_aft)
        return max(r, min_wall_mm)

    xs = np.linspace(x_front, x_back, n_sections)
    angles = np.linspace(0.0, 2 * math.pi, n_circ, endpoint=False)

    rings: List[np.ndarray] = []
    for x in xs:
        r = nacelle_radius(x)
        ring = np.column_stack([
            np.full(n_circ, x),
            r * np.cos(angles),
            r * np.sin(angles),
        ])
        rings.append(ring)

    verts = np.vstack(rings)
    faces: List[List[int]] = []

    for i in range(n_sections - 1):
        b0 = i * n_circ
        b1 = (i + 1) * n_circ
        for j in range(n_circ):
            j1 = (j + 1) % n_circ
            faces += [[b0 + j, b0 + j1, b1 + j1], [b0 + j, b1 + j1, b1 + j]]

    # Front and back caps
    for cap_b, cap_x_idx, winding in [(0, 0, 1), ((n_sections - 1) * n_circ, -1, -1)]:
        cx = np.array([xs[cap_x_idx], 0.0, 0.0])
        ci = len(verts)
        verts = np.vstack([verts, cx])
        for j in range(n_circ):
            j1 = (j + 1) % n_circ
            if winding == 1:
                faces.append([ci, cap_b + j1, cap_b + j])
            else:
                faces.append([ci, cap_b + j, cap_b + j1])

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces, dtype=np.int32), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  Vertical stabiliser (NACA profile, not a flat box)
# ─────────────────────────────────────────────────────────────────────────────

def vertical_stabilizer(
    root_chord: float,
    tip_chord: float,
    height: float,
    sweep_x: float,         # X offset of LE at top vs root
    airfoil: str = "0010",
    n_span: int = 16,
    n_chord: int = 48,
    min_thickness_mm: float = 1.2,
) -> "trimesh.Trimesh":
    """
    Vertical stabiliser: lofted NACA profile, Z = span direction (pointing up).

    Returns mesh with root at Z=0, tip at Z=height.
    """
    import trimesh

    t_arr = (1.0 - np.cos(np.linspace(0.0, math.pi, n_span))) / 2.0
    sections_3d: List[np.ndarray] = []

    for t in t_arr:
        chord = root_chord + (tip_chord - root_chord) * t
        chord = max(chord, min_thickness_mm * 4)
        pts2d = _airfoil_closed_loop(airfoil, chord, n_chord, min_thickness_mm)

        # pts2d: X = chordwise, Y = thickness → remap to X=chord, Y=thickness, Z=span
        z_span = height * t
        x_le = sweep_x * t
        sections_3d.append(np.column_stack([
            pts2d[:, 0] + x_le,
            pts2d[:, 1],          # thickness → Y (side direction)
            np.full(len(pts2d), z_span),
        ]))

    n_pts = len(sections_3d[0])
    verts = np.vstack(sections_3d)
    faces: List[List[int]] = []

    for i in range(n_span - 1):
        b0 = i * n_pts
        b1 = (i + 1) * n_pts
        for j in range(n_pts - 1):
            a, b, c, d = b0 + j, b0 + j + 1, b1 + j, b1 + j + 1
            faces += [[a, b, d], [a, d, c]]
        a, b, c, d = b0 + n_pts - 1, b0, b1 + n_pts - 1, b1
        faces += [[a, b, d], [a, d, c]]

    # Root and tip caps
    for idx_section, winding in [(0, -1), (n_span - 1, 1)]:
        center = sections_3d[idx_section].mean(axis=0)
        ci = len(verts)
        verts = np.vstack([verts, center])
        b = idx_section * n_pts
        for j in range(n_pts - 1):
            if winding == 1:
                faces.append([ci, b + j, b + j + 1])
            else:
                faces.append([ci, b + j + 1, b + j])
        j = n_pts - 1
        if winding == 1:
            faces.append([ci, b + j, b])
        else:
            faces.append([ci, b, b + j])

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces, dtype=np.int32), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  Winglet
# ─────────────────────────────────────────────────────────────────────────────

def blended_winglet(
    height: float,
    root_chord: float,
    cant_deg: float = 70.0,   # cant angle from vertical (90 = horizontal)
    airfoil: str = "0010",
    n_span: int = 12,
    n_chord: int = 40,
    min_thickness_mm: float = 1.0,
) -> "trimesh.Trimesh":
    """
    Blended winglet (like 747-400 raked tip or A320neo Sharklet).
    Cant angle: 0=vertical, 90=horizontal.

    Base at Y=0 (wing tip), tip at Y=height*sin(cant), Z=height*cos(cant).
    """
    import trimesh

    cant_rad = math.radians(cant_deg)
    t_arr = (1.0 - np.cos(np.linspace(0.0, math.pi, n_span))) / 2.0
    sections_3d: List[np.ndarray] = []
    tip_chord = root_chord * 0.30

    for t in t_arr:
        chord = root_chord + (tip_chord - root_chord) * t
        chord = max(chord, min_thickness_mm * 3)
        pts2d = _airfoil_closed_loop(airfoil, chord, n_chord, min_thickness_mm)
        sweep_x = -height * 0.15 * t  # slight forward sweep for stiffness
        dy = height * math.sin(cant_rad) * t
        dz = height * math.cos(cant_rad) * t
        sections_3d.append(np.column_stack([
            pts2d[:, 0] + sweep_x,
            pts2d[:, 1] + dy,
            np.full(len(pts2d), dz),
        ]))

    n_pts = len(sections_3d[0])
    verts = np.vstack(sections_3d)
    faces: List[List[int]] = []

    for i in range(n_span - 1):
        b0 = i * n_pts
        b1 = (i + 1) * n_pts
        for j in range(n_pts - 1):
            a, b, c, d = b0 + j, b0 + j + 1, b1 + j, b1 + j + 1
            faces += [[a, b, d], [a, d, c]]
        a, b, c, d = b0 + n_pts - 1, b0, b1 + n_pts - 1, b1
        faces += [[a, b, d], [a, d, c]]

    for idx_section, winding in [(0, -1), (n_span - 1, 1)]:
        center = sections_3d[idx_section].mean(axis=0)
        ci = len(verts)
        verts = np.vstack([verts, center])
        b = idx_section * n_pts
        for j in range(n_pts - 1):
            faces.append([ci, b + j, b + j + 1] if winding == 1 else [ci, b + j + 1, b + j])
        j = n_pts - 1
        faces.append([ci, b + j, b] if winding == 1 else [ci, b, b + j])

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces, dtype=np.int32), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  Landing gear strut (simple printable cylinder + wheel)
# ─────────────────────────────────────────────────────────────────────────────

def gear_strut(
    strut_height: float,
    strut_radius: float,
    wheel_radius: float,
    wheel_width: float,
    n_wheel: int = 28,
) -> "trimesh.Trimesh":
    """
    Gear strut + wheel pair. Bottom of strut at Z=0, top at Z=strut_height.
    """
    import trimesh

    strut = trimesh.creation.cylinder(radius=strut_radius, height=strut_height, sections=16)
    strut.apply_translation([0, 0, strut_height / 2])

    wheel = trimesh.creation.cylinder(radius=wheel_radius, height=wheel_width, sections=n_wheel)
    wheel.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))

    mesh = trimesh.util.concatenate([strut, wheel])
    trimesh.repair.fix_normals(mesh)
    return mesh
