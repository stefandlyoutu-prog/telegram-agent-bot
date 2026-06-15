"""
Parametric 3D-printable hydraulic cylinder generator.

Mathematics & proportions are taken from real CAD measured in
`data/reference_models/hydro_cylinder_dnl3986/` (Russian industrial reference,
D80 bore × D70 rod × ~600 mm stroke, 20-part STEP assembly).

Engineering ratios encoded here (also recorded in
`learned_mechanism_profiles.HYDRAULIC_CYLINDER`):

    barrel_OD / bore_ID          = 1.19    (gun-drilled tube wall)
    rod_OD   / piston_OD         = 0.875   (rod is thinner than piston)
    piston_OD / bore_ID          = 0.99    (running clearance 0.4 mm)
    stroke   / rod_OD            = ~8.6    (long-stroke industrial)
    clevis_eye / rod_OD          = 1.6     (mounting eye thickness)

Output: list of `trimesh.Trimesh` parts, each watertight, with stable
canonical names usable for AMS color assignment and assembly preview.

This file is the practical companion to `airplane_geometry.py` — same idea
(closed-form generator from measured proportions), different machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import trimesh


# ─────────────────────────────────────────────────────────────────────────────
#  Geometry primitives (watertight)
# ─────────────────────────────────────────────────────────────────────────────

def _hollow_tube(outer_r: float, inner_r: float, length: float,
                 n_circ: int = 48) -> trimesh.Trimesh:
    """Thick-walled cylinder along Z, watertight (annulus extruded)."""
    if inner_r <= 0:
        return trimesh.creation.cylinder(radius=outer_r, height=length,
                                          sections=n_circ)
    # Build via extruded annulus polygon for guaranteed watertightness
    from shapely.geometry import Polygon

    outer = [(outer_r * math.cos(2 * math.pi * i / n_circ),
              outer_r * math.sin(2 * math.pi * i / n_circ))
             for i in range(n_circ)]
    inner = [(inner_r * math.cos(2 * math.pi * i / n_circ),
              inner_r * math.sin(2 * math.pi * i / n_circ))
             for i in range(n_circ)]
    poly = Polygon(outer, [inner])
    mesh = trimesh.creation.extrude_polygon(poly, length)
    # extrude_polygon puts base at z=0
    return mesh


def _solid_disc(radius: float, thickness: float,
                n_circ: int = 48) -> trimesh.Trimesh:
    return trimesh.creation.cylinder(radius=radius, height=thickness,
                                      sections=n_circ)


def _hex_nut(across_flats: float, thickness: float,
             bore_radius: float | None = None) -> trimesh.Trimesh:
    """Standard hex nut. Across-flats = wrench size."""
    from shapely.geometry import Polygon

    r = across_flats / math.sqrt(3.0)  # vertex radius for regular hexagon
    pts = [(r * math.cos(math.pi / 6 + 2 * math.pi * i / 6),
            r * math.sin(math.pi / 6 + 2 * math.pi * i / 6))
           for i in range(6)]
    holes = None
    if bore_radius and bore_radius > 0:
        holes = [[(bore_radius * math.cos(2 * math.pi * i / 32),
                   bore_radius * math.sin(2 * math.pi * i / 32))
                  for i in range(32)]]
    poly = Polygon(pts, holes)
    return trimesh.creation.extrude_polygon(poly, thickness)


def _clevis_eye(eye_outer_d: float, eye_inner_d: float,
                base_w: float, base_h: float, thickness: float,
                neck_length: float) -> trimesh.Trimesh:
    """
    Forged-style clevis: a rectangular base, narrowing neck, then ring.
    Built in XY plane, thickness extruded along Z.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    R = eye_outer_d / 2.0
    r = eye_inner_d / 2.0
    # Base rectangle, centered on origin, with neck going +Y
    base = Polygon([
        (-base_w / 2, -base_h / 2),
        ( base_w / 2, -base_h / 2),
        ( base_w / 2,  base_h / 2),
        (-base_w / 2,  base_h / 2),
    ])
    neck = Polygon([
        (-base_w * 0.35, base_h / 2 - 1.0),
        ( base_w * 0.35, base_h / 2 - 1.0),
        ( eye_outer_d * 0.45, base_h / 2 + neck_length),
        (-eye_outer_d * 0.45, base_h / 2 + neck_length),
    ])
    # Eye ring (annulus)
    n_circ = 36
    cy = base_h / 2 + neck_length + R * 0.85
    ring_outer = [(R * math.cos(2 * math.pi * i / n_circ),
                   cy + R * math.sin(2 * math.pi * i / n_circ))
                  for i in range(n_circ)]
    ring_hole = [(r * math.cos(2 * math.pi * i / n_circ),
                  cy + r * math.sin(2 * math.pi * i / n_circ))
                 for i in range(n_circ)]
    ring = Polygon(ring_outer, [ring_hole])
    combined = unary_union([base, neck, ring])
    if combined.geom_type == "MultiPolygon":
        # Take the largest polygon (should not normally happen)
        combined = max(combined.geoms, key=lambda p: p.area)
    return trimesh.creation.extrude_polygon(combined, thickness)


# ─────────────────────────────────────────────────────────────────────────────
#  Top-level generator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HydraulicCylinderSpec:
    """User-tunable spec; defaults match the reference D80 cylinder."""

    bore_diameter_mm: float = 80.0
    rod_diameter_mm: float = 70.0
    stroke_mm: float = 600.0
    scale: float = 1.0           # overall print-down scale, 1.0 = full size
    color_hint: Dict[str, str] = field(default_factory=lambda: {
        "barrel": "metal_blue",
        "rod": "metal_chrome",
        "piston": "metal_gold",
        "gland": "metal_steel",
        "rear_clevis": "metal_blue",
        "front_clevis": "metal_blue",
        "lock_nut": "metal_steel",
    })

    # Derived constants from the reference profile
    BARREL_OD_RATIO: float = 1.19
    PISTON_CLEARANCE_MM: float = 0.4
    CLEVIS_EYE_RATIO: float = 1.6
    GLAND_OD_RATIO: float = 1.38         # gland_OD / bore_ID = 110/80
    GLAND_LENGTH_RATIO: float = 0.875     # gland_L / bore_ID

    def derived(self) -> Dict[str, float]:
        s = self.scale
        bore = self.bore_diameter_mm * s
        rod = self.rod_diameter_mm * s
        stroke = self.stroke_mm * s
        barrel_od = bore * self.BARREL_OD_RATIO
        piston_od = bore - 2 * self.PISTON_CLEARANCE_MM * s
        barrel_length = stroke + bore * 0.6           # +allowance for piston head + caps
        rod_length = stroke + bore * 0.9
        eye_od = rod * self.CLEVIS_EYE_RATIO * 1.6     # outer of clevis ring
        eye_id = rod * 0.45                            # pin bore
        gland_od = bore * self.GLAND_OD_RATIO
        gland_l = bore * self.GLAND_LENGTH_RATIO
        return dict(
            bore=bore,
            rod=rod,
            stroke=stroke,
            barrel_od=barrel_od,
            piston_od=piston_od,
            barrel_length=barrel_length,
            rod_length=rod_length,
            eye_od=eye_od,
            eye_id=eye_id,
            gland_od=gland_od,
            gland_l=gland_l,
        )


def build_hydraulic_cylinder(spec: HydraulicCylinderSpec | None = None,
                              ) -> Dict[str, trimesh.Trimesh]:
    """
    Return a dict of {part_name: Trimesh} laid out in *assembled pose*
    along the Z axis.

    Coordinate convention:
      - axis = Z
      - assembly origin at center of barrel
      - rear clevis is below (–Z), front clevis is above (+Z)

    Names are the canonical ones used by `learned_mechanism_profiles.HYDRAULIC_CYLINDER`:
       rear_clevis, barrel, piston_head, rod, gland_bushing, lock_nut, front_clevis
    """
    spec = spec or HydraulicCylinderSpec()
    d = spec.derived()
    bore = d["bore"]
    rod = d["rod"]
    barrel_od = d["barrel_od"]
    piston_od = d["piston_od"]
    BL = d["barrel_length"]
    RL = d["rod_length"]
    gland_od = d["gland_od"]
    gland_l = d["gland_l"]
    eye_od = d["eye_od"]
    eye_id = d["eye_id"]

    parts: Dict[str, trimesh.Trimesh] = {}

    # 1. Barrel — thick-wall tube, base on Z=0
    barrel = _hollow_tube(barrel_od / 2.0, bore / 2.0, BL)
    parts["barrel"] = barrel

    # 2. Rear clevis on bottom of barrel (−Z direction).
    clevis_thickness = rod * 0.6
    rear = _clevis_eye(
        eye_outer_d=eye_od,
        eye_inner_d=eye_id,
        base_w=barrel_od * 0.95,
        base_h=barrel_od * 0.55,
        thickness=clevis_thickness,
        neck_length=eye_od * 0.3,
    )
    # Rotate so the eye points down (−Z) by rotating around X by 90°
    R_align_down = trimesh.transformations.rotation_matrix(
        -math.pi / 2.0, [1, 0, 0]
    )
    rear.apply_transform(R_align_down)
    # Now neck/eye extends in −Z (we rotated +Y into −Z).
    # Translate so the base sits flush at the bottom of the barrel:
    rear.apply_translation([0, 0, 0])  # rear clevis base sits at Z=0
    parts["rear_clevis"] = rear

    # 3. Piston head — disc inside the barrel
    piston = _solid_disc(piston_od / 2.0, bore * 0.4)
    piston.apply_translation([0, 0, BL * 0.45])
    parts["piston_head"] = piston

    # 4. Rod — solid cylinder, starts inside barrel from piston, exits top
    rod_mesh = trimesh.creation.cylinder(radius=rod / 2.0, height=RL,
                                          sections=48)
    rod_mesh.apply_translation([0, 0, BL * 0.45 + RL * 0.5])
    parts["rod"] = rod_mesh

    # 5. Gland bushing — flanged ring at top of barrel
    gland = _hollow_tube(gland_od / 2.0, rod / 2.0 + 0.5 * spec.scale, gland_l)
    gland.apply_translation([0, 0, BL - 0.5])
    parts["gland_bushing"] = gland

    # 6. Lock nut on rod near gland exterior
    nut_af = rod * 0.66
    nut_t = rod * 0.35
    nut = _hex_nut(across_flats=nut_af, thickness=nut_t,
                   bore_radius=rod / 2.0 + 0.4)
    nut.apply_translation([0, 0, BL + gland_l + 1.0])
    parts["lock_nut"] = nut

    # 7. Front clevis — at very top of rod
    front = _clevis_eye(
        eye_outer_d=eye_od * 0.9,
        eye_inner_d=eye_id * 0.85,
        base_w=rod * 1.6,
        base_h=rod * 0.55,
        thickness=clevis_thickness,
        neck_length=eye_od * 0.25,
    )
    # Rotate so eye points UP (+Z)
    R_align_up = trimesh.transformations.rotation_matrix(
        math.pi / 2.0, [1, 0, 0]
    )
    front.apply_transform(R_align_up)
    # Translate to top of rod (above lock nut)
    front_z = BL + gland_l + 1.0 + nut_t + clevis_thickness / 2.0
    front.apply_translation([0, 0, front_z])
    parts["front_clevis"] = front

    return parts


def print_oriented_parts(spec: HydraulicCylinderSpec | None = None,
                          gap_mm: float = 5.0,
                          ) -> List[Tuple[str, trimesh.Trimesh]]:
    """
    Return parts laid out flat on the build plate (XY plane), spaced by
    `gap_mm`, oriented for FDM print success:
      - barrel: lying on side (axis along X)
      - rod: lying on side
      - piston head: flat on bed
      - clevis: lying flat (extrusion axis vertical)
    """
    parts = build_hydraulic_cylinder(spec)
    out: List[Tuple[str, trimesh.Trimesh]] = []

    # Lay barrel on its side
    barrel = parts["barrel"].copy()
    R_to_side = trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0])
    barrel.apply_transform(R_to_side)
    bbox = barrel.bounds
    barrel.apply_translation([-bbox[0][0], -bbox[0][1], -bbox[0][2]])
    out.append(("barrel", barrel))

    cursor_x = barrel.bounds[1][0] + gap_mm

    # Rod
    rod = parts["rod"].copy()
    rod.apply_transform(R_to_side)
    bb = rod.bounds
    rod.apply_translation([cursor_x - bb[0][0], -bb[0][1], -bb[0][2]])
    out.append(("rod", rod))
    cursor_x = rod.bounds[1][0] + gap_mm

    # Piston head — already disc, just centred
    piston = parts["piston_head"].copy()
    bb = piston.bounds
    piston.apply_translation([cursor_x - bb[0][0], -bb[0][1], -bb[0][2]])
    out.append(("piston_head", piston))
    cursor_x = piston.bounds[1][0] + gap_mm

    # Gland — flat on bed
    gland = parts["gland_bushing"].copy()
    bb = gland.bounds
    gland.apply_translation([cursor_x - bb[0][0], -bb[0][1], -bb[0][2]])
    out.append(("gland_bushing", gland))
    cursor_x = gland.bounds[1][0] + gap_mm

    # Lock nut
    nut = parts["lock_nut"].copy()
    bb = nut.bounds
    nut.apply_translation([cursor_x - bb[0][0], -bb[0][1], -bb[0][2]])
    out.append(("lock_nut", nut))
    cursor_x = nut.bounds[1][0] + gap_mm

    # Clevis eyes — flat with their eye-axis vertical
    for name in ("rear_clevis", "front_clevis"):
        c = parts[name].copy()
        bb = c.bounds
        c.apply_translation([cursor_x - bb[0][0], -bb[0][1], -bb[0][2]])
        out.append((name, c))
        cursor_x = c.bounds[1][0] + gap_mm

    return out


def export_kit_zip(zip_path: str,
                    spec: HydraulicCylinderSpec | None = None,
                    ) -> Dict[str, int]:
    """Write a kit ZIP with one STL per part + a small README."""
    import io
    import zipfile

    parts = print_oriented_parts(spec)
    spec = spec or HydraulicCylinderSpec()
    d = spec.derived()

    counts: Dict[str, int] = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, mesh in parts:
            buf = io.BytesIO()
            mesh.export(buf, file_type="stl")
            zf.writestr(f"parts/{name}.stl", buf.getvalue())
            counts[name] = len(mesh.faces)
        # Engineering report (mass / stability / overhang / orientation)
        try:
            from bot.services.mesh_engineering import kit_engineering_report

            report = kit_engineering_report(parts, material="petg",
                                            min_wall_mm=1.6)
            zf.writestr("engineering_report.txt", report.encode("utf-8"))
        except Exception:
            pass
        readme = (
            "Procedural hydraulic cylinder kit\n"
            "=================================\n"
            f"  bore     : Ø{d['bore']:.1f} mm\n"
            f"  rod      : Ø{d['rod']:.1f} mm\n"
            f"  stroke   : {d['stroke']:.1f} mm\n"
            f"  barrel_L : {d['barrel_length']:.1f} mm\n"
            f"  rod_L    : {d['rod_length']:.1f} mm\n"
            f"  gland_OD : {d['gland_od']:.1f} mm\n"
            "\nParts (all watertight):\n"
        )
        for name, mesh in parts:
            readme += (
                f"  {name:14s} V={len(mesh.vertices):5d} F={len(mesh.faces):5d}\n"
            )
        readme += (
            "\nPrint orientation: each part is laid flat on the bed.\n"
            "Recommended: 0.2 mm layers, 3 perimeters, 25% infill.\n"
            "Source proportions: data/reference_models/hydro_cylinder_dnl3986/\n"
        )
        zf.writestr("README.txt", readme.encode("utf-8"))
    return counts
