"""Артикулированная фигурка → один 3MF для Bambu Studio (несколько деталей на столе)."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import numpy as np

from bot.services.openscad import export_stl_from_scad, openscad_available
from bot.services.stl_postprocess import target_height_mm_from_text

logger = logging.getLogger(__name__)

_CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

_ARTICULATED = re.compile(
    r"шевел|подвиж|шарнир|articul|movable|moving|поворотн",
    re.IGNORECASE,
)

_SCAD_JOINTS = """
gap = {gap:.2f};
br = {ball_r:.2f};
$fn = 48;

module ball(r=br) {{
  sphere(r=r);
}}

module socket_cavity(r=br, g=gap) {{
  difference() {{
    sphere(r=r + 2.8);
    sphere(r=r + g);
    translate([0, 0, r + 1]) cube([40, 40, 40], center=true);
  }}
}}

s = {scale:.4f};
"""

# --- Четвероногий шаблон (собака / кот) ---
_SCAD_QUADRUPED = (
    _SCAD_JOINTS
    + """
module dog_torso() {{
  union() {{
    difference() {{
      hull() {{
        translate([0, 0, 14 * s]) scale([1.1, 0.85, 0.75]) sphere(r=16 * s);
        translate([18 * s, 0, 22 * s]) scale([1.0, 0.9, 0.85]) sphere(r=13 * s);
        translate([-10 * s, 0, 8 * s]) scale([0.9, 0.8, 0.6]) sphere(r=11 * s);
      }}
      translate([12 * s,  10 * s, 6 * s]) rotate([25, 0, -15]) socket_cavity();
      translate([12 * s, -10 * s, 6 * s]) rotate([25, 0,  15]) socket_cavity();
      translate([-8 * s,  9 * s, 5 * s]) rotate([-20, 0, -10]) socket_cavity();
      translate([-8 * s, -9 * s, 5 * s]) rotate([-20, 0,  10]) socket_cavity();
      translate([22 * s, 0, 24 * s]) rotate([35, 0, 0]) socket_cavity();
      translate([-18 * s, 0, 12 * s]) rotate([-35, 0, 0]) socket_cavity();
    }}
    translate([20 * s, -7 * s, 28 * s]) rotate([10, 0, 20]) scale([0.35, 0.15, 0.9]) sphere(r=8 * s);
    translate([20 * s,  7 * s, 28 * s]) rotate([10, 0, -20]) scale([0.35, 0.15, 0.9]) sphere(r=8 * s);
  }}
}}

module dog_head() {{
  union() {{
    hull() {{
      translate([0, 0, 10 * s]) sphere(r=11 * s);
      translate([9 * s, 0, 7 * s]) scale([1.3, 0.75, 0.8]) sphere(r=7 * s);
    }}
    translate([0, 0, -br]) ball();
    translate([14 * s, 0, 6 * s]) scale([1, 0.8, 0.7]) sphere(r=3.5 * s);
  }}
}}

module dog_leg() {{ union() {{
  translate([0, 0, br]) cylinder(h=26 * s, r1=5.5 * s, r2=4 * s);
  translate([0, 0, 26 * s + br]) cylinder(h=8 * s, r=3.2 * s);
  ball();
}} }}

module dog_tail() {{ union() {{
  translate([0, 0, br]) rotate([30, 0, 0]) cylinder(h=24 * s, r1=3.5 * s, r2=2 * s);
  ball();
}} }}

module dog_eye() {{ sphere(r=2.2 * s); }}
"""
)

_QUADRUPED_PARTS = {
    "body": "dog_torso();",
    "head": "dog_head();",
    "leg": "dog_leg();",
    "tail": "dog_tail();",
    "eye": "dog_eye();",
}

_QUADRUPED_SPECS: List[Tuple[str, str]] = [
    ("body", "body"),
    ("head", "head"),
    ("leg_front_left", "leg"),
    ("leg_front_right", "leg"),
    ("leg_back_left", "leg"),
    ("leg_back_right", "leg"),
    ("tail", "tail"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

# --- Ангел: тело, голова, 2 крыла, 2 глаза ---
_SCAD_ANGEL = (
    _SCAD_JOINTS
    + """
module angel_torso() {{
  union() {{
    difference() {{
      union() {{
        translate([0, 0, 18 * s]) scale([0.85, 0.55, 1.0]) cylinder(h=32 * s, r=13 * s);
        translate([0, 0, 48 * s]) scale([1.1, 0.45, 0.55]) sphere(r=11 * s);
        translate([0, 0, 8 * s]) scale([1.2, 0.9, 0.35]) cylinder(h=6 * s, r=11 * s);
      }}
      translate([14 * s, 0, 44 * s]) rotate([0, -32, 0]) socket_cavity();
      translate([-14 * s, 0, 44 * s]) rotate([0, 32, 0]) socket_cavity();
      translate([0, 0, 52 * s]) rotate([28, 0, 0]) socket_cavity();
    }}
  }}
}}

module angel_head() {{
  union() {{
    hull() {{
      translate([0, 0, 8 * s]) sphere(r=9 * s);
      translate([0, 0, 16 * s]) scale([0.9, 0.85, 1]) sphere(r=7 * s);
    }}
    translate([0, 0, -br]) ball();
  }}
}}

module angel_wing() {{
  union() {{
    ball();
    translate([0, 0, br]) hull() {{
      translate([4 * s, 0, 2 * s]) scale([0.5, 0.12, 1.4]) sphere(r=10 * s);
      translate([22 * s, 0, 8 * s]) scale([1.2, 0.08, 1.0]) sphere(r=11 * s);
      translate([38 * s, 2 * s, 4 * s]) scale([0.9, 0.06, 0.7]) sphere(r=8 * s);
    }}
  }}
}}

module angel_eye() {{ sphere(r=2.4 * s); }}
"""
)

_ANGEL_PARTS = {
    "body": "angel_torso();",
    "head": "angel_head();",
    "wing": "angel_wing();",
    "eye": "angel_eye();",
}

_ANGEL_SPECS: List[Tuple[str, str]] = [
    ("body", "body"),
    ("head", "head"),
    ("wing_left", "wing"),
    ("wing_right", "wing"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

# --- Авторский процедурный шаблон: когда точного шаблона нет, но можно сделать честный v0 ---
_SCAD_CUSTOM = (
    _SCAD_JOINTS
    + """
module winged_body() {{
  union() {{
    difference() {{
      hull() {{
        translate([0, 0, 16 * s]) scale([0.9, 0.65, 1.0]) sphere(r=16 * s);
        translate([0, 0, 40 * s]) scale([0.65, 0.45, 0.9]) sphere(r=12 * s);
      }}
      translate([15 * s, 0, 34 * s]) rotate([0, -30, 0]) socket_cavity();
      translate([-15 * s, 0, 34 * s]) rotate([0, 30, 0]) socket_cavity();
      translate([0, 0, 50 * s]) rotate([25, 0, 0]) socket_cavity();
      translate([0, -13 * s, 16 * s]) rotate([-35, 0, 0]) socket_cavity();
    }}
  }}
}}

module humanoid_body() {{
  union() {{
    difference() {{
      hull() {{
        translate([0, 0, 16 * s]) scale([0.85, 0.6, 1.0]) sphere(r=16 * s);
        translate([0, 0, 40 * s]) scale([0.65, 0.5, 0.75]) sphere(r=12 * s);
      }}
      translate([15 * s, 0, 34 * s]) rotate([0, -35, 0]) socket_cavity();
      translate([-15 * s, 0, 34 * s]) rotate([0, 35, 0]) socket_cavity();
      translate([7 * s, 0, 5 * s]) rotate([30, 0, 0]) socket_cavity();
      translate([-7 * s, 0, 5 * s]) rotate([30, 0, 0]) socket_cavity();
      translate([0, 0, 50 * s]) rotate([25, 0, 0]) socket_cavity();
    }}
  }}
}}

module custom_head() {{
  union() {{
    translate([0, 0, -br]) ball();
    translate([0, 0, 9 * s]) sphere(r=10 * s);
    translate([-7 * s, 0, 18 * s]) scale([0.45, 0.18, 0.8]) sphere(r=8 * s);
    translate([7 * s, 0, 18 * s]) scale([0.45, 0.18, 0.8]) sphere(r=8 * s);
  }}
}}

module custom_wing() {{
  union() {{
    ball();
    translate([0, 0, br]) hull() {{
      translate([4 * s, 0, 2 * s]) scale([0.45, 0.10, 1.1]) sphere(r=10 * s);
      translate([24 * s, 0, 8 * s]) scale([1.35, 0.07, 0.9]) sphere(r=11 * s);
      translate([43 * s, 2 * s, 2 * s]) scale([0.95, 0.05, 0.55]) sphere(r=8 * s);
    }}
  }}
}}

module custom_arm() {{
  union() {{
    ball();
    translate([0, 0, br]) cylinder(h=24 * s, r1=4.8 * s, r2=3.4 * s);
    translate([0, 0, 24 * s + br]) sphere(r=4.2 * s);
  }}
}}

module custom_leg() {{
  union() {{
    ball();
    translate([0, 0, br]) cylinder(h=22 * s, r1=5.5 * s, r2=4.5 * s);
    translate([2 * s, 0, 22 * s + br]) scale([1.4, 0.9, 0.45]) sphere(r=5 * s);
  }}
}}

module custom_tail() {{
  union() {{
    ball();
    translate([0, 0, br]) rotate([25, 0, 0]) cylinder(h=34 * s, r1=4.5 * s, r2=1.8 * s);
  }}
}}

module custom_eye() {{ sphere(r=2.3 * s); }}
"""
)

_CUSTOM_PARTS = {
    "winged_body": "winged_body();",
    "humanoid_body": "humanoid_body();",
    "head": "custom_head();",
    "wing": "custom_wing();",
    "arm": "custom_arm();",
    "leg": "custom_leg();",
    "tail": "custom_tail();",
    "eye": "custom_eye();",
}

_DRAGON_SPECS: List[Tuple[str, str]] = [
    ("body", "winged_body"),
    ("head", "head"),
    ("wing_left", "wing"),
    ("wing_right", "wing"),
    ("leg_left", "leg"),
    ("leg_right", "leg"),
    ("tail", "tail"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

_BAT_SPECS: List[Tuple[str, str]] = [
    ("body", "winged_body"),
    ("head", "head"),
    ("wing_left", "wing"),
    ("wing_right", "wing"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

_CHEBURASHKA_SPECS: List[Tuple[str, str]] = [
    ("body", "humanoid_body"),
    ("head", "head"),
    ("arm_left", "arm"),
    ("arm_right", "arm"),
    ("leg_left", "leg"),
    ("leg_right", "leg"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

_GENERIC_WINGED_SPECS: List[Tuple[str, str]] = [
    ("body", "winged_body"),
    ("head", "head"),
    ("wing_left", "wing"),
    ("wing_right", "wing"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

_GENERIC_HUMANOID_SPECS: List[Tuple[str, str]] = [
    ("body", "humanoid_body"),
    ("head", "head"),
    ("arm_left", "arm"),
    ("arm_right", "arm"),
    ("leg_left", "leg"),
    ("leg_right", "leg"),
    ("eye_left", "eye"),
    ("eye_right", "eye"),
]

# AMS: имя объекта → RGB (подсказка в Bambu Studio)
_PART_COLORS: Dict[str, Tuple[int, int, int]] = {
    "body": (245, 245, 245),
    "head": (245, 245, 245),
    "wing_left": (30, 30, 30),
    "wing_right": (30, 30, 30),
    "eye_left": (220, 40, 40),
    "eye_right": (220, 40, 40),
}


def openscad_articulated_kind(user_text: str) -> Optional[str]:
    """Какой OpenSCAD-шаблон подходит; None — не наш шаблон (уйдёт в Meshy)."""
    t = user_text or ""
    if re.search(r"ангел|angel", t, re.I):
        return "angel"
    if re.search(r"дракон|dragon", t, re.I):
        return "dragon"
    if re.search(r"летуч.{0,10}мыш|bat\b", t, re.I):
        return "bat"
    if re.search(r"чебурашк", t, re.I):
        return "cheburashka"
    if re.search(r"лабрадор|labrador|собак|dog|retriever|кот|cat", t, re.I):
        return "quadruped"
    if articulation_requested(t) and re.search(r"крыл|wing", t, re.I):
        return "generic_winged"
    if articulation_requested(t) and re.search(r"рук|arm|ног|leg", t, re.I):
        return "generic_humanoid"
    if articulation_requested(t):
        return "generic_humanoid"
    return None


def articulation_requested(user_text: str) -> bool:
    return bool(_ARTICULATED.search(user_text or ""))


def openscad_articulated_supported(user_text: str) -> bool:
    return articulation_requested(user_text) and openscad_articulated_kind(user_text) is not None


def requested_subject_label(user_text: str) -> str:
    t = user_text or ""
    for pattern, label in (
        (r"ангел|angel", "ангел"),
        (r"дракон|dragon", "дракон"),
        (r"летуч.{0,10}мыш|bat\b", "летучая мышь"),
        (r"чебурашк", "чебурашка"),
        (r"монстр|monster", "монстр"),
        (r"лабрадор|labrador", "лабрадор"),
        (r"собак|dog|retriever", "собака"),
        (r"кот|cat", "кот"),
    ):
        if re.search(pattern, t, re.I):
            return label
    m = re.search(r"(?:фигурк[аи]|статуэтк[аи]|персонаж)\s+([^\.\n,]{2,50})", t, re.I)
    if m:
        return m.group(1).strip()
    return "фигурка"


def expected_part_names_for_text(user_text: str) -> List[str]:
    kind = openscad_articulated_kind(user_text)
    if kind == "angel":
        return [name for name, _ in _ANGEL_SPECS]
    if kind == "quadruped":
        return [name for name, _ in _QUADRUPED_SPECS]
    if kind == "dragon":
        return [name for name, _ in _DRAGON_SPECS]
    if kind == "bat":
        return [name for name, _ in _BAT_SPECS]
    if kind == "cheburashka":
        return [name for name, _ in _CHEBURASHKA_SPECS]
    if kind == "generic_winged":
        return [name for name, _ in _GENERIC_WINGED_SPECS]
    if kind == "generic_humanoid":
        return [name for name, _ in _GENERIC_HUMANOID_SPECS]
    return []


def forbidden_part_names_for_text(user_text: str) -> List[str]:
    kind = openscad_articulated_kind(user_text)
    if kind == "angel":
        return ["leg_front_left", "leg_front_right", "leg_back_left", "leg_back_right", "tail"]
    if kind == "quadruped":
        return ["wing_left", "wing_right"]
    if kind in ("dragon",):
        return ["leg_front_left", "leg_front_right", "leg_back_left", "leg_back_right"]
    if kind in ("bat", "generic_winged"):
        return ["tail", "leg_front_left", "leg_front_right", "leg_back_left", "leg_back_right"]
    if kind in ("cheburashka", "generic_humanoid"):
        return ["wing_left", "wing_right", "tail", "leg_front_left"]
    return ["body", "head", "wing_left", "wing_right", "tail", "leg_front_left"]


def _subject_slug(user_text: str) -> str:
    kind = openscad_articulated_kind(user_text)
    if kind == "angel":
        return "angel"
    if kind == "dragon":
        return "dragon"
    if kind == "bat":
        return "bat"
    if kind == "cheburashka":
        return "cheburashka"
    if kind == "generic_winged":
        return "winged-figurine"
    if kind == "generic_humanoid":
        return "articulated-character"
    if re.search(r"лабрадор|labrador", user_text or "", re.I):
        return "labrador"
    if re.search(r"собак|dog|retriever", user_text or "", re.I):
        return "dog"
    if re.search(r"кот|cat", user_text or "", re.I):
        return "cat"
    return "figurine"


def parts_description(kind: str) -> str:
    if kind == "angel":
        return "тело, голова, 2 крыла (шарнир), 2 глаза"
    if kind == "dragon":
        return "тело, голова, 2 крыла (шарнир), 2 ноги, хвост, 2 глаза"
    if kind == "bat":
        return "тело, голова, 2 крыла (шарнир), 2 глаза"
    if kind == "cheburashka":
        return "тело, голова с ушами, 2 руки (шарнир), 2 ноги, 2 глаза"
    if kind == "generic_winged":
        return "процедурный v0: тело, голова, 2 крыла (шарнир), 2 глаза"
    if kind == "generic_humanoid":
        return "процедурный v0: тело, голова, 2 руки, 2 ноги, 2 глаза"
    return "тело, голова, 4 лапы, хвост, 2 глаза"


def _scale_from_text(user_text: str) -> float:
    target_h = target_height_mm_from_text(user_text or "")
    kind = openscad_articulated_kind(user_text)
    base = 120.0 if kind in ("angel", "dragon", "bat", "generic_winged") else 110.0
    return max(0.65, min(1.35, target_h / base))


def _gap_for_nozzle(nozzle_mm: float) -> Tuple[float, float]:
    if nozzle_mm <= 0.25:
        return 0.18, 3.2
    if nozzle_mm >= 0.6:
        return 0.45, 4.5
    return 0.30, 3.8


def _scad_for_part(
    kind: str,
    part: str,
    *,
    scale: float,
    gap: float,
    ball_r: float,
) -> bytes:
    if kind == "angel":
        lib = _SCAD_ANGEL
        calls = _ANGEL_PARTS
    elif kind in ("dragon", "bat", "cheburashka", "generic_winged", "generic_humanoid"):
        lib = _SCAD_CUSTOM
        calls = _CUSTOM_PARTS
    else:
        lib = _SCAD_QUADRUPED
        calls = _QUADRUPED_PARTS
    header = lib.format(scale=scale, gap=gap, ball_r=ball_r)
    call = calls.get(part)
    if not call:
        raise ValueError(f"unknown part: {part}")
    return (header + "\n" + call + "\n").encode("utf-8")


def _mesh_on_bed(mesh: "trimesh.Trimesh") -> "trimesh.Trimesh":
    m = mesh.copy()
    z0 = float(m.bounds[0][2])
    m.apply_translation([0, 0, -z0])
    return m


def _apply_part_color(mesh: Any, obj_name: str) -> None:
    import trimesh

    rgb = _PART_COLORS.get(obj_name)
    if not rgb or not hasattr(mesh, "visual"):
        return
    n = len(mesh.vertices)
    if n == 0:
        return
    rgba = np.tile([rgb[0], rgb[1], rgb[2], 255], (n, 1))
    mesh.visual.vertex_colors = rgba.astype(np.uint8)


def _layout_scene(
    named_meshes: List[Tuple[str, Any]],
    *,
    margin: float = 12.0,
    bed_w: float = 250.0,
) -> "trimesh.Scene":
    import trimesh

    scene = trimesh.Scene()
    x = margin
    y = margin
    row_h = 0.0

    for name, mesh in named_meshes:
        mesh = _mesh_on_bed(mesh)
        _apply_part_color(mesh, name)
        size = mesh.bounds[1] - mesh.bounds[0]
        w, d = float(size[0]), float(size[1])
        if x + w > bed_w - margin and x > margin:
            x = margin
            y += row_h + margin
            row_h = 0.0
        T = np.eye(4)
        T[0, 3] = x - float(mesh.bounds[0][0])
        T[1, 3] = y - float(mesh.bounds[0][1])
        mesh.metadata["name"] = name
        scene.add_geometry(mesh, transform=T, node_name=name, geom_name=name)
        x += w + margin
        row_h = max(row_h, d)

    return scene


def _printer_model_for_bambu(profile: Dict[str, Any]) -> str:
    raw = (profile.get("printer") or "Bambu Lab P1S").lower()
    if "p2s" in raw:
        return "Bambu Lab P2S"
    if "x1" in raw:
        return "Bambu Lab X1 Carbon"
    if "a1" in raw:
        return "Bambu Lab A1"
    if "p1" in raw:
        return "Bambu Lab P1S"
    if "bambu" in raw:
        return "Bambu Lab P1S"
    return profile.get("printer") or "Bambu Lab P1S"


_COLOR_HEX = {
    "white": "#FFFFFFFF",
    "black": "#161616FF",
    "red": "#C12E1FFF",
    "green": "#00A651FF",
    "blue": "#0A4DFFFF",
    "brown": "#7A4B2AFF",
    "yellow": "#FFD23FFF",
    "orange": "#FF8A00FF",
    "gray": "#8A8A8AFF",
}


def _filament_palette(user_text: str, profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    from bot.services.bambu_hints import color_words_from_text

    t = (user_text or "").lower()
    colors: List[str] = []

    def add(color: str) -> None:
        hexc = _COLOR_HEX[color]
        if hexc not in colors:
            colors.append(hexc)

    is_aircraft = bool(re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", t))
    if is_aircraft or re.search(r"бел|white", t):
        add("white")
    if is_aircraft or re.search(r"ч[её]рн|black", t):
        add("black")
    for color in color_words_from_text(user_text):
        add(color)
    if not colors:
        add("white")
    mat = (profile.get("material") or "PLA").upper()
    return [mat for _ in colors], colors


def _color_index(colors: List[str], color: str) -> int:
    hexc = _COLOR_HEX[color]
    if hexc not in colors:
        colors.append(hexc)
    return colors.index(hexc) + 1


def _object_extruder_map(
    objects: List[Dict[str, Any]],
    user_text: str,
    colors: List[str],
) -> Dict[str, int]:
    """Bambu object-level color assignment. Slots are 1-based."""
    from bot.services.bambu_hints import color_for_object_name, part_color_from_text

    t = (user_text or "").lower()
    is_aircraft = bool(re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", t))
    default = _color_index(colors, "white") if (is_aircraft or re.search(r"бел|white", t)) else 1
    black = _color_index(colors, "black") if (is_aircraft or re.search(r"ч[её]рн|black", t)) else default
    red = _color_index(colors, "red") if re.search(r"красн|red", t) else default
    blue = _color_index(colors, "blue") if re.search(r"син|голуб|blue", t) else default
    brown = _color_index(colors, "brown") if re.search(r"коричн|brown", t) else default
    gray = _color_index(colors, "gray") if re.search(r"сер|gray|grey|silver", t) else default

    def color_slot(color: Optional[str]) -> Optional[int]:
        if color in _COLOR_HEX:
            return _color_index(colors, color)
        return None

    mapping: Dict[str, int] = {}
    for obj in objects:
        name = str(obj["name"])
        low = name.lower()
        slot = default
        requested_slot: Optional[int] = None
        if re.search(r"red|красн", low):
            slot = _color_index(colors, "red")
        elif re.search(r"black|ч[её]рн", low):
            slot = _color_index(colors, "black")
        elif re.search(r"white|бел", low):
            slot = _color_index(colors, "white")
        elif re.search(r"blue|син|голуб", low):
            slot = _color_index(colors, "blue")
        elif re.search(r"green|зел[её]н", low):
            slot = _color_index(colors, "green")
        elif re.search(r"brown|коричн", low):
            slot = _color_index(colors, "brown")
        elif re.search(r"yellow|ж[её]лт", low):
            slot = _color_index(colors, "yellow")
        elif re.search(r"orange|оранж", low):
            slot = _color_index(colors, "orange")
        elif re.search(r"gray|grey|silver|сер", low):
            slot = _color_index(colors, "gray")
        else:
            requested_slot = color_slot(color_for_object_name(user_text, name))
            if requested_slot:
                slot = requested_slot
        if requested_slot:
            mapping[str(obj["id"])] = slot
            continue
        if is_aircraft:
            if low.startswith("airframe"):
                slot = default
            elif "engine" in low:
                slot = color_slot(part_color_from_text(user_text, r"двигател|engine|мотор")) or black
            elif "window" in low or "cockpit" in low:
                slot = black
            elif "gear" in low or "door" in low:
                slot = black
            elif "stripe" in low or "cheatline" in low:
                slot = blue if re.search(r"син|голуб|blue|полос", t) else default
            elif "winglet" in low:
                slot = color_slot(part_color_from_text(user_text, r"winglet|законцов|концов")) or default
            elif "tail" in low:
                slot = color_slot(part_color_from_text(user_text, r"хвост|tail|киль|стабилизатор")) or slot
        if low.startswith("wing") and re.search(r"крыл", t):
            slot = color_slot(part_color_from_text(user_text, r"крыл|wing")) or black
        elif low.startswith("eye"):
            slot = color_slot(part_color_from_text(user_text, r"глаз|eye")) or (red if re.search(r"красн|red", t) else default)
        elif low in ("tail",):
            slot = color_slot(part_color_from_text(user_text, r"хвост|tail")) or slot
        if re.search(r"собак|лабрадор|labrador|\bdog\b|\bcat\b|\bкот\b", t):
            if low in ("body", "head", "tail") or low.startswith("leg"):
                slot = color_slot(color_for_object_name(user_text, name)) or (black if re.search(r"ч[её]рн|black", t) else brown)
        mapping[str(obj["id"])] = slot
    return mapping


def _project_settings_config(user_text: str, profile: Dict[str, Any], colors: Optional[List[str]] = None) -> bytes:
    nozzle = float(profile.get("nozzle_mm") or 0.4)
    printer = _printer_model_for_bambu(profile)
    filament_types, filament_colors = _filament_palette(user_text, profile)
    if colors is not None:
        filament_colors = colors
        filament_types = [(profile.get("material") or "PLA").upper() for _ in filament_colors]
    layer = "0.2" if nozzle >= 0.35 else "0.12"
    manual_supports = bool(re.search(r"print_tuned_manual_supports|manual\s+supports|manual_breakaway_supports", user_text or "", re.I))
    settings = {
        "printer_model": printer,
        "printer_settings_id": f"{printer} {nozzle:g} nozzle",
        "print_settings_id": f"{layer}mm Procedural Articulated @M-Bot",
        "nozzle_diameter": [f"{nozzle:g}"],
        "curr_bed_type": "Textured PEI Plate",
        "layer_height": layer,
        "initial_layer_print_height": "0.2",
        "wall_loops": "2",
        "top_shell_layers": "3",
        "bottom_shell_layers": "3",
        "sparse_infill_density": "15%",
        "sparse_infill_pattern": "grid",
        "enable_support": "0" if manual_supports else "1",
        "support_type": "normal(auto)" if manual_supports else "tree(auto)",
        "support_on_build_plate_only": "0",
        "brim_type": "auto_brim",
        "brim_width": "5",
        "brim_object_gap": "0.1",
        "filament_type": filament_types,
        "filament_colour": filament_colors,
        "filament_settings_id": [f"Generic {m}" for m in filament_types],
        "filament_map_mode": "Auto For Flush",
        "notes": (
            "Generated by M-Bot: procedural articulated 3MF. "
            "Verify joints, supports, filament assignment and estimated weight in Bambu Studio."
            + (
                " Print-tuned file uses built-in breakaway supports; keep slicer auto-supports off."
                if manual_supports
                else ""
            )
        ),
    }
    return json.dumps(settings, ensure_ascii=False, indent=4).encode("utf-8")


def _parse_model_stats(model_xml: bytes) -> Tuple[List[Dict[str, Any]], List[float]]:
    ns = {"m": _CORE_NS}
    root = ET.fromstring(model_xml)
    build_transforms: Dict[str, Tuple[float, float, float]] = {}
    for item in root.findall("m:build/m:item", ns):
        oid = item.get("objectid") or ""
        vals = [float(x) for x in (item.get("transform") or "").split()]
        if len(vals) == 12:
            build_transforms[oid] = (vals[9], vals[10], vals[11])
        else:
            build_transforms[oid] = (0.0, 0.0, 0.0)

    objects: List[Dict[str, Any]] = []
    bbox_all: Optional[List[float]] = None
    for obj in root.findall("m:resources/m:object", ns):
        oid = obj.get("id") or ""
        name = obj.get("name") or f"object_{oid}"
        vertices = obj.find("m:mesh/m:vertices", ns)
        triangles = obj.find("m:mesh/m:triangles", ns)
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        if vertices is not None:
            dx, dy, dz = build_transforms.get(oid, (0.0, 0.0, 0.0))
            for v in vertices.findall("m:vertex", ns):
                xs.append(float(v.get("x", "0")) + dx)
                ys.append(float(v.get("y", "0")) + dy)
                zs.append(float(v.get("z", "0")) + dz)
        tri_count = len(triangles.findall("m:triangle", ns)) if triangles is not None else 0
        bbox = [
            min(xs) if xs else 0.0,
            min(ys) if ys else 0.0,
            min(zs) if zs else 0.0,
            max(xs) if xs else 0.0,
            max(ys) if ys else 0.0,
            max(zs) if zs else 0.0,
        ]
        if bbox_all is None:
            bbox_all = bbox[:]
        else:
            bbox_all = [
                min(bbox_all[0], bbox[0]),
                min(bbox_all[1], bbox[1]),
                min(bbox_all[2], bbox[2]),
                max(bbox_all[3], bbox[3]),
                max(bbox_all[4], bbox[4]),
                max(bbox_all[5], bbox[5]),
            ]
        objects.append({"id": oid, "name": name, "face_count": tri_count, "bbox": bbox})
    return objects, (bbox_all or [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


def _model_settings_config(model_xml: bytes, user_text: str, colors: List[str]) -> bytes:
    objects, _ = _parse_model_stats(model_xml)
    extruders = _object_extruder_map(objects, user_text, colors)
    root = ET.Element("config")
    for obj in objects:
        ext = str(extruders.get(str(obj["id"]), 1))
        node = ET.SubElement(root, "object", id=str(obj["id"]))
        ET.SubElement(node, "metadata", key="name", value=str(obj["name"]))
        ET.SubElement(node, "metadata", key="extruder", value=ext)
        ET.SubElement(node, "metadata", key="seam_position", value="back")
        ET.SubElement(node, "metadata", key="support_type", value="tree(auto)")
        ET.SubElement(node, "metadata", face_count=str(obj["face_count"]))
        part = ET.SubElement(node, "part", id="1", subtype="normal_part")
        ET.SubElement(part, "metadata", key="name", value=str(obj["name"]))
        ET.SubElement(part, "metadata", key="matrix", value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1")
        ET.SubElement(part, "metadata", key="source_object_id", value="0")
        ET.SubElement(part, "metadata", key="source_volume_id", value="0")
        ET.SubElement(part, "metadata", key="extruder", value=ext)
        ET.SubElement(
            part,
            "mesh_stat",
            face_count=str(obj["face_count"]),
            edges_fixed="0",
            degenerate_facets="0",
            facets_removed="0",
            facets_reversed="0",
            backwards_edges="0",
        )
    plate = ET.SubElement(root, "plate")
    for key, value in (
        ("plater_id", "1"),
        ("plater_name", ""),
        ("locked", "false"),
        ("filament_map_mode", "Auto For Flush"),
    ):
        ET.SubElement(plate, "metadata", key=key, value=value)
    ET.SubElement(
        plate,
        "metadata",
        key="filament_maps",
        value=" ".join(str(extruders.get(str(obj["id"]), 1)) for obj in objects) or "1",
    )
    for i, obj in enumerate(objects):
        inst = ET.SubElement(plate, "model_instance")
        ET.SubElement(inst, "metadata", key="object_id", value=str(obj["id"]))
        ET.SubElement(inst, "metadata", key="instance_id", value=str(i))
        ET.SubElement(inst, "metadata", key="identify_id", value=str(1000 + i))
    assemble = ET.SubElement(root, "assemble")
    for i, obj in enumerate(objects):
        ET.SubElement(
            assemble,
            "assemble_item",
            object_id=str(obj["id"]),
            instance_id=str(i),
            transform="1 0 0 0 1 0 0 0 1 0 0 0",
            offset="0 0 0",
        )
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _plate_json(model_xml: bytes, profile: Dict[str, Any]) -> bytes:
    objects, bbox = _parse_model_stats(model_xml)
    layer = 0.2 if float(profile.get("nozzle_mm") or 0.4) >= 0.35 else 0.12
    bbox2 = [bbox[0], bbox[1], bbox[3], bbox[4]]
    data = {
        "bbox_all": bbox2,
        "bbox_objects": [
            {
                "id": int(obj["id"] or 0),
                "name": obj["name"],
                "bbox": [obj["bbox"][0], obj["bbox"][1], obj["bbox"][3], obj["bbox"][4]],
                "layer_height": layer,
                "area": max(0.0, (obj["bbox"][3] - obj["bbox"][0]) * (obj["bbox"][4] - obj["bbox"][1])),
            }
            for obj in objects
        ],
        "bed_type": "textured_plate",
        "first_extruder": 0,
        "is_seq_print": False,
        "nozzle_diameter": float(profile.get("nozzle_mm") or 0.4),
        "version": 2,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _add_bambu_metadata(data: bytes, *, filename: str, user_text: str, profile: Dict[str, Any]) -> bytes:
    """Добавляет минимальный Bambu Studio project layer поверх 3MF-геометрии."""
    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    model_xml = entries.get("3D/3dmodel.model")
    if not model_xml:
        return data

    objects, _ = _parse_model_stats(model_xml)
    _, colors = _filament_palette(user_text, profile)
    _object_extruder_map(objects, user_text, colors)

    entries["Metadata/project_settings.config"] = _project_settings_config(user_text, profile, colors)
    entries["Metadata/model_settings.config"] = _model_settings_config(model_xml, user_text, colors)
    entries["Metadata/plate_1.json"] = _plate_json(model_xml, profile)
    entries["Metadata/slice_info.config"] = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b"<config><header>"
        b'<header_item key="X-BBL-Client-Type" value="slicer"/>'
        b'<header_item key="X-BBL-Client-Version" value="M-Bot-Procedural-3MF"/>'
        b"</header></config>"
    )
    entries["Metadata/filament_sequence.json"] = b'{"plate_1":{"nozzle_sequence":[],"optimal_assignment":[],"sequence":[]}}'
    entries["Metadata/cut_information.xml"] = b'<?xml version="1.0" encoding="utf-8"?><objects></objects>'

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, payload in entries.items():
            zout.writestr(name, payload)
    return out.getvalue()


async def _export_part_stl(
    kind: str,
    part: str,
    *,
    scale: float,
    gap: float,
    ball_r: float,
    tmp: Path,
) -> bytes:
    scad = _scad_for_part(kind, part, scale=scale, gap=gap, ball_r=ball_r)
    stl_path = tmp / f"{part}.stl"
    ok = await export_stl_from_scad(scad, stl_path)
    if not ok or not stl_path.is_file():
        raise RuntimeError(f"OpenSCAD не смог экспортировать деталь «{part}»")
    return stl_path.read_bytes()


async def build_articulated_figurine_3mf(
    user_text: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str, List[str], str]:
    """3MF на столе; возвращает (bytes, filename, part_names, описание деталей)."""
    if not openscad_available():
        raise RuntimeError("OpenSCAD не найден — артикулированный 3MF недоступен.")

    import trimesh

    kind = openscad_articulated_kind(user_text)
    if not kind:
        raise RuntimeError(
            "Для этой фигурки нет локального шаблона с шарнирами — попробуйте Meshy "
            "(опишите «статичная фигурка ангела») или уточните: собака/кот/ангел."
        )

    prof = profile or {}
    nozzle = float(prof.get("nozzle_mm") or 0.4)
    gap, ball_r = _gap_for_nozzle(nozzle)
    scale = _scale_from_text(user_text)
    slug = _subject_slug(user_text)
    if kind == "angel":
        part_specs = _ANGEL_SPECS
    elif kind == "dragon":
        part_specs = _DRAGON_SPECS
    elif kind == "bat":
        part_specs = _BAT_SPECS
    elif kind == "cheburashka":
        part_specs = _CHEBURASHKA_SPECS
    elif kind == "generic_winged":
        part_specs = _GENERIC_WINGED_SPECS
    elif kind == "generic_humanoid":
        part_specs = _GENERIC_HUMANOID_SPECS
    else:
        part_specs = _QUADRUPED_SPECS

    named_meshes: List[Tuple[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="art3mf-") as td:
        tmp = Path(td)
        for obj_name, scad_part in part_specs:
            stl_bytes = await _export_part_stl(
                kind,
                scad_part,
                scale=scale,
                gap=gap,
                ball_r=ball_r,
                tmp=tmp,
            )
            mesh = trimesh.load(io.BytesIO(stl_bytes), file_type="stl")
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
            named_meshes.append((obj_name, mesh))

        scene = _layout_scene(named_meshes)
        out_path = tmp / f"{slug}-articulated.3mf"
        scene.export(str(out_path))
        if not out_path.is_file():
            raise RuntimeError("Не удалось записать 3MF")
        data = out_path.read_bytes()

    part_names = [n for n, _ in named_meshes]
    desc = parts_description(kind)
    filename = f"{slug}-articulated.3mf"
    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=prof)
    logger.info(
        "articulated 3MF %s · %s · %d parts · gap=%.2f scale=%.2f",
        kind,
        slug,
        len(part_names),
        gap,
        scale,
    )
    return data, filename, part_names, desc


def assembly_hint(user_text: str) -> str:
    kind = openscad_articulated_kind(user_text)
    if kind == "angel":
        return (
            "🔧 **Сборка ангела:**\n"
            "1. Откройте 3MF в Bambu Studio (предупреждение «не от Bambu Lab» — нормально, "
            "назначьте цвета вручную).\n"
            "2. **Белый PLA:** body, head.\n"
            "3. **Чёрный PLA:** wing_left, wing_right.\n"
            "4. **Красный PLA:** eye_left, eye_right.\n"
            "5. Напечатайте → вставьте шарики крыльев в гнёзда на спине (слегка прогрейте).\n"
            "6. Голова → шея. Крылья должны **шевелиться** на шарнирах.\n"
            "Сопло 0.4 мм, слой 0.20 мм, infill 15–20%, ~50 г."
        )
    if kind in ("dragon", "bat", "cheburashka", "generic_winged", "generic_humanoid"):
        subject = requested_subject_label(user_text)
        return (
            f"🔧 **Сборка: {subject} (процедурный v0):**\n"
            "1. Откройте 3MF в Bambu Studio (предупреждение «не от Bambu Lab» — нормально).\n"
            "2. Назначьте цвета по объектам в AMS: body/head — основной цвет, "
            "wing_* — цвет крыльев, eye_* — цвет глаз.\n"
            "3. Напечатайте → шарики подвижных деталей вставляются в гнёзда тела.\n"
            "4. Это не Meshy-скульпт, а мой процедурный код: форма упрощённая, "
            "но предмет не подменяется чужим шаблоном.\n"
            "Сопло 0.4 мм, слой 0.20 мм, infill 15–20%."
        )
    return (
        "🔧 **Сборка после печати:**\n"
        "1. Откройте 3MF в Bambu Studio — все детали на столе.\n"
        "2. Назначьте филаменты по объектам в AMS.\n"
        "3. Напечатайте → шарики шарниров в гнёзда (слегка прогрейте, если туго).\n"
        "4. Голова, лапы, хвост — по гнёздам на теле.\n"
        "Сопло 0.4 мм, слой 0.20 мм, infill 15–20%."
    )
