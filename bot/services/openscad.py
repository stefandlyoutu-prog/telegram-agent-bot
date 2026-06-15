"""Локальная генерация OpenSCAD и экспорт STL через openscad CLI."""

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_OPENSCAD_CANDIDATES = [
    os.getenv("OPENSCAD_PATH", "").strip(),
    shutil.which("openscad") or "",
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    "/Applications/OpenSCAD-2021.01.app/Contents/MacOS/OpenSCAD",
]


def _find_openscad() -> str:
    for p in _OPENSCAD_CANDIDATES:
        if p and Path(p).is_file():
            return p
    return ""


OPENSCAD_BIN = _find_openscad()


def openscad_available() -> bool:
    return bool(OPENSCAD_BIN)


def _num(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _int(val: Any, default: int) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def sanitize_id(name: str, fallback: str = "part") -> str:
    s = re.sub(r"[^\w\-]+", "-", (name or fallback).strip().lower())
    return (s[:40] or fallback).strip("-") or fallback




def build_polygon_ring(points: List[Tuple[float, float]], height: float = 4.0) -> str:
    """2D polygon extrude from points."""
    pts = ', '.join(f'[{x}, {y}]' for x, y in points)
    return f'linear_extrude(height={height}) polygon(points=[{pts}]);\n'


def build_triangle_rect_circle(w: float, d: float, r: float, hole_r: float = 0.0, wall: float = 2.0) -> str:
    """Rect with triangle and circle cutouts."""
    tw = max(1.0, w - 2 * wall)
    td = max(1.0, d - 2 * wall)
    tri = f'polygon(points=[[0,0],[{tw},0],[{tw/2},{td}]]);'
    circle = f'translate([{tw/2}, {td/2}, -0.1]) cylinder(h=6, r={r}, center=false);'
    body = (
        'difference() {\n'
        f'  cube([{w}, {d}, 6], center=true);\n'
        f'  translate([{wall}, {wall}, 0]) linear_extrude(height=6) {tri}\n'
        f'  {circle}\n'
        '}\n'
    )
    if hole_r > 0:
        body += f'\ndifference() {{\n  cube([{w}, {d}, 6], center=true);\n  translate([{w/2}, {d/2}, -0.1]) cylinder(h=6.2, r={hole_r}, center=false);\n}}\n'
    return body


def build_scad_source(part: Dict[str, Any]) -> str:
    """Собрать .scad из JSON-описания детали."""
    template = str(part.get("template") or part.get("shape") or "box").lower()
    p = part.get("params") if isinstance(part.get("params"), dict) else part
    name = part.get("name") or part.get("id") or "part"
    w = _num(p.get("width_mm") or p.get("w") or p.get("width"), 40)
    d = _num(p.get("depth_mm") or p.get("d") or p.get("depth"), 40)
    h = _num(p.get("height_mm") or p.get("h") or p.get("height"), 20)
    r = _num(p.get("radius_mm") or p.get("radius") or p.get("r"), min(w, d) / 2 or 15)
    wall = _num(p.get("wall_mm") or p.get("wall"), 2.4)
    hole = _num(p.get("hole_mm") or p.get("hole"), 0)
    seg = _int(p.get("segments") or p.get("$fn"), 48)

    header = (
        f"// {name}\n"
        f"// Назначение: {part.get('purpose') or part.get('description') or '—'}\n"
        f"$fn = {seg};\n\n"
    )

    if template in ("exact", "shape", "custom") and isinstance(p.get("points"), list):
        pts = p.get("points")[:16]
        pts = [(float(x), float(y)) for x, y in pts if isinstance(x, (int, float)) and isinstance(y, (int, float))]
        if len(pts) >= 3:
            body = "difference() {\n"
            body += f"  cube([{w}, {d}, {h}]);\n"
            body += f"  translate([{wall}, {wall}, 0]) linear_extrude(height={h}) polygon(points=[" + ", ".join(f"[{x}, {y}]" for x, y in pts) + "]);\n"
            body += "}\n"
        else:
            body = f"cube([{w}, {d}, {h}]);\n"
    elif template in ("hollow_box", "box_shell", "corpus", "корпус"):
        inner_w = max(1, w - 2 * wall)
        inner_d = max(1, d - 2 * wall)
        inner_h = max(1, h - wall)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {wall}, {wall}])\n"
            f"    cube([{inner_w}, {inner_d}, {inner_h}]);\n"
            "}\n"
        )
    elif template in ("cylinder", "bobbin", "coil", "tube"):
        inner_r = max(0.5, r - wall) if template == "bobbin" else 0
        if template == "bobbin" or inner_r > 0:
            body = (
                "difference() {\n"
                f"  cylinder(h={h}, r={r}, center=false);\n"
                f"  translate([0, 0, -0.1]) cylinder(h={h + 0.2}, r={inner_r}, center=false);\n"
                "}\n"
            )
        else:
            body = f"cylinder(h={h}, r={r}, center=false);\n"
    elif template in ("triangle_rect_circle",):
        body = build_triangle_rect_circle(w, d, r, hole_r=_num(p.get("inner_hole_r") or p.get("hole_inner") or 0, 0), wall=wall)
    elif template in ("sphere", "ball"):
        body = f"sphere(r={r});\n"
    elif template in ("plate", "base", "lid"):
        body = f"cube([{w}, {d}, {h}]);\n"
    elif template in ("rugged_box_bottom",):
        lip = max(0.8, wall * 0.55)
        rib = max(0.8, wall * 0.45)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cube([{w}, {d}, {h}]);\n"
            f"    translate([{wall}, {wall}, {h}]) cube([{w - 2 * wall}, {lip}, {lip}]);\n"
            f"    translate([{wall}, {d - wall - lip}, {h}]) cube([{w - 2 * wall}, {lip}, {lip}]);\n"
            f"    translate([{wall}, {wall}, {h}]) cube([{lip}, {d - 2 * wall}, {lip}]);\n"
            f"    translate([{w - wall - lip}, {wall}, {h}]) cube([{lip}, {d - 2 * wall}, {lip}]);\n"
            f"    translate([{w * 0.18}, {-rib}, {h * 0.35}]) cube([{w * 0.64}, {rib}, {h * 0.35}]);\n"
            f"    translate([{w * 0.18}, {d}, {h * 0.35}]) cube([{w * 0.64}, {rib}, {h * 0.35}]);\n"
            "  }\n"
            f"  translate([{wall}, {wall}, {wall}]) cube([{max(1, w - 2 * wall)}, {max(1, d - 2 * wall)}, {max(1, h)}]);\n"
            "}\n"
        )
    elif template in ("rugged_box_lid",):
        lip = max(0.8, wall * 0.55)
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {max(1.2, h * 0.45)}]);\n"
            f"  translate([{wall + 0.35}, {wall + 0.35}, {max(1.2, h * 0.45)}]) "
            f"cube([{max(1, w - 2 * wall - 0.7)}, {max(1, d - 2 * wall - 0.7)}, {lip}]);\n"
            f"  translate([{w * 0.18}, {-max(0.8, wall * 0.35)}, {max(1.2, h * 0.35)}]) "
            f"cube([{w * 0.64}, {max(0.8, wall * 0.35)}, {max(1.0, h * 0.25)}]);\n"
            "}\n"
        )
    elif template in ("snap_latch",):
        hook = max(1.0, h * 0.42)
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {max(1.2, h * 0.45)}]);\n"
            f"  translate([{w * 0.68}, 0, {max(1.2, h * 0.45)}]) cube([{w * 0.22}, {d}, {hook}]);\n"
            f"  translate([{w * 0.9}, 0, {max(1.2, h * 0.45) + hook - 1.0}]) cube([{w * 0.1}, {d}, 1.0]);\n"
            "}\n"
        )
    elif template in ("fit_test_coupon",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {wall}, -0.1]) cube([{max(1, w - 2 * wall)}, {max(1, d - 2 * wall)}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("kit_card_frame",):
        tab = max(0.8, wall * 0.45)
        body = (
            "union() {\n"
            f"  difference() {{ cube([{w}, {d}, {h}]); translate([{wall}, {wall}, -0.1]) cube([{max(1, w - 2 * wall)}, {max(1, d - 2 * wall)}, {h + 0.2}]); }}\n"
            f"  translate([{w * 0.12}, {d * 0.28}, 0]) cube([{w * 0.28}, {tab}, {h}]);\n"
            f"  translate([{w * 0.56}, {d * 0.48}, 0]) cube([{w * 0.28}, {tab}, {h}]);\n"
            f"  translate([{w * 0.47}, {d * 0.18}, 0]) cube([{tab}, {d * 0.22}, {h}]);\n"
            "}\n"
        )
    elif template in ("kit_card_wedge",):
        body = (
            f"linear_extrude(height={h}) polygon(points=[[0,0],[{w}, {d/2}], [0,{d}]]);\n"
        )
    elif template in ("slot_stand",):
        slot = max(1.2, _num(p.get("slot_mm"), 2.0))
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - slot/2}, {d * 0.18}, -0.1]) cube([{slot}, {d * 0.64}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("vehicle_body_tub",):
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cube([{w}, {d}, {h}]);\n"
            f"    translate([{w * 0.18}, {d * 0.08}, {h}]) cube([{w * 0.36}, {d * 0.84}, {h * 0.45}]);\n"
            f"    translate([{w * 0.60}, {d * 0.14}, {h}]) cube([{w * 0.25}, {d * 0.72}, {h * 0.35}]);\n"
            "  }\n"
            f"  translate([{wall}, {wall}, {wall}]) cube([{max(1, w - 2 * wall)}, {max(1, d - 2 * wall)}, {h * 1.4}]);\n"
            f"  translate([{w * 0.05}, {-0.1}, -0.1]) cube([{w * 0.16}, {wall + 0.2}, {h * 0.75}]);\n"
            f"  translate([{w * 0.72}, {-0.1}, -0.1]) cube([{w * 0.16}, {wall + 0.2}, {h * 0.75}]);\n"
            f"  translate([{w * 0.05}, {d - wall - 0.1}, -0.1]) cube([{w * 0.16}, {wall + 0.2}, {h * 0.75}]);\n"
            f"  translate([{w * 0.72}, {d - wall - 0.1}, -0.1]) cube([{w * 0.16}, {wall + 0.2}, {h * 0.75}]);\n"
            "}\n"
        )
    elif template in ("vehicle_chassis",):
        axle_slot = max(2.0, wall)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.18}, -0.1, {h * 0.35}]) cube([{axle_slot}, {d + 0.2}, {h * 0.35}]);\n"
            f"  translate([{w * 0.78}, -0.1, {h * 0.35}]) cube([{axle_slot}, {d + 0.2}, {h * 0.35}]);\n"
            "}\n"
        )
    elif template in ("seat_block",):
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {max(1.2, h * 0.38)}]);\n"
            f"  translate([0, {d * 0.72}, {h * 0.35}]) cube([{w}, {max(1.2, d * 0.28)}, {h * 0.65}]);\n"
            "}\n"
        )
    elif template in ("spur_gear", "gear"):
        teeth = _int(p.get("teeth"), 32)
        module = _num(p.get("module_mm") or p.get("module"), 1.2)
        pitch_r = max(4.0, teeth * module / 2.0)
        root_r = max(3.0, pitch_r - module * 0.75)
        tooth_w = max(0.8, module * 0.9)
        hole_r = max(0.0, hole / 2.0)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cylinder(h={h}, r={root_r}, center=false);\n"
            f"    for (i=[0:{teeth - 1}]) rotate([0,0,i*360/{teeth}]) "
            f"translate([{root_r - 0.15}, {-tooth_w / 2}, 0]) cube([{module * 1.35}, {tooth_w}, {h}]);\n"
            "  }\n"
        )
        if hole_r > 0:
            body += f"  translate([0,0,-0.1]) cylinder(h={h + 0.2}, r={hole_r}, center=false);\n"
        body += "}\n"
    elif template in ("planet_arm",):
        hole_r = max(1.0, hole / 2.0)
        boss_r = max(hole_r + 2.0, r)
        end_r = max(3.0, d * 0.42)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    translate([0, {-d/2}, 0]) cube([{w}, {d}, {h}]);\n"
            f"    translate([0, 0, 0]) cylinder(h={h}, r={boss_r}, center=false);\n"
            f"    translate([{w}, 0, 0]) cylinder(h={h}, r={end_r}, center=false);\n"
            "  }\n"
            f"  translate([0,0,-0.1]) cylinder(h={h + 0.2}, r={hole_r}, center=false);\n"
            f"  translate([{w},0,-0.1]) cylinder(h={h + 0.2}, r={max(1.0, hole_r * 0.75)}, center=false);\n"
            "}\n"
        )
    elif template in ("axle_peg_set",):
        peg_r = max(1.2, r)
        peg_h = max(8.0, h * 4.0)
        body = "union() {\n"
        for idx, x in enumerate((0, 18, 36, 54, 72, 90, 108)):
            body += f"  translate([{x}, 0, 0]) cylinder(h={peg_h + (idx % 3) * 3}, r={peg_r}, center=false);\n"
        body += f"  translate([-6, {-peg_r * 2.2}, 0]) cube([{w}, {max(1.2, peg_r * 0.75)}, {max(1.0, h * 0.3)}]);\n"
        body += "}\n"
    elif template in ("gear_mesh_coupon",):
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.30}, {d/2}, {h}]) cylinder(h={max(1.0, h * 0.7)}, r=2.4, center=false);\n"
            f"  translate([{w * 0.62}, {d/2}, {h}]) cylinder(h={max(1.0, h * 0.7)}, r=2.4, center=false);\n"
            "}\n"
        )
    elif template in ("dna_helix_holder", "dna_helix_half"):
        helix_r = max(12.0, r)
        rod_r = max(1.0, wall / 2.0)
        steps = 24
        half_cut = template == "dna_helix_half"
        body = "difference() {\n  union() {\n"
        body += f"    cylinder(h={max(2.0, wall)}, r={helix_r + rod_r * 2.2}, center=false);\n"
        body += f"    translate([0,0,{h - max(2.0, wall)}]) cylinder(h={max(2.0, wall)}, r={helix_r + rod_r * 2.0}, center=false);\n"
        for i in range(steps + 1):
            z = h * i / steps
            a = i * 32
            body += f"    rotate([0,0,{a}]) translate([{helix_r},0,{z}]) sphere(r={rod_r});\n"
            body += f"    rotate([0,0,{a + 180}]) translate([{helix_r},0,{z}]) sphere(r={rod_r});\n"
            if i % 2 == 0:
                body += f"    rotate([0,0,{a}]) translate([{-helix_r}, {-rod_r/2}, {z}]) cube([{helix_r*2}, {rod_r}, {rod_r}]);\n"
        body += f"    cylinder(h={h}, r={max(10.0, helix_r * 0.42)}, center=false);\n"
        body += "  }\n"
        body += f"  translate([0,0,{max(1.0, wall)}]) cylinder(h={h + 0.2}, r={max(7.0, helix_r * 0.30)}, center=false);\n"
        if half_cut:
            body += f"  translate([{-w}, 0, -1]) cube([{w * 2}, {d * 2}, {h + 2}]);\n"
        body += "}\n"
    elif template in ("dna_support_coupon",):
        body = (
            "union() {\n"
            f"  cylinder(h={max(1.4, wall)}, r={w/2}, center=false);\n"
            f"  translate([{w * 0.22},0,{wall}]) rotate([0,0,28]) cube([{wall}, {d * 0.62}, {h}], center=false);\n"
            f"  translate([{-w * 0.22},0,{wall}]) rotate([0,0,-28]) cube([{wall}, {d * 0.62}, {h}], center=false);\n"
            "}\n"
        )
    elif template in ("impossible_cube",):
        beam = d
        body = (
            "union() {\n"
            f"  cube([{beam}, {beam}, {h}]);\n"
            f"  translate([{w - beam}, 0, 0]) cube([{beam}, {beam}, {h}]);\n"
            f"  cube([{w}, {beam}, {beam}]);\n"
            f"  translate([0, 0, {h - beam}]) cube([{w}, {beam}, {beam}]);\n"
            f"  translate([0, 0, {h - beam}]) rotate([0,45,0]) cube([{beam}, {beam}, {w * 0.72}]);\n"
            f"  translate([{w - beam}, 0, 0]) rotate([0,-45,0]) cube([{beam}, {beam}, {w * 0.72}]);\n"
            "}\n"
        )
    elif template in ("illusion_bar_coupon",):
        body = (
            "union() {\n"
            f"  cube([{d}, {d}, {h}]);\n"
            f"  translate([{w * 0.15},0,0]) rotate([0,-35,0]) cube([{d}, {d}, {w * 0.7}]);\n"
            "}\n"
        )
    elif template in ("puzzle_tile_center",):
        body = f"cube([{w}, {d}, {h}]);\n"
    elif template in ("puzzle_tile_tab",):
        tab_w = max(8.0, w * 0.28)
        tab_d = max(4.0, d * 0.22)
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - tab_w/2}, {d}, 0]) cube([{tab_w}, {tab_d}, {h}]);\n"
            "}\n"
        )
    elif template in ("puzzle_tile_slot",):
        tab_w = max(8.0, w * 0.28)
        tab_d = max(4.0, d * 0.22)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - tab_w/2}, {d - tab_d + 0.1}, -0.1]) cube([{tab_w}, {tab_d + 0.2}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("puzzle_tile_corner",):
        tab_w = max(8.0, w * 0.25)
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - tab_w/2}, {d}, 0]) cube([{tab_w}, {max(4.0, d * 0.16)}, {h}]);\n"
            f"  translate([{w}, {d/2 - tab_w/2}, 0]) cube([{max(4.0, w * 0.16)}, {tab_w}, {h}]);\n"
            "}\n"
        )
    elif template in ("tab_slot_coupon",):
        body = (
            "union() {\n"
            f"  cube([{w * 0.46}, {d}, {h}]);\n"
            f"  translate([{w * 0.46}, {d * 0.35}, 0]) cube([{w * 0.16}, {d * 0.3}, {h}]);\n"
            f"  translate([{w * 0.66}, 0, 0]) difference() {{ cube([{w * 0.34}, {d}, {h}]); translate([0, {d * 0.35}, -0.1]) cube([{w * 0.18}, {d * 0.3}, {h + 0.2}]); }}\n"
            "}\n"
        )
    elif template in ("spiral_chess_piece",):
        base_h = max(2.0, h * 0.12)
        stem_r = max(2.4, r * 0.32)
        body = (
            "union() {\n"
            f"  cylinder(h={base_h}, r={r}, center=false);\n"
            f"  translate([0,0,{base_h}]) cylinder(h={h - base_h}, r1={stem_r * 1.35}, r2={stem_r * 0.75}, center=false);\n"
            f"  translate([0,0,{h - r * 0.55}]) sphere(r={r * 0.48});\n"
            f"  for (i=[0:11]) rotate([0,0,i*30]) translate([{stem_r}, -{wall/2}, {base_h} + i*{(h - base_h) / 14}]) cube([{wall}, {wall}, {(h - base_h) / 3}]);\n"
            "}\n"
        )
    elif template in ("lamp_shade_shell", "greek_meander_shade"):
        cutout_count = 12 if template == "greek_meander_shade" else 8
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cylinder(h={h}, r1={r * 1.08}, r2={max(4.0, r * 0.72)}, center=false);\n"
            f"    translate([0,0,{h - wall}]) cylinder(h={wall}, r={max(4.0, r * 0.76)}, center=false);\n"
            "  }\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.2}, r1={max(1.0, r * 1.08 - wall)}, r2={max(1.0, r * 0.72 - wall)}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={wall + 0.3}, r={max(1.0, r * 0.60)}, center=false);\n"
        )
        for i in range(cutout_count):
            z = h * (0.18 + (i % 4) * 0.16)
            a = i * 360 / cutout_count
            body += f"  rotate([0,0,{a}]) translate([{r * 0.78}, {-wall * 0.65}, {z}]) cube([{wall * 3.0}, {wall * 1.3}, {h * 0.10}]);\n"
        body += "}\n"
    elif template in ("lamp_base",):
        cable = max(3.0, hole)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cube([{w}, {d}, {h}], center=false);\n"
            f"    translate([{w/2}, {d/2}, {h}]) cylinder(h={max(2.0, wall)}, r={min(w, d) * 0.34}, center=false);\n"
            "  }\n"
            f"  translate([{w/2}, {-0.1}, {h * 0.42}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={cable/2}, center=false);\n"
            f"  translate([{w/2}, {d/2}, {h - 0.1}]) cylinder(h={max(2.0, wall) + 0.3}, r={min(w, d) * 0.22}, center=false);\n"
            "}\n"
        )
    elif template in ("led_fit_coupon",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.28}, {d/2}, -0.1]) cylinder(h={h + 0.2}, r={max(1.5, hole/2)}, center=false);\n"
            f"  translate([{w * 0.58}, {d * 0.25}, {h * 0.45}]) cube([{w * 0.34}, {d * 0.5}, {h * 0.35}]);\n"
            "}\n"
        )
    elif template in ("character_body",):
        body = (
            "union() {\n"
            f"  cylinder(h={h * 0.55}, r={r}, center=false);\n"
            f"  translate([0,0,{h * 0.55}]) sphere(r={r * 0.92});\n"
            f"  translate([0,0,{h * 0.08}]) cylinder(h={h * 0.08}, r={r * 1.08}, center=false);\n"
            "}\n"
        )
    elif template in ("character_insert",):
        body = (
            "hull() {\n"
            f"  sphere(r={max(1.5, h * 0.42)});\n"
            f"  translate([{w},0,0]) sphere(r={max(0.8, h * 0.12)});\n"
            "}\n"
        )
    elif template in ("button_set",):
        body = "union() {\n"
        for i in range(3):
            x = (i - 1) * max(6.0, w * 0.24)
            body += f"  translate([{x},0,0]) cylinder(h={h}, r={max(1.2, r)}, center=false);\n"
        body += "}\n"
    elif template in ("branch_arm_set",):
        branch = max(1.2, wall)
        body = (
            "union() {\n"
            f"  cube([{w}, {branch}, {h}], center=true);\n"
            f"  translate([{w * 0.24},0,0]) rotate([0,0,32]) cube([{w * 0.28}, {branch}, {h}], center=true);\n"
            f"  translate([{w * 0.58},0,0]) rotate([0,0,-32]) cube([{w * 0.24}, {branch}, {h}], center=true);\n"
            "}\n"
        )
    elif template in ("rocket_planter_shell", "temple_planter_shell"):
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cylinder(h={h}, r={r}, center=false);\n"
        )
        if template == "rocket_planter_shell":
            body += f"    translate([0,0,{h}]) cylinder(h={h * 0.22}, r1={r}, r2={max(3.0, r * 0.18)}, center=false);\n"
            for a in (0, 120, 240):
                body += f"    rotate([0,0,{a}]) translate([{r * 0.78}, {-wall/2}, 0]) cube([{r * 0.45}, {wall}, {h * 0.32}]);\n"
        else:
            for level in range(4):
                body += f"    translate([{-w * (0.43 - level * 0.06)}, {-d * (0.43 - level * 0.06)}, {level * h * 0.17}]) cube([{w * (0.86 - level * 0.12)}, {d * (0.86 - level * 0.12)}, {h * 0.08}]);\n"
        body += (
            "  }\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.4}, r={max(1.0, r - wall)}, center=false);\n"
            "}\n"
        )
    elif template in ("plant_pot_liner",):
        body = (
            "difference() {\n"
            f"  cylinder(h={h}, r={r}, center=false);\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.2}, r={max(1.0, r - wall)}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={wall + 0.3}, r={max(1.0, hole/2)}, center=false);\n"
            f"  translate([{r * 0.42},0,-0.1]) cylinder(h={wall + 0.3}, r={max(1.0, hole/2)}, center=false);\n"
            f"  translate([{-r * 0.42},0,-0.1]) cylinder(h={wall + 0.3}, r={max(1.0, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("drainage_ring",):
        body = (
            "difference() {\n"
            f"  cylinder(h={h}, r={r}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={h + 0.2}, r={max(1.0, r - wall)}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={h + 0.2}, r={max(1.0, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("drainage_coupon",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  for (x=[{w*0.25},{w*0.5},{w*0.75}]) translate([x,{d/2},-0.1]) cylinder(h={h + 0.2}, r={max(1.0, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("decorative_box_shell",):
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cylinder(h={h}, r={r}, center=false);\n"
            f"    for (i=[0:23]) rotate([0,0,i*15]) translate([{r * 0.74}, {-wall/2}, {h}]) cube([{wall * 1.8}, {wall}, {max(0.6, wall * 0.45)}]);\n"
            "  }\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.3}, r={max(1.0, r - wall)}, center=false);\n"
            "}\n"
        )
    elif template in ("box_liner",):
        body = (
            "difference() {\n"
            f"  cylinder(h={h}, r={r}, center=false);\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.2}, r={max(1.0, r - wall)}, center=false);\n"
            "}\n"
        )
    elif template in ("ring_fit_coupon",):
        body = (
            "difference() {\n"
            f"  cylinder(h={h}, r={r}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={h + 0.2}, r={max(1.0, r - wall)}, center=false);\n"
            "}\n"
        )
    elif template in ("low_poly_vase_shell",):
        body = (
            "difference() {\n"
            f"  scale([1,{max(0.45, d / max(w, 1))},1]) cylinder(h={h}, r1={r * 0.86}, r2={r * 0.58}, $fn=12, center=false);\n"
            f"  translate([0,0,{wall * 2.2}]) scale([1,{max(0.45, d / max(w, 1))},1]) cylinder(h={h + 0.2}, r1={max(1.0, r * 0.86 - wall)}, r2={max(1.0, r * 0.58 - wall)}, $fn=12, center=false);\n"
            "}\n"
        )
    elif template in ("vase_wall_coupon",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {wall}, {wall}]) cube([{max(1, w - 2 * wall)}, {max(1, d - 2 * wall)}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("sla_calibration_town", "sla_supported_variant"):
        support_h = h * 0.18 if template == "sla_supported_variant" else 0
        body = "union() {\n"
        if support_h > 0:
            body += f"  translate([0,0,0]) cube([{w}, {d}, {support_h}]);\n"
        z0 = support_h
        body += f"  translate([0,0,{z0}]) cube([{w}, {d}, {h * 0.12}]);\n"
        body += f"  translate([{w*0.08},{d*0.12},{z0 + h*0.12}]) cube([{w*0.28}, {d*0.28}, {h*0.35}]);\n"
        body += f"  translate([{w*0.48},{d*0.12},{z0 + h*0.12}]) cube([{w*0.36}, {d*0.38}, {h*0.48}]);\n"
        body += f"  translate([{w*0.20},{d*0.72},{z0 + h*0.12}]) cylinder(h={h*0.42}, r={max(0.6, wall)}, center=false);\n"
        body += f"  translate([{w*0.62},{d*0.72},{z0 + h*0.12}]) cylinder(h={h*0.62}, r={max(0.45, wall*0.72)}, center=false);\n"
        body += "}\n"
    elif template in ("sla_exposure_ladder",):
        body = "union() {\n"
        for i in range(5):
            body += f"  translate([{i * w / 5},0,0]) cube([{w / 5 - 0.4}, {d}, {max(0.4, h * (0.35 + i * 0.14))}]);\n"
        body += "}\n"
    elif template in ("egg_low_poly", "egg_wavy", "egg_voronoi_safe"):
        body = (
            "union() {\n"
            f"  scale([{w/(2*r)}, {d/(2*r)}, {h/(2*r)}]) sphere(r={r}, $fn={12 if template == 'egg_low_poly' else 32});\n"
        )
        if template == "egg_wavy":
            for i in range(8):
                body += f"  rotate([0,0,{i*45}]) translate([{r*0.82},-{wall/2},0]) cube([{wall}, {wall}, {h*0.42}], center=true);\n"
        if template == "egg_voronoi_safe":
            for i in range(6):
                body += f"  rotate([0,0,{i*60}]) translate([{r*0.72},0,0]) cylinder(h={h*0.82}, r={max(0.6, wall*0.6)}, center=true);\n"
        body += "}\n"
    elif template in ("thin_bridge_coupon",):
        body = (
            "union() {\n"
            f"  cube([{w * 0.32}, {d}, {h}]);\n"
            f"  translate([{w * 0.68},0,0]) cube([{w * 0.32}, {d}, {h}]);\n"
            f"  translate([{w * 0.30},{d/2 - wall/2},{h/2 - wall/2}]) cube([{w * 0.40}, {wall}, {wall}]);\n"
            "}\n"
        )
    elif template in ("jewellery_tree_panel",):
        branch = max(1.6, wall)
        body = (
            "union() {\n"
            f"  translate([{w/2 - branch/2},0,0]) cube([{branch}, {d}, {h}]);\n"
            f"  translate([{w/2 - branch/2},0,{h * 0.28}]) rotate([0,0,28]) cube([{w * 0.36}, {d}, {branch}]);\n"
            f"  translate([{w/2 - branch/2},0,{h * 0.42}]) rotate([0,0,-30]) cube([{w * 0.34}, {d}, {branch}]);\n"
            f"  translate([{w/2 - branch/2},0,{h * 0.58}]) rotate([0,0,42]) cube([{w * 0.28}, {d}, {branch}]);\n"
            f"  translate([{w/2 - branch/2},0,{h * 0.72}]) rotate([0,0,-45]) cube([{w * 0.22}, {d}, {branch}]);\n"
            "}\n"
        )
    elif template in ("jewellery_tree_base",):
        slot = max(2.0, hole)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - slot/2}, {d * 0.18}, {h * 0.35}]) cube([{slot}, {d * 0.64}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("bust_head_torso",):
        drain_r = max(1.5, hole / 2.0)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    translate([0,0,{h * 0.30}]) scale([{w/(2*r)}, {d/(2*r)}, {h/(3.0*r)}]) sphere(r={r});\n"
            f"    translate([0,0,{h * 0.62}]) scale([{w/(2.4*r)}, {d/(2.2*r)}, {h/(3.2*r)}]) sphere(r={r});\n"
            f"    translate([{-w * 0.36},{-d * 0.30},0]) cube([{w * 0.72}, {d * 0.60}, {h * 0.18}]);\n"
            "  }\n"
            f"  translate([0,0,{wall}]) scale([{max(0.1, (w - 2*wall)/(2*r))}, {max(0.1, (d - 2*wall)/(2*r))}, {h/(3.1*r)}]) sphere(r={r});\n"
            f"  translate([0,{-d * 0.22},-0.1]) cylinder(h={wall + 0.4}, r={drain_r}, center=false);\n"
            "}\n"
        )
    elif template in ("display_base_keyed", "collectible_display_base"):
        socket = max(2.0, hole)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    scale([1,{max(0.35, d/max(w, 1))},1]) cylinder(h={h}, r={w/2}, center=false);\n"
            f"    translate([{-w * 0.34},{-d * 0.18},{h}]) cube([{w * 0.68}, {d * 0.36}, {max(1.0, wall * 0.8)}]);\n"
            "  }\n"
            f"  translate([0,0,{h - wall * 0.45}]) cylinder(h={wall + 0.4}, r={socket}, center=false);\n"
            f"  translate([{w * 0.18},0,{h - wall * 0.45}]) cylinder(h={wall + 0.4}, r={max(1.0, socket * 0.55)}, center=false);\n"
            f"  translate([{-w * 0.18},0,{h - wall * 0.45}]) cylinder(h={wall + 0.4}, r={max(1.0, socket * 0.55)}, center=false);\n"
            "}\n"
        )
    elif template in ("nameplate_blank", "paint_swatch_strip"):
        body = "union() {\n"
        body += f"  cube([{w}, {d}, {h}]);\n"
        if template == "paint_swatch_strip":
            for i in range(5):
                body += f"  translate([{i * w / 5 + 0.4},0,{h}]) cube([{w / 5 - 0.8}, {d}, {max(0.5, wall * 0.5)}]);\n"
        body += "}\n"
    elif template in ("hollow_support_coupon",):
        drain_r = max(1.5, hole / 2.0)
        body = (
            "difference() {\n"
            f"  cylinder(h={h}, r1={w * 0.42}, r2={w * 0.30}, center=false);\n"
            f"  translate([0,0,{wall}]) cylinder(h={h + 0.2}, r1={max(1.0, w * 0.42 - wall)}, r2={max(1.0, w * 0.30 - wall)}, center=false);\n"
            f"  translate([0,0,-0.1]) cylinder(h={wall + 0.3}, r={drain_r}, center=false);\n"
            "}\n"
        )
    elif template in ("collectible_full_preview",):
        body = (
            "union() {\n"
            f"  cylinder(h={h * 0.10}, r={r * 1.15}, center=false);\n"
            f"  translate([0,0,{h * 0.10}]) scale([0.85,0.65,1.15]) sphere(r={r});\n"
            f"  translate([0,0,{h * 0.56}]) scale([0.95,0.82,0.88]) sphere(r={r});\n"
            f"  translate([{r * 0.62},0,{h * 0.52}]) sphere(r={r * 0.20});\n"
            f"  translate([{-r * 0.62},0,{h * 0.52}]) sphere(r={r * 0.20});\n"
            "}\n"
        )
    elif template in ("keyed_character_torso",):
        pin_r = max(1.2, hole / 2.0)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    scale([{w/(2*r)}, {d/(2*r)}, {h/(2.3*r)}]) sphere(r={r});\n"
            f"    translate([0,0,{h * 0.46}]) cylinder(h={max(3.0, wall * 2.0)}, r={pin_r}, center=false);\n"
            f"    translate([{w * 0.42},0,{h * 0.30}]) cylinder(h={max(3.0, wall * 1.6)}, r={max(1.0, pin_r * 0.75)}, center=false);\n"
            f"    translate([{-w * 0.42},0,{h * 0.30}]) cylinder(h={max(3.0, wall * 1.6)}, r={max(1.0, pin_r * 0.75)}, center=false);\n"
            "  }\n"
            f"  translate([0,0,-0.1]) cylinder(h={wall + 0.3}, r={pin_r}, center=false);\n"
            "}\n"
        )
    elif template in ("keyed_character_head",):
        socket_r = max(1.2, hole / 2.0)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    scale([{w/(2*r)}, {d/(2*r)}, {h/(2*r)}]) sphere(r={r});\n"
            f"    translate([{w * 0.22},{-d * 0.34},{h * 0.06}]) sphere(r={max(1.2, r * 0.08)});\n"
            f"    translate([{-w * 0.22},{-d * 0.34},{h * 0.06}]) sphere(r={max(1.2, r * 0.08)});\n"
            "  }\n"
            f"  translate([0,0,{-h * 0.42}]) cylinder(h={h * 0.45}, r={socket_r}, center=false);\n"
            "}\n"
        )
    elif template in ("character_ears_pair",):
        peg_r = max(0.8, hole / 2.0)
        body = (
            "union() {\n"
            f"  translate([{-w * 0.23},0,0]) scale([0.55,0.18,1.0]) sphere(r={h * 0.55});\n"
            f"  translate([{w * 0.23},0,0]) scale([0.55,0.18,1.0]) sphere(r={h * 0.55});\n"
            f"  translate([{-w * 0.23},0,{-h * 0.30}]) cylinder(h={h * 0.34}, r={peg_r}, center=false);\n"
            f"  translate([{w * 0.23},0,{-h * 0.30}]) cylinder(h={h * 0.34}, r={peg_r}, center=false);\n"
            "}\n"
        )
    elif template in ("character_hands_pair",):
        peg_r = max(0.8, hole / 2.0)
        body = (
            "union() {\n"
            f"  translate([{-w * 0.22},0,0]) scale([1.0,0.65,0.55]) sphere(r={h * 0.55});\n"
            f"  translate([{w * 0.22},0,0]) scale([1.0,0.65,0.55]) sphere(r={h * 0.55});\n"
            f"  translate([{-w * 0.22},{d * 0.26},0]) rotate([90,0,0]) cylinder(h={d * 0.38}, r={peg_r}, center=false);\n"
            f"  translate([{w * 0.22},{d * 0.26},0]) rotate([90,0,0]) cylinder(h={d * 0.38}, r={peg_r}, center=false);\n"
            "}\n"
        )
    elif template in ("pin_connector_set",):
        peg_r = max(0.9, r)
        body = "union() {\n"
        for i in range(5):
            body += f"  translate([{i * w / 5},0,0]) cylinder(h={h + i * 1.2}, r={peg_r}, center=false);\n"
        body += f"  translate([{-peg_r * 2},{-peg_r * 2},0]) cube([{w + peg_r * 2}, {max(0.8, peg_r * 0.55)}, {max(0.8, h * 0.35)}]);\n"
        body += "}\n"
    elif template in ("pin_socket_coupon",):
        socket = max(1.5, hole / 2.0)
        body = (
            "union() {\n"
            f"  cylinder(h={h}, r={socket * 0.82}, center=false);\n"
            f"  translate([{w * 0.45},0,0]) difference() {{ cube([{w * 0.45}, {d}, {h}]); translate([{w * 0.22},{d/2},-0.1]) cylinder(h={h + 0.2}, r={socket}, center=false); }}\n"
            "}\n"
        )
    elif template in ("cape_shell",):
        body = (
            "difference() {\n"
            f"  scale([1,0.28,1]) cylinder(h={h}, r1={w * 0.52}, r2={w * 0.34}, center=false);\n"
            f"  translate([0,0,{wall}]) scale([1,0.22,1]) cylinder(h={h + 0.2}, r1={max(1.0, w * 0.52 - wall)}, r2={max(1.0, w * 0.34 - wall)}, center=false);\n"
            "}\n"
        )
    elif template in ("sleeves_pair",):
        sleeve_r = max(2.0, d * 0.28)
        body = (
            "union() {\n"
            f"  translate([{-w * 0.24},0,0]) rotate([0,90,0]) cylinder(h={w * 0.22}, r={sleeve_r}, center=true);\n"
            f"  translate([{w * 0.24},0,0]) rotate([0,90,0]) cylinder(h={w * 0.22}, r={sleeve_r}, center=true);\n"
            "}\n"
        )
    elif template in ("prop_pumpkin",):
        body = "union() {\n"
        for i in range(8):
            body += f"  rotate([0,0,{i * 45}]) translate([{r * 0.18},0,0]) scale([0.75,0.55,0.8]) sphere(r={r});\n"
        body += f"  translate([0,0,{h * 0.34}]) cylinder(h={h * 0.22}, r1={max(1.2, wall)}, r2={max(0.8, wall * 0.6)}, center=false);\n"
        body += "}\n"
    elif template in ("color_eye_set",):
        eye_r = max(1.0, r)
        body = (
            "union() {\n"
            f"  translate([{-w * 0.18},0,0]) cylinder(h={h}, r={eye_r}, center=false);\n"
            f"  translate([{w * 0.18},0,0]) cylinder(h={h}, r={eye_r}, center=false);\n"
            f"  translate([{-w * 0.18},0,{h}]) sphere(r={eye_r * 0.62});\n"
            f"  translate([{w * 0.18},0,{h}]) sphere(r={eye_r * 0.62});\n"
            "}\n"
        )
    elif template in ("nail_claw_set",):
        claw_w = max(1.0, wall)
        body = "union() {\n"
        for i in range(10):
            body += f"  translate([{i * w / 10},0,0]) linear_extrude(height={h}) polygon(points=[[0,0],[{claw_w},{d * 0.45}],[{claw_w * 2},0]]);\n"
        body += "}\n"
    elif template in ("seed_cell_tray",):
        cols, rows = 3, 2
        cell_w = w / cols
        cell_d = d / rows
        body = "difference() {\n  union() {\n"
        body += f"    cube([{w}, {d}, {wall}]);\n"
        for cx in range(cols):
            for cy in range(rows):
                body += f"    translate([{cx * cell_w + wall/2}, {cy * cell_d + wall/2}, 0]) cube([{cell_w - wall}, {cell_d - wall}, {h}]);\n"
        body += "  }\n"
        for cx in range(cols):
            for cy in range(rows):
                body += f"  translate([{cx * cell_w + wall * 1.3}, {cy * cell_d + wall * 1.3}, {wall}]) cube([{cell_w - wall * 2.6}, {cell_d - wall * 2.6}, {h + 0.2}]);\n"
                body += f"  translate([{cx * cell_w + cell_w/2}, {cy * cell_d + cell_d/2}, -0.1]) cylinder(h={wall + 0.3}, r={max(1.0, hole/2)}, center=false);\n"
        body += "}\n"
    elif template in ("water_gap_base",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {wall}, {wall}]) cube([{max(1, w - 2*wall)}, {max(1, d - 2*wall)}, {h}]);\n"
            "}\n"
        )
    elif template in ("humidity_dome",):
        vent = max(2.0, hole / 2)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    translate([{w/2}, {d/2}, 0]) scale([{w/2}, {d/2}, {h}]) sphere(r=1, $fn=48);\n"
            f"    cube([{w}, {d}, {wall}]);\n"
            "  }\n"
            f"  translate([{wall}, {wall}, -0.1]) cube([{max(1, w - 2*wall)}, {max(1, d - 2*wall)}, {h + 0.2}]);\n"
            f"  translate([{w/2}, {d/2}, {h * 0.75}]) cylinder(h={h}, r={vent}, center=false);\n"
            "}\n"
        )
    elif template in ("soil_press",):
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {max(2.0, h * 0.32)}]);\n"
            f"  translate([{w/2}, {d/2}, {h * 0.32}]) cylinder(h={h * 0.68}, r={min(w,d)*0.18}, center=false);\n"
            "}\n"
        )
    elif template in ("wall_plate",):
        screw_r = max(1.5, hole / 2)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2}, {-0.1}, {h * 0.25}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={screw_r}, center=false);\n"
            f"  translate([{w/2}, {-0.1}, {h * 0.75}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={screw_r}, center=false);\n"
            f"  translate([{wall}, {d * 0.45}, {h * 0.15}]) cube([{w - 2*wall}, {d}, {h * 0.18}]);\n"
            "}\n"
        )
    elif template in ("object_mount_half",):
        rail = max(2.0, wall)
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {-rail}, {h * 0.18}]) cube([{w - 2*wall}, {rail}, {h * 0.18}]);\n"
            f"  translate([{wall}, {-rail}, {h * 0.64}]) cube([{w - 2*wall}, {rail}, {h * 0.18}]);\n"
            "}\n"
        )
    elif template in ("key_hook_bar",):
        hook_r = max(2.0, r)
        body = "union() {\n"
        body += f"  cube([{w}, {max(2.0, wall)}, {max(4.0, h * 0.25)}]);\n"
        for i in range(4):
            x = w * (0.15 + i * 0.23)
            body += f"  translate([{x}, {d * 0.45}, {h * 0.14}]) rotate([90,0,0]) cylinder(h={d * 0.78}, r={hook_r}, center=false);\n"
        body += "}\n"
    elif template in ("screw_clearance_coupon",):
        screw_r = max(1.5, hole / 2)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.33}, {d/2}, -0.1]) cylinder(h={h + 0.2}, r={screw_r}, center=false);\n"
            f"  translate([{w * 0.70}, {d/2}, {h * 0.55}]) cylinder(h={h * 0.5}, r={screw_r * 1.8}, center=false);\n"
            "}\n"
        )
    elif template in ("load_test_bar",):
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.15},0,{h}]) cube([{w * 0.12}, {d}, {h * 0.55}]);\n"
            f"  translate([{w * 0.73},0,{h}]) cube([{w * 0.12}, {d}, {h * 0.55}]);\n"
            "}\n"
        )
    elif template in ("printer_tool_holder_rail",):
        slot = max(4.0, hole)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.08}, {d * 0.32}, -0.1]) cube([{w * 0.84}, {slot}, {h + 0.2}]);\n"
            f"  translate([{w * 0.12}, {-0.1}, {h * 0.42}]) cube([{w * 0.76}, {d + 0.2}, {slot * 0.55}]);\n"
            "}\n"
        )
    elif template in ("nozzle_slot_block",):
        hole_r = max(2.0, hole / 2)
        body = "difference() {\n"
        body += f"  cube([{w}, {d}, {h}]);\n"
        for i in range(5):
            body += f"  translate([{w * (0.14 + i * 0.18)}, {d/2}, -0.1]) cylinder(h={h + 0.2}, r={hole_r}, center=false);\n"
        body += "}\n"
    elif template in ("hex_key_rack",):
        body = "difference() {\n"
        body += f"  cube([{w}, {d}, {h}]);\n"
        for i in range(6):
            body += f"  translate([{w * (0.10 + i * 0.15)}, {d * 0.20}, {h * 0.35}]) cube([{max(1.4, wall * 0.7 + i * 0.25)}, {d}, {h}]);\n"
        body += "}\n"
    elif template in ("scraper_hook",):
        body = (
            "union() {\n"
            f"  cube([{w}, {max(3.0, wall)}, {h}]);\n"
            f"  translate([0,{d * 0.55},0]) cube([{w}, {max(3.0, wall)}, {h * 0.28}]);\n"
            f"  translate([0,{d * 0.55},{h * 0.28}]) cube([{max(3.0, wall)}, {max(3.0, wall)}, {h * 0.45}]);\n"
            "}\n"
        )
    elif template in ("rail_fit_coupon",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {d * 0.35}, -0.1]) cube([{w - 2*wall}, {max(3.0, hole)}, {h + 0.2}]);\n"
            "}\n"
        )
    elif template in ("stackable_crate_body", "screw_compartment_box"):
        lip = max(1.0, wall * 0.65)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    cube([{w}, {d}, {h}]);\n"
            f"    translate([{wall}, {wall}, {h}]) cube([{w - 2*wall}, {d - 2*wall}, {lip}]);\n"
            "  }\n"
            f"  translate([{wall}, {wall}, {wall}]) cube([{max(1, w - 2*wall)}, {max(1, d - 2*wall)}, {h + lip + 0.2}]);\n"
            "}\n"
        )
    elif template in ("crate_mesh_side",):
        body = "union() {\n"
        body += f"  difference() {{ cube([{w}, {d}, {h}]); translate([{wall}, {wall}, {wall}]) cube([{w - 2*wall}, {d - 2*wall}, {h + 0.2}]); }}\n"
        for x in range(1, 5):
            body += f"  translate([{x * w / 5},0,0]) cube([{wall}, {d}, {h}]);\n"
        for z in range(1, 4):
            body += f"  translate([0,0,{z * h / 4}]) cube([{w}, {d}, {wall}]);\n"
        body += "}\n"
    elif template in ("storage_divider",):
        body = f"cube([{w}, {max(0.8, d)}, {h}]);\n"
    elif template in ("label_tab",):
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.08}, {d}, 0]) cube([{w * 0.84}, {max(0.8, wall)}, {h}]);\n"
            "}\n"
        )
    elif template in ("stacking_lip_coupon",):
        body = (
            "union() {\n"
            f"  difference() {{ cube([{w * 0.46}, {d}, {h}]); translate([{wall}, {wall}, {wall}]) cube([{w * 0.46 - 2*wall}, {d - 2*wall}, {h}]); }}\n"
            f"  translate([{w * 0.54},0,0]) cube([{w * 0.46}, {d}, {h * 0.55}]);\n"
            "}\n"
        )
    elif template in ("pegboard_base_plate",):
        peg_r = max(2.0, hole / 2)
        body = "difference() {\n"
        body += f"  cube([{w}, {d}, {h}]);\n"
        for ix in range(4):
            for iz in range(3):
                body += f"  translate([{w * (0.18 + ix * 0.21)}, {-0.1}, {h * (0.20 + iz * 0.30)}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={peg_r}, center=false);\n"
        body += "}\n"
    elif template in ("peg_hook_module",):
        peg_r = max(2.0, hole / 2)
        body = (
            "union() {\n"
            f"  cube([{w}, {max(2.4, wall)}, {h}]);\n"
            f"  translate([{w * 0.28}, {-d * 0.30}, {h * 0.68}]) rotate([-90,0,0]) cylinder(h={d * 0.42}, r={peg_r}, center=false);\n"
            f"  translate([{w * 0.72}, {-d * 0.30}, {h * 0.68}]) rotate([-90,0,0]) cylinder(h={d * 0.42}, r={peg_r}, center=false);\n"
            f"  translate([{w * 0.50}, {d * 0.15}, {h * 0.25}]) rotate([0,90,0]) cylinder(h={w * 0.46}, r={max(2.0, wall)}, center=true);\n"
            "}\n"
        )
    elif template in ("peg_box_module",):
        peg_r = max(2.0, hole / 2)
        body = (
            "union() {\n"
            f"  difference() {{ cube([{w}, {d}, {h}]); translate([{wall}, {wall}, {wall}]) cube([{w - 2*wall}, {d - 2*wall}, {h}]); }}\n"
            f"  translate([{w * 0.25}, {-peg_r}, {h * 0.70}]) rotate([-90,0,0]) cylinder(h={d * 0.25}, r={peg_r}, center=false);\n"
            f"  translate([{w * 0.75}, {-peg_r}, {h * 0.70}]) rotate([-90,0,0]) cylinder(h={d * 0.25}, r={peg_r}, center=false);\n"
            "}\n"
        )
    elif template in ("peg_caliper_holder",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w * 0.20}, {wall}, {h * 0.18}]) cube([{w * 0.60}, {d}, {h * 0.62}]);\n"
            f"  translate([{w * 0.18}, {-0.1}, {h * 0.78}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={max(2.0, hole/2)}, center=false);\n"
            f"  translate([{w * 0.82}, {-0.1}, {h * 0.78}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={max(2.0, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("peg_flashlight_clip",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2}, {d/2}, {h/2}]) rotate([90,0,0]) cylinder(h={d + 0.2}, r={r}, center=true);\n"
            f"  translate([{w/2}, {-0.1}, {h * 0.82}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={max(2.0, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("peg_spacing_coupon",):
        peg_r = max(2.0, hole / 2)
        spacing = 25.4
        body = (
            "union() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{w/2 - spacing/2}, {-d * 0.35}, {h * 0.55}]) rotate([-90,0,0]) cylinder(h={d * 0.45}, r={peg_r}, center=false);\n"
            f"  translate([{w/2 + spacing/2}, {-d * 0.35}, {h * 0.55}]) rotate([-90,0,0]) cylinder(h={d * 0.45}, r={peg_r}, center=false);\n"
            "}\n"
        )
    elif template in ("perforated_basket_shell",):
        hole_r = max(2.0, hole / 2)
        body = "difference() {\n"
        body += f"  cube([{w}, {d}, {h}]);\n"
        body += f"  translate([{wall}, {wall}, {wall}]) cube([{w - 2*wall}, {d - 2*wall}, {h + 0.2}]);\n"
        for ix in range(1, 6):
            for iz in range(1, 4):
                body += f"  translate([{ix * w / 6}, {-0.1}, {iz * h / 5}]) rotate([-90,0,0]) cylinder(h={d + 0.2}, r={hole_r}, center=false);\n"
        body += "}\n"
    elif template in ("basket_handle",):
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}]);\n"
            f"  translate([{wall}, {-0.1}, {wall}]) cube([{w - 2*wall}, {d + 0.2}, {h - 2*wall}]);\n"
            "}\n"
        )
    elif template in ("rib_strength_coupon",):
        body = "union() {\n"
        for i in range(5):
            body += f"  translate([{i * w / 5},0,0]) cube([{wall}, {d}, {h}]);\n"
        body += f"  translate([0,{d/2 - wall/2},{h/2 - wall/2}]) cube([{w}, {wall}, {wall}]);\n"
        body += "}\n"
    elif template in ("winged_body_statue",):
        pin_r = max(1.5, hole / 2)
        body = (
            "union() {\n"
            f"  translate([0,0,{h * 0.32}]) scale([{w/(2*r)}, {d/(2*r)}, {h/(2.8*r)}]) sphere(r={r});\n"
            f"  translate([0,0,{h * 0.68}]) scale([{w/(2.5*r)}, {d/(2.3*r)}, {h/(4.0*r)}]) sphere(r={r});\n"
            f"  translate([{w * 0.36},0,{h * 0.52}]) rotate([0,90,0]) cylinder(h={wall * 2.2}, r={pin_r}, center=false);\n"
            f"  translate([{-w * 0.36},0,{h * 0.52}]) rotate([0,-90,0]) cylinder(h={wall * 2.2}, r={pin_r}, center=false);\n"
            "}\n"
        )
    elif template in ("wing_pair_split",):
        body = "union() {\n"
        for side in (-1, 1):
            body += f"  translate([{side * w * 0.20},0,0]) linear_extrude(height={max(1.0, d)}) polygon(points=[[0,0],[{side * w * 0.30},{h * 0.92}],[{side * w * 0.48},{h * 0.08}]]);\n"
            body += f"  translate([{side * w * 0.08},0,{h * 0.18}]) rotate([90,0,0]) cylinder(h={d}, r={max(1.5, hole/2)}, center=true);\n"
        body += "}\n"
    elif template in ("tail_segment",):
        body = (
            "hull() {\n"
            f"  sphere(r={max(2.0, d * 0.35)});\n"
            f"  translate([{w},0,{h * 0.25}]) sphere(r={max(1.2, d * 0.18)});\n"
            "}\n"
        )
    elif template in ("creature_base",):
        body = (
            "difference() {\n"
            f"  scale([1,{max(0.4, d/max(w,1))},1]) cylinder(h={h}, r={w/2}, $fn=18, center=false);\n"
            f"  translate([{w * 0.18},0,{h - wall}]) cylinder(h={wall + 0.2}, r={max(1.5, hole/2)}, center=false);\n"
            f"  translate([{-w * 0.18},0,{h - wall}]) cylinder(h={wall + 0.2}, r={max(1.5, hole/2)}, center=false);\n"
            "}\n"
        )
    elif template in ("support_scar_coupon",):
        body = (
            "union() {\n"
            f"  cube([{w * 0.32}, {d}, {wall}]);\n"
            f"  translate([{w * 0.26},0,{wall}]) rotate([0,-24,0]) cube([{w * 0.62}, {d}, {wall}]);\n"
            f"  translate([{w * 0.72},0,0]) cube([{wall}, {d}, {h}]);\n"
            "}\n"
        )
    elif template in ("airliner_fuselage_shell",):
        length = max(w, h * 3.5)
        rad = max(6.0, min(d, h) * 0.5)
        socket = max(1.8, hole / 2.0)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    rotate([0,90,0]) cylinder(h={length * 0.76}, r={rad}, center=true);\n"
            f"    translate([{length * 0.38},0,0]) scale([1.25,1,1]) sphere(r={rad});\n"
            f"    translate([{-length * 0.43},0,0]) scale([1.8,0.78,0.78]) sphere(r={rad});\n"
            f"    translate([{length * 0.10},{-rad * 0.55},{-rad * 0.92}]) cube([{length * 0.12}, {rad * 1.1}, {wall * 1.8}]);\n"
            "  }\n"
            f"  translate([0,0,{-rad * 0.92}]) rotate([90,0,0]) cylinder(h={d + 2}, r={socket}, center=true);\n"
            f"  translate([{length * 0.18},0,{-rad * 0.98}]) cube([{length * 0.18}, {d + 2}, {wall * 2.4}], center=true);\n"
            "}\n"
        )
    elif template in ("airliner_fuselage_section",):
        section = str(p.get("section") or "fwd").lower()
        length = max(w, h * 3.2)
        rad = max(6.0, min(d, h) * 0.5)
        socket = max(1.8, hole / 2.0)
        if section == "aft":
            body = (
                "difference() {\n"
                "  union() {\n"
                f"    rotate([0,90,0]) translate([{-length * 0.22},0,0]) "
                f"cylinder(h={length * 0.44}, r={rad * 0.96}, center=true);\n"
                f"    translate([{-length * 0.43},0,0]) scale([1.7,0.78,0.78]) sphere(r={rad * 0.92});\n"
                "  }\n"
                f"  translate([{-length * 0.08},0,{-rad * 0.9}]) "
                f"cube([{length * 0.16}, {d + 2}, {wall * 2.2}], center=true);\n"
                "}\n"
            )
        else:
            body = (
                "difference() {\n"
                "  union() {\n"
                f"    rotate([0,90,0]) translate([{length * 0.18},0,0]) "
                f"cylinder(h={length * 0.52}, r={rad}, center=true);\n"
                f"    translate([{length * 0.38},0,0]) scale([1.22,1,1]) sphere(r={rad * 1.02});\n"
                f"    translate([{length * 0.10},{-rad * 0.55},{-rad * 0.92}]) "
                f"cube([{length * 0.12}, {rad * 1.1}, {wall * 1.8}]);\n"
                "  }\n"
                f"  translate([0,0,{-rad * 0.92}]) rotate([90,0,0]) cylinder(h={d + 2}, r={socket}, center=true);\n"
                "}\n"
            )
    elif template in ("airliner_wing_half",):
        side = str(p.get("side") or "left").lower()
        half_span = max(30.0, w * 0.47)
        chord = max(18.0, d)
        thick = max(1.2, h)
        tab = max(5.0, hole * 1.6)
        mirror = "" if side == "left" else "mirror([1,0,0]) "
        body = (
            "union() {\n"
            f"  {mirror}linear_extrude(height={thick}) "
            f"polygon(points=[[0,0],[{half_span},{chord * 0.18}],"
            f"[{half_span * 0.82},{chord * 0.54}],[0,{chord * 0.30}]]);\n"
            f"  translate([{-tab/2},{chord * 0.10},{thick}]) cube([{tab}, {chord * 0.22}, {max(1.2, wall)}]);\n"
            f"  translate([{half_span * 0.34},{chord * 0.20},{thick}]) "
            f"cube([{wall * 2.4}, {chord * 0.20}, {max(1.0, wall * 0.7)}]);\n"
            "}\n"
        )
    elif template in ("airliner_vert_stab",):
        thick = max(1.2, d)
        body = (
            "union() {\n"
            f"  linear_extrude(height={thick}) polygon(points=[[0,0],[{w * 0.18},{h}],[{w * 0.44},{h * 0.12}]]);\n"
            f"  translate([0,0,0]) cube([{max(4.0, hole * 1.4)}, {thick}, {max(1.2, wall)}]);\n"
            "}\n"
        )
    elif template in ("airliner_horz_stab_half",):
        side = str(p.get("side") or "left").lower()
        thick = max(1.2, d)
        mirror = "" if side == "left" else "mirror([1,0,0]) "
        body = (
            f"{mirror}translate([{w * 0.25},0,{h * 0.10}]) rotate([0,0,16]) "
            f"cube([{w * 0.42}, {thick}, {max(1.2, wall)}]);\n"
        )
    elif template in ("airliner_engine_pod_single",):
        pod_r = max(4.0, r)
        pod_len = max(12.0, d * 0.42)
        axle_r = max(0.7, hole / 2.0)
        x_off = float(p.get("x_offset_mm") or 0.0)
        body = (
            "union() {\n"
            f"  translate([{x_off},0,0]) rotate([90,0,0]) difference() {{ "
            f"cylinder(h={pod_len}, r={pod_r}, center=true); "
            f"cylinder(h={pod_len + 0.4}, r={max(1.0, pod_r - wall)}, center=true); }}\n"
            f"  translate([{x_off},{-pod_len/2 - wall * 0.5},0]) "
            f"cylinder(h={max(1.0, wall * 1.2)}, r={pod_r * 0.92}, center=true);\n"
            f"  translate([{x_off},{-pod_len/2 - wall * 0.2},0]) "
            f"rotate([90,0,0]) cylinder(h={wall * 2.5}, r={axle_r * 1.25}, center=true);\n"
            "}\n"
        )
    elif template in ("airliner_fan_rotor_single",):
        fan_r = max(5.0, r)
        axle_r = max(0.6, hole / 2.0)
        x_off = float(p.get("x_offset_mm") or 0.0)
        body = "union() {\n"
        body += f"  translate([{x_off},0,0]) cylinder(h={h}, r={fan_r * 0.92}, center=false);\n"
        for blade in range(6):
            body += (
                f"  translate([{x_off},{fan_r * 0.22},{h}]) rotate([0,0,{blade * 60}]) "
                f"cube([{fan_r * 0.55}, {max(0.65, wall * 0.5)}, {max(0.65, wall * 0.45)}], center=true);\n"
            )
        body += (
            f"  translate([{x_off},0,{-wall * 0.4}]) "
            f"cylinder(h={wall}, r={axle_r}, center=false);\n"
        )
        body += "}\n"
    elif template in ("airliner_wing_pair_swept",):
        half_span = max(30.0, w * 0.47)
        chord = max(18.0, d)
        thick = max(1.2, h)
        tab = max(5.0, hole * 1.6)
        body = (
            "union() {\n"
            f"  linear_extrude(height={thick}) polygon(points=[[0,0],[{half_span},{chord * 0.18}],[{half_span * 0.82},{chord * 0.54}],[0,{chord * 0.30}]]);\n"
            f"  mirror([1,0,0]) linear_extrude(height={thick}) polygon(points=[[0,0],[{half_span},{chord * 0.18}],[{half_span * 0.82},{chord * 0.54}],[0,{chord * 0.30}]]);\n"
            f"  translate([{-tab/2},{chord * 0.10},{thick}]) cube([{tab}, {chord * 0.22}, {max(1.2, wall)}]);\n"
            f"  translate([{half_span * 0.34},{chord * 0.20},{thick}]) cube([{wall * 2.4}, {chord * 0.20}, {max(1.0, wall * 0.7)}]);\n"
            f"  translate([{-half_span * 0.34},{chord * 0.20},{thick}]) cube([{wall * 2.4}, {chord * 0.20}, {max(1.0, wall * 0.7)}]);\n"
            "}\n"
        )
    elif template in ("airliner_tail_set",):
        thick = max(1.2, d)
        body = (
            "union() {\n"
            f"  linear_extrude(height={thick}) polygon(points=[[0,0],[{w * 0.18},{h}],[{w * 0.44},{h * 0.12}]]);\n"
            f"  translate([{w * 0.25},0,{h * 0.10}]) rotate([0,0,16]) cube([{w * 0.42}, {thick}, {max(1.2, wall)}]);\n"
            f"  translate([{w * 0.25},0,{h * 0.10}]) rotate([0,0,-16]) mirror([1,0,0]) cube([{w * 0.42}, {thick}, {max(1.2, wall)}]);\n"
            f"  translate([0,0,0]) cube([{max(4.0, hole * 1.4)}, {thick}, {max(1.2, wall)}]);\n"
            "}\n"
        )
    elif template in ("airliner_engine_pod_fan_set",):
        pod_r = max(4.0, r)
        pod_len = max(12.0, d * 0.42)
        body = "union() {\n"
        for i, x in enumerate((-w * 0.36, -w * 0.12, w * 0.12, w * 0.36)):
            body += f"  translate([{x},0,0]) rotate([90,0,0]) difference() {{ cylinder(h={pod_len}, r={pod_r}, center=true); cylinder(h={pod_len + 0.4}, r={max(1.0, pod_r - wall)}, center=true); }}\n"
            body += f"  translate([{x},{-pod_len/2 - wall * 0.6},0]) cylinder(h={max(1.0, wall)}, r={pod_r * 0.84}, center=true);\n"
            for blade in range(6):
                body += f"  translate([{x},{-pod_len/2 - wall * 1.1},0]) rotate([0,{blade * 60},0]) cube([{pod_r * 0.72}, {max(0.7, wall * 0.45)}, {max(0.7, wall * 0.45)}], center=true);\n"
        body += "}\n"
    elif template in ("airliner_folding_gear_set",):
        pin_r = max(1.0, hole / 2.0)
        body = "union() {\n"
        for i, x in enumerate((-w * 0.32, 0, w * 0.32)):
            arm_len = h * (2.0 if i == 1 else 2.6)
            body += f"  translate([{x},0,0]) cylinder(h={max(3.0, wall * 2)}, r={pin_r * 1.8}, center=false);\n"
            body += f"  translate([{x},{d * 0.18},{wall}]) rotate([18,0,0]) cube([{max(2.0, wall)}, {arm_len}, {max(2.0, wall)}], center=true);\n"
            body += f"  translate([{x},{d * 0.42},{wall}]) rotate([90,0,0]) cylinder(h={d * 0.28}, r={pin_r}, center=true);\n"
        body += "}\n"
    elif template in ("airliner_wheel_axle_set",):
        wheel_r = max(2.4, r)
        axle_r = max(0.8, hole / 2.0)
        body = "union() {\n"
        for i in range(6):
            x = i * (wheel_r * 2.6)
            body += f"  translate([{x},0,0]) rotate([90,0,0]) difference() {{ cylinder(h={max(2.2, d * 0.28)}, r={wheel_r}, center=true); cylinder(h={d}, r={axle_r * 1.15}, center=true); }}\n"
        for i in range(5):
            body += f"  translate([{i * (wheel_r * 2.6)}, {d * 0.45}, 0]) rotate([90,0,0]) cylinder(h={d * 0.75}, r={axle_r}, center=true);\n"
        body += "}\n"
    elif template in ("airliner_fan_blade_coupon",):
        fan_r = max(5.0, r)
        body = "union() {\n"
        body += f"  cylinder(h={h}, r={fan_r}, center=false);\n"
        for blade in range(8):
            body += f"  rotate([0,0,{blade * 45}]) translate([{fan_r * 0.28}, {-wall/2}, {h}]) cube([{fan_r * 0.62}, {max(0.7, wall)}, {max(0.7, wall * 0.7)}]);\n"
        body += "}\n"
    elif template in ("airliner_nose_cap",):
        body = (
            "union() {\n"
            f"  scale([1.35,1,1]) sphere(r={max(8.0, w * 0.42)});\n"
            f"  translate([{-w * 0.22},0,0]) cylinder(h={max(4.0, d * 0.35)}, r={max(5.0, h * 0.22)}, center=true);\n"
            "}\n"
        )
    elif template in ("airliner_gear_strut",):
        pin_r = max(1.0, hole / 2.0)
        arm = max(18.0, h)
        body = (
            "union() {\n"
            f"  cylinder(h={max(3.5, wall * 2.2)}, r={pin_r * 2.0}, center=false);\n"
            f"  translate([0,{d * 0.22},{wall}]) rotate([22,0,0]) cube([{max(2.2, wall)}, {arm}, {max(2.2, wall)}], center=true);\n"
            f"  translate([0,{d * 0.48},{wall}]) rotate([90,0,0]) cylinder(h={d * 0.32}, r={pin_r}, center=true);\n"
            f"  translate([0,{d * 0.62},0]) rotate([90,0,0]) difference() {{"
            f"cylinder(h={max(2.0, d * 0.22)}, r={max(2.4, r)}, center=true); "
            f"cylinder(h={d}, r={pin_r * 1.1}, center=true); }}\n"
            "}\n"
        )
    elif template in ("airliner_engine_pod_shell",):
        pod_r = max(4.0, r)
        pod_len = max(12.0, d * 0.42)
        axle_r = max(0.7, hole / 2.0)
        body = "union() {\n"
        for x in (-w * 0.36, -w * 0.12, w * 0.12, w * 0.36):
            body += (
                f"  translate([{x},0,0]) rotate([90,0,0]) difference() {{ "
                f"cylinder(h={pod_len}, r={pod_r}, center=true); "
                f"cylinder(h={pod_len + 0.4}, r={max(1.0, pod_r - wall)}, center=true); }}\n"
            )
            body += (
                f"  translate([{x},{-pod_len/2 - wall * 0.5},0]) "
                f"cylinder(h={max(1.0, wall * 1.2)}, r={pod_r * 0.92}, center=true);\n"
            )
            body += (
                f"  translate([{x},{-pod_len/2 - wall * 0.2},0]) "
                f"rotate([90,0,0]) cylinder(h={wall * 2.5}, r={axle_r * 1.25}, center=true);\n"
            )
        body += "}\n"
    elif template in ("airliner_fan_rotor_revolute",):
        fan_r = max(5.0, r)
        axle_r = max(0.6, hole / 2.0)
        body = "union() {\n"
        for i, x in enumerate((-w * 0.36, -w * 0.12, w * 0.12, w * 0.36)):
            body += f"  translate([{x},0,0]) cylinder(h={h}, r={fan_r * 0.92}, center=false);\n"
            for blade in range(6):
                body += (
                    f"  translate([{x},{fan_r * 0.22},{h}]) rotate([0,0,{blade * 60}]) "
                    f"cube([{fan_r * 0.55}, {max(0.65, wall * 0.5)}, {max(0.65, wall * 0.45)}], center=true);\n"
                )
            body += (
                f"  translate([{x},0,{-wall * 0.4}]) "
                f"cylinder(h={wall}, r={axle_r}, center=false);\n"
            )
        body += "}\n"
    elif template in ("airliner_wheel_revolute",):
        wheel_r = max(2.4, r)
        axle_r = max(0.7, hole / 2.0)
        body = "union() {\n"
        for i, x in enumerate((0, w * 0.34, w * 0.68)):
            wr = wheel_r * (0.92 if i == 0 else 1.0)
            body += (
                f"  translate([{x},0,0]) rotate([90,0,0]) difference() {{ "
                f"cylinder(h={max(2.4, d * 0.3)}, r={wr}, center=true); "
                f"cylinder(h={d}, r={axle_r * 1.12}, center=true); }}\n"
            )
        body += "}\n"
    elif template in ("airliner_wheel_fit_coupon",):
        wheel_r = max(2.4, r)
        axle_r = max(0.7, hole / 2.0)
        socket_r = axle_r * 1.18
        body = (
            "union() {\n"
            f"  difference() {{ cylinder(h={h}, r={wheel_r}, center=false); "
            f"translate([0,0,-0.2]) cylinder(h={h+0.4}, r={axle_r*1.05}, center=false); }}\n"
            f"  translate([{wheel_r * 1.8},0,{h/2}]) rotate([90,0,0]) "
            f"difference() {{ cylinder(h={d}, r={socket_r}, center=true); "
            f"cylinder(h={d+0.2}, r={axle_r}, center=true); }}\n"
            "}\n"
        )
    elif template in ("tube_clip", "clip"):
        gap = _num(p.get("gap_mm"), 1.2)
        body = (
            "difference() {\n"
            f"  cube([{w}, {d}, {h}], center=true);\n"
            f"  translate([0, 0, {gap / 2}])\n"
            f"    cylinder(h={h}, r={r + gap / 2}, center=true);\n"
            "}\n"
        )
    elif template in ("bottle_handle", "handle", "grip"):
        neck_r = _num(p.get("neck_radius_mm") or p.get("radius_mm"), 26)
        grip_w = _num(p.get("width_mm"), 120)
        grip_h = _num(p.get("height_mm"), 25)
        grip_t = _num(p.get("depth_mm") or p.get("wall_mm"), 8)
        body = (
            "difference() {\n"
            "  union() {\n"
            f"    translate([{-grip_w / 2}, {-grip_t / 2}, 0]) cube([{grip_w}, {grip_t}, {grip_h}]);\n"
            f"    translate([0, 0, {grip_h / 2}]) rotate([90, 0, 0]) "
            f"cylinder(h={grip_t + 2}, r={neck_r + 3}, center=true);\n"
            "  }\n"
            f"  translate([0, 0, -0.1]) cylinder(h={grip_h + 20}, r={neck_r}, center=false);\n"
            "}\n"
        )
    else:
        body = f"cube([{w}, {d}, {h}]);\n"

    if hole > 0:
        body = (
            "difference() {\n"
            f"  {body.rstrip()}\n"
            f"  translate([{w/2}, {d/2}, -0.1]) cylinder(h={h + 0.2}, r={hole/2}, center=false);\n"
            "}\n"
        )

    return header + body


async def export_stl_from_scad(scad_bytes: bytes, stl_path: Path) -> bool:
    if not openscad_available():
        return False
    scad_path = stl_path.with_suffix(".scad")
    scad_path.write_bytes(scad_bytes)
    try:
        proc = await asyncio.create_subprocess_exec(
            OPENSCAD_BIN,
            "-o",
            str(stl_path),
            str(scad_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            logger.warning("OpenSCAD export failed: %s", err.decode()[:300])
            return False
        return stl_path.is_file() and stl_path.stat().st_size > 0
    except Exception as e:
        logger.warning("OpenSCAD: %s", e)
        return False


def build_bom_csv(parts: List[Dict[str, Any]]) -> str:
    lines = ["part_id,name,material,qty,notes"]
    for idx, p in enumerate(parts, start=1):
        pid = sanitize_id(str(p.get("id") or p.get("name") or f"part-{idx:02d}"))
        name = str(p.get("name") or pid).replace(",", ";")
        mat = str(p.get("material") or "PETG").replace(",", ";")
        notes = str(p.get("purpose") or p.get("description") or "").replace(",", ";")[:120]
        lines.append(f"{pid},{name},{mat},1,{notes}")
    return "\n".join(lines) + "\n"


def build_print_plan(parts: List[Dict[str, Any]], profile: Dict[str, Any]) -> str:
    from bot.services.print_profile import format_profile

    lines = [
        "ПЛАН ПЕЧАТИ",
        "===========",
        format_profile(profile),
        "",
    ]
    for idx, p in enumerate(parts, start=1):
        lines.append(f"--- Кадр {idx}: {p.get('name') or p.get('id')} ---")
        lines.append(f"Файл SCAD: scad/{sanitize_id(str(p.get('id') or p.get('name') or idx))}.scad")
        if p.get("stl_included"):
            lines.append(f"Файл STL:  stl/{sanitize_id(str(p.get('id') or p.get('name') or idx))}.stl")
        lines.append(f"Материал: {p.get('material') or 'PETG'}")
        lines.append(f"Ориентация: {p.get('orientation') or 'как удобнее, без больших свесов'}")
        lines.append(f"Назначение: {p.get('purpose') or p.get('description') or '—'}")
        if p.get("assembly_step"):
            lines.append(f"Сборка: {p['assembly_step']}")
        lines.append("")
    lines.append(
        "Откройте .scad в OpenSCAD (F6) → File → Export → STL,\n"
        "или используйте уже приложенные .stl если OpenSCAD установлен на сервере бота."
    )
    return "\n".join(lines)


def build_assembly_md(project_name: str, parts: List[Dict[str, Any]]) -> str:
    lines = [f"# Сборка: {project_name}", ""]
    for idx, p in enumerate(parts, start=1):
        lines.append(f"## {idx}. {p.get('name') or p.get('id')}")
        lines.append(p.get("purpose") or p.get("description") or "Деталь проекта.")
        if p.get("assembly_step"):
            lines.append(f"\n**Шаг сборки:** {p['assembly_step']}")
        lines.append("")
    lines.append("---")
    lines.append("Порядок: печать всех деталей → проверка размеров → сборка по шагам выше.")
    return "\n".join(lines)
