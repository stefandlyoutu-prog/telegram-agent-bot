"""Portrait photo -> stylized figurine workflow (printU-like)."""

from __future__ import annotations

import re
from dataclasses import dataclass


_PORTRAIT_FIGURINE = re.compile(
    r"портретн|по\s+фото.*(?:фигур|статуэт|3d|3д)|"
    r"фигурк[уаи].{0,40}(?:по\s+фото|человек|меня|портрет)|"
    r"bobble\s*head|bobblehead|бобл|бабл|chibi|чиби|cartoon|мульт|emoji|"
    r"printu|makerworld.*printu|кукл[ау]|мини.?я|аватар.*3d",
    re.I,
)

_STYLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"chibi|чиби", re.I), "chibi"),
    (re.compile(r"cartoon|мульт", re.I), "cartoon"),
    (re.compile(r"emoji|эмод", re.I), "emoji"),
    (re.compile(r"bobble\s*head|bobblehead|бобл|бабл", re.I), "bobblehead"),
)

_POSTURE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"t-?pose|т-?поз", re.I), "t-pose"),
    (re.compile(r"natural|естествен|прямо|стоя", re.I), "natural pose"),
    (re.compile(r"как\s+на\s+фото|image\s+pose|поз[ауы].{0,20}фото", re.I), "image pose"),
)


@dataclass(frozen=True)
class PortraitFigurinePlan:
    style: str = "bobblehead"
    posture: str = "image pose"
    concept_model_hint: str = "nano-banana-pro"

    @property
    def label(self) -> str:
        return f"Портретная фигурка: {self.style}, {self.posture}"


def is_portrait_figurine_request(text: str) -> bool:
    """Photo request that should use concept-first portrait figurine mode."""
    return bool(_PORTRAIT_FIGURINE.search(text or ""))


def parse_portrait_plan(text: str) -> PortraitFigurinePlan:
    style = "bobblehead"
    posture = "image pose"
    for pat, value in _STYLE_PATTERNS:
        if pat.search(text or ""):
            style = value
            break
    for pat, value in _POSTURE_PATTERNS:
        if pat.search(text or ""):
            posture = value
            break
    return PortraitFigurinePlan(style=style, posture=posture)


def concept_prompt_from_facts(facts: str, user_text: str) -> str:
    plan = parse_portrait_plan(user_text)
    style_desc = {
        "bobblehead": "premium bobblehead figurine, oversized head, friendly likeness",
        "chibi": "cute chibi collectible figurine, large expressive eyes",
        "cartoon": "stylized cartoon collectible figurine",
        "emoji": "emoji-style 3D avatar figurine, simplified expressive face",
    }.get(plan.style, "premium bobblehead figurine")
    posture_desc = {
        "image pose": "match the body pose from the reference photo",
        "natural pose": "natural standing pose with legs straight",
        "t-pose": "clean T-pose, best for later rigging or pose adjustment",
    }.get(plan.posture, "match the body pose from the reference photo")
    return (
        f"{style_desc}; {posture_desc}; full body, single character, "
        "3D printable toy concept, clean white background, thick printable features, "
        "recognizable outfit and hairstyle from this description: "
        f"{facts[:900]}. "
        "Do not include text, watermark, extra people, props, or background scenery."
    )[:1200]


def image_to_3d_prompt(user_text: str) -> str:
    plan = parse_portrait_plan(user_text)
    return (
        f"3D printable {plan.style} portrait figurine, {plan.posture}, full body, "
        "thick FDM-friendly features, clean manifold character, preserve colors and outfit, "
        "single figurine, no text, no base unless needed, optimized for Bambu Studio"
    )

