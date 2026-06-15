"""Small on-disk cache for expensive Meshy print assets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from bot.config import DATA_DIR


CACHE_DIR = DATA_DIR / "mesh_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class CachedMeshAsset:
    data: bytes
    filename: str
    meta: Dict[str, Any]


def _safe_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", key.strip().lower())[:80] or "asset"


def _base_path(user_id: int, key: str) -> Path:
    user_dir = CACHE_DIR / str(int(user_id))
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / _safe_key(key)


def save_mesh_asset(
    user_id: int,
    key: str,
    *,
    data: bytes,
    filename: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    base = _base_path(user_id, key)
    (base.with_suffix(".bin")).write_bytes(data)
    (base.with_suffix(".json")).write_text(
        json.dumps({"filename": filename, "meta": meta or {}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_mesh_asset(user_id: int, key: str) -> Optional[CachedMeshAsset]:
    base = _base_path(user_id, key)
    bin_path = base.with_suffix(".bin")
    json_path = base.with_suffix(".json")
    if not bin_path.exists() or not json_path.exists():
        return None
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        filename = str(raw.get("filename") or f"{_safe_key(key)}.stl")
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        return CachedMeshAsset(data=bin_path.read_bytes(), filename=filename, meta=meta)
    except Exception:
        return None

