"""Extract part geometry and naming from reference STL kits."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference_models"

ROLE_PATTERNS: List[Tuple[str, str]] = [
    (r"fuselage|fuse|body_tub|hull|chassis|корпус", "fuselage"),
    (r"wing|крыл", "wing"),
    (r"vert|rudder|киль|tail_fin", "vert_stab"),
    (r"horz|elevator|stabilizer|стаб", "horz_stab"),
    (r"engine|motor|pod|nacelle|двиг", "engine"),
    (r"fan|prop|rotor|blade|лопаст|винт", "rotor"),
    (r"landing|gear|шасси|strut", "landing_gear"),
    (r"wheel|tire|tyre|rim|колес", "wheel"),
    (r"pin|axle|shaft|ось|штифт", "pin"),
    (r"gear|шестерн|planet|pinion", "gear"),
    (r"arm|link|звен", "link"),
    (r"gripper|jaw|клешн|claw", "gripper"),
    (r"base|stand|подстав", "base"),
    (r"lid|cover|крыш", "lid"),
    (r"box|crate|basket|короб|ящик", "container"),
]


def _slugify_id(stem: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    s = re.sub(r"_+", "_", s)
    return (s[:48] or "part")


def _human_name(stem: str) -> str:
    s = re.sub(r"[_\-]+", " ", stem).strip()
    return s[:80] if s else "Деталь"


def stl_bbox_mm(path: Path) -> Optional[Tuple[float, float, float]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 84 or data[:5] == b"solid":
        return None
    n = struct.unpack_from("<I", data, 80)[0]
    if n <= 0 or 84 + n * 50 > len(data):
        return None
    xs, ys, zs = [], [], []
    off = 84
    for _ in range(min(n, 12000)):
        vals = struct.unpack_from("<12f", data, off)
        xs.extend(vals[0::3])
        ys.extend(vals[1::3])
        zs.extend(vals[2::3])
        off += 50
    if not xs:
        return None
    return (
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    )


def _detect_role(name: str) -> str:
    blob = name.lower()
    for pat, role in ROLE_PATTERNS:
        if re.search(pat, blob, re.I):
            return role
    return "generic"


def _template_for_role(role: str, sx: float, sy: float, sz: float, category: str) -> Tuple[str, Dict[str, float]]:
    sx, sy, sz = max(sx, 1.0), max(sy, 1.0), max(sz, 1.0)
    flat = sz <= min(sx, sy) * 0.35
    if role == "wing":
        return "airliner_wing_half", {"span_mm": max(sx, sy), "chord_mm": min(sx, sy), "wall_mm": 1.8}
    if role == "fuselage":
        if category in {"rc_aircraft", "mechanical_boeing_airliner"}:
            return "airliner_fuselage_section", {
                "length_mm": max(sx, sy, sz),
                "radius_mm": min(sx, sy) / 2,
                "wall_mm": 2.0,
            }
        return "vehicle_body_tub", {
            "width_mm": sx,
            "depth_mm": sy,
            "height_mm": sz,
            "wall_mm": 2.0,
        }
    if role == "vert_stab":
        return "airliner_vert_stab", {"height_mm": sz, "chord_mm": max(sx, sy), "wall_mm": 1.6}
    if role == "horz_stab":
        return "airliner_horz_stab_half", {"span_mm": max(sx, sy), "chord_mm": min(sx, sy), "wall_mm": 1.6}
    if role == "engine":
        return "airliner_engine_pod_single", {
            "length_mm": max(sx, sy, sz),
            "radius_mm": min(sx, sy) / 2,
            "wall_mm": 1.8,
        }
    if role == "rotor":
        return "airliner_fan_rotor_single", {
            "radius_mm": max(sx, sy) / 2,
            "height_mm": max(sz, 2),
            "wall_mm": 1.2,
        }
    if role in {"wheel", "pin"}:
        return "cylinder", {
            "radius_mm": max(min(sx, sy) / 2, 1.5),
            "height_mm": max(sz, sx, sy),
            "wall_mm": 1.2,
            "segments": 48,
        }
    if role == "gear":
        return "spur_gear", {"radius_mm": max(sx, sy) / 2, "height_mm": max(sz, 4), "wall_mm": 2.0}
    if role == "landing_gear":
        return "cylinder", {
            "radius_mm": max(min(sx, sy) / 2, 1.2),
            "height_mm": max(sz, sx),
            "wall_mm": 1.4,
            "segments": 24,
        }
    if role == "link":
        return "plate", {"width_mm": sx, "depth_mm": sy, "height_mm": max(sz, 8), "wall_mm": 2.0}
    if role in {"gripper", "container", "lid"}:
        return "hollow_box", {"width_mm": sx, "depth_mm": sy, "height_mm": sz, "wall_mm": 2.0}
    if role == "base" or flat:
        return "plate", {"width_mm": sx, "depth_mm": sy, "height_mm": max(sz, 3), "wall_mm": 2.0}
    return "hollow_box", {"width_mm": sx, "depth_mm": sy, "height_mm": sz, "wall_mm": 2.0}


def _scale_boxes(
    parts: List[Dict[str, Any]], target_max_mm: float = 180.0
) -> List[Dict[str, Any]]:
    max_dim = 0.0
    for p in parts:
        bb = p.get("bbox_mm") or {}
        max_dim = max(max_dim, float(bb.get("x", 0)), float(bb.get("y", 0)), float(bb.get("z", 0)))
    if max_dim < 1e-3:
        return parts
    factor = target_max_mm / max_dim
    out = []
    for p in parts:
        p = dict(p)
        bb = p.pop("bbox_mm", {})
        sx = float(bb.get("x", 10)) * factor
        sy = float(bb.get("y", 10)) * factor
        sz = float(bb.get("z", 10)) * factor
        role = p.get("role", "generic")
        cat = p.get("_category", "general_kit")
        tmpl, params = _template_for_role(role, sx, sy, sz, cat)
        p["template"] = tmpl
        p["params"] = params
        out.append(p)
    return out


def build_geometry_profile(slug: str, *, force: bool = False) -> Optional[Dict[str, Any]]:
    kit_dir = REF / slug
    if not kit_dir.is_dir():
        return None
    cache = kit_dir / "geometry_profile.json"
    if cache.is_file() and not force:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    stls = sorted(kit_dir.rglob("*.stl"))
    if not stls:
        return None
    manifest_path = kit_dir / "manifest.json"
    category = "general_kit"
    if manifest_path.is_file():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            category = m.get("category") or category
        except Exception:
            pass
    idx_path = REF / "library_index.json"
    if idx_path.is_file():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            for k in idx.get("kits") or []:
                if k.get("slug") == slug:
                    category = k.get("category") or category
                    break
        except Exception:
            pass

    raw_parts: List[Dict[str, Any]] = []
    for stl in stls[:32]:
        bb = stl_bbox_mm(stl)
        if not bb:
            continue
        stem = stl.stem
        role = _detect_role(stem)
        raw_parts.append(
            {
                "id": _slugify_id(stem),
                "name": _human_name(stem),
                "source_file": str(stl.relative_to(kit_dir)),
                "role": role,
                "_category": category,
                "bbox_mm": {"x": round(bb[0], 2), "y": round(bb[1], 2), "z": round(bb[2], 2)},
            }
        )
    if not raw_parts:
        return None
  # Largest parts first (main assemblies before hardware)
    raw_parts.sort(
        key=lambda p: -(p["bbox_mm"]["x"] * p["bbox_mm"]["y"] * p["bbox_mm"]["z"]),
    )
    scaled = _scale_boxes(raw_parts)
    for p in scaled:
        p.pop("_category", None)
    envelope = {"x": 0.0, "y": 0.0, "z": 0.0}
    for p in raw_parts:
        for ax in "xyz":
            envelope[ax] = max(envelope[ax], p["bbox_mm"][ax])
    profile = {
        "slug": slug,
        "category": category,
        "part_count": len(scaled),
        "envelope_mm": envelope,
        "parts": scaled,
        "roles_present": sorted({p["role"] for p in scaled}),
    }
    cache.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def parts_to_print_spec_parts(
    profile: Dict[str, Any],
    *,
    material: str = "PLA",
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in profile.get("parts") or []:
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "template": p["template"],
                "params": dict(p.get("params") or {}),
                "material": material,
                "orientation": "по референсу STL",
                "purpose": f"Роль: {p.get('role')}; файл: {p.get('source_file', '')}",
                "assembly_step": f"Собрать по engineering/reference_blueprint.json ({profile.get('slug')}).",
                "tolerance_mm": 0.25,
                "reference_source": p.get("source_file"),
                "reference_role": p.get("role"),
            }
        )
    return out


def try_build_specs_from_reference(
    text: str,
    *,
    slug: str,
    project_kind: str,
    strategy: str,
    project_name: str,
    requirements: List[str],
    category: str = "general_kit",
) -> Optional[Dict[str, Any]]:
    from bot.services.print_project import _with_print_contract

    profile = build_geometry_profile(slug)
    if not profile or profile.get("part_count", 0) < 3:
        return None
    parts = parts_to_print_spec_parts(profile)
    if len(parts) > 28:
        parts = parts[:28]
    reqs = list(requirements)
    reqs.insert(
        0,
        f"Blueprint из STL `{slug}`: {profile['part_count']} деталей, роли {', '.join(profile.get('roles_present') or [])}.",
    )
    return _with_print_contract(
        {
            "project_name": project_name,
            "requirements": reqs,
            "reference_blueprint": profile,
            "critical_dimensions": [
                {
                    "name": "габарит референса",
                    "value_mm": f"{profile['envelope_mm']['x']:.0f}×{profile['envelope_mm']['y']:.0f}×{profile['envelope_mm']['z']:.0f}",
                    "tolerance_mm": 2.0,
                },
            ],
            "parts": parts,
        },
        strategy=strategy,
        project_kind=project_kind,
    )
