"""Print tolerances learned from reference library categories."""

from __future__ import annotations

from typing import Any, Dict

# mm — typical FDM clearance from community kits (conservative for Bambu).
CATEGORY_TOLERANCES: Dict[str, Dict[str, float]] = {
    "rc_aircraft": {"fit_coupon": 0.2, "pin": 0.2, "hinge": 0.25, "snap": 0.35, "default": 0.3},
    "drone_fpv": {"fit_coupon": 0.2, "arm_joint": 0.25, "default": 0.25},
    "vehicle_rc": {"wheel_axle": 0.25, "snap": 0.35, "default": 0.3},
    "robot_mechanism": {"pin": 0.2, "gripper": 0.25, "default": 0.25},
    "mechanical_gear": {"gear_mesh": 0.15, "bearing": 0.2, "default": 0.2},
    "kit_card": {"tab": 0.15, "default": 0.2},
    "architecture_miniature": {"facade": 0.15, "default": 0.2},
    "articulated_wearable": {"joint": 0.3, "default": 0.3},
    "character_sculpt": {"keyed_split": 0.35, "default": 0.35},
    "general_kit": {"default": 0.3},
}


def tolerance_mm_for_role(category: str, role: str) -> float:
    table = CATEGORY_TOLERANCES.get(category) or CATEGORY_TOLERANCES["general_kit"]
    if role in table:
        return table[role]
    if role in {"pin", "axle", "wheel", "landing_gear", "rotor"}:
        return table.get("pin", table["default"])
    if role in {"fuselage", "wing", "container", "link"}:
        return table.get("snap", table["default"])
    return table["default"]


def meshy_tolerance_prompt(category: str) -> str:
    t = CATEGORY_TOLERANCES.get(category) or CATEGORY_TOLERANCES["general_kit"]
    d = t.get("default", 0.3)
    return (
        f"printable clearances about {d:.2f} mm between mating parts, "
        "thick walls, no paper-thin details, FDM-friendly"
    )


def apply_tolerances_to_blueprint(profile: Dict[str, Any]) -> Dict[str, Any]:
    cat = profile.get("category") or "general_kit"
    out = dict(profile)
    parts = []
    for p in profile.get("parts") or []:
        pc = dict(p)
        pc["tolerance_mm"] = tolerance_mm_for_role(cat, pc.get("role") or "generic")
        parts.append(pc)
    out["parts"] = parts
    out["category_tolerances"] = CATEGORY_TOLERANCES.get(cat, CATEGORY_TOLERANCES["general_kit"])
    return out
