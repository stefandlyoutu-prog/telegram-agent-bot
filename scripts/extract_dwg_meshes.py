"""
Batch extractor for DWG-archive → STL meshes.

Pipeline:
  1. Each archive is unzipped to a temp dir.
  2. All .dwg files are converted via ODA File Converter (DWG → DXF, ACAD2018).
  3. Each DXF is parsed via ezdxf; we extract:
       - 3DFACE  → triangle/quad faces (trivially tessellated)
       - POLYLINE (polyface_mesh / polygon_mesh) → mesh
       - MESH    → SubD mesh (uses ezdxf MeshBuilder)
       - 3DSOLID / BODY / REGION / *SURFACE → ezdxf.acis tessellator
         (parses Autodesk-ASM/ACIS SAB blobs and builds a MeshTransformer)
       - INSERT  → recursive flatten of block definitions
  4. ACIS bodies that fail parsing/tessellation are logged but do not abort
     the archive.
  5. Per-archive STL is written to data/reference_models/<slug>/.

Usage:
  .venv/bin/python scripts/extract_dwg_meshes.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ODA_BIN = Path("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")
DOWNLOADS = Path.home() / "Downloads"
REF_DIR = ROOT / "data" / "reference_models"

TESSELLATABLE = {"3DFACE", "MESH", "POLYLINE", "POLYFACE"}
# These used to be skipped; we now tessellate them via ezdxf.acis.
ACIS_TYPES = {"3DSOLID", "REGION", "BODY", "SURFACE", "REVOLVEDSURFACE",
              "EXTRUDEDSURFACE", "LOFTEDSURFACE", "SWEPTSURFACE",
              "PLANESURFACE", "NURBSSURFACE"}


# Russian/Ukrainian → ASCII transliteration table (no accents).
_CYR_TO_ASCII = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "a", "Б": "b", "В": "v", "Г": "g", "Д": "d", "Е": "e", "Ё": "e",
    "Ж": "zh", "З": "z", "И": "i", "Й": "y", "К": "k", "Л": "l", "М": "m",
    "Н": "n", "О": "o", "П": "p", "Р": "r", "С": "s", "Т": "t", "У": "u",
    "Ф": "f", "Х": "kh", "Ц": "ts", "Ч": "ch", "Ш": "sh", "Щ": "shch",
    "Ъ": "", "Ы": "y", "Ь": "", "Э": "e", "Ю": "yu", "Я": "ya",
    "і": "i", "І": "i", "ї": "yi", "Ї": "yi", "є": "e", "Є": "e",
    "ґ": "g", "Ґ": "g",
})


def _slugify(s: str) -> str:
    # 1) transliterate Cyrillic before NFKD so we keep meaningful tokens
    s = s.translate(_CYR_TO_ASCII)
    # 2) drop any remaining diacritics
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    s = re.sub(r"_+", "_", s)
    # Cap length but keep first 60 chars (more uniqueness than 50)
    return s[:60] or "archive"


def _extract_dwgs(zip_path: Path, dst: Path) -> int:
    """Unpack only .dwg files (with safe ASCII names)."""
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".dwg"):
                continue
            out = dst / f"{n:03d}.dwg"
            out.write_bytes(zf.read(info))
            n += 1
    return n


def _run_oda(src: Path, dst: Path, *, recursive: bool = True,
              audit: bool = False, timeout: int = 300) -> bool:
    args = [
        str(ODA_BIN),
        str(src), str(dst),
        "ACAD2018", "DXF",
        "1" if recursive else "0",
        "1" if audit else "0",
        "*.DWG",
    ]
    try:
        subprocess.run(args, timeout=timeout,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False)
        return True
    except subprocess.TimeoutExpired:
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  DXF → triangle list
# ─────────────────────────────────────────────────────────────────────────────

def _xform(p, transform):
    """Apply 4x4 transform to 3D point if transform is not None."""
    a = np.asarray(p, dtype=np.float64)[:3]
    if transform is None:
        return a
    h = np.concatenate([a, [1.0]])
    out = transform @ h
    return out[:3]


def _emit_3dface(e, transform, triangles):
    """3DFACE → 1 or 2 triangles."""
    pts = []
    for k in ("vtx0", "vtx1", "vtx2", "vtx3"):
        try:
            pts.append(_xform(getattr(e.dxf, k), transform))
        except Exception:
            return
    v0, v1, v2, v3 = pts
    triangles.append(np.array([v0, v1, v2]))
    if not np.allclose(v2, v3, atol=1e-6):
        triangles.append(np.array([v0, v2, v3]))


def _emit_polyface(e, transform, triangles):
    """POLYLINE polyface_mesh: use ezdxf face iteration."""
    try:
        # ezdxf 1.x: indexed_faces() gives ((v_indices, []) pairs
        # Most stable API: virtual_entities() decomposes to 3DFACE entities.
        for sub in e.virtual_entities():
            if sub.dxftype() == "3DFACE":
                _emit_3dface(sub, transform, triangles)
    except Exception:
        pass


def _emit_polymesh(e, transform, triangles):
    """POLYLINE polygon_mesh (M×N grid): triangulate each quad."""
    try:
        m = e.dxf.m_count
        n = e.dxf.n_count
        verts = [v.dxf.location for v in e.vertices]
        if len(verts) < m * n:
            return
        grid = [[_xform(verts[i*n + j], transform) for j in range(n)]
                for i in range(m)]
        for i in range(m - 1):
            for j in range(n - 1):
                a, b = grid[i][j], grid[i][j + 1]
                c, d = grid[i + 1][j + 1], grid[i + 1][j]
                triangles.append(np.array([a, b, c]))
                triangles.append(np.array([a, c, d]))
    except Exception:
        pass


def _emit_mesh(e, transform, triangles):
    """MESH entity (SubD): faces are explicit polygons."""
    try:
        verts = [_xform(v, transform) for v in e.vertices]
        for face in e.faces:
            if len(face) < 3:
                continue
            p0 = verts[face[0]]
            for k in range(1, len(face) - 1):
                triangles.append(np.array([p0, verts[face[k]], verts[face[k + 1]]]))
    except Exception:
        pass


def _apply_transform(verts: np.ndarray, transform) -> np.ndarray:
    if transform is None:
        return verts
    h = np.hstack([verts, np.ones((len(verts), 1), dtype=np.float64)])
    return (transform @ h.T).T[:, :3]


def _emit_acis(e, transform, triangles, acis_stats):
    """3DSOLID / BODY / REGION / *SURFACE → ezdxf.acis tessellator.

    Reads the raw Autodesk-ASM (SAB) blob, parses it into ACIS bodies,
    runs the built-in MeshTransformer tessellator, and emits triangles.
    Failures are counted but never raise — partial bodies are normal in
    real-world DWGs.
    """
    try:
        from ezdxf.acis import api as acis
    except Exception:
        acis_stats["import_fail"] = acis_stats.get("import_fail", 0) + 1
        return

    try:
        sab = e.sab
    except Exception:
        sab = None
    if not sab:
        # No binary SAB blob — try ASCII SAT data as a fallback
        try:
            sat = e.sat
        except Exception:
            sat = None
        if not sat:
            acis_stats["no_data"] = acis_stats.get("no_data", 0) + 1
            return
        try:
            bodies = acis.load(sat)
        except Exception:
            acis_stats["parse_fail"] = acis_stats.get("parse_fail", 0) + 1
            return
    else:
        try:
            bodies = acis.load(sab)
        except Exception:
            acis_stats["parse_fail"] = acis_stats.get("parse_fail", 0) + 1
            return

    for b in bodies:
        try:
            mts = acis.mesh_from_body(b)
        except Exception:
            acis_stats["tess_fail"] = acis_stats.get("tess_fail", 0) + 1
            continue

        for m in mts:
            try:
                verts = np.asarray(m.vertices, dtype=np.float64)
                if verts.size == 0:
                    continue
                if transform is not None:
                    verts = _apply_transform(verts, transform)
                for f in m.faces:
                    if len(f) < 3:
                        continue
                    p0 = verts[f[0]]
                    for k in range(1, len(f) - 1):
                        triangles.append(
                            np.array([p0, verts[f[k]], verts[f[k + 1]]])
                        )
                acis_stats["ok"] = acis_stats.get("ok", 0) + 1
            except Exception:
                acis_stats["emit_fail"] = acis_stats.get("emit_fail", 0) + 1


def _flatten_modelspace(msp, transform=None, depth: int = 0,
                         acis_stats: Optional[dict] = None
                         ) -> Tuple[List, Counter, dict]:
    """
    Walk modelspace + nested INSERT blocks.
    Returns (triangles, entity_counts, acis_stats).
    """
    triangles: List[np.ndarray] = []
    counts: Counter = Counter()
    if acis_stats is None:
        acis_stats = {}

    for e in msp:
        et = e.dxftype()
        counts[et] += 1

        if et == "3DFACE":
            _emit_3dface(e, transform, triangles)
        elif et == "MESH":
            _emit_mesh(e, transform, triangles)
        elif et == "POLYLINE":
            try:
                if e.is_poly_face_mesh:
                    _emit_polyface(e, transform, triangles)
                elif e.is_polygon_mesh:
                    _emit_polymesh(e, transform, triangles)
            except Exception:
                pass
        elif et in ACIS_TYPES:
            _emit_acis(e, transform, triangles, acis_stats)
        elif et == "INSERT" and depth < 4:
            try:
                block = msp.doc.blocks.get(e.dxf.name)
                if block is None:
                    continue
                ins = e.dxf.insert
                sx, sy, sz = (e.dxf.xscale, e.dxf.yscale, e.dxf.zscale)
                rot = np.deg2rad(getattr(e.dxf, "rotation", 0.0) or 0.0)
                cr, sr = float(np.cos(rot)), float(np.sin(rot))
                T = np.array([
                    [cr*sx, -sr*sy, 0, ins[0]],
                    [sr*sx,  cr*sy, 0, ins[1]],
                    [0,      0,     sz, ins[2] if len(ins) > 2 else 0],
                    [0,      0,     0,  1.0],
                ], dtype=np.float64)
                if transform is not None:
                    T = transform @ T
                inner_tris, inner_counts, _ = _flatten_modelspace(
                    block, transform=T, depth=depth + 1, acis_stats=acis_stats
                )
                triangles.extend(inner_tris)
                for k, v in inner_counts.items():
                    counts[f"insert:{k}"] += v
            except Exception:
                pass

    return triangles, counts, acis_stats


def _triangles_to_stl(triangles: List[np.ndarray], out_path: Path) -> int:
    if not triangles:
        return 0
    import trimesh
    arr = np.stack(triangles, axis=0)  # (n, 3, 3)
    verts = arr.reshape(-1, 3)
    faces = np.arange(len(verts)).reshape(-1, 3)
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    # Try merging close vertices for cleaner output
    try:
        m.merge_vertices()
    except Exception:
        pass
    m.export(str(out_path))
    return len(m.faces)


# ─────────────────────────────────────────────────────────────────────────────
#  Per-archive pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process_archive(zip_path: Path) -> dict:
    import ezdxf

    title = re.sub(r"\s*dnl\d+(\s\(\d+\))?\.zip$", "", zip_path.name,
                    flags=re.I).strip()
    # Defend against slug collisions for similar Russian titles (e.g. all
    # 3D-something archives) by appending the dnl-id when present.
    dnl_m = re.search(r"dnl(\d+)", zip_path.name, re.I)
    suffix = f"_{dnl_m.group(1)}" if dnl_m else ""
    slug = f"dwg_{_slugify(title)}{suffix}"
    result = {
        "archive": zip_path.name,
        "title": title,
        "slug": slug,
        "ok": False,
        "n_dwg": 0,
        "n_dxf": 0,
        "n_triangles": 0,
        "n_faces": 0,
        "acis_total": 0,
        "acis_stats": {},
        "entity_counts": {},
        "stl_path": None,
        "bbox_mm": None,
        "error": None,
    }

    tmp_src = Path(tempfile.mkdtemp(prefix="oda_src_"))
    tmp_dst = Path(tempfile.mkdtemp(prefix="oda_dst_"))
    try:
        result["n_dwg"] = _extract_dwgs(zip_path, tmp_src)
        if result["n_dwg"] == 0:
            result["error"] = "no DWG files in archive"
            return result

        ok = _run_oda(tmp_src, tmp_dst, timeout=300)
        if not ok:
            result["error"] = "ODA conversion timed out"
            return result

        dxfs = list(tmp_dst.glob("*.dxf"))
        result["n_dxf"] = len(dxfs)
        if not dxfs:
            result["error"] = "no DXF produced (ODA failed silently)"
            return result

        all_triangles: List[np.ndarray] = []
        all_counts: Counter = Counter()
        all_acis: dict = {}
        for dxf in dxfs:
            try:
                doc = ezdxf.readfile(str(dxf))
                tris, counts, acis_stats = _flatten_modelspace(doc.modelspace())
                all_triangles.extend(tris)
                for k, v in counts.items():
                    all_counts[k] += v
                for k, v in acis_stats.items():
                    all_acis[k] = all_acis.get(k, 0) + v
            except Exception as exc:
                result.setdefault("warnings", []).append(
                    f"{dxf.name}: {type(exc).__name__}: {exc}"
                )

        result["n_triangles"] = len(all_triangles)
        result["entity_counts"] = {k: int(v) for k, v in all_counts.most_common(20)}
        result["acis_total"] = sum(
            v for k, v in all_counts.items() if k in ACIS_TYPES
        )
        result["acis_stats"] = {k: int(v) for k, v in all_acis.items()}

        if all_triangles:
            dst_dir = REF_DIR / slug
            dst_dir.mkdir(parents=True, exist_ok=True)
            stl_path = dst_dir / "extracted_mesh.stl"
            n_faces = _triangles_to_stl(all_triangles, stl_path)
            result["n_faces"] = n_faces
            result["stl_path"] = str(stl_path.relative_to(ROOT))

            # bbox
            arr = np.stack(all_triangles, axis=0).reshape(-1, 3)
            bbox = arr.max(0) - arr.min(0)
            result["bbox_mm"] = [round(float(x), 2) for x in bbox]

            # mini manifest
            (dst_dir / "manifest.json").write_text(
                json.dumps({
                    **{k: v for k, v in result.items() if k != "stl_path"},
                    "extracted_via": "ODA File Converter 27.1 + ezdxf",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["ok"] = True
        else:
            result["error"] = (
                f"No tessellatable 3D entities found "
                f"({result['acis_total']} ACIS solids/surfaces found, "
                f"stats={result['acis_stats']})."
            )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp_src, ignore_errors=True)
        shutil.rmtree(tmp_dst, ignore_errors=True)

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                         help="Process only first N archives")
    parser.add_argument("--filter", type=str, default="",
                         help="Substring filter on archive name")
    parser.add_argument("--rerun", action="store_true",
                         help="Process all DWG archives, even those already "
                              "extracted previously (used after enabling "
                              "ACIS tessellation).")
    args = parser.parse_args()

    if not ODA_BIN.exists():
        print(f"[FATAL] ODA binary missing: {ODA_BIN}")
        return 2

    # Find candidate archives from the catalog (DWG-only ones)
    cat_path = REF_DIR / "cad_archives_catalog.json"
    if not cat_path.is_file():
        print(f"[FATAL] catalog missing: {cat_path}")
        return 2
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    candidates = [
        DOWNLOADS / a["name"]
        for a in cat["archives"]
        if a["content_formats"].get("dwg")
        and (args.rerun or not any(
            a["content_formats"].get(k)
            for k in ("stl", "step", "stp", "obj", "3mf")
        ))
    ]
    if args.filter:
        candidates = [c for c in candidates if args.filter.lower() in c.name.lower()]
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"Processing {len(candidates)} DWG archives...\n")

    results: List[dict] = []
    t0 = time.time()
    for i, zp in enumerate(candidates, 1):
        if not zp.exists():
            print(f"  [{i}/{len(candidates)}] SKIP missing: {zp.name}")
            continue
        r = process_archive(zp)
        results.append(r)
        flag = "OK " if r["ok"] else "—  "
        size_kb = (Path(ROOT) / r["stl_path"]).stat().st_size // 1024 \
                  if r["ok"] and r["stl_path"] else 0
        bbox = (
            "×".join(f"{x:.0f}" for x in r["bbox_mm"])
            if r.get("bbox_mm") else "—"
        )
        ok_acis = r.get("acis_stats", {}).get("ok", 0)
        info = (
            f"{flag} [{i:2d}/{len(candidates)}] {zp.name[:48]:48s} "
            f"DWG={r['n_dwg']} tris={r['n_triangles']:6d} "
            f"acis={ok_acis}/{r['acis_total']:<4d} bbox={bbox}"
        )
        if not r["ok"]:
            info += f"  ✗ {r['error']}"
        elif size_kb:
            info += f"  → {size_kb} KB"
        print(info)

    acis_ok_total = sum(r.get("acis_stats", {}).get("ok", 0) for r in results)
    acis_total = sum(r.get("acis_total", 0) for r in results)
    summary = {
        "total_archives": len(candidates),
        "ok": sum(1 for r in results if r["ok"]),
        "acis_total": acis_total,
        "acis_tessellated_ok": acis_ok_total,
        "elapsed_sec": round(time.time() - t0, 1),
        "results": results,
    }
    out = REF_DIR / "dwg_extraction_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\nReport: {out}")
    print(f"  archives processed     : {summary['total_archives']}")
    print(f"  STLs produced          : {summary['ok']}")
    print(f"  ACIS bodies seen       : {summary['acis_total']}")
    print(f"  ACIS bodies tessellated: {summary['acis_tessellated_ok']}")
    print(f"  elapsed                : {summary['elapsed_sec']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
