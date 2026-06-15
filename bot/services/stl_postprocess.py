"""Нормализация STL после Meshy: масштаб в мм, постановка на стол."""

from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

# Bambu P2S / типичный стол
DEFAULT_MAX_DIM_MM = 250.0
DEFAULT_FIGURINE_HEIGHT_MM = 110.0


@dataclass
class StlNormalizeResult:
    data: bytes
    width_mm: float
    depth_mm: float
    height_mm: float
    scale_applied: float
    note: str


def target_length_mm_from_text(text: str) -> float | None:
    """Явная длина модели: «длина 15 см», «150 мм length»."""
    if not text:
        return None
    ml_cm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d+(?:[,.]\d+)?)\s*см", text, re.I)
    if not ml_cm:
        ml_cm = re.search(r"(\d+(?:[,.]\d+)?)\s*см\D{0,12}(?:длин[ауы]?|length)", text, re.I)
    if ml_cm:
        return max(20.0, min(300.0, float(ml_cm.group(1).replace(",", ".")) * 10.0))
    ml_mm = re.search(r"(?:длин[ауы]?|length)\D{0,20}(\d{2,3})\s*мм", text, re.I)
    if not ml_mm:
        ml_mm = re.search(r"(\d{2,3})\s*мм\D{0,12}(?:длин[ауы]?|length)", text, re.I)
    if ml_mm:
        return max(20.0, min(300.0, float(ml_mm.group(1))))
    return None


def target_height_mm_from_text(text: str, default: float = DEFAULT_FIGURINE_HEIGHT_MM) -> float:
    """Ориентир высоты по явному размеру или «50 г» PETG (~110 мм для фигурки)."""
    if not text:
        return default
    mh_cm = re.search(r"(?:высот[ауы]?|height)\D{0,20}(\d+(?:[,.]\d+)?)\s*см", text, re.I)
    if not mh_cm:
        mh_cm = re.search(r"(\d+(?:[,.]\d+)?)\s*см\D{0,12}(?:высот[ауы]?|height)", text, re.I)
    if mh_cm:
        val = mh_cm.group(1)
        return max(20.0, min(250.0, float(val.replace(",", ".")) * 10.0))
    mh_mm = re.search(r"(?:высот[ауы]?|height)\D{0,20}(\d{2,3})\s*мм", text, re.I)
    if not mh_mm:
        mh_mm = re.search(r"(\d{2,3})\s*мм\D{0,12}(?:высот[ауы]?|height)", text, re.I)
    if mh_mm:
        return float(mh_mm.group(1))
    m = re.search(r"(\d+)\s*г(?:р|рамм)?", text, re.I)
    if m:
        grams = max(1, int(m.group(1)))
        vol_cm3 = grams / 1.24
        # ~100 мм при ~30 см³ (≈37 г PETG); для 50 г ≈ 110 мм
        return max(60.0, min(180.0, (vol_cm3 / 30.0) ** (1 / 3) * 100.0))
    m2 = re.search(r"(\d{2,3})\s*мм", text, re.I)
    if m2:
        return float(m2.group(1))
    return default


def _parse_binary_stl(data: bytes) -> np.ndarray:
    if len(data) < 84:
        raise ValueError("STL too small")
    n = struct.unpack_from("<I", data, 80)[0]
    need = 84 + n * 50
    if len(data) < need:
        raise ValueError("STL truncated")
    tris = np.zeros((n, 3, 3), dtype=np.float64)
    off = 84
    for i in range(n):
        off += 12  # normal
        for v in range(3):
            tris[i, v] = struct.unpack_from("<fff", data, off)
            off += 12
        off += 2  # attr
    return tris


def _parse_ascii_stl(data: bytes) -> np.ndarray:
    text = data.decode("utf-8", errors="ignore")
    verts: List[Tuple[float, float, float]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            parts = line.split()
            if len(parts) >= 4:
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
    if not verts:
        raise ValueError("ASCII STL empty")
    arr = np.array(verts, dtype=np.float64).reshape(-1, 3, 3)
    return arr


def _parse_stl(data: bytes) -> np.ndarray:
    if data[:5].lower() == b"solid":
        return _parse_ascii_stl(data)
    return _parse_binary_stl(data)


def _write_binary_stl(tris: np.ndarray) -> bytes:
    n = int(tris.shape[0])
    out = bytearray(80)
    out.extend(struct.pack("<I", n))
    for i in range(n):
        v0, v1, v2 = tris[i]
        edge1 = v1 - v0
        edge2 = v2 - v0
        nrm = np.cross(edge1, edge2)
        norm_len = np.linalg.norm(nrm)
        if norm_len > 1e-12:
            nrm = nrm / norm_len
        else:
            nrm = np.array([0.0, 0.0, 1.0])
        out.extend(struct.pack("<fff", float(nrm[0]), float(nrm[1]), float(nrm[2])))
        for v in (v0, v1, v2):
            out.extend(struct.pack("<fff", float(v[0]), float(v[1]), float(v[2])))
        out.extend(struct.pack("<H", 0))
    return bytes(out)


def _dims(tris: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    flat = tris.reshape(-1, 3)
    mins = flat.min(axis=0)
    maxs = flat.max(axis=0)
    size = maxs - mins
    return mins, maxs, size


def normalize_meshy_stl(
    stl_bytes: bytes,
    *,
    user_text: str = "",
    target_height: float | None = None,
    max_dim_mm: float = DEFAULT_MAX_DIM_MM,
) -> StlNormalizeResult:
    """
    Meshy часто отдаёт модель в «метрах» (высота ~1–2 м).
    Масштабируем до печатного размера и ставим на стол (Z=0).
    """
    tris = _parse_stl(stl_bytes)
    mins, maxs, size = _dims(tris)
    w, d, h = float(size[0]), float(size[1]), float(size[2])
    max_size = max(w, d, h)
    tgt_h = target_height if target_height is not None else target_height_mm_from_text(user_text)
    tgt_len = target_length_mm_from_text(user_text)

    scale = 1.0
    note_parts: List[str] = []

    # >500 мм — почти наверняка не миллиметры для фигурки
    if max_size > 500 or h > tgt_h * 2.5:
        scale = tgt_h / h if h > 1e-6 else (max_dim_mm / max_size if max_size > 1e-6 else 1.0)
        note_parts.append(f"масштаб ×{scale:.4f} → высота ~{tgt_h:.0f} мм")
    elif h > 1e-6 and max_size < 10:
        scale = tgt_h / h
        note_parts.append(f"масштаб ×{scale:.4f} → высота ~{tgt_h:.0f} мм")
    elif max_size > max_dim_mm:
        scale = max_dim_mm / max_size
        note_parts.append(f"уменьшен до {max_dim_mm:.0f} мм по большей стороне")

    if abs(scale - 1.0) > 1e-6:
        center = (mins + maxs) / 2.0
        tris = (tris - center) * scale + center

    mins, maxs, size = _dims(tris)
    if tgt_len:
        horizontal = float(max(size[0], size[1]))
        if horizontal > 1e-6 and (horizontal > tgt_len * 1.03 or horizontal < tgt_len * 0.97):
            xy_scale = tgt_len / horizontal
            center = (mins + maxs) / 2.0
            tris[:, :, 0] = (tris[:, :, 0] - center[0]) * xy_scale + center[0]
            tris[:, :, 1] = (tris[:, :, 1] - center[1]) * xy_scale + center[1]
            note_parts.append(f"XY ×{xy_scale:.4f} → длина ~{tgt_len:.0f} мм")

    mins, maxs, size = _dims(tris)
    # На стол: нижняя точка Z = 0, центр по XY около нуля
    flat = tris.reshape(-1, 3)
    cx = (mins[0] + maxs[0]) / 2.0
    cy = (mins[1] + maxs[1]) / 2.0
    flat[:, 0] -= cx
    flat[:, 1] -= cy
    flat[:, 2] -= mins[2]
    tris = flat.reshape(-1, 3, 3)

    mins, maxs, size = _dims(tris)
    w, d, h = float(size[0]), float(size[1]), float(size[2])
    note = "; ".join(note_parts) if note_parts else "масштаб OK"
    return StlNormalizeResult(
        data=_write_binary_stl(tris),
        width_mm=w,
        depth_mm=d,
        height_mm=h,
        scale_applied=scale,
        note=note,
    )


def _repair_stl_mesh_local(stl_bytes: bytes) -> Tuple[bytes, str]:
    """Локальный repair: pymeshfix + trimesh (для Bambu non-manifold)."""
    try:
        import io

        import trimesh
        from trimesh import repair as trimesh_repair
    except ImportError:
        return stl_bytes, "repair: trimesh не установлен"

    try:
        loaded = trimesh.load(io.BytesIO(stl_bytes), file_type="stl")
        if isinstance(loaded, trimesh.Scene):
            meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                return stl_bytes, "repair: пустая сцена"
            mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        elif isinstance(loaded, trimesh.Trimesh):
            mesh = loaded
        else:
            return stl_bytes, "repair: неизвестный тип"

        def local_cleanup(candidate):
            candidate.merge_vertices()
            candidate.update_faces(candidate.nondegenerate_faces())
            if hasattr(candidate, "unique_faces"):
                candidate.update_faces(candidate.unique_faces())
            elif hasattr(candidate, "remove_duplicate_faces"):
                candidate.remove_duplicate_faces()
            candidate.remove_unreferenced_vertices()
            trimesh_repair.fix_normals(candidate)
            trimesh_repair.fix_winding(candidate)
            trimesh_repair.fill_holes(candidate)
            candidate.process(validate=True)
            return candidate

        mesh = local_cleanup(mesh)
        pymesh_note = "trimesh"
        try:
            import pymeshfix

            fixer = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
            _run_meshfix_repair(fixer, joincomp=True, remove_smallest_components=False)
            verts, faces = _meshfix_arrays(fixer)
            mesh = local_cleanup(trimesh.Trimesh(vertices=verts, faces=faces, process=False))
            pymesh_note = "pymeshfix"
            if _count_non_manifold_edges(mesh) > 0:
                fixer = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
                _run_meshfix_repair(fixer, joincomp=True, remove_smallest_components=True)
                verts2, faces2 = _meshfix_arrays(fixer)
                mesh2 = local_cleanup(trimesh.Trimesh(vertices=verts2, faces=faces2, process=False))
                if 0 <= _count_non_manifold_edges(mesh2) < _count_non_manifold_edges(mesh):
                    mesh = mesh2
                    pymesh_note = "pymeshfix strict"
        except Exception as e:
            pymesh_note = f"{pymesh_note}; pymeshfix skip: {type(e).__name__}: {str(e)[:80]}"

        watertight = bool(getattr(mesh, "is_watertight", False))
        nm = _count_non_manifold_edges(mesh)
        out = mesh.export(file_type="stl")
        if isinstance(out, str):
            out = out.encode("latin-1", errors="ignore")
        if watertight and nm == 0:
            note = f"repair OK ({pymesh_note})"
        elif nm > 0:
            note = f"repair WARNING: {nm} non-manifold edges ({pymesh_note})"
        else:
            note = f"repair: частично ({pymesh_note})"
        return bytes(out), note
    except Exception as e:
        return stl_bytes, f"repair skip: {e}"


def _run_meshfix_repair(fixer: object, *, joincomp: bool, remove_smallest_components: bool) -> None:
    """pymeshfix has different signatures across Python envs."""
    try:
        fixer.repair(
            verbose=False,
            joincomp=joincomp,
            remove_smallest_components=remove_smallest_components,
        )
    except TypeError:
        fixer.repair(
            joincomp=joincomp,
            remove_smallest_components=remove_smallest_components,
        )


def _meshfix_arrays(fixer: object) -> tuple[np.ndarray, np.ndarray]:
    """Return repaired vertices/faces across pymeshfix API variants."""
    vertices = getattr(fixer, "v", None)
    faces = getattr(fixer, "f", None)
    if vertices is None:
        vertices = getattr(fixer, "points", None)
    if faces is None:
        faces = getattr(fixer, "faces", None)
    if vertices is None or faces is None:
        raise AttributeError("MeshFix has no repaired vertex/face arrays")
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _manifold_repair_stl_mesh_local(stl_bytes: bytes) -> Tuple[bytes, str]:
    """Strict repair: rebuild through manifold3d, then close remaining pinholes."""
    try:
        import io

        import trimesh
        from manifold3d import Manifold, Mesh
    except ImportError as e:
        return stl_bytes, f"manifold repair skip: {e}"

    try:
        loaded = trimesh.load(io.BytesIO(stl_bytes), file_type="stl")
        if isinstance(loaded, trimesh.Scene):
            meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                return stl_bytes, "manifold repair skip: пустая сцена"
            mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        elif isinstance(loaded, trimesh.Trimesh):
            mesh = loaded
        else:
            return stl_bytes, "manifold repair skip: неизвестный тип"

        before = _count_non_manifold_edges(mesh)
        mani = Manifold(
            mesh=Mesh(
                vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
            )
        )
        status = str(mani.status())
        out_mesh = mani.to_mesh()
        if len(out_mesh.tri_verts) == 0:
            return stl_bytes, f"manifold repair skip: empty ({status})"
        verts = np.asarray(out_mesh.vert_properties, dtype=np.float64)
        faces = np.asarray(out_mesh.tri_verts, dtype=np.int64)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        # Avoid trimesh.process/export here: on some large Meshy meshes it can
        # native-crash with Floating point exception. Count on the raw manifold.
        manifold_count = _count_non_manifold_edges(mesh)
        note = f"manifold3d {before}→{manifold_count} ({status})"

        final_verts, final_faces = verts, faces
        if manifold_count > 0:
            try:
                import pymeshfix

                fixer = pymeshfix.MeshFix(final_verts, final_faces)
                _run_meshfix_repair(fixer, joincomp=True, remove_smallest_components=True)
                candidate_verts, candidate_faces = _meshfix_arrays(fixer)
                candidate_mesh = trimesh.Trimesh(
                    vertices=candidate_verts, faces=candidate_faces, process=False
                )
                candidate_count = _count_non_manifold_edges(candidate_mesh)
                if candidate_count <= max(0, manifold_count):
                    final_verts, final_faces = candidate_verts, candidate_faces
                    manifold_count = candidate_count
                    note += f"; pymeshfix strict →{manifold_count}"
            except Exception as e:
                note += f"; pymeshfix strict skip: {type(e).__name__}: {str(e)[:80]}"

        out = _write_binary_stl(final_verts[final_faces])
        try:
            checked = trimesh.load(io.BytesIO(out), file_type="stl")
            nm = _count_non_manifold_edges(checked)
            watertight = bool(getattr(checked, "is_watertight", False))
        except Exception:
            nm = manifold_count
            watertight = nm == 0
        if nm > 0:
            try:
                import pymeshfix

                fixer = pymeshfix.MeshFix(final_verts, final_faces)
                _run_meshfix_repair(fixer, joincomp=True, remove_smallest_components=True)
                candidate_verts, candidate_faces = _meshfix_arrays(fixer)
                candidate_out = _write_binary_stl(candidate_verts[candidate_faces])
                checked2 = trimesh.load(io.BytesIO(candidate_out), file_type="stl")
                nm2 = _count_non_manifold_edges(checked2)
                watertight2 = bool(getattr(checked2, "is_watertight", False))
                if 0 <= nm2 < nm or (nm2 == 0 and watertight2):
                    out = candidate_out
                    nm = nm2
                    watertight = watertight2
                    note += f"; post-write pymeshfix →{nm}"
            except Exception as e:
                note += f"; post-write pymeshfix skip: {type(e).__name__}: {str(e)[:80]}"
        if watertight and nm == 0:
            return bytes(out), f"repair OK ({note})"
        if nm > 0:
            return bytes(out), f"repair WARNING: {nm} non-manifold edges ({note})"
        return bytes(out), f"repair: частично ({note})"
    except Exception as e:
        return stl_bytes, f"manifold repair skip: {type(e).__name__}: {str(e)[:100]}"


def manifold_repair_stl_mesh(stl_bytes: bytes, *, timeout: int = 240) -> Tuple[bytes, str]:
    """
    Strict watertight repair in a worker process. This is slower than the
    ordinary pymeshfix path, so it is reserved for Meshy STL that Bambu rejects.
    """
    if not stl_bytes:
        return stl_bytes, "manifold repair skip: пустой STL"
    try:
        with tempfile.TemporaryDirectory(prefix="mro-bot-manifold-repair-") as td:
            tmp = Path(td)
            src = tmp / "in.stl"
            dst = tmp / "out.stl"
            note = tmp / "note.txt"
            src.write_bytes(stl_bytes)
            code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from bot.services.stl_postprocess import _manifold_repair_stl_mesh_local\n"
                "data = Path(sys.argv[1]).read_bytes()\n"
                "out, msg = _manifold_repair_stl_mesh_local(data)\n"
                "Path(sys.argv[2]).write_bytes(out)\n"
                "Path(sys.argv[3]).write_text(msg, encoding='utf-8')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, str(src), str(dst), str(note)],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="ignore").strip()
                if proc.returncode < 0:
                    err = f"signal {-proc.returncode}"
                return stl_bytes, f"manifold repair skip: worker failed ({err[:120]})"
            if not dst.exists():
                return stl_bytes, "manifold repair skip: worker produced no STL"
            return dst.read_bytes(), note.read_text(encoding="utf-8", errors="ignore")[:500]
    except subprocess.TimeoutExpired:
        return stl_bytes, "manifold repair skip: worker timeout"
    except Exception as e:
        return stl_bytes, f"manifold repair skip: worker error {type(e).__name__}: {str(e)[:100]}"


def repair_stl_mesh(stl_bytes: bytes) -> Tuple[bytes, str]:
    """
    Repair runs in a worker process because trimesh/pymeshfix can crash the
    interpreter with a native Floating point exception on malformed Meshy STL.
    """
    if not stl_bytes:
        return stl_bytes, "repair skip: пустой STL"
    if len(stl_bytes) < 2_000:
        return _repair_stl_mesh_local(stl_bytes)

    try:
        with tempfile.TemporaryDirectory(prefix="mro-bot-repair-") as td:
            tmp = Path(td)
            src = tmp / "in.stl"
            dst = tmp / "out.stl"
            note = tmp / "note.txt"
            src.write_bytes(stl_bytes)
            code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from bot.services.stl_postprocess import _repair_stl_mesh_local\n"
                "data = Path(sys.argv[1]).read_bytes()\n"
                "out, msg = _repair_stl_mesh_local(data)\n"
                "Path(sys.argv[2]).write_bytes(out)\n"
                "Path(sys.argv[3]).write_text(msg, encoding='utf-8')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, str(src), str(dst), str(note)],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=90,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="ignore").strip()
                if proc.returncode < 0:
                    err = f"signal {-proc.returncode}"
                return stl_bytes, f"repair skip: worker failed ({err[:120]})"
            if not dst.exists():
                return stl_bytes, "repair skip: worker produced no STL"
            return dst.read_bytes(), note.read_text(encoding="utf-8", errors="ignore")[:300]
    except subprocess.TimeoutExpired:
        return stl_bytes, "repair skip: worker timeout"
    except Exception as e:
        return stl_bytes, f"repair skip: worker error {type(e).__name__}: {str(e)[:100]}"


def _count_non_manifold_edges(mesh: object) -> int:
    """Сколько рёбер не manifold (как в Bambu Studio)."""
    try:
        import numpy as np

        m = mesh  # type: ignore
        edges = m.edges_sorted
        if edges is None or len(edges) == 0:
            return 0
        inv = m.edges_unique_inverse
        counts = np.bincount(inv)
        # Bambu warns both about open boundary edges (<2 faces) and over-connected edges (>2 faces).
        bad = int(np.sum(counts != 2))
        return bad
    except Exception:
        return -1


def _repair_note_non_manifold_count(note: str) -> int | None:
    m = re.search(r"(\d+)\s+non-manifold", note or "", re.I)
    return int(m.group(1)) if m else None


def _prepare_meshy_stl_for_bambu_local(
    stl_bytes: bytes,
    *,
    user_text: str = "",
) -> StlNormalizeResult:
    """Масштаб → repair → готово для Bambu Studio."""
    norm = normalize_meshy_stl(stl_bytes, user_text=user_text)
    repaired, repair_note = repair_stl_mesh(norm.data)
    if "repair WARNING" in repair_note or "repair skip" in repair_note:
        strict_data, strict_note = manifold_repair_stl_mesh(repaired)
        strict_count = _repair_note_non_manifold_count(strict_note)
        repair_count = _repair_note_non_manifold_count(repair_note)
        if (
            ("repair OK" in strict_note)
            or (repair_count is not None and strict_count is not None and strict_count < repair_count)
            or (repair_count is None and "repair skip" in repair_note and "repair skip" not in strict_note)
        ):
            repaired = strict_data
            repair_note = f"{strict_note}; selected over ordinary repair: {repair_note}"
        else:
            repair_note = f"{repair_note}; manifold retry not better: {strict_note}"
    notes = [norm.note, repair_note]
    try:
        tris = _parse_stl(repaired)
        _, _, size = _dims(tris)
        w, d, h = float(size[0]), float(size[1]), float(size[2])
        return StlNormalizeResult(
            data=repaired,
            width_mm=w,
            depth_mm=d,
            height_mm=h,
            scale_applied=norm.scale_applied,
            note="; ".join(n for n in notes if n),
        )
    except Exception:
        return StlNormalizeResult(
            data=repaired,
            width_mm=norm.width_mm,
            depth_mm=norm.depth_mm,
            height_mm=norm.height_mm,
            scale_applied=norm.scale_applied,
            note="; ".join(n for n in notes if n),
        )


def _prepare_large_meshy_stl_for_bambu(
    stl_bytes: bytes,
    *,
    user_text: str = "",
) -> StlNormalizeResult:
    """
    Heavy Meshy exports can spend most of the worker timeout inside repair.
    Keep scale/centering deterministic in-process, then isolate only repair.
    """
    norm = normalize_meshy_stl(stl_bytes, user_text=user_text)
    repaired, repair_note = manifold_repair_stl_mesh(norm.data)
    if "repair OK" not in repair_note:
        ordinary_data, ordinary_note = repair_stl_mesh(repaired)
        ordinary_count = _repair_note_non_manifold_count(ordinary_note)
        repair_count = _repair_note_non_manifold_count(repair_note)
        if (
            "repair OK" in ordinary_note
            or (repair_count is not None and ordinary_count is not None and ordinary_count < repair_count)
        ):
            repaired = ordinary_data
            repair_note = f"{ordinary_note}; selected after manifold repair: {repair_note}"
        else:
            repair_note = f"{repair_note}; ordinary retry not better: {ordinary_note}"
    notes = [norm.note, repair_note]
    try:
        tris = _parse_stl(repaired)
        _, _, size = _dims(tris)
        w, d, h = float(size[0]), float(size[1]), float(size[2])
        return StlNormalizeResult(
            data=repaired,
            width_mm=w,
            depth_mm=d,
            height_mm=h,
            scale_applied=norm.scale_applied,
            note="; ".join(n for n in notes if n),
        )
    except Exception:
        return StlNormalizeResult(
            data=repaired,
            width_mm=norm.width_mm,
            depth_mm=norm.depth_mm,
            height_mm=norm.height_mm,
            scale_applied=norm.scale_applied,
            note="; ".join(n for n in notes if n),
        )


def prepare_meshy_stl_for_bambu(
    stl_bytes: bytes,
    *,
    user_text: str = "",
) -> StlNormalizeResult:
    """
    Normalize+repair in a worker process. Meshy STL can trigger native FPE in
    numpy/trimesh on macOS; the Telegram polling process must survive that.
    """
    if not stl_bytes:
        return StlNormalizeResult(
            data=stl_bytes,
            width_mm=0.0,
            depth_mm=0.0,
            height_mm=0.0,
            scale_applied=1.0,
            note="postprocess skip: пустой STL",
        )
    if len(stl_bytes) > 8_000_000:
        try:
            return _prepare_large_meshy_stl_for_bambu(stl_bytes, user_text=user_text)
        except Exception as e:
            return StlNormalizeResult(
                data=stl_bytes,
                width_mm=0.0,
                depth_mm=0.0,
                height_mm=0.0,
                scale_applied=1.0,
                note=f"postprocess skip: large STL error {type(e).__name__}: {str(e)[:100]}",
            )
    try:
        with tempfile.TemporaryDirectory(prefix="mro-bot-postprocess-") as td:
            tmp = Path(td)
            src = tmp / "in.stl"
            dst = tmp / "out.stl"
            meta = tmp / "meta.json"
            src.write_bytes(stl_bytes)
            code = (
                "import json, sys\n"
                "from pathlib import Path\n"
                "from bot.services.stl_postprocess import _prepare_meshy_stl_for_bambu_local\n"
                "res = _prepare_meshy_stl_for_bambu_local(Path(sys.argv[1]).read_bytes(), user_text=sys.argv[4])\n"
                "Path(sys.argv[2]).write_bytes(res.data)\n"
                "Path(sys.argv[3]).write_text(json.dumps({\n"
                " 'width_mm': res.width_mm, 'depth_mm': res.depth_mm, 'height_mm': res.height_mm,\n"
                " 'scale_applied': res.scale_applied, 'note': res.note\n"
                "}, ensure_ascii=False), encoding='utf-8')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, str(src), str(dst), str(meta), user_text[:2000]],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="ignore").strip()
                if proc.returncode < 0:
                    err = f"signal {-proc.returncode}"
                return StlNormalizeResult(
                    data=stl_bytes,
                    width_mm=0.0,
                    depth_mm=0.0,
                    height_mm=0.0,
                    scale_applied=1.0,
                    note=f"postprocess skip: worker failed ({err[:120]})",
                )
            raw = json.loads(meta.read_text(encoding="utf-8"))
            return StlNormalizeResult(
                data=dst.read_bytes(),
                width_mm=float(raw.get("width_mm") or 0.0),
                depth_mm=float(raw.get("depth_mm") or 0.0),
                height_mm=float(raw.get("height_mm") or 0.0),
                scale_applied=float(raw.get("scale_applied") or 1.0),
                note=str(raw.get("note") or "postprocess OK"),
            )
    except subprocess.TimeoutExpired:
        return StlNormalizeResult(
            data=stl_bytes,
            width_mm=0.0,
            depth_mm=0.0,
            height_mm=0.0,
            scale_applied=1.0,
            note="postprocess skip: worker timeout",
        )
    except Exception as e:
        return StlNormalizeResult(
            data=stl_bytes,
            width_mm=0.0,
            depth_mm=0.0,
            height_mm=0.0,
            scale_applied=1.0,
            note=f"postprocess skip: worker error {type(e).__name__}: {str(e)[:100]}",
        )
