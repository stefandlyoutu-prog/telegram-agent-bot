"""Wrap printable STL meshes into Bambu 3MF projects."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple


def _load_stl_mesh(stl_bytes: bytes):
    import trimesh

    loaded = trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if hasattr(g, "vertices")]
        if not meshes:
            raise ValueError("STL scene has no mesh geometry")
        loaded = trimesh.util.concatenate(meshes)
    if not hasattr(loaded, "vertices") or len(loaded.vertices) == 0:
        raise ValueError("STL has no vertices")
    return loaded


def support_3mf_filename(stl_filename: str) -> str:
    base = (stl_filename or "meshy-model.stl").rsplit(".", 1)[0]
    if base.endswith("-meshy"):
        base = base[: -len("-meshy")]
    return f"{base}-bambu-supports.3mf"


def _worker_error(proc: subprocess.CompletedProcess[bytes]) -> str:
    if proc.returncode < 0:
        return f"worker signal {-proc.returncode}"
    err = proc.stderr.decode("utf-8", errors="ignore").strip()
    return err[:200] or f"worker exit {proc.returncode}"


def _repo_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def _wrap_stl_as_support_3mf_local(
    stl_bytes: bytes,
    *,
    stl_filename: str,
    user_text: str,
    profile: Dict[str, Any],
) -> Tuple[bytes, str]:
    """Return a Bambu Studio 3MF with Tree(auto) support metadata."""
    from bot.services.articulated_3mf import _add_bambu_metadata

    import trimesh

    mesh = _load_stl_mesh(stl_bytes)
    z0 = float(mesh.bounds[0][2])
    if z0 != 0.0:
        mesh.apply_translation([0, 0, -z0])
    obj_name = Path(stl_filename).stem if stl_filename else "model"
    mesh.metadata["name"] = obj_name

    filename = support_3mf_filename(stl_filename)
    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name=obj_name, node_name=obj_name)
    with tempfile.TemporaryDirectory(prefix="support3mf-") as td:
        out_path = Path(td) / filename
        scene.export(str(out_path))
        data = out_path.read_bytes()
    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=profile)
    return data, filename


def wrap_stl_as_support_3mf(
    stl_bytes: bytes,
    *,
    stl_filename: str,
    user_text: str,
    profile: Dict[str, Any],
) -> Tuple[bytes, str]:
    """Worker-isolated wrapper: Meshy STL may crash native trimesh in-process."""
    with tempfile.TemporaryDirectory(prefix="support3mf-worker-") as td:
        tmp = Path(td)
        src = tmp / "in.stl"
        out = tmp / "out.3mf"
        meta = tmp / "meta.json"
        args = tmp / "args.json"
        src.write_bytes(stl_bytes)
        args.write_text(
            json.dumps(
                {"stl_filename": stl_filename, "user_text": user_text, "profile": profile},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        code = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "from bot.services.support_3mf import _wrap_stl_as_support_3mf_local\n"
            "src, out, meta, args = map(Path, sys.argv[1:5])\n"
            "cfg = json.loads(args.read_text(encoding='utf-8'))\n"
            "data, filename = _wrap_stl_as_support_3mf_local(\n"
            "    src.read_bytes(), stl_filename=cfg['stl_filename'], user_text=cfg['user_text'], profile=cfg.get('profile') or {}\n"
            ")\n"
            "out.write_bytes(data)\n"
            "meta.write_text(json.dumps({'filename': filename}, ensure_ascii=False), encoding='utf-8')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(src), str(out), str(meta), str(args)],
            cwd=_repo_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"support 3MF worker failed: {_worker_error(proc)}")
        info = json.loads(meta.read_text(encoding="utf-8"))
        return out.read_bytes(), str(info["filename"])


def _component_3mf_filename(stl_filename: str) -> str:
    base = (stl_filename or "meshy-model.stl").rsplit(".", 1)[0]
    if base.endswith("-meshy"):
        base = base[: -len("-meshy")]
    return f"{base}-components-ams.3mf"


def _is_airplane(text: str) -> bool:
    return bool(re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", text or "", re.I))


def _classify_component_names(components: List[Any], user_text: str) -> List[str]:
    """Best-effort component names for Bambu object-level colors.

    Connected-component splitting is intentionally conservative: if Meshy did not
    separate a part geometrically, this function cannot invent a reliable part.
    """
    if not components:
        return []
    if not _is_airplane(user_text):
        return [f"component_{i + 1:02d}" for i in range(len(components))]

    face_counts = [len(getattr(c, "faces", [])) for c in components]
    largest_idx = max(range(len(components)), key=lambda i: face_counts[i])
    global_min = components[0].bounds[0].copy()
    global_max = components[0].bounds[1].copy()
    for comp in components[1:]:
        global_min = [min(global_min[i], comp.bounds[0][i]) for i in range(3)]
        global_max = [max(global_max[i], comp.bounds[1][i]) for i in range(3)]
    ext = [max(1e-6, global_max[i] - global_min[i]) for i in range(3)]
    length_axis = max(range(3), key=lambda i: ext[i])
    z_axis = 2
    z_mid = (global_min[z_axis] + global_max[z_axis]) / 2.0

    names: List[str] = []
    engine_no = 1
    component_no = 1
    for i, comp in enumerate(components):
        if i == largest_idx:
            names.append("airframe_white")
            continue
        b0, b1 = comp.bounds
        center = [(b0[j] + b1[j]) / 2.0 for j in range(3)]
        comp_ext = [max(1e-6, b1[j] - b0[j]) for j in range(3)]
        along = (center[length_axis] - global_min[length_axis]) / ext[length_axis]
        low_part = center[z_axis] < z_mid
        small_vs_plane = max(comp_ext) < max(ext) * 0.38
        high_extreme = center[z_axis] >= z_mid and (along < 0.25 or along > 0.75)
        if low_part and small_vs_plane:
            names.append(f"engine_{engine_no}")
            engine_no += 1
        elif high_extreme and small_vs_plane:
            names.append("tail_red" if re.search(r"хвост|tail|красн|red", user_text, re.I) else "tail")
        else:
            names.append(f"component_{component_no:02d}")
            component_no += 1
    return names


def _component_split_health(parts: List[Any]) -> Dict[str, Any]:
    """Reject Meshy split artifacts before Bambu opens zero-volume shard soup."""
    import math

    finite = 0
    solid = 0
    usable = 0
    min_thicknesses: List[float] = []
    volumes: List[float] = []
    face_counts: List[int] = []
    for part in parts:
        faces = int(len(getattr(part, "faces", [])))
        face_counts.append(faces)
        try:
            b0, b1 = part.bounds
            ext = [float(b1[i] - b0[i]) for i in range(3)]
        except Exception:
            continue
        if not all(math.isfinite(x) for x in ext):
            continue
        finite += 1
        positive = [x for x in ext if x > 1e-6]
        min_thickness = min(positive) if positive else 0.0
        min_thicknesses.append(min_thickness)
        is_watertight = bool(getattr(part, "is_watertight", False))
        if is_watertight:
            try:
                volume = abs(float(getattr(part, "volume", 0.0) or 0.0))
            except Exception:
                volume = 0.0
        else:
            volume = 0.0
        volumes.append(volume)
        if faces >= 12 and max(ext) >= 2.0 and min_thickness >= 0.2:
            usable += 1
        if is_watertight and volume >= 0.5:
            solid += 1
    total_volume = float(sum(volumes))
    dominant_volume = max(volumes) if volumes else 0.0
    dominant_ratio = (dominant_volume / total_volume) if total_volume > 1e-6 else 0.0
    return {
        "component_count": len(parts),
        "finite_components": finite,
        "usable_components": usable,
        "solid_components": solid,
        "total_volume_mm3": total_volume,
        "dominant_volume_ratio": dominant_ratio,
        "min_thickness_mm": min(min_thicknesses) if min_thicknesses else 0.0,
        "max_faces": max(face_counts) if face_counts else 0,
    }


def _wrap_stl_as_component_3mf_local(
    stl_bytes: bytes,
    *,
    stl_filename: str,
    user_text: str,
    profile: Dict[str, Any],
    min_components: int = 2,
) -> Tuple[bytes, str, Dict[str, Any]]:
    """Return a Bambu 3MF if an STL contains separable connected components."""
    from bot.services.articulated_3mf import _add_bambu_metadata
    from bot.services.bambu_hints import extract_part_color_requests

    import trimesh

    mesh = _load_stl_mesh(stl_bytes)
    parts = [m.copy() for m in mesh.split(only_watertight=False) if len(getattr(m, "faces", [])) > 0]
    if len(parts) < min_components:
        raise ValueError(f"STL has {len(parts)} connected component(s), cannot split into objects")
    health = _component_split_health(parts)
    if (
        health["component_count"] > 8
        or health["finite_components"] != len(parts)
        or health["usable_components"] < min_components
        or health["solid_components"] < min_components
        or health["total_volume_mm3"] < 25.0
        or health["dominant_volume_ratio"] < 0.35
    ):
        raise ValueError(f"component split is not print-solid: {health}")

    names = _classify_component_names(parts, user_text)
    all_min_z = min(float(part.bounds[0][2]) for part in parts)
    if all_min_z != 0.0:
        for part in parts:
            part.apply_translation([0, 0, -all_min_z])

    scene = trimesh.Scene()
    for name, part in zip(names, parts):
        part.metadata["name"] = name
        scene.add_geometry(part, geom_name=name, node_name=name)

    filename = _component_3mf_filename(stl_filename)
    with tempfile.TemporaryDirectory(prefix="component3mf-") as td:
        out_path = Path(td) / filename
        scene.export(str(out_path))
        data = out_path.read_bytes()
    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=profile)

    requested = extract_part_color_requests(user_text)
    joined_names = " ".join(names).lower()
    object_level_colors = any(
        (part == "engines" and "engine" in joined_names)
        or (part == "tail" and "tail" in joined_names)
        or (part == "wings" and "wing" in joined_names)
        or (part == "eyes" and "eye" in joined_names)
        or (part in joined_names)
        for part in requested
    )
    return data, filename, {
        "component_count": len(parts),
        "component_names": names,
        "object_level_colors": object_level_colors,
        **health,
    }


def wrap_stl_as_component_3mf(
    stl_bytes: bytes,
    *,
    stl_filename: str,
    user_text: str,
    profile: Dict[str, Any],
    min_components: int = 2,
) -> Tuple[bytes, str, Dict[str, Any]]:
    """Worker-isolated component splitter for Meshy STL."""
    with tempfile.TemporaryDirectory(prefix="component3mf-worker-") as td:
        tmp = Path(td)
        src = tmp / "in.stl"
        out = tmp / "out.3mf"
        meta = tmp / "meta.json"
        args = tmp / "args.json"
        src.write_bytes(stl_bytes)
        args.write_text(
            json.dumps(
                {
                    "stl_filename": stl_filename,
                    "user_text": user_text,
                    "profile": profile,
                    "min_components": min_components,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        code = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "from bot.services.support_3mf import _wrap_stl_as_component_3mf_local\n"
            "src, out, meta, args = map(Path, sys.argv[1:5])\n"
            "cfg = json.loads(args.read_text(encoding='utf-8'))\n"
            "data, filename, info = _wrap_stl_as_component_3mf_local(\n"
            "    src.read_bytes(), stl_filename=cfg['stl_filename'], user_text=cfg['user_text'],\n"
            "    profile=cfg.get('profile') or {}, min_components=int(cfg.get('min_components') or 2)\n"
            ")\n"
            "out.write_bytes(data)\n"
            "info['filename'] = filename\n"
            "meta.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(src), str(out), str(meta), str(args)],
            cwd=_repo_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"component 3MF worker failed: {_worker_error(proc)}")
        info = json.loads(meta.read_text(encoding="utf-8"))
        filename = str(info.pop("filename"))
        return out.read_bytes(), filename, info
