"""Reference kit metadata derived from downloaded CLERX / community models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
CLERX_747SP_DIR = ROOT / "data" / "reference_models" / "clerx_boeing_747sp"

# Exploded layout groups (left-to-right in preview) — matches pro kit naming.
CLERX_747SP_EXPLODED_GROUPS: List[Tuple[str, List[str]]] = [
    ("fit_coupons", ["hinge_fit_coupon", "wheel_fit_coupon", "fan_blade_coupon"]),
    (
        "landing_gear",
        ["nose_gear_strut", "main_gear_left", "main_gear_right", "wheel_set", "axle_pin_set"],
    ),
    (
        "rotors_engines",
        [
            "fan_disc_L1",
            "fan_disc_R1",
            "fan_disc_L2",
            "fan_disc_R2",
            "engine_pod_L1",
            "engine_pod_L2",
            "engine_pod_R1",
            "engine_pod_R2",
        ],
    ),
    ("fuselage", ["fuselage_fwd", "fuselage_aft"]),
    ("wings", ["wing_left", "wing_right"]),
    ("tail", ["vert_stab", "horz_stab_left", "horz_stab_right"]),
    ("hardware", ["assembly_pin_set"]),
]

# Semantic pose offsets in fuselage frame (fractions of target length_mm).
# Tuned for 747SP proportions (short wide-body, four under-wing pods).
CLERX_747SP_POSE_OFFSETS: Dict[str, Dict[str, float]] = {
    "fuselage_fwd": {"x": 0.52, "y": 0.0, "z": 0.12},
    "fuselage_aft": {"x": 0.18, "y": 0.0, "z": 0.11},
    "wing_left": {"x": 0.42, "y": 0.38, "z": 0.14},
    "wing_right": {"x": 0.42, "y": -0.38, "z": 0.14},
    "vert_stab": {"x": 0.06, "y": 0.0, "z": 0.28},
    "horz_stab_left": {"x": 0.08, "y": 0.14, "z": 0.20},
    "horz_stab_right": {"x": 0.08, "y": -0.14, "z": 0.20},
    "engine_pod_L1": {"x": 0.40, "y": 0.30, "z": 0.05},
    "engine_pod_L2": {"x": 0.48, "y": 0.18, "z": 0.05},
    "engine_pod_R1": {"x": 0.40, "y": -0.30, "z": 0.05},
    "engine_pod_R2": {"x": 0.48, "y": -0.18, "z": 0.05},
    "fan_disc_L1": {"x": 0.40, "y": 0.30, "z": 0.06},
    "fan_disc_R1": {"x": 0.40, "y": -0.30, "z": 0.06},
    "fan_disc_L2": {"x": 0.48, "y": 0.18, "z": 0.06},
    "fan_disc_R2": {"x": 0.48, "y": -0.18, "z": 0.06},
    "nose_gear_strut": {"x": 0.78, "y": 0.0, "z": -0.06},
    "main_gear_left": {"x": 0.44, "y": 0.22, "z": -0.08},
    "main_gear_right": {"x": 0.44, "y": -0.22, "z": -0.08},
    "wheel_set": {"x": 0.50, "y": 0.0, "z": -0.10},
}

# Map legacy v2 part ids → v3 ids for placement hints.
PART_ID_ALIASES: Dict[str, str] = {
    "fuselage_main": "fuselage_fwd",
    "wing_pair": "wing_left",
    "tail_set": "vert_stab",
    "engine_pod_shells": "engine_pod_L1",
    "fan_rotor_set": "fan_disc_L1",
}


def clerx_747sp_available() -> bool:
    return CLERX_747SP_DIR.is_dir() and any(CLERX_747SP_DIR.glob("fuselage-fwd.stl"))


def exploded_sort_key(part_id: str) -> Tuple[int, int]:
    for gi, (_label, ids) in enumerate(CLERX_747SP_EXPLODED_GROUPS):
        if part_id in ids:
            return (gi, ids.index(part_id))
    return (99, 0)


def pose_offset_for_part(part_id: str) -> Dict[str, float] | None:
    pid = PART_ID_ALIASES.get(part_id, part_id)
    return CLERX_747SP_POSE_OFFSETS.get(pid)


# Generic exploded order by project_kind (preview grouping).
EXPLODED_BY_KIND: Dict[str, List[Tuple[str, List[str]]]] = {
    "rc_aircraft_kit": [
        ("coupons", ["fit_coupon_a", "fit_coupon"]),
        ("fuselage", ["fuselage_fwd", "fuselage_aft", "fuselage_main"]),
        ("wings", ["wing_left", "wing_right", "wing_pair"]),
        ("tail", ["vert_stab", "horz_stab", "horz_stab_left", "horz_stab_right"]),
        ("power", ["engine_pod", "prop_disc", "fan_disc_L1", "fan_disc_R1"]),
        ("gear", ["landing_gear", "wheel_set", "nose_gear_strut"]),
    ],
    "drone_fpv_kit": [
        ("frame", ["frame_plate", "arm_fl", "arm_fr", "arm_rl", "arm_rr"]),
        ("mounts", ["motor_mount", "battery_strap_clip"]),
        ("protection", ["prop_guard", "camera_bumper"]),
    ],
    "vehicle_kit": [
        ("chassis", ["chassis", "body_tub", "hull_lower"]),
        ("wheels", ["wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr", "axle_front", "axle_rear"]),
        ("body", ["hood", "windshield", "front_seat", "rear_seat"]),
    ],
}


def exploded_sort_key_for_kind(project_kind: str, part_id: str) -> Tuple[int, int]:
    groups = EXPLODED_BY_KIND.get(project_kind)
    if not groups:
        return exploded_sort_key(part_id)
    pid = PART_ID_ALIASES.get(part_id, part_id)
    for gi, (_label, ids) in enumerate(groups):
        if pid in ids:
            return (gi, ids.index(pid))
    return (99, 0)


def reference_notes() -> Dict[str, Any]:
    return {
        "clerx_747sp": {
            "available": clerx_747sp_available(),
            "path": str(CLERX_747SP_DIR),
            "source": "https://www.printables.com/model/60733-boeing-747sp-1200",
            "part_names": [
                "fuselage-fwd",
                "fuselage-aft",
                "wing-left",
                "wing-right",
                "engine-1..4",
                "fan-blades",
                "vert-stab",
                "horz-stab-left/right",
                "pin",
                "stand",
            ],
        }
    }
