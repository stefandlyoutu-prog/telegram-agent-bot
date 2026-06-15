"""Level 3: reference mood board → Meshy image-to-3D + blueprint STL split."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from bot.services.meshy_route import meshy_available


@dataclass
class MeshyLevel3Plan:
    enabled: bool = False
    slug: Optional[str] = None
    category: Optional[str] = None
    mood_board_png: Optional[bytes] = None
    blueprint_part_count: int = 0
    use_image_to_3d: bool = False
    apply_split: bool = False
    prompt_suffix: str = ""
    notes: List[str] = field(default_factory=list)


_SPLIT_INTENT = re.compile(
    r"разбей|раздел|на\s+част|multi[\s-]?part|kit|набор|сборк|blueprint|"
    r"по\s+референс|как\s+скачан|уровень\s*3|level\s*3|отдельн.{0,12}детал",
    re.I,
)
_HIGH_DETAIL = re.compile(
    r"максимальн|детал|реалист|как\s+на|похож|high[\s-]?detail|фантаст|уникальн",
    re.I,
)
_SKIP_IMAGE_REF = re.compile(
    r"без\s+референс|без\s+mood|только\s+текст|text[\s-]?only|не\s+использ.{0,12}референс",
    re.I,
)


def should_reference_split(text: str, *, part_count: int = 0) -> bool:
    if part_count >= 6:
        return True
    if part_count >= 4 and _SPLIT_INTENT.search(text or ""):
        return True
    return bool(_SPLIT_INTENT.search(text or ""))


def should_use_reference_image_meshy(text: str, *, part_count: int) -> bool:
    from bot.services.airplane_3mf import airplane_wants_realistic_mesh

    if airplane_wants_realistic_mesh(text or ""):
        return False
    if _SKIP_IMAGE_REF.search(text or ""):
        return False
    if part_count < 3:
        return False
    if _HIGH_DETAIL.search(text or ""):
        return True
    if _SPLIT_INTENT.search(text or ""):
        return True
    if re.search(
        r"самол|plane|drone|дрон|танк|robot|робот|castle|замок|kit|набор|makerworld|cults",
        text or "",
        re.I,
    ):
        return True
    return False


def build_meshy_level3_plan(user_text: str) -> MeshyLevel3Plan:
    plan = MeshyLevel3Plan()
    if not meshy_available():
        return plan

    from bot.services.reference_library import find_best_kits
    from bot.services.reference_render import render_mood_board_png
    from bot.services.reference_tolerance import meshy_tolerance_prompt

    kits = find_best_kits(user_text, limit=1)
    if not kits:
        return plan

    slug = kits[0].get("slug") or ""
    cat = kits[0].get("category") or "general_kit"
    stl_n = int(kits[0].get("stl_count") or 0)
    if stl_n < 3:
        from bot.services.reference_geometry import build_geometry_profile

        prof = build_geometry_profile(slug)
        stl_n = int((prof or {}).get("part_count") or 0)

    plan.slug = slug
    plan.category = cat
    plan.blueprint_part_count = stl_n
    plan.enabled = stl_n >= 3

    if not plan.enabled:
        return plan

    plan.mood_board_png = render_mood_board_png(slug)
    if plan.mood_board_png:
        plan.notes.append(f"mood board from `{slug}` ({stl_n} ref parts)")

    plan.use_image_to_3d = bool(
        plan.mood_board_png and should_use_reference_image_meshy(user_text, part_count=stl_n)
    )
    plan.apply_split = should_reference_split(user_text, part_count=stl_n)

    tol = meshy_tolerance_prompt(cat)
    plan.prompt_suffix = (
        f"; reference kit {slug}, {stl_n}-part assembly, {tol}"
    )
    if plan.apply_split:
        plan.prompt_suffix += "; design as separable multi-part printable kit matching reference layout"
    return plan
