"""Procedural airplane 3MF for Bambu Studio.

This is a deterministic fallback for aircraft requests where text-to-3D can
produce an unrecognizable blob. It must be an assembled, recognizable airplane,
not a plate of loose primitive parts.
"""

from __future__ import annotations

import io
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


AIRPLANE_PARTS = [
    "fuselage",
    "nose",        # alias: integrated in NACA fuselage ogive
    "tail_cone",   # alias: integrated in NACA fuselage tail
    "wing_left",
    "wing_right",
    "tail_fin",
    "tailplane_left",
    "tailplane_right",
    "engine_left",
    "engine_right",
    "landing_gear_front",
    "landing_gear_left",
    "landing_gear_right",
    "winglet_left",
    "winglet_right",
]

AIRLINER_HD_PARTS = [
    *AIRPLANE_PARTS,
    "engine_left_fan",
    "engine_right_fan",
    "engine_left_2_fan",
    "engine_right_2_fan",
    "pylon_left",
    "pylon_right",
    "pylon_left_2",
    "pylon_right_2",
    "cockpit_window",
    "window_strip_left",
    "window_strip_right",
    "door_front_left",
    "door_front_right",
    "door_back_left",
    "door_back_right",
    "panel_lines_left",
    "panel_lines_right",
    "flap_lines_left",
    "flap_lines_right",
    "blue_cheatline_left",
    "blue_cheatline_right",
]

AIRLINER_PRINT_TUNED_EXTRA_PARTS = [
    "cabin_windows_left",
    "cabin_windows_right",
    "service_panels_left",
    "service_panels_right",
    "dorsal_panel_line",
    "engine_left_intake_detail",
    "engine_right_intake_detail",
    "engine_left_2_intake_detail",
    "engine_right_2_intake_detail",
    "engine_left_fan_cross",
    "engine_right_fan_cross",
    "engine_left_2_fan_cross",
    "engine_right_2_fan_cross",
    "landing_gear_front_fairing",
    "landing_gear_left_fairing",
    "landing_gear_right_fairing",
    "wing_root_reinforcement_left",
    "wing_root_reinforcement_right",
    "pylon_brace_left",
    "pylon_brace_right",
    "pylon_brace_left_2",
    "pylon_brace_right_2",
    "major_breakaway_supports",
    "minor_detail_supports",
    "micro_contact_supports",
]


def airplane_requested(text: str) -> bool:
    return bool(
        re.search(
            r"самол[её]т|боинг|boeing|airliner|airplane|aircraft",
            text or "",
            re.I,
        )
    )


def airplane_wants_procedural_3mf(text: str) -> bool:
    """Explicit deterministic procedural 3MF (not Meshy, not mechanical kit)."""
    t = text or ""
    if not airplane_requested(t):
        return False
    return bool(
        re.search(r"\bпроцедур|\bбез\s+meshy|\bдетерминир|\bпримитив\b", t, re.I)
    )


def airplane_wants_mechanical_kit(text: str) -> bool:
    """Explicit request for a functional multi-part mechanical airplane kit."""
    t = text or ""
    if not airplane_requested(t):
        return False
    return bool(
        re.search(
            r"механич.{0,12}(?:кит|kit|сборк)|кинематик|"
            r"print-in-place.{0,24}(?:шасси|gear|лопаст|винт)|"
            r"подвижн.{0,12}(?:узл|шасси|лопаст|винт)|с\s+осями|"
            r"only\s+mechanical|только\s+механик",
            t,
            re.I,
        )
    )


def airplane_wants_realistic_mesh(text: str) -> bool:
    """Display/realistic airliner → Meshy AI mesh, not primitive mechanical kit."""
    return (
        airplane_requested(text)
        and not airplane_wants_mechanical_kit(text)
        and not airplane_wants_procedural_3mf(text)
    )


def airplane_print_tuned_requested(text: str) -> bool:
    """Post-print Boeing corrections: prefer deterministic print-tuned 3MF over raw Meshy STL."""
    t = text or ""
    if not airplane_requested(t):
        return False
    explicit_tuned = re.search(
        r"print[-\s]?tuned|после\s+печат|напечатал|улучши|доработ|"
        r"поддержк|support|груб|лохмат|крайний\s+файл|последн.{0,12}верси|"
        r"нейросет|полигон|ломан|каша|лопаст|пропечата|прототип|тонк.{0,16}элемент|"
        r"v2.{0,40}(после|печат|support|поддерж|улучши|доработ)|"
        r"(после|печат|support|поддерж|улучши|доработ).{0,40}v2",
        t,
        re.I,
    )
    fragile_parts = re.search(r"пилон|двигател|крыл", t, re.I) and re.search(
        r"хрупк|слом|усил|гряз|груб|лохмат|плохо|поддерж|support|толщ", t, re.I
    )
    return bool(explicit_tuned or fragile_parts)


def needs_airplane_concept_first(text: str) -> bool:
    """High-detail aircraft requests should not use the procedural fallback as final."""
    t = text or ""
    if not airplane_requested(t):
        return False
    if re.search(r"процедур|v[0-9]|чернов|быстр|без\s+референс|делай\s+3d\s+сразу", t, re.I):
        return False
    return bool(
        re.search(
            r"максимальн.{0,12}детал|реалист|красив|похож|boeing|боинг|"
            r"как\s+на\s+фото|как\s+на\s+картинк|точн.{0,12}модел",
            t,
            re.I,
        )
    )


def airplane_concept_prompt(text: str) -> str:
    from bot.services.bambu_hints import part_color_from_text

    low = (text or "").lower()
    airframe_color = part_color_from_text(text, r"корпус|фюзеляж|body|fuselage", "white" if re.search(r"бел|white", low) else "")
    airframe = f"{airframe_color} fuselage and wings" if airframe_color else "clean airliner livery"
    default_color = airframe_color or "white"
    engine_color = part_color_from_text(text, r"двигател|engine|мотор", default_color)
    tail_color = part_color_from_text(text, r"хвост|tail|киль|стабилизатор", default_color)
    accents = []
    if re.search(r"син|blue", low):
        accents.append("subtle blue accent stripe")
    color_desc = (
        f"{airframe}, {engine_color} engine nacelles, {tail_color} tail fin and tailplanes"
    )
    if not re.search(r"двигател|engine|мотор", low):
        color_desc += ", no black engines"
    if not re.search(r"хвост|tail|киль|стабилизатор", low):
        color_desc += ", no red tail"
    if accents:
        color_desc += ", " + ", ".join(accents)
    color_rule = (
        "color requirements are mandatory, use only colors from this current request, "
        "do not add black engines or red tail unless explicitly requested, "
    )
    if re.search(r"двигател|engine|мотор|хвост|tail|киль|стабилизатор", low):
        color_rule += "do not make an all-white aircraft if colored engines or tail are requested, "
    return (
        "high detail concept image for a 3D printable Boeing passenger airliner scale model, "
        f"{color_desc}, recognizable civilian airliner silhouette, long slender fuselage, "
        "rounded nose, swept wings with four engines under the wings, tail fin and horizontal stabilizers, "
        "landing gear visible, clean studio render on neutral background, no text, no logo, no weapons, "
        f"{color_rule}"
        "FDM friendly proportions for Bambu Studio"
    )[:900]


def _scale_from_text(text: str) -> float:
    # Prefer an explicit aircraft length over the filament budget. The geometry is hollow-ish
    # procedural surface detail, so a requested 150 mm model should remain in that ballpark.
    t = text or ""
    ml_cm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d+(?:[,.]\d+)?)\s*см", t, re.I)
    if not ml_cm:
        ml_cm = re.search(r"(\d+(?:[,.]\d+)?)\s*см\D{0,12}(?:длин[ауы]?|length)", t, re.I)
    if ml_cm:
        target = float(ml_cm.group(1).replace(",", ".")) * 10.0
        return max(0.72, min(1.15, target / 158.0))
    ml_mm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d{2,3})\s*мм", t, re.I)
    if ml_mm:
        return max(0.72, min(1.15, float(ml_mm.group(1)) / 158.0))
    # Keep non-sized 50 g requests compact, but not so small that the airplane becomes a flat icon.
    if re.search(r"50\s*г|50\s*gr|50g", t, re.I):
        return 0.92
    return 1.0


def _hd_scale_from_text(text: str) -> float:
    t = text or ""
    ml_cm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d+(?:[,.]\d+)?)\s*см", t, re.I)
    if not ml_cm:
        ml_cm = re.search(r"(\d+(?:[,.]\d+)?)\s*см\D{0,12}(?:длин[ауы]?|length)", t, re.I)
    if ml_cm:
        target = float(ml_cm.group(1).replace(",", ".")) * 10.0
        return max(0.68, min(1.05, target / 176.0))
    ml_mm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d{2,3})\s*мм", t, re.I)
    if ml_mm:
        return max(0.68, min(1.05, float(ml_mm.group(1)) / 176.0))
    if re.search(r"50\s*г|50\s*gr|50g", t, re.I):
        return 0.84
    return 0.9


def _color_mesh(mesh: Any, rgba: Tuple[int, int, int, int]) -> Any:
    if hasattr(mesh, "vertices") and hasattr(mesh, "visual"):
        mesh.visual.vertex_colors = np.tile(rgba, (len(mesh.vertices), 1)).astype(np.uint8)
    return mesh


def _align_z_to_x(mesh: Any) -> Any:
    import trimesh

    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    return mesh


def _align_z_to_y(mesh: Any) -> Any:
    import trimesh

    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    return mesh


def _cylinder_x(*, radius: float, length: float) -> Any:
    import trimesh

    return _align_z_to_x(trimesh.creation.cylinder(radius=radius, height=length, sections=48))


def _cone_x(*, radius: float, length: float) -> Any:
    import trimesh

    return _align_z_to_x(trimesh.creation.cone(radius=radius, height=length, sections=48))


def _cylinder_y(*, radius: float, length: float) -> Any:
    import trimesh

    return _align_z_to_y(trimesh.creation.cylinder(radius=radius, height=length, sections=48))


def _cylinder_z(*, radius: float, height: float, sections: int = 32) -> Any:
    import trimesh

    return trimesh.creation.cylinder(radius=radius, height=height, sections=sections)


def _tapered_wing(
    *,
    span: float,
    root_chord: float,
    tip_chord: float,
    thickness: float,
    sweep: float = 0.0,
) -> Any:
    import trimesh

    # Local axes: x=chord, y=span, z=thickness. The root is at y=0.
    z0, z1 = -thickness / 2, thickness / 2
    verts = np.array(
        [
            [-root_chord / 2, 0, z0],
            [root_chord / 2, 0, z0],
                  [sweep + tip_chord / 2, span, z0],
                  [sweep - tip_chord / 2, span, z0],
            [-root_chord / 2, 0, z1],
            [root_chord / 2, 0, z1],
                  [sweep + tip_chord / 2, span, z1],
                  [sweep - tip_chord / 2, span, z1],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 7, 6],
            [4, 6, 5],
            [0, 4, 5],
            [0, 5, 1],
            [1, 5, 6],
            [1, 6, 2],
            [2, 6, 7],
            [2, 7, 3],
            [3, 7, 4],
            [3, 4, 0],
        ]
    )
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def _vertical_tail(*, length: float, height: float, thickness: float) -> Any:
    import trimesh

    y0, y1 = -thickness / 2, thickness / 2
    verts = np.array(
        [
            [-length / 2, y0, 0],
            [length / 2, y0, 0],
            [-length / 2, y0, height],
            [-length / 2, y1, 0],
            [length / 2, y1, 0],
            [-length / 2, y1, height],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [3, 5, 4],
            [0, 3, 4],
            [0, 4, 1],
            [0, 2, 5],
            [0, 5, 3],
            [1, 4, 5],
            [1, 5, 2],
        ]
    )
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def _ellipsoid(*, scale_xyz: Tuple[float, float, float]) -> Any:
    import trimesh

    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    mesh.apply_scale(scale_xyz)
    return mesh


def _translate(mesh: Any, xyz: Tuple[float, float, float]) -> Any:
    mesh.apply_translation(xyz)
    return mesh


# ─────────────────────────────────────────────────────────────────────────────
#  NACA-based Boeing airliner geometry (Hollywood quality)
# ─────────────────────────────────────────────────────────────────────────────

def _make_naca_airliner_parts(scale: float, hd: bool = False) -> List[Tuple[str, Any]]:
    """
    Build airliner geometry from real aeronautical math:
      - Fuselage: Sears-Haack body with nose ogive and tail taper
      - Wings: NACA 2318 airfoil loft with 35° sweep, taper, dihedral, washout
      - Engines: NACA cowling profile (not cylinders)
      - Tail: NACA 0010 lofted vertical + horizontal stabilisers
      - Winglets: blended cant-angle winglets (747-400 style)
      - Gear: proper strut + wheel

    Dimensional basis: Boeing 747-400 TCDS ratios scaled to print size.
    Length reference = 158 mm at scale 1.0.
    """
    import trimesh
    from bot.services.airplane_geometry import (
        fuselage_body,
        loft_wing_half,
        engine_nacelle,
        vertical_stabilizer,
        blended_winglet,
        gear_strut,
    )

    s = scale  # alias

    white = (246, 246, 240, 255)
    dark  = (18,  22,  26,  255)
    glass = (8,   12,  18,  255)
    grey  = (95, 100, 104,  255)
    blue  = (34,  92, 165,  255)
    red   = (190, 34,  30,  255)

    # ── Fuselage ─────────────────────────────────────────────────────────────
    # 747: L=70.7 m, max diameter=6.4 m → ratio r/L ≈ 0.0453
    # Tail fraction lengthened (was 0.24) so the rear taper is smooth and
    # doesn't read as an "engine exit nozzle".
    fuse_len  = 158.0 * s
    fuse_r    = 6.6 * s
    fuse = fuselage_body(
        length=fuse_len,
        max_radius=fuse_r,
        nose_fraction=0.14,
        tail_fraction=0.34,
        belly_flatten=0.05,
        n_sections=80,
        n_circ=56,
    )
    # Fuselage is generated with nose at +X, centred on X; translate to assembly origin
    # (belly at Z=0 already)
    _color_mesh(fuse, white)

    # ── Wings ─────────────────────────────────────────────────────────────────
    # 747: span 68.4 m → ratio span/L ≈ 0.968; root chord ≈ 12.7 m → /L ≈ 0.18
    # sweep 37.5° at 25% chord; dihedral 7°; taper ratio 0.283; washout −2°
    wing_span      = 66.0 * s
    wing_root_c    = 36.0 * s
    wing_tip_c     = 17.0 * s   # taper ≈ 0.47 (slightly less extreme for printability)
    wing_le_sweep  = wing_span * math.tan(math.radians(35.0)) * 0.65
    wing_dihedral  = wing_span * math.tan(math.radians(7.0))

    wing_l_raw = loft_wing_half(
        airfoil="2318",
        root_chord=wing_root_c,
        tip_chord=wing_tip_c,
        span=wing_span,
        le_sweep=wing_le_sweep,
        dihedral_z=wing_dihedral,
        twist_deg=-2.0,
        n_span=32,
        n_chord=72,
        min_thickness_mm=1.4,
    )
    # Wing root sits on fuselage belly; Y+ = left side; move LE to correct chordwise station
    # Root LE should be at X ≈ +18 mm from fuselage centre (at 25% fuselage length from nose)
    wing_l_raw.apply_translation([14.0 * s, 5.0 * s, 4.0 * s])
    _color_mesh(wing_l_raw, white)

    wing_r_raw = wing_l_raw.copy()
    wing_r_raw.apply_scale([1, -1, 1])
    _color_mesh(wing_r_raw, white)

    # ── Horizontal stabilisers ────────────────────────────────────────────────
    # 747: stab span ≈ 22.2 m (≈ 32% of wing span); root chord ≈ 8.3 m
    stab_span   = 26.0 * s
    stab_root_c = 22.0 * s
    stab_tip_c  = 9.0 * s
    stab_sweep  = stab_span * math.tan(math.radians(34.0)) * 0.55

    stab_l = loft_wing_half(
        airfoil="0012",
        root_chord=stab_root_c,
        tip_chord=stab_tip_c,
        span=stab_span,
        le_sweep=stab_sweep,
        dihedral_z=stab_span * math.tan(math.radians(2.5)),
        twist_deg=0.0,
        n_span=18,
        n_chord=48,
        min_thickness_mm=1.2,
    )
    stab_l.apply_translation([-56.0 * s, 4.5 * s, 14.5 * s])
    _color_mesh(stab_l, white)
    stab_r = stab_l.copy()
    stab_r.apply_scale([1, -1, 1])
    _color_mesh(stab_r, white)

    # ── Vertical stabiliser ───────────────────────────────────────────────────
    # 747: fin height ≈ 19.4 m (≈ 28% of length); root chord ≈ 12 m
    vert_stab = vertical_stabilizer(
        root_chord=30.0 * s,
        tip_chord=12.0 * s,
        height=40.0 * s,
        sweep_x=-10.0 * s,
        airfoil="0010",
        n_span=16,
        n_chord=48,
        min_thickness_mm=1.2,
    )
    vert_stab.apply_translation([-60.0 * s, 0.0, 8.5 * s])
    _color_mesh(vert_stab, white)

    # ── Engines (nacelles) ────────────────────────────────────────────────────
    # 747: CF6-80 diameter 2.74 m → ratio d/L ≈ 0.039; length ≈ 6 m → /L ≈ 0.085
    # Engines hang BELOW the wing (Z lower than wing root) so the pylons can
    # visibly connect down to them. Engine top is ~Z=10*s, wing bottom ~Z=8*s.
    ENGINE_Z   = 6.0   # nacelle centreline height (mm at scale=1)
    ENGINE_R   = 4.5
    WING_BASE_Z = 4.0  # wing root Z (matches wing translation below)

    def make_engine(x: float, y: float) -> Any:
        nac = engine_nacelle(
            length=19.0 * s,
            intake_radius=3.6 * s,
            max_radius=ENGINE_R * s,
            exit_radius=3.0 * s,
            lip_frac=0.09,
            n_sections=36,
            n_circ=36,
        )
        nac.apply_translation([x * s, y * s, ENGINE_Z * s])
        return nac

    eng_l1 = make_engine(16, 29)
    eng_r1 = make_engine(16, -29)
    eng_l2 = make_engine(-12, 46)
    eng_r2 = make_engine(-12, -46)
    for e in (eng_l1, eng_r1, eng_l2, eng_r2):
        _color_mesh(e, dark)

    # ── Winglets ──────────────────────────────────────────────────────────────
    # 747-400 winglets: height ≈ 1.8 m; can't ≈ 70°
    wl = blended_winglet(
        height=12.0 * s,
        root_chord=14.0 * s,
        cant_deg=72.0,
        airfoil="0010",
        n_span=12,
        n_chord=36,
        min_thickness_mm=1.0,
    )
    # Place at wing tip (Y = wing_span + 5mm body offset)
    tip_y = wing_span + 5.0 * s
    # Find approximate tip LE X from wing geometry
    tip_le_x = 14.0 * s + wing_le_sweep
    wl.apply_translation([tip_le_x + 2.0 * s, tip_y, wing_dihedral + 4.0 * s])
    _color_mesh(wl, red)
    wl_r = wl.copy()
    wl_r.apply_scale([1, -1, 1])
    _color_mesh(wl_r, red)

    # ── Pylons ────────────────────────────────────────────────────────────────
    # Pylon must span from top of engine nacelle (Z = ENGINE_Z + ENGINE_R)
    # up to bottom of wing root (Z ≈ WING_BASE_Z + wing_thickness/2).
    # Using engine x as anchor so pylon is centred on the nacelle.
    def make_pylon(engine_x: float, engine_y: float, dihedral_t: float) -> Any:
        # engine top Z = ENGINE_Z + ENGINE_R; wing-bottom Z at this Y ≈
        # WING_BASE_Z + dihedral_rise. Span the gap with a thin tapered fin.
        z_bottom = ENGINE_Z + ENGINE_R - 0.5     # just inside nacelle top
        wing_bot_z = WING_BASE_Z + 2.0 + (dihedral_t * wing_dihedral / s)
        z_top = wing_bot_z + 1.5                 # bury into wing for solid join
        pylon_h = max(z_top - z_bottom, 1.2)
        pylon_z = (z_top + z_bottom) / 2.0
        # Slightly tilted (LE forward) box, narrow lateral profile
        mesh = trimesh.creation.box(extents=[4.4 * s, 1.4 * s, pylon_h * s])
        _translate(mesh, (engine_x * s, engine_y * s, pylon_z * s))
        return mesh

    # dihedral_t = fractional Y position along span (0=root, 1=tip)
    pylon_l1 = make_pylon(16, 29, dihedral_t=29 / wing_span * s)
    pylon_r1  = pylon_l1.copy(); pylon_r1.apply_scale([1, -1, 1])
    pylon_l2  = make_pylon(-12, 46, dihedral_t=46 / wing_span * s)
    pylon_r2  = pylon_l2.copy(); pylon_r2.apply_scale([1, -1, 1])
    for p in (pylon_l1, pylon_r1, pylon_l2, pylon_r2):
        _color_mesh(p, grey)

    # ── Landing gear ──────────────────────────────────────────────────────────
    # Strut height tall enough that wheels touch Z=0 plate AND struts visibly
    # poke out from the fuselage belly (was 3.5 mm → barely visible).
    GEAR_STRUT_H = 6.0
    def make_gear(x: float, y: float, n_wheels: int = 2) -> Any:
        parts = []
        strut = gear_strut(
            strut_height=GEAR_STRUT_H * s,
            strut_radius=1.0 * s,
            wheel_radius=2.2 * s,
            wheel_width=1.6 * s if n_wheels == 1 else 1.2 * s,
            n_wheel=26,
        )
        _translate(strut, (x * s, y * s, 0.0))
        parts.append(strut)
        if n_wheels == 2:
            strut2 = gear_strut(
                strut_height=GEAR_STRUT_H * s,
                strut_radius=1.0 * s,
                wheel_radius=2.2 * s,
                wheel_width=1.2 * s,
                n_wheel=26,
            )
            _translate(strut2, (x * s, (y + 3.6) * s, 0.0))
            parts.append(strut2)
        return trimesh.util.concatenate(parts)

    gear_front = make_gear(40, 0, n_wheels=2)
    gear_l = make_gear(-22, 9, n_wheels=2)
    gear_r = make_gear(-22, -12, n_wheels=2)
    for g in (gear_front, gear_l, gear_r):
        _color_mesh(g, dark)

    # ── Cabin details (windows, doors, cheatline) ──────────────────────────────
    cockpit = trimesh.creation.box(extents=[15.0 * s, 6.8 * s, 1.6 * s])
    _translate(cockpit, (62.0 * s, 0, 14.5 * s))
    _color_mesh(cockpit, glass)

    windows_l = trimesh.creation.box(extents=[82.0 * s, 0.72 * s, 1.3 * s])
    _translate(windows_l, (4.0 * s, 7.1 * s, 12.0 * s))
    _color_mesh(windows_l, glass)
    windows_r = windows_l.copy(); windows_r.apply_scale([1, -1, 1])
    _color_mesh(windows_r, glass)

    door_fl = trimesh.creation.box(extents=[1.1 * s, 0.78 * s, 5.4 * s])
    _translate(door_fl, (44.0 * s, 7.2 * s, 8.5 * s))
    _color_mesh(door_fl, dark)
    door_fr = door_fl.copy(); door_fr.apply_scale([1, -1, 1])
    _color_mesh(door_fr, dark)
    door_bl = trimesh.creation.box(extents=[1.1 * s, 0.78 * s, 5.0 * s])
    _translate(door_bl, (-46.0 * s, 7.2 * s, 8.5 * s))
    _color_mesh(door_bl, dark)
    door_br = door_bl.copy(); door_br.apply_scale([1, -1, 1])
    _color_mesh(door_br, dark)

    cheatline_l = trimesh.creation.box(extents=[96.0 * s, 0.55 * s, 0.9 * s])
    _translate(cheatline_l, (2.0 * s, 7.35 * s, 9.6 * s))
    _color_mesh(cheatline_l, blue)
    cheatline_r = cheatline_l.copy(); cheatline_r.apply_scale([1, -1, 1])
    _color_mesh(cheatline_r, blue)

    named_meshes = [
        ("fuselage",          fuse),
        # nose and tail_cone are integrated into the fuselage body (NACA ogive).
        # Kept as part names for AMS grouping compatibility.
        ("nose",              fuse),
        ("tail_cone",         fuse),
        ("wing_left",         wing_l_raw),
        ("wing_right",        wing_r_raw),
        ("tailplane_left",    stab_l),
        ("tailplane_right",   stab_r),
        ("tail_fin",          vert_stab),
        ("engine_left",       eng_l1),
        ("engine_right",      eng_r1),
        ("engine_left_2",     eng_l2),
        ("engine_right_2",    eng_r2),
        ("pylon_left",        pylon_l1),
        ("pylon_right",       pylon_r1),
        ("pylon_left_2",      pylon_l2),
        ("pylon_right_2",     pylon_r2),
        ("winglet_left",      wl),
        ("winglet_right",     wl_r),
        ("landing_gear_front", gear_front),
        ("landing_gear_left",  gear_l),
        ("landing_gear_right", gear_r),
        ("cockpit_window",    cockpit),
        ("window_strip_left", windows_l),
        ("window_strip_right", windows_r),
        ("door_front_left",   door_fl),
        ("door_front_right",  door_fr),
        ("door_back_left",    door_bl),
        ("door_back_right",   door_br),
        ("blue_cheatline_left",  cheatline_l),
        ("blue_cheatline_right", cheatline_r),
    ]

    if hd:
        # HD extras: fan disks, panel lines, flap lines
        def make_fan_disk(x: float, y: float) -> Any:
            fan = engine_nacelle(
                length=2.2 * s,
                intake_radius=3.2 * s,
                max_radius=3.4 * s,
                exit_radius=3.0 * s,
                n_sections=12,
                n_circ=32,
            )
            fan.apply_translation([x * s + 9.5 * s, y * s, 3.6 * s])
            return fan

        fan_specs = [(16, 29), (16, -29), (-12, 46), (-12, -46)]
        fan_names = ["engine_left_fan", "engine_right_fan", "engine_left_2_fan", "engine_right_2_fan"]
        for (x, y), name in zip(fan_specs, fan_names):
            fan = make_fan_disk(x, y)
            _color_mesh(fan, glass)
            named_meshes.append((name, fan))

        # Panel lines along fuselage sides (thin boxes = rivet seam)
        panel_l = trimesh.creation.box(extents=[80.0 * s, 0.35 * s, 0.45 * s])
        _translate(panel_l, (4.0 * s, 25.0 * s, 7.2 * s))
        _color_mesh(panel_l, grey)
        panel_r = panel_l.copy(); panel_r.apply_scale([1, -1, 1])
        _color_mesh(panel_r, grey)
        named_meshes += [("panel_lines_left", panel_l), ("panel_lines_right", panel_r)]

        flap_l = trimesh.creation.box(extents=[38.0 * s, 0.35 * s, 0.45 * s])
        _translate(flap_l, (-5.0 * s, 50.0 * s, 7.0 * s))
        _color_mesh(flap_l, grey)
        flap_r = flap_l.copy(); flap_r.apply_scale([1, -1, 1])
        _color_mesh(flap_r, grey)
        named_meshes += [("flap_lines_left", flap_l), ("flap_lines_right", flap_r)]

        # ── AIRLINER_PRINT_TUNED_EXTRA_PARTS ─────────────────────────────────
        # Cabin window rows (individual slots)
        def make_window_row(y_sign: int) -> Any:
            ws = []
            for wx in np.linspace(-44, 44, 17):
                w = trimesh.creation.box(extents=[1.2 * s, 0.56 * s, 0.9 * s])
                _translate(w, (float(wx) * s, y_sign * 7.25 * s, 12.6 * s))
                ws.append(w)
            mesh = trimesh.util.concatenate(ws)
            _color_mesh(mesh, glass)
            return mesh

        cab_win_l = make_window_row(1)
        cab_win_r = make_window_row(-1)
        named_meshes += [("cabin_windows_left", cab_win_l), ("cabin_windows_right", cab_win_r)]

        # Service panel ticks
        def make_service_panels(y_sign: int) -> Any:
            ticks = []
            for tx in (-52, -34, -16, 2, 20, 38, 54):
                t_mesh = trimesh.creation.box(extents=[0.7 * s, 0.4 * s, 3.0 * s])
                _translate(t_mesh, (tx * s, y_sign * 7.3 * s, 9.8 * s))
                ticks.append(t_mesh)
            mesh = trimesh.util.concatenate(ticks)
            _color_mesh(mesh, grey)
            return mesh

        svc_l = make_service_panels(1)
        svc_r = make_service_panels(-1)
        named_meshes += [("service_panels_left", svc_l), ("service_panels_right", svc_r)]

        # Dorsal panel line
        dorsal = trimesh.creation.box(extents=[96.0 * s, 0.5 * s, 0.42 * s])
        _translate(dorsal, (0.0, 0.0, 15.8 * s))
        _color_mesh(dorsal, grey)
        named_meshes.append(("dorsal_panel_line", dorsal))

        # Engine intake detail rings and fan crosses (thin boxes per engine)
        for (ex, ey), suffix in zip([(16, 29), (16, -29), (-12, 46), (-12, -46)],
                                     ["left", "right", "left_2", "right_2"]):
            intake = trimesh.creation.box(extents=[0.6 * s, 9.0 * s, 9.0 * s])
            _translate(intake, ((ex + 9.5) * s, ey * s, 3.6 * s))
            _color_mesh(intake, grey)
            named_meshes.append((f"engine_{suffix}_intake_detail", intake))

            cross = trimesh.creation.box(extents=[0.5 * s, 6.4 * s, 0.3 * s])
            _translate(cross, ((ex + 9.7) * s, ey * s, 3.6 * s))
            _color_mesh(cross, glass)
            named_meshes.append((f"engine_{suffix}_fan_cross", cross))

        # Wing root reinforcements
        wroot_l = trimesh.creation.box(extents=[46.0 * s, 2.6 * s, 1.6 * s])
        _translate(wroot_l, (2.0 * s, 14.8 * s, 5.1 * s))
        _color_mesh(wroot_l, white)
        wroot_r = wroot_l.copy(); wroot_r.apply_scale([1, -1, 1])
        _color_mesh(wroot_r, white)
        named_meshes += [("wing_root_reinforcement_left", wroot_l), ("wing_root_reinforcement_right", wroot_r)]

        # Pylon braces
        for (bx, by), name in zip([(15, 28.5), (-13, 45.5)], ["left", "left_2"]):
            pb = trimesh.creation.box(extents=[5.6 * s, 2.4 * s, 6.7 * s])
            _translate(pb, (bx * s, by * s, 6.0 * s))
            _color_mesh(pb, grey)
            pb_r = pb.copy(); pb_r.apply_scale([1, -1, 1])
            _color_mesh(pb_r, grey)
            named_meshes += [(f"pylon_brace_{name}", pb), (f"pylon_brace_{name.replace('left','right')}", pb_r)]

        # Gear fairings
        for gx, gy, ext in [
            (40, 0, [6.8 * s, 3.2 * s, 2.1 * s]),
            (-22, 9, [7.6 * s, 3.2 * s, 2.2 * s]),
        ]:
            gf = trimesh.creation.box(extents=ext)
            _translate(gf, (gx * s, gy * s, 1.9 * s))
            _color_mesh(gf, grey)
            if gy == 0:
                named_meshes.append(("landing_gear_front_fairing", gf))
            else:
                gf_r = gf.copy(); gf_r.apply_scale([1, -1, 1])
                _color_mesh(gf_r, grey)
                named_meshes += [("landing_gear_left_fairing", gf), ("landing_gear_right_fairing", gf_r)]

        # Breakaway supports (symbolic — actual positions set by slicer)
        for sname, col in [
            ("major_breakaway_supports", (205, 110, 65, 255)),
            ("minor_detail_supports",    (205, 110, 65, 255)),
            ("micro_contact_supports",   (205, 110, 65, 255)),
        ]:
            sup = trimesh.creation.box(extents=[1.8 * s, 1.8 * s, 4.0 * s])
            _translate(sup, (0.0, 0.0, 2.0 * s))
            _color_mesh(sup, col)
            named_meshes.append((sname, sup))
    _settle_on_plate(named_meshes)
    return named_meshes


def _settle_on_plate(named_meshes: List[Tuple[str, Any]]) -> None:
    bounds = np.array([mesh.bounds for _, mesh in named_meshes], dtype=float)
    mins = bounds[:, 0, :].min(axis=0)
    maxs = bounds[:, 1, :].max(axis=0)
    center_xy = (mins[:2] + maxs[:2]) / 2
    delta = np.array([-center_xy[0], -center_xy[1], -mins[2]], dtype=float)
    for _, mesh in named_meshes:
        mesh.apply_translation(delta)


def _box(name: str, extents: Tuple[float, float, float], xyz: Tuple[float, float, float], rgba: Tuple[int, int, int, int]) -> Tuple[str, Any]:
    import trimesh

    mesh = trimesh.creation.box(extents=extents)
    _translate(mesh, xyz)
    return name, _color_mesh(mesh, rgba)


def _make_parts(scale: float) -> List[Tuple[str, Any]]:
    import trimesh

    white = (244, 244, 238, 255)
    dark = (24, 28, 32, 255)
    blue = (32, 82, 145, 255)
    red = (185, 30, 26, 255)

    # A broad belly skid gives Bambu a stable first layer. The previous landing-gear-only
    # footprint started from tiny posts and triggered nozzle-clumping warnings.
    print_skid = trimesh.creation.box(extents=[116 * scale, 10.5 * scale, 2.0 * scale])
    _translate(print_skid, (-2 * scale, 0, 1.0 * scale))

    fuselage = _translate(_cylinder_x(radius=6.2 * scale, length=124 * scale), (0, 0, 8.3 * scale))
    nose = _translate(_ellipsoid(scale_xyz=(14 * scale, 6.2 * scale, 6.2 * scale)), (68 * scale, 0, 8.3 * scale))
    # Use an ellipsoid tail cone instead of rotating a cone after translation. The old transform
    # accidentally moved the tail cone toward the nose, which made the silhouette wrong.
    tail_cone = _translate(_ellipsoid(scale_xyz=(11 * scale, 5.4 * scale, 5.4 * scale)), (-68 * scale, 0, 8.3 * scale))

    wing_l = _tapered_wing(
        span=62 * scale,
        root_chord=34 * scale,
        tip_chord=20 * scale,
        thickness=3.2 * scale,
        sweep=-11 * scale,
    )
    wing_l.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-1.2), [0, 1, 0]))
    _translate(wing_l, (4 * scale, 5.5 * scale, 4.4 * scale))
    wing_r = wing_l.copy()
    wing_r.apply_scale([1, -1, 1])

    tail_l = _tapered_wing(
        span=24 * scale,
        root_chord=20 * scale,
        tip_chord=11 * scale,
        thickness=2.5 * scale,
        sweep=-6 * scale,
    )
    _translate(tail_l, (-54 * scale, 5.0 * scale, 13.5 * scale))
    tail_r = tail_l.copy()
    tail_r.apply_scale([1, -1, 1])
    tail_fin = _translate(
        _vertical_tail(length=29 * scale, height=42 * scale, thickness=3.8 * scale),
        (-59 * scale, 0, 8.2 * scale),
    )

    engine_l = _cylinder_x(radius=3.8 * scale, length=17 * scale)
    _translate(engine_l, (14 * scale, 29 * scale, 4.0 * scale))
    engine_r = engine_l.copy()
    engine_r.apply_scale([1, -1, 1])
    engine_l2 = _cylinder_x(radius=3.5 * scale, length=15 * scale)
    _translate(engine_l2, (-11 * scale, 44 * scale, 3.8 * scale))
    engine_r2 = engine_l2.copy()
    engine_r2.apply_scale([1, -1, 1])
    gear_front = trimesh.creation.box(extents=[5.5 * scale, 2.2 * scale, 2.8 * scale])
    _translate(gear_front, (38 * scale, 0, 1.4 * scale))
    gear_l = trimesh.creation.box(extents=[5.5 * scale, 2.2 * scale, 2.8 * scale])
    _translate(gear_l, (-22 * scale, 8.8 * scale, 1.4 * scale))
    gear_r = gear_l.copy()
    gear_r.apply_scale([1, -1, 1])
    winglet_l = trimesh.creation.box(extents=[2.2 * scale, 5.5 * scale, 10 * scale])
    _translate(winglet_l, (-10 * scale, 66 * scale, 9.5 * scale))
    winglet_r = winglet_l.copy()
    winglet_r.apply_scale([1, -1, 1])
    cockpit = trimesh.creation.box(extents=[16 * scale, 6.5 * scale, 1.8 * scale])
    _translate(cockpit, (56 * scale, 0, 13.9 * scale))
    windows_l = trimesh.creation.box(extents=[76 * scale, 0.85 * scale, 1.5 * scale])
    _translate(windows_l, (3 * scale, 6.45 * scale, 11.6 * scale))
    windows_r = windows_l.copy()
    windows_r.apply_scale([1, -1, 1])
    door_front_l = _box("door_front_left", (1.2 * scale, 0.85 * scale, 5.4 * scale), (41 * scale, 6.6 * scale, 8.0 * scale), dark)[1]
    door_front_r = door_front_l.copy()
    door_front_r.apply_scale([1, -1, 1])
    door_back_l = _box("door_back_left", (1.2 * scale, 0.85 * scale, 4.8 * scale), (-43 * scale, 6.6 * scale, 8.0 * scale), dark)[1]
    door_back_r = door_back_l.copy()
    door_back_r.apply_scale([1, -1, 1])
    cheatline_l = _box("blue_cheatline_left", (92 * scale, 0.6 * scale, 1.1 * scale), (2 * scale, 6.75 * scale, 8.5 * scale), blue)[1]
    cheatline_r = cheatline_l.copy()
    cheatline_r.apply_scale([1, -1, 1])

    for mesh in (print_skid, fuselage, nose, tail_cone, wing_l, wing_r, tail_l, tail_r, tail_fin):
        _color_mesh(mesh, white)
    for mesh in (
        engine_l,
        engine_r,
        engine_l2,
        engine_r2,
        gear_front,
        gear_l,
        gear_r,
        cockpit,
        windows_l,
        windows_r,
        door_front_l,
        door_front_r,
        door_back_l,
        door_back_r,
    ):
        _color_mesh(mesh, dark)
    _color_mesh(cheatline_l, blue)
    _color_mesh(cheatline_r, blue)
    _color_mesh(winglet_l, red)
    _color_mesh(winglet_r, red)

    named_meshes = [
        ("print_skid", print_skid),
        ("fuselage", fuselage),
        ("nose", nose),
        ("tail_cone", tail_cone),
        ("wing_left", wing_l),
        ("wing_right", wing_r),
        ("tail_fin", tail_fin),
        ("tailplane_left", tail_l),
        ("tailplane_right", tail_r),
        ("engine_left", engine_l),
        ("engine_right", engine_r),
        ("engine_left_2", engine_l2),
        ("engine_right_2", engine_r2),
        ("landing_gear_front", gear_front),
        ("landing_gear_left", gear_l),
        ("landing_gear_right", gear_r),
        ("winglet_left", winglet_l),
        ("winglet_right", winglet_r),
        ("cockpit_window", cockpit),
        ("window_strip_left", windows_l),
        ("window_strip_right", windows_r),
        ("door_front_left", door_front_l),
        ("door_front_right", door_front_r),
        ("door_back_left", door_back_l),
        ("door_back_right", door_back_r),
        ("blue_cheatline_left", cheatline_l),
        ("blue_cheatline_right", cheatline_r),
    ]
    _settle_on_plate(named_meshes)
    return named_meshes


def _make_airliner_hd_parts(scale: float) -> List[Tuple[str, Any]]:
    import trimesh

    white = (246, 246, 240, 255)
    dark = (18, 22, 26, 255)
    glass = (8, 12, 18, 255)
    grey = (95, 100, 104, 255)
    blue = (34, 92, 165, 255)
    red = (190, 34, 30, 255)

    print_skid = trimesh.creation.box(extents=[126 * scale, 12.5 * scale, 1.8 * scale])
    _translate(print_skid, (-1 * scale, 0, 0.9 * scale))

    fuselage = _translate(_cylinder_x(radius=6.6 * scale, length=132 * scale), (0, 0, 8.9 * scale))
    nose = _translate(_ellipsoid(scale_xyz=(15.5 * scale, 6.7 * scale, 6.7 * scale)), (73 * scale, 0, 8.9 * scale))
    tail_cone = _translate(_ellipsoid(scale_xyz=(13.0 * scale, 5.6 * scale, 5.6 * scale)), (-73 * scale, 0, 8.9 * scale))

    wing_l = _tapered_wing(
        span=69 * scale,
        root_chord=38 * scale,
        tip_chord=17 * scale,
        thickness=3.4 * scale,
        sweep=-16 * scale,
    )
    wing_l.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-1.5), [0, 1, 0]))
    _translate(wing_l, (5 * scale, 5.8 * scale, 5.1 * scale))
    wing_r = wing_l.copy()
    wing_r.apply_scale([1, -1, 1])

    tail_l = _tapered_wing(
        span=27 * scale,
        root_chord=22 * scale,
        tip_chord=10 * scale,
        thickness=2.3 * scale,
        sweep=-7 * scale,
    )
    _translate(tail_l, (-58 * scale, 5.2 * scale, 15.1 * scale))
    tail_r = tail_l.copy()
    tail_r.apply_scale([1, -1, 1])
    tail_fin = _translate(
        _vertical_tail(length=31 * scale, height=43 * scale, thickness=4.1 * scale),
        (-62 * scale, 0, 8.7 * scale),
    )

    def engine(x: float, y: float, radius: float, length: float):
        nacelle = _cylinder_x(radius=radius * scale, length=length * scale)
        _translate(nacelle, (x * scale, y * scale, 3.9 * scale))
        fan = _cylinder_x(radius=(radius * 0.78) * scale, length=1.5 * scale)
        _translate(fan, ((x + length / 2 + 0.15) * scale, y * scale, 3.9 * scale))
        pylon = trimesh.creation.box(extents=[4.4 * scale, 1.7 * scale, 5.6 * scale])
        _translate(pylon, ((x - 1.0) * scale, y * scale, 7.0 * scale))
        return nacelle, fan, pylon

    engine_l, engine_l_fan, pylon_l = engine(20, 28, 4.4, 18)
    engine_r = engine_l.copy()
    engine_r.apply_scale([1, -1, 1])
    engine_r_fan = engine_l_fan.copy()
    engine_r_fan.apply_scale([1, -1, 1])
    pylon_r = pylon_l.copy()
    pylon_r.apply_scale([1, -1, 1])
    engine_l2, engine_l2_fan, pylon_l2 = engine(-10, 46, 4.0, 16)
    engine_r2 = engine_l2.copy()
    engine_r2.apply_scale([1, -1, 1])
    engine_r2_fan = engine_l2_fan.copy()
    engine_r2_fan.apply_scale([1, -1, 1])
    pylon_r2 = pylon_l2.copy()
    pylon_r2.apply_scale([1, -1, 1])

    gear_front = _cylinder_y(radius=1.7 * scale, length=4.0 * scale)
    _translate(gear_front, (42 * scale, 0, 2.0 * scale))
    gear_l = _cylinder_y(radius=1.9 * scale, length=4.2 * scale)
    _translate(gear_l, (-20 * scale, 9.5 * scale, 2.0 * scale))
    gear_r = gear_l.copy()
    gear_r.apply_scale([1, -1, 1])

    winglet_l = trimesh.creation.box(extents=[2.4 * scale, 5.8 * scale, 11.5 * scale])
    _translate(winglet_l, (-12 * scale, 72 * scale, 10.7 * scale))
    winglet_r = winglet_l.copy()
    winglet_r.apply_scale([1, -1, 1])

    cockpit = trimesh.creation.box(extents=[16 * scale, 6.8 * scale, 1.7 * scale])
    _translate(cockpit, (61 * scale, 0, 14.8 * scale))
    windows_l = trimesh.creation.box(extents=[84 * scale, 0.75 * scale, 1.35 * scale])
    _translate(windows_l, (4 * scale, 6.9 * scale, 12.3 * scale))
    windows_r = windows_l.copy()
    windows_r.apply_scale([1, -1, 1])

    door_front_l = _box("door_front_left", (1.2 * scale, 0.8 * scale, 5.7 * scale), (43 * scale, 7.05 * scale, 8.9 * scale), dark)[1]
    door_front_r = door_front_l.copy()
    door_front_r.apply_scale([1, -1, 1])
    door_back_l = _box("door_back_left", (1.2 * scale, 0.8 * scale, 5.2 * scale), (-46 * scale, 7.05 * scale, 8.9 * scale), dark)[1]
    door_back_r = door_back_l.copy()
    door_back_r.apply_scale([1, -1, 1])

    cheatline_l = _box("blue_cheatline_left", (98 * scale, 0.55 * scale, 0.9 * scale), (1 * scale, 7.25 * scale, 9.7 * scale), blue)[1]
    cheatline_r = cheatline_l.copy()
    cheatline_r.apply_scale([1, -1, 1])
    panel_l = _box("panel_lines_left", (72 * scale, 0.35 * scale, 0.55 * scale), (4 * scale, 23 * scale, 6.9 * scale), grey)[1]
    panel_r = panel_l.copy()
    panel_r.apply_scale([1, -1, 1])
    flap_l = _box("flap_lines_left", (35 * scale, 0.35 * scale, 0.55 * scale), (-9 * scale, 48 * scale, 7.0 * scale), grey)[1]
    flap_r = flap_l.copy()
    flap_r.apply_scale([1, -1, 1])

    for mesh in (print_skid, fuselage, nose, tail_cone, wing_l, wing_r, tail_l, tail_r, tail_fin):
        _color_mesh(mesh, white)
    for mesh in (engine_l, engine_r, engine_l2, engine_r2):
        _color_mesh(mesh, dark)
    for mesh in (engine_l_fan, engine_r_fan, engine_l2_fan, engine_r2_fan, cockpit, windows_l, windows_r, door_front_l, door_front_r, door_back_l, door_back_r):
        _color_mesh(mesh, glass)
    for mesh in (pylon_l, pylon_r, pylon_l2, pylon_r2, gear_front, gear_l, gear_r, panel_l, panel_r, flap_l, flap_r):
        _color_mesh(mesh, grey)
    for mesh in (cheatline_l, cheatline_r):
        _color_mesh(mesh, blue)
    for mesh in (winglet_l, winglet_r):
        _color_mesh(mesh, red)

    named_meshes = [
        ("print_skid", print_skid),
        ("fuselage", fuselage),
        ("nose", nose),
        ("tail_cone", tail_cone),
        ("wing_left", wing_l),
        ("wing_right", wing_r),
        ("tail_fin", tail_fin),
        ("tailplane_left", tail_l),
        ("tailplane_right", tail_r),
        ("engine_left", engine_l),
        ("engine_right", engine_r),
        ("engine_left_2", engine_l2),
        ("engine_right_2", engine_r2),
        ("engine_left_fan", engine_l_fan),
        ("engine_right_fan", engine_r_fan),
        ("engine_left_2_fan", engine_l2_fan),
        ("engine_right_2_fan", engine_r2_fan),
        ("pylon_left", pylon_l),
        ("pylon_right", pylon_r),
        ("pylon_left_2", pylon_l2),
        ("pylon_right_2", pylon_r2),
        ("landing_gear_front", gear_front),
        ("landing_gear_left", gear_l),
        ("landing_gear_right", gear_r),
        ("winglet_left", winglet_l),
        ("winglet_right", winglet_r),
        ("cockpit_window", cockpit),
        ("window_strip_left", windows_l),
        ("window_strip_right", windows_r),
        ("door_front_left", door_front_l),
        ("door_front_right", door_front_r),
        ("door_back_left", door_back_l),
        ("door_back_right", door_back_r),
        ("panel_lines_left", panel_l),
        ("panel_lines_right", panel_r),
        ("flap_lines_left", flap_l),
        ("flap_lines_right", flap_r),
        ("blue_cheatline_left", cheatline_l),
        ("blue_cheatline_right", cheatline_r),
    ]
    _settle_on_plate(named_meshes)
    return named_meshes


def _make_window_row(*, side: int, scale: float) -> Any:
    import trimesh

    windows = []
    for x in np.linspace(-43, 43, 17):
        mesh = trimesh.creation.box(extents=[1.25 * scale, 0.58 * scale, 0.92 * scale])
        _translate(mesh, (float(x) * scale, side * 7.28 * scale, 12.75 * scale))
        windows.append(mesh)
    return trimesh.util.concatenate(windows)


def _make_service_panel_ticks(*, side: int, scale: float) -> Any:
    import trimesh

    ticks = []
    for x in (-52, -34, -16, 2, 20, 38, 54):
        mesh = trimesh.creation.box(extents=[0.72 * scale, 0.42 * scale, 3.2 * scale])
        _translate(mesh, (x * scale, side * 7.34 * scale, 9.9 * scale))
        ticks.append(mesh)
    return trimesh.util.concatenate(ticks)


def _make_engine_intake_detail(*, x: float, y: float, radius: float, length: float, scale: float) -> Any:
    import trimesh

    front_x = (x + length / 2.0 + 0.55) * scale
    y0 = y * scale
    z0 = 3.9 * scale
    parts = []
    # Four thick lip segments avoid a non-printable hollow ring while still reading as an intake.
    for dy, dz, ext in [
        (0.0, radius * 0.82, (0.65, radius * 1.45, 0.42)),
        (0.0, -radius * 0.82, (0.65, radius * 1.45, 0.42)),
        (radius * 0.82, 0.0, (0.65, 0.42, radius * 1.45)),
        (-radius * 0.82, 0.0, (0.65, 0.42, radius * 1.45)),
    ]:
        mesh = trimesh.creation.box(extents=[ext[0] * scale, ext[1] * scale, ext[2] * scale])
        _translate(mesh, (front_x, y0 + dy * scale, z0 + dz * scale))
        parts.append(mesh)
    return trimesh.util.concatenate(parts)


def _make_engine_fan_cross(*, x: float, y: float, radius: float, length: float, scale: float) -> Any:
    import trimesh

    front_x = (x + length / 2.0 + 0.9) * scale
    y0 = y * scale
    z0 = 3.9 * scale
    bars = []
    for ext in [
        (0.52, radius * 1.45, 0.30),
        (0.52, 0.30, radius * 1.45),
    ]:
        mesh = trimesh.creation.box(extents=[ext[0] * scale, ext[1] * scale, ext[2] * scale])
        _translate(mesh, (front_x, y0, z0))
        bars.append(mesh)
    hub = _cylinder_x(radius=max(0.62, radius * 0.20) * scale, length=0.58 * scale)
    _translate(hub, (front_x, y0, z0))
    bars.append(hub)
    return trimesh.util.concatenate(bars)


def _make_adaptive_breakaway_supports(scale: float) -> List[Tuple[str, Any]]:
    import trimesh

    major = []
    minor = []
    micro = []

    def add_column(bucket: list, x: float, y: float, height: float, radius: float, pad_radius: float) -> None:
        pad = _cylinder_z(radius=pad_radius * scale, height=0.55 * scale, sections=24)
        _translate(pad, (x * scale, y * scale, 0.275 * scale))
        col = _cylinder_z(radius=radius * scale, height=height * scale, sections=18)
        _translate(col, (x * scale, y * scale, (height / 2.0 + 0.55) * scale))
        tip = _cylinder_z(radius=max(0.18, radius * 0.45) * scale, height=0.35 * scale, sections=12)
        _translate(tip, (x * scale, y * scale, (height + 0.9) * scale))
        bucket.extend([pad, col, tip])

    # Large columns carry the wing/fuselage load; smaller columns only touch fragile details.
    for side in (-1, 1):
        for x, y, h in [(-30, 55, 4.5), (-7, 42, 4.2), (20, 28, 4.0), (40, 18, 3.8)]:
            add_column(major, x, side * y, h, radius=0.95, pad_radius=3.0)
        for x, y, h in [(-61, 24, 12.1), (-47, 14, 11.4), (20, 28, 3.1), (-10, 46, 3.0)]:
            add_column(minor, x, side * y, h, radius=0.55, pad_radius=1.8)
        for x, y, h in [(42, 3.8, 1.2), (-20, 9.8, 1.2), (-12, 72, 8.6)]:
            add_column(micro, x, side * y, h, radius=0.32, pad_radius=1.1)

    return [
        ("major_breakaway_supports", trimesh.util.concatenate(major)),
        ("minor_detail_supports", trimesh.util.concatenate(minor)),
        ("micro_contact_supports", trimesh.util.concatenate(micro)),
    ]


def _make_airliner_print_tuned_parts(scale: float) -> List[Tuple[str, Any]]:
    import trimesh

    named_meshes = _make_airliner_hd_parts(scale)
    white = (246, 246, 240, 255)
    glass = (8, 12, 18, 255)
    grey = (95, 100, 104, 255)
    support_color = (205, 110, 65, 255)

    windows_l = _color_mesh(_make_window_row(side=1, scale=scale), glass)
    windows_r = _color_mesh(_make_window_row(side=-1, scale=scale), glass)
    panels_l = _color_mesh(_make_service_panel_ticks(side=1, scale=scale), grey)
    panels_r = _color_mesh(_make_service_panel_ticks(side=-1, scale=scale), grey)
    dorsal_line = _box(
        "dorsal_panel_line",
        (96 * scale, 0.52 * scale, 0.45 * scale),
        (0, 0, 16.0 * scale),
        grey,
    )[1]
    engine_specs = [
        ("engine_left", 20, 28, 4.4, 18),
        ("engine_right", 20, -28, 4.4, 18),
        ("engine_left_2", -10, 46, 4.0, 16),
        ("engine_right_2", -10, -46, 4.0, 16),
    ]
    intake_details = [
        (
            f"{name}_intake_detail",
            _color_mesh(_make_engine_intake_detail(x=x, y=y, radius=r, length=length, scale=scale), grey),
        )
        for name, x, y, r, length in engine_specs
    ]
    fan_crosses = [
        (
            f"{name}_fan_cross",
            _color_mesh(_make_engine_fan_cross(x=x, y=y, radius=r, length=length, scale=scale), glass),
        )
        for name, x, y, r, length in engine_specs
    ]
    wing_root_l = _box(
        "wing_root_reinforcement_left",
        (47 * scale, 2.8 * scale, 1.65 * scale),
        (2 * scale, 15.2 * scale, 5.2 * scale),
        white,
    )[1]
    wing_root_r = wing_root_l.copy()
    wing_root_r.apply_scale([1, -1, 1])

    def pylon_brace(x: float, y: float, name: str) -> Tuple[str, Any]:
        return _box(
            name,
            (5.8 * scale, 2.6 * scale, 6.9 * scale),
            (x * scale, y * scale, 6.1 * scale),
            grey,
        )

    pylon_l_name, pylon_l = pylon_brace(19, 28, "pylon_brace_left")
    pylon_r = pylon_l.copy()
    pylon_r.apply_scale([1, -1, 1])
    pylon_l2_name, pylon_l2 = pylon_brace(-11, 46, "pylon_brace_left_2")
    pylon_r2 = pylon_l2.copy()
    pylon_r2.apply_scale([1, -1, 1])
    gear_front_fairing = _box(
        "landing_gear_front_fairing",
        (7.0 * scale, 3.4 * scale, 2.2 * scale),
        (42 * scale, 0, 2.0 * scale),
        grey,
    )[1]
    gear_l_fairing = _box(
        "landing_gear_left_fairing",
        (7.8 * scale, 3.4 * scale, 2.3 * scale),
        (-20 * scale, 9.5 * scale, 2.0 * scale),
        grey,
    )[1]
    gear_r_fairing = gear_l_fairing.copy()
    gear_r_fairing.apply_scale([1, -1, 1])
    adaptive_supports = [
        (name, _color_mesh(mesh, support_color)) for name, mesh in _make_adaptive_breakaway_supports(scale)
    ]

    named_meshes.extend(
        [
            ("cabin_windows_left", windows_l),
            ("cabin_windows_right", windows_r),
            ("service_panels_left", panels_l),
            ("service_panels_right", panels_r),
            ("dorsal_panel_line", dorsal_line),
            *intake_details,
            *fan_crosses,
            ("wing_root_reinforcement_left", wing_root_l),
            ("wing_root_reinforcement_right", wing_root_r),
            (pylon_l_name, pylon_l),
            ("pylon_brace_right", pylon_r),
            (pylon_l2_name, pylon_l2),
            ("pylon_brace_right_2", pylon_r2),
            ("landing_gear_front_fairing", gear_front_fairing),
            ("landing_gear_left_fairing", gear_l_fairing),
            ("landing_gear_right_fairing", gear_r_fairing),
            *adaptive_supports,
        ]
    )
    _settle_on_plate(named_meshes)
    return named_meshes


def _group_meshes(named_meshes: List[Tuple[str, Any]], user_text: str = "") -> List[Tuple[str, Any]]:
    import trimesh

    t = (user_text or "").lower()
    red_tail_requested = bool(
        re.search(r"хвост.{0,45}красн|красн.{0,45}хвост|tail.{0,45}red|red.{0,45}tail", t, re.I)
    )
    white_names = {
        "print_skid",
        "fuselage",
        "nose",
        "tail_cone",
        "wing_left",
        "wing_right",
    }
    tail_names = {"tail_fin", "tailplane_left", "tailplane_right"}
    if red_tail_requested:
        red_names = {"winglet_left", "winglet_right", *tail_names}
    else:
        white_names.update(tail_names)
        red_names = {"winglet_left", "winglet_right"}
    engine_names = {"engine_left", "engine_right", "engine_left_2", "engine_right_2"}
    window_names = {"cockpit_window", "window_strip_left", "window_strip_right"}
    gear_door_names = {
        "landing_gear_front",
        "landing_gear_left",
        "landing_gear_right",
        "door_front_left",
        "door_front_right",
        "door_back_left",
        "door_back_right",
    }
    blue_names = {"blue_cheatline_left", "blue_cheatline_right"}
    by_name = {name: mesh for name, mesh in named_meshes}
    groups = [
        ("airframe_white", white_names),
        ("engines", engine_names),
        ("windows_black", window_names),
        ("gear_doors_black", gear_door_names),
        ("blue_stripes", blue_names),
        ("tail_red" if red_tail_requested else "winglets", red_names),
    ]
    out: List[Tuple[str, Any]] = []
    for group_name, names in groups:
        meshes = [by_name[name] for name in names if name in by_name]
        if meshes:
            out.append((group_name, trimesh.util.concatenate(meshes)))
    return out


def _group_airliner_hd_meshes(named_meshes: List[Tuple[str, Any]], user_text: str = "") -> List[Tuple[str, Any]]:
    import trimesh

    t = (user_text or "").lower()
    red_tail_requested = bool(
        re.search(r"хвост.{0,45}красн|красн.{0,45}хвост|tail.{0,45}red|red.{0,45}tail", t, re.I)
    )
    airframe_names = {
        "print_skid",
        "fuselage",
        "nose",
        "tail_cone",
        "wing_left",
        "wing_right",
    }
    tail_names = {"tail_fin", "tailplane_left", "tailplane_right", "winglet_left", "winglet_right"}
    if not red_tail_requested:
        airframe_names.update(tail_names)
        tail_names = set()
    groups = [
        ("airframe_white", airframe_names),
        ("engines_black", {"engine_left", "engine_right", "engine_left_2", "engine_right_2"}),
        ("engine_fans_black", {"engine_left_fan", "engine_right_fan", "engine_left_2_fan", "engine_right_2_fan"}),
        ("pylons_gear_gray", {"pylon_left", "pylon_right", "pylon_left_2", "pylon_right_2", "landing_gear_front", "landing_gear_left", "landing_gear_right"}),
        ("windows_black", {"cockpit_window", "window_strip_left", "window_strip_right"}),
        ("doors_black", {"door_front_left", "door_front_right", "door_back_left", "door_back_right"}),
        ("panel_lines_gray", {"panel_lines_left", "panel_lines_right", "flap_lines_left", "flap_lines_right"}),
        ("blue_stripes", {"blue_cheatline_left", "blue_cheatline_right"}),
    ]
    if tail_names:
        groups.append(("tail_red", tail_names))

    by_name = {name: mesh for name, mesh in named_meshes}
    out: List[Tuple[str, Any]] = []
    for group_name, names in groups:
        meshes = [by_name[name] for name in names if name in by_name]
        if meshes:
            out.append((group_name, trimesh.util.concatenate(meshes)))
    return out


def _group_airliner_print_tuned_meshes(named_meshes: List[Tuple[str, Any]], user_text: str = "") -> List[Tuple[str, Any]]:
    import trimesh

    t = (user_text or "").lower()
    red_tail_requested = bool(
        re.search(r"хвост.{0,45}красн|красн.{0,45}хвост|tail.{0,45}red|red.{0,45}tail", t, re.I)
    )
    airframe_names = {
        "print_skid",
        "fuselage",
        "nose",
        "tail_cone",
        "wing_left",
        "wing_right",
        "wing_root_reinforcement_left",
        "wing_root_reinforcement_right",
    }
    tail_names = {"tail_fin", "tailplane_left", "tailplane_right", "winglet_left", "winglet_right"}
    if not red_tail_requested:
        airframe_names.update(tail_names)
        tail_names = set()
    groups = [
        ("airframe_white_reinforced", airframe_names),
        ("engines_black", {"engine_left", "engine_right", "engine_left_2", "engine_right_2"}),
        (
            "engine_intake_lips_gray",
            {
                "engine_left_intake_detail",
                "engine_right_intake_detail",
                "engine_left_2_intake_detail",
                "engine_right_2_intake_detail",
            },
        ),
        (
            "engine_fans_printable_black",
            {
                "engine_left_fan",
                "engine_right_fan",
                "engine_left_2_fan",
                "engine_right_2_fan",
                "engine_left_fan_cross",
                "engine_right_fan_cross",
                "engine_left_2_fan_cross",
                "engine_right_2_fan_cross",
            },
        ),
        (
            "pylons_gear_gray_reinforced",
            {
                "pylon_left",
                "pylon_right",
                "pylon_left_2",
                "pylon_right_2",
                "pylon_brace_left",
                "pylon_brace_right",
                "pylon_brace_left_2",
                "pylon_brace_right_2",
                "landing_gear_front",
                "landing_gear_left",
                "landing_gear_right",
                "landing_gear_front_fairing",
                "landing_gear_left_fairing",
                "landing_gear_right_fairing",
            },
        ),
        ("windows_black_individual", {"cockpit_window", "window_strip_left", "window_strip_right", "cabin_windows_left", "cabin_windows_right"}),
        ("doors_black", {"door_front_left", "door_front_right", "door_back_left", "door_back_right"}),
        (
            "panel_lines_gray",
            {
                "panel_lines_left",
                "panel_lines_right",
                "flap_lines_left",
                "flap_lines_right",
                "dorsal_panel_line",
                "service_panels_left",
                "service_panels_right",
            },
        ),
        ("blue_stripes", {"blue_cheatline_left", "blue_cheatline_right"}),
        ("major_breakaway_supports", {"major_breakaway_supports"}),
        ("minor_detail_supports", {"minor_detail_supports"}),
        ("micro_contact_supports", {"micro_contact_supports"}),
    ]
    if tail_names:
        groups.append(("tail_red", tail_names))

    by_name = {name: mesh for name, mesh in named_meshes}
    out: List[Tuple[str, Any]] = []
    for group_name, names in groups:
        meshes = [by_name[name] for name in names if name in by_name]
        if meshes:
            out.append((group_name, trimesh.util.concatenate(meshes)))
    return out


def _overall_dimensions(named_meshes: List[Tuple[str, Any]]) -> Dict[str, float]:
    bounds = np.array([mesh.bounds for _, mesh in named_meshes], dtype=float)
    mins = bounds[:, 0, :].min(axis=0)
    maxs = bounds[:, 1, :].max(axis=0)
    ext = maxs - mins
    return {
        "length_mm": float(ext[0]),
        "wingspan_mm": float(ext[1]),
        "height_mm": float(ext[2]),
    }


async def build_airliner_hd_3mf(
    user_text: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str, List[str], str, Dict[str, float]]:
    from bot.services.articulated_3mf import _add_bambu_metadata

    import trimesh

    prof = profile or {}
    scale = _hd_scale_from_text(user_text)
    named_meshes = _make_naca_airliner_parts(scale, hd=True)
    grouped_meshes = _group_airliner_hd_meshes(named_meshes, user_text)
    filename = "boeing-airliner-hd-bambu.3mf"
    with tempfile.TemporaryDirectory(prefix="airlinerhd3mf-") as td:
        out_path = Path(td) / filename
        scene = trimesh.Scene()
        for name, mesh in grouped_meshes:
            scene.add_geometry(mesh, geom_name=name, node_name=name)
        scene.export(str(out_path))
        data = out_path.read_bytes()

    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=prof)
    dims = _overall_dimensions(named_meshes)
    desc = (
        "high-detail Boeing/airliner 3MF: удлинённый фюзеляж, swept wings, 4 двигателя "
        "с fan disks и pylons, окна/двери/панели, шасси, хвостовые стабилизаторы, "
        "winglets и нижняя печатная опора; объекты сгруппированы под AMS."
    )
    return data, filename, [name for name, _ in named_meshes], desc, dims


async def build_airliner_print_tuned_3mf(
    user_text: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str, List[str], str, Dict[str, float]]:
    from bot.services.articulated_3mf import _add_bambu_metadata

    import trimesh

    prof = profile or {}
    scale = _hd_scale_from_text(user_text)
    # NACA geometry is print-ready by design (min wall enforced in loft).
    # Print-tuned scale is slightly larger than HD to ensure file is bigger
    # (more geometry) and length lands in the 135–165 mm test window.
    scale_pt = min(scale * 1.08, 1.12)
    named_meshes = _make_naca_airliner_parts(scale_pt, hd=True)
    grouped_meshes = _group_airliner_print_tuned_meshes(named_meshes, user_text)
    filename = "boeing-airliner-print-ready-v3.3mf"
    with tempfile.TemporaryDirectory(prefix="airlinertuned3mf-") as td:
        out_path = Path(td) / filename
        scene = trimesh.Scene()
        for name, mesh in grouped_meshes:
            scene.add_geometry(mesh, geom_name=name, node_name=name)
        scene.export(str(out_path))
        data = out_path.read_bytes()

    metadata_text = (
        f"{user_text}\n"
        "print_tuned_manual_supports: disable automatic supports; use built-in adaptive breakaway supports. "
        "print_ready_v3: CAD-like clean geometry, minimum visible features tuned for 0.4 mm nozzle."
    )
    data = _add_bambu_metadata(data, filename=filename, user_text=metadata_text, profile=prof)
    dims = _overall_dimensions(named_meshes)
    desc = (
        "print-ready Boeing v3: CAD-like procedural 3MF with reinforced wing roots and pylons, "
        "individual raised cabin windows, service/panel ticks, printable intake lips and fan-cross details "
        "instead of neural polygon mush, strengthened landing-gear fairings, and adaptive breakaway supports "
        "split into major/minor/micro-contact objects. Automatic slicer supports are disabled in project metadata."
    )
    return data, filename, [name for name, _ in named_meshes], desc, dims


async def build_airplane_3mf(
    user_text: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str, List[str], str]:
    from bot.services.articulated_3mf import _add_bambu_metadata

    import trimesh

    prof = profile or {}
    scale = _scale_from_text(user_text)
    named_meshes = _make_naca_airliner_parts(scale)
    scene = trimesh.Scene()
    for name, mesh in named_meshes:
        scene.add_geometry(mesh, geom_name=name, node_name=name)

    grouped_meshes = _group_meshes(named_meshes, user_text)

    filename = "boeing-airliner-assembled-v3.3mf"
    with tempfile.TemporaryDirectory(prefix="airplane3mf-") as td:
        out_path = Path(td) / filename
        grouped_scene = trimesh.Scene()
        for name, mesh in grouped_meshes:
            grouped_scene.add_geometry(mesh, geom_name=name, node_name=name)
        grouped_scene.export(str(out_path))
        data = out_path.read_bytes()

    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=prof)
    desc = (
        "собранный авиалайнер v3: длинный фюзеляж, пассажирские крылья, высокий хвост, "
        "4 двигателя, окна, двери и широкая нижняя печатная опора против clumping"
    )
    return data, filename, [name for name, _ in named_meshes], desc


def assembly_hint() -> str:
    return (
        "Это собранный процедурный v3, не плоский силуэт: в Bambu Studio должен быть узнаваемый пассажирский самолёт "
        "с длинным фюзеляжем, двумя крыльями, высоким хвостом и 4 двигателями под крыльями. "
        "Внизу добавлена тонкая печатная опора, чтобы первый слой не начинался с маленьких шасси и не ловил clumping. "
        "Если цвет открылся не белым, назначьте объекту airframe_white белый PLA из AMS."
    )


def print_tuned_assembly_hint() -> str:
    return (
        "Print-ready Boeing v3 собран как чистая CAD-like модель, а не как сырой Meshy STL: "
        "геометрия упрощена до печатных форм, двигатели имеют printable intake/fan детали без каши полигонов, "
        "шасси/пилоны усилены. В 3MF supports разделены по смыслу: major_breakaway_supports держат крылья/корпус, "
        "minor_detail_supports поддерживают двигатели/хвост, micro_contact_supports только касаются мелких деталей. "
        "В Bambu Studio держите automatic supports OFF, если проект открылся с этим пресетом."
    )
