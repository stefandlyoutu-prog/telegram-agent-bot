"""Match user requests to downloaded reference kits and print archetypes."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "data" / "reference_models" / "library_index.json"

# Maps library category → bot project_kind (existing deterministic builders).
CATEGORY_TO_PROJECT_KIND: Dict[str, str] = {
    "rc_aircraft": "rc_aircraft_kit",
    "drone_fpv": "drone_fpv_kit",
    "vehicle_rc": "vehicle_kit",
    "robot_mechanism": "robot_mechanism_kit",
    "mechanical_gear": "mechanical_planetarium",
    "architecture_miniature": "architecture_miniature",
    "kit_card": "kit_card",
    "articulated_wearable": "articulated_wearable",
    "printer_accessory": "printer_tool_holder",
    "functional_container": "modular_storage_system",
    "character_sculpt": "split_collectible_character",
    "train_system": "train_track_system",
    "toy_mechanism": "toy_mechanism",
    "kinetic_decor": "kinetic_decor",
    "display_stand": "display_stand_kit",
    "general_kit": "reference_guided_kit",
    # DWG-extracted reference categories
    "compressor_reference": "compressor_kit",
    "valve_reference": "valve_fitting",
    "fan_reference": "compressor_kit",
    "fastener_reference": "reference_guided_kit",
    "furniture_reference": "reference_guided_kit",
    "tree_reference": "reference_guided_kit",
    "human_figure_reference": "human_figure",
    "vehicle_reference": "rc_vehicle",
    "aircraft_reference": "rc_aircraft_kit",
    "boardgame_reference": "reference_guided_kit",
    "cctv_reference": "reference_guided_kit",
    "industrial_reference": "industrial_model",
    "architecture_reference": "architecture_miniature",
    "container_reference": "organizer_box",
    "plumbing_reference": "reference_guided_kit",
    "dwg_reference": "reference_guided_kit",
}

# Extra keyword → project_kind overrides (checked before category scoring).
KEYWORD_KIND: List[Tuple[str, str]] = [
    (r"boeing|747|airliner|пассажирск", "mechanical_boeing_airliner"),
    (r"extra\s*300|fokker|rc\s*plane|самол[её]т|airplane|авиа", "rc_aircraft_kit"),
    (r"drone|квадрокоптер|fpv|дрон|multicopter", "drone_fpv_kit"),
    (r"tank|танк|гусениц|tracked", "rc_tracked_vehicle"),
    (r"truck|грузовик|фура|semi", "rc_truck_kit"),
    (r"robot|робот|manipulator|клешн|gripper|scara", "robot_mechanism_kit"),
    (r"castle|замок|eiffel|эйфел|город|city|architecture|миниатюр", "architecture_miniature"),
    (r"gearbox|редуктор|планетар|planetarium|шестерн", "mechanical_planetarium"),
    (r"kit\s*card|кит\s*кард", "kit_card"),
    (r"gauntlet|перчатк|articulated", "articulated_wearable"),
    (r"pegboard|перфорац|tool\s*holder|катушк|spool", "printer_tool_holder"),
    (r"train|поезд|рельс|rail", "train_track_system"),
    (r"catapult|катапульт", "toy_mechanism"),
    (r"kamaz|камаз|vms|военн.{0,12}техник", "rc_truck_kit"),
    (r"гидроцилиндр|hydraulic\s*cylinder|hydraulic\s*ram|шток.{0,15}поршн", "mechanism_kit"),
    (r"таблетниц|pill\s*box|органайзер|organizer|шкатулк|комод|drawer", "organizer_box"),
    (r"трафарет|stencil|name[-\s]?plate|signage|sign\s*plate", "stencil_plate"),
    # Note: keep the "fan" rule before the valve rule so "вентилятор"
    # doesn't get matched by "вентил" from valve patterns.
    (r"вентилятор|осевой\s*вентил|fan\s*ducted|axial\s*fan", "compressor_kit"),
    (r"задвижк|затвор|клапан|valve|kran|кран\s*шаров|вентил[ья]\b", "valve_fitting"),
    (r"компрессор|atlas\s*copco|копко", "compressor_kit"),
    (r"пикап|pickup", "rc_vehicle"),
    (r"ядерн.{0,8}реактор|ввэр|рбмк|vver|rbmk", "industrial_model"),
    (r"уголок|профил\s+ст|gost\s*8509|балк[аи]", "steel_profile"),
    (r"камин|interior|интерьер", "interior_decor"),
    (r"человеч|figure|фигур\s+люд|шарнирн.{0,8}человек", "human_figure"),
    (r"кенворт|kenworth|тягач|truck.{0,8}semi|седельн.{0,8}тягач", "rc_truck_kit"),
    (r"автомоб|легковуш|седан|внедорожн", "rc_vehicle"),
    (r"мебел|стол.{0,8}3d|шкаф|кресл", "furniture_reference"),
    (r"дерев[ьояе]|tree.{0,8}3d|растен", "vegetation_reference"),
    (r"шашк|шахмат|нард|chess|checker|backgammon|настольн.{0,12}игр", "boardgame_reference"),
    (r"камер.{0,12}(набл|cctv)|pelco|videosurveill", "cctv_reference"),
    (r"цок|бункер|silo|резервуар|conveyer|конвейер|приёмник\s*угл", "industrial_model"),
    (r"данфосс|danfoss|фитинг|холодильн.{0,8}арматур", "valve_fitting"),
    (r"чаша\s*генуя|сантехник|santeh|toilet|унитаз|раковин", "reference_guided_kit"),
    (r"экзотическ.{0,10}техник|industrial\s*equipment|industrial\s*scene", "industrial_model"),
    (r"damas\s*chinas|chinese\s*checkers", "boardgame_reference"),
]


@lru_cache(maxsize=1)
def load_index() -> Dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"kits": [], "kit_count": 0}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def library_stats() -> Dict[str, Any]:
    idx = load_index()
    return {
        "kit_count": idx.get("kit_count", 0),
        "total_stl": idx.get("total_stl", 0),
        "categories": idx.get("categories") or {},
    }


def _score_kit(text: str, kit: Dict[str, Any]) -> float:
    t = text.lower()
    score = 0.0
    slug = kit.get("slug") or ""
    for tok in kit.get("keywords") or []:
        if tok in t:
            score += 2.0
    if slug.replace("_", " ") in t or slug.replace("_", "-") in t:
        score += 5.0
    for tok in kit.get("top_tokens") or []:
        if len(tok) > 3 and tok in t:
            score += 1.0
    cat = kit.get("category") or ""
    if cat.replace("_", " ") in t:
        score += 3.0
    # category-specific boosts
    if kit.get("has_wing_tokens") and re.search(r"самол|plane|wing|крыл|aviation|aircraft", t, re.I):
        score += 4.0
    if kit.get("has_wheel_tokens") and re.search(r"wheel|колес|шасси|jeep|машин", t, re.I):
        score += 3.0
    if kit.get("has_gear_tokens") and re.search(r"gear|шестерн|механизм|planet", t, re.I):
        score += 3.0
    return score


def find_best_kits(text: str, *, limit: int = 3) -> List[Dict[str, Any]]:
    kits = load_index().get("kits") or []
    scored = [( _score_kit(text, k), k) for k in kits]
    scored.sort(key=lambda x: -x[0])
    return [k for s, k in scored[:limit] if s > 0.5]


def infer_project_kind_from_library(text: str) -> Optional[str]:
    t = text or ""
    from bot.services.airplane_3mf import airplane_wants_realistic_mesh

    skip = {"mechanical_boeing_airliner"} if airplane_wants_realistic_mesh(t) else set()
    for pat, kind in KEYWORD_KIND:
        if kind in skip:
            continue
        if re.search(pat, t, re.I):
            return kind
    best = find_best_kits(t, limit=1)
    if not best:
        return None
    cat = best[0].get("category") or "general_kit"
    return CATEGORY_TO_PROJECT_KIND.get(cat, "reference_guided_kit")


def reference_hints_for_text(text: str) -> Dict[str, Any]:
    """Metadata injected into specs for captions, preview, and LLM context."""
    best = find_best_kits(text, limit=3)
    if not best:
        return {}
    primary = best[0]
    return {
        "reference_library": {
            "primary_slug": primary.get("slug"),
            "primary_category": primary.get("category"),
            "primary_stl_count": primary.get("stl_count"),
            "split_style": primary.get("split_style"),
            "related_slugs": [k.get("slug") for k in best[1:]],
            "stats": library_stats(),
        }
    }


def get_geometry_profile(slug: str) -> Optional[Dict[str, Any]]:
    from bot.services.reference_geometry import build_geometry_profile

    return build_geometry_profile(slug)


@lru_cache(maxsize=1)
def _load_cad_archives_catalog() -> Dict[str, Any]:
    """Lightweight vocabulary index of downloaded CAD archive names."""
    p = INDEX_PATH.parent / "cad_archives_catalog.json"
    if not p.is_file():
        return {"summary": {}, "archives": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"summary": {}, "archives": []}


_DIM_TOKEN_RE = re.compile(r"(?:Ду|Dy|DN)\s*(\d{2,4})", re.I)


def _cad_archive_hint(text: str) -> str:
    """Match user text against archive titles to surface relevant categories."""
    cat = _load_cad_archives_catalog()
    if not cat.get("archives"):
        return ""
    t = (text or "").lower()
    # Pull any pipe-size token from user text — Ду65 / DN150 etc.
    dim_match = _DIM_TOKEN_RE.search(t)
    matched_tags: Dict[str, int] = {}
    matched_titles: List[str] = []
    for a in cat["archives"]:
        title = (a.get("title_ru") or "").lower()
        if not title:
            continue
        # Match by simple substring of any 4+ char word in title
        tokens = [w for w in re.split(r"[\s_\-]+", title) if len(w) > 3]
        if any(w in t for w in tokens):
            for tg in a.get("tags") or []:
                matched_tags[tg] = matched_tags.get(tg, 0) + 1
            if len(matched_titles) < 5:
                matched_titles.append(a.get("title_ru") or "")
    if not matched_tags and not dim_match:
        return ""
    lines = ["CAD ARCHIVE VOCABULARY (downloaded library, DWG-indexed):"]
    if matched_tags:
        sorted_tags = sorted(matched_tags.items(), key=lambda kv: -kv[1])
        lines.append("  categories user touched: " + ", ".join(
            f"{tg} (×{cnt})" for tg, cnt in sorted_tags[:6]
        ))
    if matched_titles:
        lines.append("  relevant archive titles:")
        for tt in matched_titles[:4]:
            lines.append(f"    • {tt}")
    if dim_match:
        lines.append(
            f"  ⚠ pipe-size token detected: Ду/DN {dim_match.group(1)} "
            f"— this is nominal bore in mm (e.g. Ду50 = 50 mm DN). "
            "Use this when sizing valves / pipe-related models."
        )
    return "\n".join(lines)


def llm_reference_context(text: str, *, max_chars: int = 2800) -> str:
    """Structured blueprint summary for LLM project generation."""
    blocks: List[str] = []

    # Curated, measured mechanism profiles always come first when they match
    # — they contain real CAD measurements and assembly hints learned from
    # downloaded reference kits.
    try:
        from bot.services.learned_mechanism_profiles import (
            find_mechanism_profile,
            llm_context_for,
        )
        mech = find_mechanism_profile(text)
        if mech is not None:
            blocks.append(llm_context_for(mech))
    except Exception:
        # Never block LLM context on a learned-profile error
        pass

    # CAD archive vocabulary hint (lightweight — only adds if user text
    # actually touches one of the indexed categories or pipe-size tokens).
    try:
        cad_hint = _cad_archive_hint(text)
        if cad_hint:
            blocks.append(cad_hint)
    except Exception:
        pass

    for kit in find_best_kits(text, limit=2):
        prof = get_geometry_profile(kit.get("slug") or "")
        if not prof:
            continue
        lines = [
            f"REFERENCE KIT `{kit.get('slug')}` category={kit.get('category')} "
            f"parts={prof.get('part_count')} roles={', '.join(prof.get('roles_present') or [])}",
        ]
        for p in (prof.get("parts") or [])[:16]:
            lines.append(
                f"  • {p.get('id')}: {p.get('name')} role={p.get('role')} "
                f"template={p.get('template')} source={p.get('source_file', '')}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:max_chars]


def meshy_style_fragment(text: str) -> str:
    """English fragment for Meshy prompts — split/structure hints from nearest kit."""
    best = find_best_kits(text, limit=1)
    if not best:
        return ""
    kit = best[0]
    prof = get_geometry_profile(kit.get("slug") or "")
    if not prof:
        cat = kit.get("category") or "kit"
        return f"inspired by reference {cat} multi-part printable kit, clean manifold, FDM friendly"
    roles = ", ".join((prof.get("roles_present") or [])[:8])
    sample = ", ".join(p.get("name", "") for p in (prof.get("parts") or [])[:6])
    return (
        f"reference structure like {kit.get('slug')}: include {roles}; "
        f"recognizable parts similar to {sample}; high detail, watertight, no thin wires"
    )


def enrich_specs(specs: Dict[str, Any], user_text: str) -> Dict[str, Any]:
    hints = reference_hints_for_text(user_text)
    if not hints:
        return specs
    specs = dict(specs)
    specs.setdefault("requirements", [])
    ref = hints.get("reference_library") or {}
    slug = ref.get("primary_slug")
    stl_n = ref.get("primary_stl_count")
    if slug and isinstance(specs.get("requirements"), list):
        note = (
            f"Референс из библиотеки ({library_stats().get('kit_count', 0)} kits): "
            f"`{slug}` — {stl_n or '?'} STL, стиль разбиения: {ref.get('split_style')}."
        )
        if note not in specs["requirements"]:
            specs["requirements"].insert(0, note)
    specs.update(hints)
    return specs
