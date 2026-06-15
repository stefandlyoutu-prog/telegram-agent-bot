"""Split Meshy sculpt STL using reference blueprint (level 3)."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from bot.services.reference_geometry import build_geometry_profile
from bot.services.reference_tolerance import apply_tolerances_to_blueprint, tolerance_mm_for_role

logger = logging.getLogger(__name__)

MIN_FACES_PER_PART = 80


@dataclass
class SplitPart:
    part_id: str
    name: str
    role: str
    stl_bytes: bytes
    face_count: int
    tolerance_mm: float


def _load_trimesh(stl_bytes: bytes):
    import trimesh

    mesh = trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return mesh


def _part_centers_normalized(profile: Dict[str, Any]) -> List[Tuple[str, np.ndarray]]:
    env = profile.get("envelope_mm") or {"x": 1, "y": 1, "z": 1}
    ex = max(float(env.get("x") or 1), 1e-3)
    ey = max(float(env.get("y") or 1), 1e-3)
    ez = max(float(env.get("z") or 1), 1e-3)
    centers = []
    for p in profile.get("parts") or []:
        bb = p.get("bbox_mm") or {}
        c = np.array(
            [
                float(bb.get("x", 10)) / 2 / ex,
                float(bb.get("y", 10)) / 2 / ey,
                float(bb.get("z", 10)) / 2 / ez,
            ],
            dtype=np.float64,
        )
        pid = p.get("id") or "part"
        centers.append((pid, c))
    return centers


def split_stl_by_blueprint(
    stl_bytes: bytes,
    profile: Dict[str, Any],
    *,
    min_faces: int = MIN_FACES_PER_PART,
) -> List[SplitPart]:
    """Assign each triangle to nearest reference part by centroid distance in normalized space."""
    profile = apply_tolerances_to_blueprint(profile)
    centers = _part_centers_normalized(profile)
    if len(centers) < 2:
        return []

    mesh = _load_trimesh(stl_bytes)
    bounds = mesh.bounds
    size = bounds[1] - bounds[0]
    size = np.maximum(size, 1e-6)
    tri_centers = mesh.triangles_center
    norm_centers = (tri_centers - bounds[0]) / size

    part_ids = [c[0] for c in centers]
    center_arr = np.array([c[1] for c in centers])
    # nearest reference part per triangle
    dists = np.linalg.norm(norm_centers[:, None, :] - center_arr[None, :, :], axis=2)
    labels = np.argmin(dists, axis=1)

    meta_by_id = {p["id"]: p for p in profile.get("parts") or []}
    out: List[SplitPart] = []
    for idx, pid in enumerate(part_ids):
        face_mask = labels == idx
        if int(face_mask.sum()) < min_faces:
            continue
        sub = mesh.submesh([np.where(face_mask)[0]], append=True)
        if sub.is_empty:
            continue
        stl_out = sub.export(file_type="stl")
        meta = meta_by_id.get(pid) or {}
        role = meta.get("role") or "generic"
        cat = profile.get("category") or "general_kit"
        out.append(
            SplitPart(
                part_id=pid,
                name=str(meta.get("name") or pid),
                role=role,
                stl_bytes=stl_out,
                face_count=int(face_mask.sum()),
                tolerance_mm=tolerance_mm_for_role(cat, role),
            )
        )
    return out


def build_split_zip(
    parts: List[SplitPart],
    profile: Dict[str, Any],
    *,
    whole_stl: Optional[bytes] = None,
) -> bytes:
    buf = io.BytesIO()
    manifest = {
        "slug": profile.get("slug"),
        "category": profile.get("category"),
        "split_method": "blueprint_centroid_assignment_v1",
        "parts": [
            {
                "id": p.part_id,
                "name": p.name,
                "role": p.role,
                "faces": p.face_count,
                "tolerance_mm": p.tolerance_mm,
                "file": f"stl/{i+1:02d}_{p.part_id}.stl",
            }
            for i, p in enumerate(parts)
        ],
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if whole_stl:
            zf.writestr("stl/00_whole_meshy_sculpt.stl", whole_stl)
        for i, p in enumerate(parts):
            zf.writestr(f"stl/{i+1:02d}_{p.part_id}.stl", p.stl_bytes)
        zf.writestr(
            "engineering/reference_split_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "engineering/reference_blueprint.json",
            json.dumps(profile, ensure_ascii=False, indent=2),
        )
    return buf.getvalue()


def split_meshy_delivery(
    stl_bytes: bytes,
    slug: str,
) -> Tuple[List[SplitPart], Optional[bytes], Optional[Dict[str, Any]]]:
    profile = build_geometry_profile(slug)
    if not profile or profile.get("part_count", 0) < 4:
        return [], None, profile
    parts = split_stl_by_blueprint(stl_bytes, profile)
    if len(parts) < 2:
        return [], None, profile
    z = build_split_zip(parts, profile, whole_stl=stl_bytes)
    return parts, z, profile
