"""
Mechanism / vehicle proportions learned from real downloaded reference kits.

Each profile is extracted from actual STL geometry — bounding boxes, ratios
and part roles measured from watertight meshes in `data/reference_models/`.
The bot uses these to prompt LLMs and CAD generators with realistic
dimensional constraints, instead of guessing or routing to primitives.

Source kits (Cults3D originals):
  - shock_absorber_jl_3dprint_6t305g  (JL_3DPRINT)
  - toy_pickup_truck_1mg9e65          (3DPrintingOne)
  - push_release_fidget_perinim98_1u3lszj (perinim98)
  - hydro_cylinder_dnl3986            (Russian engineering reference,
                                        D80/D70 mobile equipment cylinder)
  - pill_box_heptagonal               (pjfernandez, 28×14 mm 7-cell pill box)
  - master_box                        (pjfernandez, 42×28×10 mm teacher box)
  - hamster_cube_house                (pjfernandez, 62×16 mm hamster cube)
  - floating_photo_display            (pjfernandez, 35×23×13 mm easel)
  - small_drawer_organizer            (pjfernandez, 61×61×30 mm mini cabinet)
  - sine_cosine_stencil               (perinim98, 100×36×2.5 mm wave stencil)
  - recycle_bin                       (pjfernandez, 60×30×30 mm cylindrical bin)

All measurements are in millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PartSpec:
    role: str                # what this part is in the assembly
    extents_mm: tuple        # bounding box (W, H, D)
    volume_cc: float         # solid volume in cc
    notes: str = ""


@dataclass
class MechanismProfile:
    slug: str
    description: str
    category: str            # routes here when user asks something like this
    keywords: List[str]      # regex-ish; matched case-insensitively
    parts: Dict[str, PartSpec] = field(default_factory=dict)
    assembly_hints: List[str] = field(default_factory=list)
    proportions: Dict[str, float] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
#  Shock absorber — full mechanical assembly with spring + piston + body
# ─────────────────────────────────────────────────────────────────────────────
SHOCK_ABSORBER = MechanismProfile(
    slug="shock_absorber",
    description=(
        "Printable telescopic shock absorber. Two coaxial bodies (outer/inner) "
        "with a piston rod sliding inside, surrounded by a helical spring, "
        "closed by a top plug and locked by a thin nut."
    ),
    category="mechanism_kit",
    keywords=[
        r"амортизатор", r"shock absorber", r"shock-absorber",
        r"пружинн.{0,10}механизм", r"подвеск", r"suspension",
        r"телескоп.{0,10}механизм",
    ],
    parts={
        "outer_body": PartSpec(
            "Outer cylindrical housing (CUERPO B)",
            (40.0, 48.0, 40.0), 43.7,
            "Short, slightly oversized cylinder. ID > piston rod by ~1 mm clearance.",
        ),
        "inner_body": PartSpec(
            "Inner shaft housing (CUERPO INTERNO)",
            (40.0, 71.3, 40.0), 37.5,
            "Longer than outer body; slides freely inside.",
        ),
        "piston": PartSpec(
            "Piston rod (PISTON)",
            (20.0, 69.7, 20.0), 13.7,
            "Half the diameter of bodies. Length matches inner body so piston "
            "head emerges flush at full extension.",
        ),
        "spring": PartSpec(
            "Helical compression spring (MUELLE)",
            (55.0, 131.0, 55.0), 27.1,
            "Free length ≈ 3× compressed length. Wire diameter implied by "
            "(coil_OD - coil_ID)/2 ≈ 3 mm. Print in TPU or flat-coil PLA.",
        ),
        "top_plug": PartSpec(
            "Top cap (TAPON)",
            (40.0, 48.0, 40.0), 38.9,
            "Closes outer body; matches outer body geometry exactly.",
        ),
        "lock_nut": PartSpec(
            "Lock nut (TUEARCA)",
            (67.6, 14.0, 67.6), 20.9,
            "Wide flat hex-ish nut, ~1.7× body OD. Thin (14 mm) — needs supports.",
        ),
    },
    proportions={
        "piston_diameter_ratio": 0.50,    # piston D / body D
        "spring_free_to_body": 2.73,      # spring length / outer body length
        "nut_to_body_diameter": 1.69,
        "clearance_mm": 0.4,              # measured tolerance between sliding parts
    },
    assembly_hints=[
        "Print piston with seam-aware orientation: vertical, head down.",
        "Spring needs no supports if printed coil-axis-vertical.",
        "Test piston-fits-inner-body coupon before printing all parts.",
        "Lock nut is thin — print flat on bed with 4 walls minimum.",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Toy pickup truck — vehicle proportions, FDM-tuned
# ─────────────────────────────────────────────────────────────────────────────
TOY_PICKUP_TRUCK = MechanismProfile(
    slug="toy_pickup_truck",
    description=(
        "Printable toy pickup truck. Two main body shells (cab + bed) of "
        "matching cross-section, plus two thin chassis/wheel-plate panels."
    ),
    category="rc_vehicle",
    keywords=[
        r"пикап", r"pickup", r"toy truck", r"игрушечн.{0,12}машин",
        r"грузовичок", r"flatbed",
    ],
    parts={
        "body_main": PartSpec(
            "Cab + bed primary shell",
            (85.0, 36.0, 22.4), 25.7,
            "Length 2.4× width, height ≈ 0.62× width.",
        ),
        "body_alt": PartSpec(
            "Alternate body variant (same footprint, 2 mm taller)",
            (85.0, 36.0, 24.4), 26.8,
            "Same XY footprint, slightly taller roofline.",
        ),
        "chassis_plate": PartSpec(
            "Lower chassis / wheel mount",
            (52.1, 62.7, 7.1), 5.6,
            "Wider than the body (62.7 vs 36). Wheel arches integrated.",
        ),
        "chassis_plate_alt": PartSpec(
            "Alt chassis variant",
            (58.6, 63.3, 7.3), 5.8,
            "Slightly larger footprint; lower stance.",
        ),
    },
    proportions={
        "length_to_width": 2.36,
        "height_to_width": 0.62,
        "chassis_overhang": 1.74,         # chassis Y / body Y
        "chassis_thickness_ratio": 0.32,  # chassis Z / body Z
    },
    assembly_hints=[
        "Cab/bed and chassis are separate prints — glue or pin together.",
        "Body shells fit on the chassis with 0.25 mm clearance per edge.",
        "Print body roof-up on bed; chassis flat side down.",
        "Use 3-wall, 25% infill for FDM strength on cab corners.",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Push-release fidget — click-snap mechanism
# ─────────────────────────────────────────────────────────────────────────────
PUSH_RELEASE_FIDGET = MechanismProfile(
    slug="push_release_fidget",
    description=(
        "Print-in-place click-snap fidget. Square base (50×50×40 mm) holds a "
        "spring-tab mechanism; press-fit top cap engages and releases with audible click."
    ),
    category="articulated_fidget",
    keywords=[
        r"fidget", r"фиджет", r"антистресс", r"antistress",
        r"клик.{0,10}механизм", r"click[-\s]?release",
        r"push.{0,10}release",
    ],
    parts={
        "base": PartSpec(
            "Square base with snap mechanism",
            (50.0, 50.0, 39.7), 39.0,
            "Internal cam path; needs 0.4 mm nozzle and 0.2 mm layer for clicks.",
        ),
        "top_cap": PartSpec(
            "Press-fit top cap",
            (50.0, 50.0, 25.0), 21.4,
            "Snap tabs on the underside; cap height ≈ 0.63× base height.",
        ),
        "themed_top": PartSpec(
            "Themed alternate top (Death Star variant)",
            (50.0, 50.0, 25.0), 20.6,
            "Same snap geometry as default top; outer surface decorative.",
        ),
    },
    proportions={
        "base_to_cap_height": 1.59,
        "cap_overhang_mm": 0.0,           # caps flush with base
        "snap_engagement_mm": 0.4,
    },
    assembly_hints=[
        "Print both halves in same orientation (cap-down) so snap geometry "
        "comes out crisp.",
        "Click tactility comes from a 0.4 mm engagement step in the cam path — "
        "do not over-tolerance.",
        "If clicks are mushy: dry filament, slow inner walls to 30 mm/s, and "
        "verify the cam-path layer lines are not delaminated.",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Hydraulic cylinder D80/D70 — industrial double-acting cylinder
#  Source: Russian engineering reference assembly (Гидроцилиндр dnl3986),
#  full 20-part STEP assembly with measured dimensions and named seal stack.
# ─────────────────────────────────────────────────────────────────────────────
HYDRAULIC_CYLINDER = MechanismProfile(
    slug="hydraulic_cylinder",
    description=(
        "Industrial double-acting hydraulic cylinder, D80 bore × D70 rod, "
        "~600 mm stroke. Welded barrel with rear clevis, chromed rod with "
        "front clevis, full seal/wiper stack (KPD piston seal, A70/80 rod "
        "seal, SAG 70 wiper, FE 80 guide rings). Mobile-equipment scale "
        "(loader / excavator outrigger / press)."
    ),
    category="hydraulic_actuator",
    keywords=[
        r"гидроцилиндр", r"hydraulic cylinder", r"hydraulic[-\s]?cylinder",
        r"гидро.{0,6}привод", r"hydraulic ram", r"гидравлич.{0,12}цилиндр",
        r"hydraulic actuator", r"шток.{0,15}поршн",
    ],
    parts={
        "barrel": PartSpec(
            "Cylinder barrel (gun-drilled tube)",
            (95.0, 95.0, 645.0), 0.0,
            "Outer Ø95, bore Ø80 (1.19× ID), length 645. Welded rear clevis.",
        ),
        "rod": PartSpec(
            "Piston rod (hard-chromed shaft)",
            (70.0, 70.0, 670.0), 0.0,
            "Rod Ø70 = 0.875× piston diameter. Length 670 (≈ barrel + clevis).",
        ),
        "piston_head": PartSpec(
            "Piston head with seal groove",
            (78.4, 78.4, 32.0), 0.0,
            "Piston OD 78.4 (0.4 mm clearance to bore). Carries KPD 80 piston "
            "seal in central groove and FE 80 guide ring at front shoulder.",
        ),
        "gland_bushing": PartSpec(
            "Front gland bushing (стат. уплотнение грундбуксы)",
            (110.0, 110.0, 70.0), 0.0,
            "Flanged bushing Ø110 × 70 — retains rod seals and houses wiper.",
        ),
        "rear_clevis": PartSpec(
            "Rear mounting clevis (проушина стенки)",
            (130.0, 181.0, 130.0), 0.0,
            "Forged or welded clevis, eye height 181 mm. Eye thickness ~60 mm.",
        ),
        "front_clevis": PartSpec(
            "Front rod-end clevis (проушина вала)",
            (112.0, 186.0, 62.0), 0.0,
            "Threaded onto rod end. Eye axis perpendicular to rear clevis.",
        ),
        "rod_seal": PartSpec(
            "Rod seal A70 80 7",
            (80.0, 80.0, 8.0), 0.0,
            "Standard rod-seal designation: shaft Ø70, housing Ø80, 7 mm wide.",
        ),
        "piston_seal": PartSpec(
            "Piston seal KPD 80 69 4.2b",
            (80.0, 80.0, 4.2), 0.0,
            "Bore Ø80, groove ID Ø69, 4.2 mm thick. PTFE-energised type.",
        ),
        "wiper": PartSpec(
            "Wiper SAG 70",
            (78.0, 78.0, 4.0), 0.0,
            "Dust scraper at gland external face. Shaft Ø70 nominal.",
        ),
        "guide_ring": PartSpec(
            "Guide ring FE 80",
            (80.0, 80.0, 12.8), 0.0,
            "Bronze/PTFE-filled phenolic ring. Bore Ø80, 12.8 mm wide.",
        ),
        "lock_nut": PartSpec(
            "Lock nut ГОСТ 5915-70",
            (46.0, 53.0, 25.6), 0.0,
            "Hex nut, across-flats 46 (≈ M30). Retains front clevis on rod.",
        ),
    },
    proportions={
        "barrel_OD_over_ID": 1.19,
        "rod_over_piston_diameter": 0.875,
        "stroke_over_rod_diameter": 8.6,
        "rod_length_over_barrel_length": 1.04,
        "clevis_eye_over_rod_diameter": 1.6,
        "piston_clearance_mm": 0.4,
        "rod_clearance_mm": 0.5,
    },
    assembly_hints=[
        "Architecture along the axis: rear clevis → barrel → guide ring → "
        "piston (KPD seal) → guide ring → rod → gland bushing (FE 80 + "
        "A70/80 seal + SAG 70 wiper) → lock nut → front clevis.",
        "Two clevis eyes are mutually perpendicular: rear pin is horizontal "
        "(load-bearing pivot), front pin is vertical or aligned with load.",
        "For FDM downscaled prints: hold the 1.19× barrel OD/ID ratio so the "
        "cylinder still looks 'thick-walled and machined', not toy-like.",
        "If user asks for 'a 3D-printable hydraulic ram', use Ø70 rod / Ø80 "
        "bore / 600 mm stroke as the canonical proportional reference; only "
        "scale all dimensions uniformly, do not change ratios.",
        "Seal stack should always be three rings (wiper + rod seal + guide), "
        "not one — even on stylised prints this matters for realism.",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Small desk-scale storage container (pill box / drawer / bin / cube house)
#  Aggregated from 6 measured kits — common geometry:
#    * 28–62 mm footprint, 5–30 mm height
#    * thin walls (2.0–2.4 mm typical)
#    * watertight when designed as box (open-top), non-watertight if it's a
#      decorative shell
#    * print orientation: open face up, flat side down
# ─────────────────────────────────────────────────────────────────────────────
SMALL_STORAGE_CONTAINER = MechanismProfile(
    slug="small_storage_container",
    description=(
        "Desk-scale 3D-printable storage container: pill boxes, drawer "
        "organizers, decorative cube houses, recycle bins, small cabinets. "
        "Footprint 30–70 mm, height 5–60 mm, walls 2–2.4 mm. Almost always "
        "single-print, no assembly. Prints flat-side-down with no supports."
    ),
    category="organizer_box",
    keywords=[
        r"коробк", r"box", r"organizer", r"органайзер", r"таблетниц",
        r"pill[-\s]?box", r"корзин", r"ведерк", r"bin", r"подставк",
        r"стенд", r"хомяч", r"drawer", r"комод", r"шкатулк",
        r"контейнер", r"кейс", r"кубик", r"easel", r"display",
    ],
    parts={
        "pill_box": PartSpec(
            "Heptagonal 7-cell pill box",
            (28.7, 14.6, 5.5), 0.5,
            "Flat, very thin (5.5 mm). Print without supports, lid sold separately.",
        ),
        "teacher_box": PartSpec(
            "Master / teacher box",
            (42.1, 28.1, 10.4), 4.0,
            "Open-top tray, walls ~2.2 mm.",
        ),
        "cube_house": PartSpec(
            "Hamster cube house / decorative shell",
            (62.5, 16.1, 16.1), 8.0,
            "Closed-shell decorative element with print-in-place hinges.",
        ),
        "photo_easel": PartSpec(
            "Floating photo display / easel",
            (34.9, 22.6, 13.2), 5.5,
            "Slot for photo + freestanding base.",
        ),
        "mini_cabinet": PartSpec(
            "Mini drawer cabinet (two-drawer)",
            (61.0, 61.2, 30.2), 35.0,
            "61×61 footprint with 2 stacked drawers; print drawers separately.",
        ),
        "cylindrical_bin": PartSpec(
            "Tall cylindrical recycle bin",
            (60.7, 29.9, 30.0), 8.5,
            "Tall thin cylinder with 2.0 mm walls; print upright on bed.",
        ),
    },
    proportions={
        "wall_thickness_mm": 2.2,
        "footprint_to_height_min": 1.0,
        "footprint_to_height_max": 5.2,
        "typical_layer_height_mm": 0.2,
        "minimum_first_layer_walls": 3,
    },
    assembly_hints=[
        "Walls 2.0–2.4 mm — at least 3 perimeters for FDM strength.",
        "Print flat-side-down; opening upward for clean inside floor.",
        "For decorative cube/house shells, allow 0.4 mm clearance on snap "
        "joints, otherwise lid won't slide.",
        "Avoid sub-1 mm overhang fins inside cells — they curl.",
        "Drawer cabinets: print body and drawers separately, 0.3 mm gap each side.",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Thin flat stencil / line-art plate
# ─────────────────────────────────────────────────────────────────────────────
THIN_STENCIL = MechanismProfile(
    slug="thin_stencil",
    description=(
        "Flat 2.5 mm stencil/plate with cut-out shapes. Long-narrow format "
        "(2–3× aspect). Used as drawing template, signage, or decorative "
        "overlay. Watertight by construction."
    ),
    category="stencil_plate",
    keywords=[
        r"стенсил", r"stencil", r"трафарет", r"шаблон.{0,15}рисов",
        r"sine[-\s]?cosine", r"плоск.{0,8}пластин", r"name[-\s]?plate",
        r"signage", r"plate.{0,10}cut[-\s]?out",
    ],
    parts={
        "final_template": PartSpec(
            "Finished stencil",
            (100.0, 36.0, 2.5), 6.0,
            "Long thin plate, 100 × 36 × 2.5 mm. Cut-outs designed for "
            "0.4 mm nozzle — minimum slit width 0.8 mm.",
        ),
        "demo_card": PartSpec(
            "Demo / sample card",
            (53.3, 35.3, 2.5), 3.8,
            "Shorter variant with same thickness/cut-out logic.",
        ),
    },
    proportions={
        "thickness_mm": 2.5,
        "min_slit_width_mm": 0.8,
        "min_bridge_width_mm": 1.5,
        "aspect_long_to_short": 2.78,
    },
    assembly_hints=[
        "Print flat on bed, no supports — single object, no assembly.",
        "Minimum cut-out width 0.8 mm (2× nozzle); below this, slits fuse.",
        "Use 3 perimeters and 4 top/bottom layers to keep plate rigid.",
        "If user asks for a name plate or sign, default to ~2.5 mm thick.",
    ],
)


# Master registry
MECHANISM_PROFILES: Dict[str, MechanismProfile] = {
    p.slug: p
    for p in (
        SHOCK_ABSORBER,
        TOY_PICKUP_TRUCK,
        PUSH_RELEASE_FIDGET,
        HYDRAULIC_CYLINDER,
        SMALL_STORAGE_CONTAINER,
        THIN_STENCIL,
    )
}


def find_mechanism_profile(text: str) -> MechanismProfile | None:
    """Return the first profile whose keyword regex matches the user text."""
    import re

    t = (text or "").lower()
    for prof in MECHANISM_PROFILES.values():
        for kw in prof.keywords:
            if re.search(kw, t, re.I):
                return prof
    return None


def llm_context_for(profile: MechanismProfile) -> str:
    """Compact human-readable summary for LLM system/user prompts."""
    lines: List[str] = [
        f"REFERENCE KIT: {profile.slug}",
        f"  {profile.description}",
        "  Parts (measured from real CAD):",
    ]
    for pid, p in profile.parts.items():
        w, h, d = p.extents_mm
        lines.append(f"    - {pid}: {w:.0f}×{h:.0f}×{d:.0f} mm, V={p.volume_cc:.1f} cc — {p.role}")
        if p.notes:
            lines.append(f"        note: {p.notes}")
    if profile.proportions:
        lines.append("  Key proportions:")
        for k, v in profile.proportions.items():
            lines.append(f"    - {k}: {v}")
    if profile.assembly_hints:
        lines.append("  Assembly / print hints:")
        for h in profile.assembly_hints:
            lines.append(f"    • {h}")
    return "\n".join(lines)
