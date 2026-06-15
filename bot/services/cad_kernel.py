"""
Real CAD kernel layer (OpenCASCADE via CadQuery).

This is the bot's first *true* B-rep CAD backend.  Unlike the OpenSCAD
template path (extruded primitives) and the raw trimesh builders, this module
does genuine mechanical CAD: boolean operations, fillets, chamfers,
counterbores, gussets and STEP export — the operations a real
инженер-конструктор uses.

Design goals:

  * **Lazy import.**  OCP is a ~185 MB native library; importing it costs a
    couple of seconds.  We never import it at bot start-up or for non-CAD
    requests — only when a CAD generator is actually invoked.
  * **trimesh hand-off.**  Every builder returns a clean, watertight
    :class:`trimesh.Trimesh` so the rest of the pipeline (mesh_engineering,
    AMS colours, assembly preview, ZIP export) works unchanged.
  * **STEP alongside STL.**  Functional parts ship a STEP file too, so the
    user can edit them in any MCAD tool.

If CadQuery is not installed the module degrades gracefully: :func:`available`
returns ``False`` and callers fall back to the existing generators.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import trimesh
except Exception:  # pragma: no cover
    trimesh = None  # type: ignore

_CQ = None
_CQ_TRIED = False


def _cq():
    """Lazily import cadquery; cache the module (or None on failure)."""
    global _CQ, _CQ_TRIED
    if _CQ_TRIED:
        return _CQ
    _CQ_TRIED = True
    try:
        import cadquery as cq  # noqa: WPS433 (lazy on purpose)

        _CQ = cq
    except Exception:
        _CQ = None
    return _CQ


def available() -> bool:
    return _cq() is not None


# ─────────────────────────────────────────────────────────────────────────────
#  CAD → trimesh / STEP
# ─────────────────────────────────────────────────────────────────────────────

def to_trimesh(obj, tol: float = 0.1) -> "trimesh.Trimesh":
    """Tessellate a CadQuery Workplane/Shape into a clean trimesh mesh.

    ``tol`` is the linear deflection in mm — smaller ⇒ finer mesh.
    """
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")

    shape = obj.val() if hasattr(obj, "val") else obj
    verts, faces = shape.tessellate(tol)
    # Copy out of the OCP objects immediately so no OCCT handles linger while
    # trimesh works (reduces intermittent native crashes).
    V = np.array([[v.x, v.y, v.z] for v in verts], dtype=float)
    F = np.array(faces, dtype=np.int64)
    del verts, faces, shape
    # process=True already merges duplicate vertices and drops degenerate
    # faces; we avoid the deprecated explicit calls that can crash trimesh 4.x.
    m = trimesh.Trimesh(vertices=V, faces=F, process=True)
    try:
        m.fix_normals()
    except Exception:
        pass
    return m


def export_step(obj, path: str) -> None:
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")
    cq.exporters.export(obj, path)


def import_step(path: str, tol: float = 0.1) -> "trimesh.Trimesh":
    """Read a STEP (ISO 10303) file via OCCT and tessellate to trimesh.

    This is the recommended path for solids that ACIS/SAB readers choke on:
    re-export to STEP in the source CAD, then load it here.
    """
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")
    wp = cq.importers.importStep(path)
    return to_trimesh(wp, tol=tol)


def export_step_bytes(obj) -> bytes:
    import tempfile
    import os

    p = tempfile.mktemp(suffix=".step")
    try:
        export_step(obj, p)
        with open(p, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(p)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Parametric functional generators (return CadQuery Workplanes)
# ─────────────────────────────────────────────────────────────────────────────

def mounting_bracket(arm_a: float = 60.0, arm_b: float = 60.0,
                     width: float = 40.0, thickness: float = 5.0,
                     hole_d: float = 6.5, counterbore_d: float = 11.0,
                     counterbore_depth: float = 3.0,
                     fillet: float = 6.0, gusset: bool = True):
    """L-shaped angle bracket with rounded inner corner, a triangular gusset
    rib and counterbored mounting holes on both flanges.

    Everything here is impossible with plain extruded primitives — it needs
    real fillets, a swept gusset and counterbores from a CAD kernel.
    """
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")

    t = thickness
    # Build the L as one extruded profile in the XZ plane, extruded along Y.
    # Profile (x = along horizontal arm, z = up the vertical arm):
    #   (0,0) → (arm_a,0) → (arm_a,t) → (t,t) → (t,arm_b) → (0,arm_b) → close
    profile = [
        (0.0, 0.0), (arm_a, 0.0), (arm_a, t),
        (t, t), (t, arm_b), (0.0, arm_b),
    ]
    bracket = (cq.Workplane("XZ")
               .workplane(offset=-width / 2.0)
               .polyline(profile).close()
               .extrude(width))

    # Fillet the single concave inner edge (runs along Y at x=t, z=t).
    if fillet > 0:
        try:
            inner = bracket.edges(
                cq.NearestToPointSelector((t, 0.0, t))
            )
            bracket = inner.fillet(min(fillet, t * 1.6, width / 3.0))
        except Exception:
            pass

    # Triangular gusset rib in the mid-plane for bending strength.
    if gusset:
        try:
            gh = min(arm_a, arm_b) * 0.6
            pts = [(t, t), (t + gh, t), (t, t + gh)]
            rib = (cq.Workplane("XZ")
                   .workplane(offset=-t / 2.0)
                   .polyline(pts).close()
                   .extrude(t))
            bracket = bracket.union(rib)
        except Exception:
            pass

    # Counterbored hole in the horizontal flange (top face, +Z).
    try:
        bracket = (bracket.faces(">Z").workplane(centerOption="CenterOfMass")
                   .pushPoints([(arm_a * 0.6 - (arm_a) / 2.0, 0)])
                   .cboreHole(hole_d, counterbore_d, counterbore_depth))
    except Exception:
        pass
    # Through hole in the vertical flange (back face, -X).
    try:
        bracket = (bracket.faces("<X").workplane(centerOption="CenterOfMass")
                   .pushPoints([(0, arm_b * 0.6 - arm_b / 2.0)])
                   .hole(hole_d))
    except Exception:
        pass

    return bracket


def filleted_box(width: float = 60.0, depth: float = 40.0, height: float = 25.0,
                 wall: float = 2.4, fillet: float = 4.0,
                 lid_lip: float = 1.0):
    """Open-top box with rounded vertical edges and a stacking lip — a clean
    parametric container that the OpenSCAD `hollow_box` cannot round."""
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")
    box = (cq.Workplane("XY").box(width, depth, height,
                                  centered=(True, True, False)))
    try:
        box = box.edges("|Z").fillet(fillet)
    except Exception:
        pass
    # Hollow it out from the top.
    box = (box.faces(">Z").shell(-wall))
    return box


def flanged_bushing(bore: float = 20.0, flange_d: float = 60.0,
                    flange_t: float = 6.0, hub_d: float = 32.0,
                    hub_len: float = 24.0, chamfer: float = 1.5):
    """Flanged bushing/gland: a hub + flange with a chamfered bore lead-in.
    Demonstrates chamfers and concentric turning the template path lacks."""
    cq = _cq()
    if cq is None:
        raise RuntimeError("CadQuery is not available")
    part = (cq.Workplane("XY")
            .circle(flange_d / 2.0).extrude(flange_t)
            .faces(">Z").workplane()
            .circle(hub_d / 2.0).extrude(hub_len))
    part = part.faces(">Z").workplane().hole(bore)
    try:
        part = part.faces(">Z").edges(cq.NearestToPointSelector((0, 0, 0))).chamfer(chamfer)
    except Exception:
        try:
            part = part.edges("%CIRCLE").chamfer(chamfer)
        except Exception:
            pass
    return part


# ─────────────────────────────────────────────────────────────────────────────
#  Kit export (STL + STEP + engineering report)
# ─────────────────────────────────────────────────────────────────────────────

# Registry of named parametric generators (for the subprocess worker).
GENERATORS = {
    "mounting_bracket": mounting_bracket,
    "filleted_box": filleted_box,
    "flanged_bushing": flanged_bushing,
}


def build_kit_zip_from_specs(zip_path: str,
                             specs: List[Dict],
                             material: str = "petg",
                             tol: float = 0.12,
                             min_wall_mm: float = 1.2) -> Dict[str, int]:
    """Build a kit ZIP from JSON-serialisable specs.

    Each spec is ``{"name": str, "generator": str, "params": {...}}`` where
    ``generator`` is a key of :data:`GENERATORS`.  This is what the subprocess
    worker calls so OCCT never runs in the bot's own process.
    """
    parts: List[Tuple[str, object]] = []
    for spec in specs:
        gen = GENERATORS.get(spec.get("generator", ""))
        if gen is None:
            continue
        params = spec.get("params") or {}
        wp = gen(**params)
        parts.append((spec.get("name") or spec["generator"], wp))
    return export_cad_kit_zip(zip_path, parts, material=material, tol=tol,
                              min_wall_mm=min_wall_mm)


def build_kit_zip_safe(zip_path: str,
                       specs: List[Dict],
                       material: str = "petg",
                       timeout: int = 120,
                       attempts: int = 3) -> Dict:
    """Run :func:`build_kit_zip_from_specs` in an isolated subprocess.

    OpenCASCADE is non-reentrant and can intermittently segfault; running it
    out-of-process guarantees the bot itself never dies, and we retry a few
    times because such crashes are often transient.  Returns a dict with
    ``ok``, ``counts`` and optional ``error``.
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parents[2])
    payload = json.dumps({
        "zip_path": zip_path,
        "specs": specs,
        "material": material,
    })
    worker = str(Path(root) / "scripts" / "cad_worker.py")

    last: Dict = {"ok": False, "error": "not attempted"}
    for attempt in range(1, max(1, attempts) + 1):
        try:
            proc = subprocess.run(
                [sys.executable, worker, payload],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            last = {"ok": False, "error": f"CAD worker timeout ({timeout}s)"}
            continue
        if proc.returncode != 0:
            sig = -proc.returncode if proc.returncode < 0 else proc.returncode
            last = {"ok": False,
                    "error": f"CAD worker crashed (rc={proc.returncode}, "
                             f"sig={sig}, attempt {attempt}); "
                             f"{(proc.stderr or '').strip()[:160]}"}
            continue
        try:
            out = json.loads((proc.stdout or "{}").strip().splitlines()[-1])
        except Exception as exc:
            last = {"ok": False, "error": f"bad worker output: {exc}"}
            continue
        if out.get("ok"):
            out["attempts"] = attempt
            return out
        last = out
    return last


def export_cad_kit_zip(zip_path: str,
                       parts: List[Tuple[str, object]],
                       material: str = "petg",
                       tol: float = 0.1,
                       min_wall_mm: float = 1.2) -> Dict[str, int]:
    """Write a kit ZIP: per-part STL **and** STEP, plus an engineering report.

    ``parts`` is a list of (name, cadquery_workplane).
    """
    import io
    import zipfile

    # Optional closed-loop auto-prep (orient/split) before writing STL.
    try:
        from bot.services import mesh_engineering as _ME
    except Exception:
        _ME = None

    meshes: List[Tuple[str, "trimesh.Trimesh"]] = []
    counts: Dict[str, int] = {}
    actions_all: List[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, wp in parts:
            mesh = to_trimesh(wp, tol=tol)

            # STEP is the editable master — always the as-designed solid.
            try:
                zf.writestr(f"step/{name}.step", export_step_bytes(wp))
            except Exception:
                pass

            # STL is print-ready: auto-oriented and split if it won't fit.
            out_parts: List[Tuple[str, "trimesh.Trimesh"]] = [(name, mesh)]
            if _ME is not None:
                try:
                    res = _ME.auto_prepare(mesh, name=name, material=material,
                                           min_wall_mm=min_wall_mm)
                    out_parts = res.parts
                    for a in res.actions:
                        actions_all.append(f"{name}: {a}")
                except Exception:
                    out_parts = [(name, mesh)]

            for pname, pmesh in out_parts:
                meshes.append((pname, pmesh))
                counts[pname] = len(pmesh.faces)
                sbuf = io.BytesIO()
                pmesh.export(sbuf, file_type="stl")
                zf.writestr(f"parts/{pname}.stl", sbuf.getvalue())

        if _ME is not None:
            try:
                report = _ME.kit_engineering_report(meshes, material=material,
                                                    min_wall_mm=min_wall_mm)
                if actions_all:
                    report += ("\nАВТО-ПОДГОТОВКА (замкнутая петля):\n  - "
                               + "\n  - ".join(actions_all) + "\n")
                zf.writestr("engineering_report.txt", report.encode("utf-8"))
            except Exception:
                pass

        readme = (
            "CAD kit (OpenCASCADE / CadQuery)\n"
            "================================\n"
            "Каждая деталь идёт в STL (для печати) и STEP (для CAD-правки).\n"
            "Геометрия построена настоящим B-rep кернелом: фаски, скругления,\n"
            "boolean, counterbore — не выдавленные примитивы.\n\n"
            "Детали:\n"
        )
        for name, mesh in meshes:
            readme += (f"  {name:18s} V={len(mesh.vertices):6d} "
                       f"F={len(mesh.faces):6d} "
                       f"watertight={mesh.is_watertight}\n")
        zf.writestr("README.txt", readme.encode("utf-8"))

    return counts
