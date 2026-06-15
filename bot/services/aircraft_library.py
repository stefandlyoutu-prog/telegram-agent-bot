"""Real Boeing 747 models prepared for FDM printing (watertight solid → Bambu 3MF).

Primary source: rreusser/747-model (CC BY 4.0) — a single clean mesh without
window cutouts or 300+ shell fragments.  Voxel-solidify + validate before export.
No procedural fallback: if validation fails, the builder raises.
"""

from __future__ import annotations

import io
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "reference_models" / "aircraft_cache"

_RREUSSER_747 = "https://raw.githubusercontent.com/rreusser/747-model/master/model/747.obj"

CATALOG: Dict[str, Dict[str, Any]] = {
    "b744": {
        "title": "Boeing 747-400",
        "keywords": [r"747[\s-]*400", r"\b744\b", r"bo[e]?ing", r"самол", r"airliner", r"b747"],
    },
    "b748": {
        "title": "Boeing 747-8i",
        "keywords": [r"747[\s-]*8", r"\b748\b"],
    },
}
DEFAULT_MODEL = "b744"


def select_model(text: str) -> str:
    t = text or ""
    for key, spec in CATALOG.items():
        for kw in spec["keywords"]:
            if re.search(kw, t, re.I):
                return key
    return DEFAULT_MODEL


def _download(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "telegram-agent-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read()


def _target_length_mm(text: str) -> float:
    t = text or ""
    m = re.search(r"(\d{2,3})\s*(см|cm)", t, re.I)
    if m:
        return max(80.0, min(250.0, float(m.group(1)) * 10.0))
    m = re.search(r"(\d{2,3})\s*(мм|mm)", t, re.I)
    if m:
        return max(80.0, min(250.0, float(m.group(1))))
    return 200.0


def _load_rreusser_747():
    import trimesh

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "747_rreusser.obj"
    if not cached.exists() or cached.stat().st_size < 1024:
        cached.write_bytes(_download(_RREUSSER_747))
    return trimesh.load(str(cached), file_type="obj", process=True)


def _orient_airliner(mesh):
    """Sort axes by extent: longest→length X, middle→span Y, shortest→height Z."""
    import numpy as np

    mesh = mesh.copy()
    ext = np.ptp(mesh.vertices, axis=0)
    order = sorted(range(3), key=lambda a: -ext[a])  # largest first
    R = np.zeros((3, 3))
    for new_i, old_i in enumerate(order):
        R[new_i, old_i] = 1.0
    T = np.eye(4)
    T[:3, :3] = R
    mesh.apply_transform(T)
    return mesh


def _section_interior_hits(mesh, x: float, samples: int = 20) -> int:
    import numpy as np

    b = mesh.bounds
    ys = np.linspace(b[0][1] + 0.08 * (b[1][1] - b[0][1]), b[1][1] - 0.08 * (b[1][1] - b[0][1]), samples)
    zs = np.linspace(b[0][2] + 0.08 * (b[1][2] - b[0][2]), b[1][2] - 0.08 * (b[1][2] - b[0][2]), samples)
    pts = np.array([[x, y, z] for y in ys for z in zs])
    return int(mesh.contains(pts).sum())


def validate_print_solid(solid) -> Tuple[bool, List[str]]:
    """Hard gate — must pass before we send a file to the user."""
    issues: List[str] = []
    if not solid.is_watertight:
        issues.append("меш не watertight")
    if not solid.is_winding_consistent:
        issues.append("неконсистентные нормали")

    b = solid.bounds
    ext = b[1] - b[0]
    length, span, height = float(ext[0]), float(ext[1]), float(ext[2])
    if length < 80.0:
        issues.append(f"длина слишком мала ({length:.0f} мм)")
    ratio_ws = span / length if length else 0.0
    ratio_h = height / length if length else 0.0
    if ratio_ws < 0.72 or ratio_ws > 1.08:
        issues.append(f"размах/длина={ratio_ws:.2f} вне нормы")
    if ratio_h < 0.14 or ratio_h > 0.42:
        issues.append(f"высота/длина={ratio_h:.2f} вне нормы")
    vol = float(solid.volume)
    if vol < 12_000:
        issues.append(f"объём слишком мал ({vol:.0f} мм³)")

    for label, frac in (("нос", 0.12), ("центр", 0.50), ("хвост", 0.88)):
        x = b[0][0] + frac * length
        hits = _section_interior_hits(solid, x)
        if hits < 6:
            issues.append(f"пустой разрез у {label} (hits={hits})")

    return (not issues, issues)


def _solidify_for_print(mesh, target_len_mm: float, pitch: float):
    import numpy as np
    import trimesh

    mesh = _orient_airliner(mesh.copy())
    ext = np.ptp(mesh.vertices, axis=0)
    mesh.apply_scale(target_len_mm / ext[0])

    solid = mesh.voxelized(pitch).fill().marching_cubes
    cur_len = float(np.ptp(solid.vertices, axis=0)[0])
    if cur_len > 1e-6:
        solid.apply_scale(target_len_mm / cur_len)
    if len(solid.faces) > 0:
        try:
            solid = trimesh.smoothing.filter_taubin(solid, lamb=0.5, nu=-0.53, iterations=6)
        except Exception:
            pass
    solid.merge_vertices()
    trimesh.repair.fix_normals(solid)
    solid.apply_translation([0, 0, -solid.bounds[0][2]])
    solid.apply_translation([-solid.centroid[0], -solid.centroid[1], 0])
    return solid


def _build_print_solid(mesh, target_len_mm: float):
    """Try several pitches / orientations until validate_print_solid passes."""
    import numpy as np

    pitches = [0.75, 0.85]
    last_issues: List[str] = ["не удалось собрать solid"]

    for pitch in pitches:
        for flip in (False, True):
            src = mesh.copy()
            if flip:
                src.apply_transform(np.diag([-1.0, 1.0, 1.0, 1.0]))
            solid = _solidify_for_print(src, target_len_mm, pitch)
            ok, issues = validate_print_solid(solid)
            if ok:
                return solid, pitch
            last_issues = issues

    raise ValueError(
        "Модель не прошла проверку качества перед отправкой: " + "; ".join(last_issues)
    )


async def build_library_airliner_3mf(
    user_text: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str, List[str], str, Dict[str, float]]:
    import asyncio

    return await asyncio.to_thread(_build_library_airliner_3mf_sync, user_text, profile or {})


def _build_library_airliner_3mf_sync(user_text: str, profile: Dict[str, Any]):
    import numpy as np
    import trimesh

    from bot.services.articulated_3mf import _add_bambu_metadata

    t0 = time.time()
    model_key = select_model(user_text)
    spec = CATALOG[model_key]
    target = _target_length_mm(user_text)

    mesh = _load_rreusser_747()
    solid, pitch = _build_print_solid(mesh, target)

    # Final gate (belt-and-suspenders)
    ok, issues = validate_print_solid(solid)
    if not ok:
        raise ValueError("Финальная проверка не пройдена: " + "; ".join(issues))

    ext = np.ptp(solid.vertices, axis=0)
    dims = {
        "length_mm": round(float(ext[0]), 1),
        "wingspan_mm": round(float(ext[1]), 1),
        "height_mm": round(float(ext[2]), 1),
    }

    filename = f"{model_key}-Boeing_747-print-ready.3mf"
    import tempfile

    with tempfile.TemporaryDirectory(prefix="aclib3mf-") as td:
        out_path = Path(td) / filename
        scene = trimesh.Scene()
        scene.add_geometry(solid, geom_name=spec["title"], node_name=spec["title"])
        scene.export(str(out_path))
        data = out_path.read_bytes()

    data = _add_bambu_metadata(data, filename=filename, user_text=user_text, profile=profile)
    desc = (
        f"{spec['title']} — чистая модель 747 (CC BY 4.0, rreusser), watertight-solid "
        f"длина {dims['length_mm']:.0f}мм, pitch {pitch:.2f}мм, проверена перед отправкой."
    )
    parts = [spec["title"]]
    _ = time.time() - t0
    return data, filename, parts, desc, dims
