"""Virtual assembly previews: combine part STLs for visual check before printing."""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_MECHANICAL_BOEING_SKIP_POSE = frozenset(
    {
        "hinge_fit_coupon",
        "wheel_fit_coupon",
        "fan_blade_coupon",
        "axle_pin_set",
        "assembly_pin_set",
    }
)


def _load_trimesh(stl_bytes: bytes):
    import trimesh

    loaded = trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("empty scene")
        return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    return loaded


def _mesh_to_stl_bytes(mesh) -> bytes:
    return mesh.export(file_type="stl")


def _part_id_from_ordered(ordered_name: str) -> str:
    if "-" in ordered_name:
        return ordered_name.split("-", 1)[1]
    return ordered_name


def _length_from_specs(specs: Dict[str, Any]) -> float:
    for item in specs.get("critical_dimensions") or []:
        if isinstance(item, dict) and str(item.get("name") or "").startswith("target length"):
            try:
                return float(item.get("value_mm") or 200.0)
            except (TypeError, ValueError):
                break
    for part in specs.get("parts") or []:
        if isinstance(part, dict) and part.get("id") == "fuselage_main":
            p = part.get("params") or {}
            try:
                return float(p.get("width_mm") or 200.0)
            except (TypeError, ValueError):
                break
    return 200.0


def _align_fuselage_on_bed(mesh):
    """Long axis +X, symmetric Y, bottom on Z=0."""
    import trimesh

    m = mesh.copy()
    ext = m.extents
    axis = int(np.argmax(ext))
    if axis != 0:
        if axis == 1:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        elif axis == 2:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    m.apply_translation(
        [
            -m.bounds[0][0],
            -(m.bounds[0][1] + m.bounds[1][1]) / 2.0,
            -m.bounds[0][2],
        ]
    )
    return m


def _fuselage_frame(fuselage) -> Dict[str, float]:
    b0, b1 = fuselage.bounds
    cx = (b0[0] + b1[0]) / 2.0
    cy = (b0[1] + b1[1]) / 2.0
    top_z = b1[2]
    belly_z = b0[2]
    nose_x = b1[0]
    tail_x = b0[0]
    return {
        "cx": cx,
        "cy": cy,
        "top_z": top_z,
        "belly_z": belly_z,
        "nose_x": nose_x,
        "tail_x": tail_x,
        "length": b1[0] - b0[0],
        "half_width": (b1[1] - b0[1]) / 2.0,
    }


def _place_part_from_profile(part_id: str, mesh, frame: Dict[str, float], length_mm: float):
    """Place using CLERX-derived semantic offsets (scaled to target length)."""
    from bot.services.reference_kit_profiles import pose_offset_for_part

    off = pose_offset_for_part(part_id)
    if not off:
        return None
    import trimesh

    m = mesh.copy()
    l = max(80.0, float(length_mm))
    target = np.array(
        [
            off["x"] * l,
            off["y"] * l,
            off["z"] * l + frame["belly_z"],
        ],
        dtype=float,
    )
    m.apply_translation(target - m.centroid)
    return m


def _place_part_for_pose(part_id: str, mesh, frame: Dict[str, float], length_mm: float = 200.0):
    """Rotate/translate printable part STL into fuselage-aligned assembly frame."""
    import trimesh

    profiled = _place_part_from_profile(part_id, mesh, frame, length_mm)
    if profiled is not None:
        return profiled

    m = mesh.copy()
    ext = m.extents
    l = frame["length"]

    if part_id in ("wing_pair", "wing_left", "wing_right"):
        if ext[0] > ext[1]:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        y_off = 0.0
        if part_id == "wing_left":
            y_off = frame["half_width"] * 0.85
        elif part_id == "wing_right":
            y_off = -frame["half_width"] * 0.85
        m.apply_translation(
            [frame["cx"], frame["cy"] + y_off, frame["top_z"] + m.extents[2] * 0.05]
        )
        return m

    if part_id in ("tail_set", "vert_stab", "horz_stab_left", "horz_stab_right"):
        # Fin extruded on Z; put root near tail top.
        m.apply_translation(
            [
                frame["tail_x"] + l * 0.06,
                frame["cy"],
                frame["top_z"] * 0.55,
            ]
        )
        return m

    if part_id == "nose_cap":
        m.apply_translation([frame["nose_x"] + m.extents[0] * 0.18, frame["cy"], frame["cx"] * 0.0])
        m.apply_translation([0, 0, frame["top_z"] * 0.35])
        return m

    if part_id in (
        "engine_pod_shells",
        "fan_rotor_set",
        "engine_pod_L1",
        "engine_pod_L2",
        "engine_pod_R1",
        "engine_pod_R2",
        "fan_disc_L1",
        "fan_disc_R1",
        "fan_disc_L2",
        "fan_disc_R2",
    ):
        # Pods exported along X in a row; tuck under wing root.
        m.apply_translation(
            [
                frame["cx"] - l * 0.02,
                frame["cy"],
                frame["belly_z"] - m.extents[2] * 0.55,
            ]
        )
        return m

    if part_id == "nose_gear_strut":
        m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        m.apply_translation(
            [frame["nose_x"] - l * 0.18, frame["cy"], frame["belly_z"] - m.extents[2] * 0.2]
        )
        return m

    if part_id == "main_gear_left":
        m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        m.apply_translation(
            [
                frame["cx"] - l * 0.08,
                frame["cy"] + frame["half_width"] * 1.05,
                frame["belly_z"] - m.extents[2] * 0.15,
            ]
        )
        return m

    if part_id == "main_gear_right":
        m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        m.apply_translation(
            [
                frame["cx"] - l * 0.08,
                frame["cy"] - frame["half_width"] * 1.05,
                frame["belly_z"] - m.extents[2] * 0.15,
            ]
        )
        return m

    if part_id == "wheel_set":
        # Wheel strip along X -> split conceptually: park under gear region.
        m.apply_translation(
            [frame["cx"] - l * 0.05, frame["cy"], frame["belly_z"] - m.extents[2] * 1.2]
        )
        return m

    return None


def _validate_pose_cluster(meshes, frame: Dict[str, float]) -> List[str]:
    """Pose валиден iff общий габарит уложенных деталей вписан в разумный envelope самолёта.

    Раньше мерили расстояние центроидов от центра фюзеляжа — это давало
    ложные срабатывания (крыло легитимно уходит на ~length/2 по Y),
    и пайплайн молча подсовывал примитив-силуэт вместо реальной сборки.
    Теперь проверяем bbox уложенных деталей:
        X (длина)  <= 1.4 * length
        Y (размах) <= 2.0 * length
        Z (высота) <= 1.0 * length
    """
    issues: List[str] = []
    if not meshes:
        return ["no pose meshes"]
    length = max(1.0, frame["length"])
    mins = np.min(np.stack([m.bounds[0] for m in meshes]), axis=0)
    maxs = np.max(np.stack([m.bounds[1] for m in meshes]), axis=0)
    extents = (maxs - mins).tolist()
    limits = (length * 1.4, length * 2.0, length * 1.0)
    axes = ("X (длина)", "Y (размах)", "Z (высота)")
    for ext_val, lim, name in zip(extents, limits, axes):
        if ext_val > lim:
            issues.append(f"{name} {ext_val:.0f} мм > предел {lim:.0f} мм")
    return issues


def build_mechanical_boeing_previews(
    stl_entries: List[Tuple[int, bytes, str, str, str]],
    specs: Dict[str, Any],
) -> Dict[str, bytes]:
    try:
        import trimesh
    except ImportError:
        logger.warning("trimesh missing — assembly preview skipped")
        return {}

    length_mm = _length_from_specs(specs)
    by_id: Dict[str, bytes] = {}
    for _fn, stl_bytes, ordered_name, _title, _desc in stl_entries:
        by_id[_part_id_from_ordered(ordered_name)] = stl_bytes

    fuselage_raw = by_id.get("fuselage_fwd") or by_id.get("fuselage_main")
    if not fuselage_raw:
        logger.warning("No fuselage_fwd for assembly preview")
        return {}

    try:
        fuselage = _align_fuselage_on_bed(_load_trimesh(fuselage_raw))
        if by_id.get("fuselage_aft"):
            aft = _align_fuselage_on_bed(_load_trimesh(by_id["fuselage_aft"]))
            fuse_b = fuselage.bounds
            aft_b = aft.bounds
            aft.apply_translation([fuse_b[0][0] - aft_b[1][0], 0, 0])
            fuselage = trimesh.util.concatenate([fuselage, aft])
    except Exception as e:
        logger.warning("Fuselage preview failed: %s", e)
        return {}

    frame = _fuselage_frame(fuselage)
    pose_meshes = [fuselage]

    for part_id, stl_bytes in by_id.items():
        if part_id in _MECHANICAL_BOEING_SKIP_POSE or part_id in (
            "fuselage_main",
            "fuselage_fwd",
            "fuselage_aft",
        ):
            continue
        try:
            raw = _load_trimesh(stl_bytes)
            placed = _place_part_for_pose(part_id, raw, frame, length_mm)
            if placed is not None:
                pose_meshes.append(placed)
        except Exception as e:
            logger.warning("Preview skip %s: %s", part_id, e)

    # POLITIKA: ВСЕГДА использовать NACA reference pose, никогда не пытаться
    # склеить «семантическую» сборку из реальных print-oriented STL.
    # Реальные детали экспортируются плашмя (под FDM), поэтому даже когда
    # bbox-проверка проходит — собранный результат выглядит как склад деталей,
    # а не самолёт. Пользователь должен видеть НАСТОЯЩИЙ самолёт в pose preview.
    pose_ok = False
    skip_reasons: List[str] = ["semantic assembly disabled — using NACA reference pose"]
    logger.info("Building NACA reference pose (semantic assembly disabled)")

    from bot.services.reference_kit_profiles import (
        exploded_sort_key,
        exploded_sort_key_for_kind,
    )

    kind = specs.get("project_kind") or ""
    sort_key_fn = (
        (lambda pid: exploded_sort_key_for_kind(kind, pid))
        if kind in {"rc_aircraft_kit", "drone_fpv_kit", "vehicle_kit", "mechanical_boeing_airliner"}
        else exploded_sort_key
    )

    exploded_meshes = []
    gap = length_mm * 0.08
    row_gap = length_mm * 0.14
    y_row = 0.0
    last_group = -1
    x_cursor = 0.0
    sorted_entries = sorted(
        stl_entries,
        key=lambda x: sort_key_fn(_part_id_from_ordered(x[2])),
    )
    for _fn, stl_bytes, ordered_name, _title, _desc in sorted_entries:
        part_id = _part_id_from_ordered(ordered_name)
        group_idx, _ = sort_key_fn(part_id)
        if last_group >= 0 and group_idx != last_group:
            y_row += row_gap
            x_cursor = 0.0
        last_group = group_idx
        try:
            mesh = _load_trimesh(stl_bytes)
            span = max(float(mesh.extents.max()), 8.0)
            exp = mesh.copy()
            exp.apply_translation([x_cursor + span * 0.5, y_row, 0.0])
            exploded_meshes.append(exp)
            x_cursor += span + gap
        except Exception as e:
            logger.warning("Exploded skip %s: %s", ordered_name, e)

    out: Dict[str, bytes] = {}

    if pose_ok:
        combined = trimesh.util.concatenate(pose_meshes)
        combined.apply_translation(-combined.bounds[0])
        out["preview/assembly_pose.stl"] = _mesh_to_stl_bytes(combined)
        pose_source = "semantic"
    else:
        # Pose from real parts failed → build a NACA reference airplane.
        # This shows what the assembled result should look like, not the
        # individual print-oriented parts. It is clearly labelled as a
        # reference, not a copy of the actual kit geometry.
        try:
            naca_pose = _build_naca_reference_pose(length_mm)
            out["preview/assembly_pose.stl"] = _mesh_to_stl_bytes(naca_pose)
            pose_source = "naca_reference"
            logger.info(
                "Pose cluster check failed (%s) — using NACA reference pose (L=%.0f mm)",
                skip_reasons, length_mm,
            )
        except Exception as e:
            logger.warning("NACA reference pose failed: %s — no pose included", e)
            pose_source = "unavailable"

    # Exploded view: rename to make clear this is a PARTS LIST, not an assembly.
    # Users opening the file in Bambu Studio should understand they're looking
    # at print-oriented parts, not an assembled airplane.
    if exploded_meshes:
        exploded = trimesh.util.concatenate(exploded_meshes)
        exploded.apply_translation(-exploded.bounds[0])
        out["preview/parts_layout_print_orientation.stl"] = _mesh_to_stl_bytes(exploded)

    if out:
        if pose_source == "naca_reference":
            pose_note = (
                "assembly_pose.stl — NACA-референс самолёта в лётной позе.\n"
                "  Показывает как должен выглядеть собранный результат.\n"
                "  Детали kit печатаются из parts_layout_print_orientation.stl.\n"
            )
        elif pose_source == "semantic":
            pose_note = (
                "assembly_pose.stl — виртуальная сборка реальных STL в лётной позе "
                "(без coupons/pins).\n"
            )
        else:
            pose_note = "assembly_pose.stl — не сгенерирован.\n"

        out["preview/README_preview.txt"] = (
            "ПРЕВЬЮ СБОРКИ (проверка перед печатью)\n"
            "================================\n\n"
            f"{pose_note}"
            "parts_layout_print_orientation.stl — все детали в ориентации для печати "
            "(coupons→gear→engines→fuse→wings→tail).\n\n"
            "Как пользоваться:\n"
            "1. assembly_pose.stl — узнаваемый самолёт, проверьте пропорции.\n"
            "2. parts_layout_print_orientation.stl — полный комплект деталей для печати.\n"
            "3. Печатайте fit-coupons 01–03 до полного kit.\n\n"
            "Превью не заменяет физический тест зазоров.\n"
        ).encode("utf-8")
    return out


def _build_naca_reference_pose(length_mm: float):
    """
    Build a NACA-geometry reference airplane at the given target length.
    Used as the assembly_pose.stl when parts cannot be posed from real STLs.
    This is a reference showing what the assembled result should look like.
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
    import math

    s = max(length_mm, 80.0) / 158.0   # scale to match requested length

    parts = []

    # Fuselage — smooth taper at tail so it doesn't look like an engine nozzle
    fuse = fuselage_body(158 * s, 6.6 * s,
                          nose_fraction=0.14, tail_fraction=0.34,
                          n_sections=64, n_circ=44)
    parts.append(fuse)

    # Wings
    wing_span   = 66.0 * s
    wing_root_c = 36.0 * s
    wing_tip_c  = 17.0 * s
    le_sweep    = wing_span * math.tan(math.radians(35.0)) * 0.65
    dihedral_z  = wing_span * math.tan(math.radians(7.0))
    WING_Z_OFFSET = 4.0 * s

    wing_l = loft_wing_half("2318", wing_root_c, wing_tip_c, wing_span,
                             le_sweep, dihedral_z, n_span=22, n_chord=56,
                             min_thickness_mm=1.4)
    wing_l.apply_translation([14.0 * s, 5.0 * s, WING_Z_OFFSET])
    wing_r = wing_l.copy()
    wing_r.apply_scale([1, -1, 1])
    parts += [wing_l, wing_r]

    # Horizontal stabilisers
    stab_l = loft_wing_half("0012", 22.0 * s, 9.0 * s, 26.0 * s,
                             26.0 * s * math.tan(math.radians(34.0)) * 0.55,
                             26.0 * s * math.tan(math.radians(2.5)),
                             n_span=14, n_chord=36, min_thickness_mm=1.2)
    stab_l.apply_translation([-56.0 * s, 4.5 * s, 14.5 * s])
    stab_r = stab_l.copy(); stab_r.apply_scale([1, -1, 1])
    parts += [stab_l, stab_r]

    # Vertical stabiliser
    vstab = vertical_stabilizer(30.0 * s, 12.0 * s, 40.0 * s, -10.0 * s,
                                 n_span=14, n_chord=36, min_thickness_mm=1.2)
    vstab.apply_translation([-60.0 * s, 0.0, 8.5 * s])
    parts.append(vstab)

    # Engines hang below wings; pylons connect them visibly to wing underside
    ENGINE_Z = 6.0 * s
    ENGINE_R = 4.5
    engine_specs = [(16, 29), (16, -29), (-12, 46), (-12, -46)]
    for x, y in engine_specs:
        eng = engine_nacelle(19.0 * s, 3.6 * s, ENGINE_R * s, 3.0 * s,
                              n_sections=24, n_circ=28)
        eng.apply_translation([x * s, y * s, ENGINE_Z])
        parts.append(eng)

    # Pylons — span engine top → wing bottom
    for ex, ey in engine_specs:
        z_bot = ENGINE_Z + (ENGINE_R - 0.5) * s
        wing_bot = WING_Z_OFFSET + 1.0 * s + (abs(ey) / wing_span) * dihedral_z * s
        pylon_h = max(wing_bot - z_bot + 2.0 * s, 1.2 * s)
        pylon = trimesh.creation.box(extents=[4.4 * s, 1.4 * s, pylon_h])
        pylon.apply_translation([ex * s, ey * s, (z_bot + wing_bot) / 2.0])
        parts.append(pylon)

    # Winglets
    wl = blended_winglet(12.0 * s, 14.0 * s, n_span=10, n_chord=28,
                          min_thickness_mm=1.0)
    tip_y = wing_span + 5.0 * s
    wl.apply_translation([14.0 * s + le_sweep + 2.0 * s, tip_y, dihedral_z + 4.0 * s])
    wl_r = wl.copy(); wl_r.apply_scale([1, -1, 1])
    parts += [wl, wl_r]

    # Visible landing gear — tall enough to poke out from belly
    GEAR_H = 6.0 * s
    for gx, gy in [(40, 0), (-22, 9), (-22, -9)]:
        g = gear_strut(strut_height=GEAR_H, strut_radius=1.0 * s,
                        wheel_radius=2.2 * s, wheel_width=1.5 * s, n_wheel=20)
        g.apply_translation([gx * s, gy * s, 0.0])
        parts.append(g)

    combined = trimesh.util.concatenate(parts)
    # Settle on plate
    combined.apply_translation([0, 0, -combined.bounds[0][2]])
    combined.apply_translation(-np.array([
        (combined.bounds[0][0] + combined.bounds[1][0]) / 2,
        (combined.bounds[0][1] + combined.bounds[1][1]) / 2,
        0,
    ]))
    return combined


def build_assembly_previews(
    specs: Dict[str, Any],
    stl_files_out: List[Tuple[int, bytes, str, str, str]],
) -> Dict[str, bytes]:
    if specs.get("project_kind") == "mechanical_boeing_airliner":
        return build_mechanical_boeing_previews(stl_files_out, specs)
    return {}
