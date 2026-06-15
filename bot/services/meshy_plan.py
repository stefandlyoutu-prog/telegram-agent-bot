"""Выбор Meshy-пайплайна под задачу: простота для пользователя, максимум API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from bot.services.meshy_route import meshy_available

_LOWPOLY = re.compile(
    r"low[\s-]?poly|лоуполи|низкополиг|игр[аоу]|game\s*asset|roblox|unity|godot|"
    r"оптимизир.*полигон",
    re.I,
)
_TEXTURES = re.compile(
    r"текстур|pbr|цветн|красив|детализ|реалист|ams|мульти.?цвет|"
    r"несколько\s+цвет|покрас|окрас",
    re.I,
)
_COLORS = re.compile(
    r"ч[ёе]рн|бел|красн|зел[её]н|син|ж[её]лт|оранж|сер|коричн|"
    r"black|white|red|green|blue|yellow|brown|gray|grey",
    re.I,
)
_MULTIVIEW = re.compile(r"несколько\s+ракурс|multi[\s-]?view|с\s+разных\s+сторон", re.I)
_CONCEPT_IMAGE = re.compile(
    r"нарисуй|сгенерир.{0,12}картин|иллюстрац|концепт|референс|"
    r"картинк[аиу].{0,12}(без|не).{0,8}3d|"
    r"nano[\s-]?banana|визуализац",
    re.I,
)
_PRO_IMAGE = re.compile(r"pro\b|качеств|4k|детальн|hd\b|высок.{0,6}качеств", re.I)
_HIGH_DETAIL_3D = re.compile(
    r"максимальн.{0,16}детал|очень\s+детальн|high[\s-]?detail|реалист|похож|"
    r"как\s+на\s+фото|коллекцион|витринн",
    re.I,
)
_FAST_PREVIEW = re.compile(
    r"быстр|чернов|тестов|упрощ|без\s+текстур|без\s+цвет",
    re.I,
)
_GLB_REQUEST = re.compile(r"\bglb\b|gltf|цветн.{0,12}glb|текстурн.{0,12}glb|preview", re.I)
_AVITO_CARD = re.compile(
    r"карточк.{0,12}авитo|авитo.{0,12}карточ|обложк.{0,12}авитo|"
    r"seo.{0,12}авитo|макет.{0,10}авитo",
    re.I,
)
_3D_PRINT = re.compile(
    r"3d[\s-]?(модел|модель|печат)|stl|для\s+печат|bambu|бамбу|"
    r"слайсер|принтер|фигур|статуэтк",
    re.I,
)
_ANIMATION = re.compile(
    r"анимац|ожив|ходьб|бег|движен|танц|walk|run|dance|idle|атак|"
    r"покачив|машет",
    re.I,
)
_HUMANOID = re.compile(
    r"человек|персонаж|гер[оояей]|humanoid|human\s+character|рыцар|knight|"
    r"warrior|soldier|аниме|anime|робот.?человек|воин|маг|wizard|elf",
    re.I,
)
_NOT_RIG = re.compile(
    r"лабрадор|собак|dog|кот|cat|чебурашк|животн|retriever|"
    r"шарнир|подвиж|шевел|articul|3mf|bambu.*печат",
    re.I,
)


class Meshy3DPipeline(str, Enum):
    PRINT_FAST = "print_fast"
    PRINT_TEXTURED = "print_textured"
    LOWPOLY = "lowpoly"
    PHOTO_TEXTURED = "photo_textured"
    PHOTO_FAST = "photo_fast"
    RIG_ANIMATE = "rig_animate"


@dataclass
class Meshy3DPlan:
    pipeline: Meshy3DPipeline
    label: str
    use_refine: bool = False
    model_type: str = "standard"
    texture_prompt: str = ""
    remesh_formats: List[str] = field(default_factory=lambda: ["stl"])
    deliver_glb: bool = False
    should_texture_photo: bool = True
    target_polycount: int = 30000
    hd_texture: bool = False
    preserve_source_mesh: bool = False

    def status_hint(self) -> str:
        hints = {
            Meshy3DPipeline.PRINT_FAST: "геометрия → remesh → STL",
            Meshy3DPipeline.PRINT_TEXTURED: "геометрия → текстуры → STL",
            Meshy3DPipeline.LOWPOLY: "low-poly → remesh → STL",
            Meshy3DPipeline.PHOTO_TEXTURED: "фото → 3D с текстурами → STL",
            Meshy3DPipeline.PHOTO_FAST: "фото → 3D → remesh → STL",
            Meshy3DPipeline.RIG_ANIMATE: "3D+текстуры → rig → анимация GLB",
        }
        return hints.get(self.pipeline, "Meshy 3D")


def wants_meshy_textures(text: str) -> bool:
    t = text or ""
    if _FAST_PREVIEW.search(t):
        return False
    return bool(_TEXTURES.search(t) or _COLORS.search(t))


def wants_meshy_lowpoly(text: str) -> bool:
    return bool(_LOWPOLY.search(text or ""))


def wants_glb_output(text: str) -> bool:
    return bool(_GLB_REQUEST.search(text or ""))


def texture_prompt_from_text(text: str, mesh_prompt: str) -> str:
    from bot.services.bambu_hints import color_words_from_text, part_color_prompt_fragment

    colors = color_words_from_text(text)
    part_colors = part_color_prompt_fragment(text)
    base = (mesh_prompt or text or "")[:400]
    details = []
    if part_colors:
        details.append(f"part-specific colors: {part_colors}")
    if colors:
        details.append(f"palette: {', '.join(colors)}")
    if details:
        return f"{base}, {', '.join(details)}, clean PBR textures"
    return base[:500]


def rig_animation_intent(text: str) -> bool:
    """Человекоподобный персонаж + анимация (без проверки ключа Meshy)."""
    t = text or ""
    if not _ANIMATION.search(t):
        return False
    if _NOT_RIG.search(t):
        return False
    from bot.services.bambu_hints import wants_articulated_figurine

    if wants_articulated_figurine(t):
        return False
    return bool(_HUMANOID.search(t))


def wants_meshy_rig_animation(text: str) -> bool:
    if not meshy_available():
        return False
    return rig_animation_intent(text)


def plan_rig_animation(user_text: str) -> Meshy3DPlan:
    return Meshy3DPlan(
        pipeline=Meshy3DPipeline.RIG_ANIMATE,
        label="Meshy: персонаж + rig + анимация",
        use_refine=True,
        texture_prompt=texture_prompt_from_text(user_text, user_text),
        deliver_glb=True,
    )


def plan_text_to_3d(user_text: str, mesh_prompt: str) -> Meshy3DPlan:
    high_detail = bool(_HIGH_DETAIL_3D.search(user_text or ""))
    target_polycount = 250000 if high_detail else 30000
    if rig_animation_intent(user_text):
        return plan_rig_animation(user_text)
    if wants_meshy_lowpoly(user_text):
        return Meshy3DPlan(
            pipeline=Meshy3DPipeline.LOWPOLY,
            label="Meshy low-poly → STL",
            model_type="lowpoly",
            remesh_formats=["stl"],
            target_polycount=12000,
        )
    if wants_meshy_textures(user_text):
        tp = texture_prompt_from_text(user_text, mesh_prompt)
        return Meshy3DPlan(
            pipeline=Meshy3DPipeline.PRINT_TEXTURED,
            label="Meshy text-to-3D + текстуры",
            use_refine=True,
            texture_prompt=tp,
            remesh_formats=["stl"],
            deliver_glb=True,
            target_polycount=target_polycount,
            hd_texture=high_detail,
            preserve_source_mesh=high_detail,
        )
    return Meshy3DPlan(
        pipeline=Meshy3DPipeline.PRINT_FAST,
        label="Meshy text-to-3D (STL)",
        remesh_formats=["stl"],
        target_polycount=target_polycount,
        deliver_glb=high_detail,
        hd_texture=high_detail,
        preserve_source_mesh=high_detail,
    )


def plan_airliner_text_to_3d(
    user_text: str,
    mesh_prompt: str,
    *,
    fast: bool = True,
) -> Meshy3DPlan:
    """Reliable Boeing path: direct text-to-3D preview → remesh, no mood board / refine."""
    high = bool(_HIGH_DETAIL_3D.search(user_text or ""))
    poly = 65000 if high else 35000
    if fast:
        return Meshy3DPlan(
            pipeline=Meshy3DPipeline.PRINT_FAST,
            label="Meshy Boeing text-to-3D",
            use_refine=False,
            remesh_formats=["stl"],
            target_polycount=poly,
            deliver_glb=False,
        )
    tp = texture_prompt_from_text(user_text, mesh_prompt)
    return Meshy3DPlan(
        pipeline=Meshy3DPipeline.PRINT_TEXTURED,
        label="Meshy Boeing text-to-3D (retry)",
        use_refine=False,
        texture_prompt=tp,
        remesh_formats=["stl"],
        target_polycount=poly,
        deliver_glb=False,
    )


def plan_photo_to_3d(user_text: str) -> Meshy3DPlan:
    high_detail = bool(_HIGH_DETAIL_3D.search(user_text or ""))
    target_polycount = 250000 if high_detail else 30000
    if wants_meshy_lowpoly(user_text):
        return Meshy3DPlan(
            pipeline=Meshy3DPipeline.LOWPOLY,
            label="Meshy image-to-3D low-poly",
            model_type="lowpoly",
            should_texture_photo=False,
            remesh_formats=["stl"],
            target_polycount=12000,
        )
    if _FAST_PREVIEW.search(user_text or ""):
        return Meshy3DPlan(
            pipeline=Meshy3DPipeline.PHOTO_FAST,
            label="Meshy image-to-3D",
            should_texture_photo=False,
            remesh_formats=["stl"],
            target_polycount=20000,
        )
    tp = texture_prompt_from_text(user_text, user_text)
    return Meshy3DPlan(
        pipeline=Meshy3DPipeline.PHOTO_TEXTURED,
        label="Meshy image-to-3D + текстуры",
        should_texture_photo=True,
        texture_prompt=tp,
        remesh_formats=["stl"],
        deliver_glb=True,
        target_polycount=target_polycount,
        hd_texture=high_detail,
        preserve_source_mesh=high_detail,
    )


@dataclass
class MeshyImagePlan:
    ai_model: str = "nano-banana-pro"
    generate_multi_view: bool = False
    aspect_ratio: str = "1:1"
    label: str = "Meshy text-to-image (Pro)"

    def status_hint(self) -> str:
        mv = " · multi-view" if self.generate_multi_view else ""
        return f"{self.ai_model}{mv}"


def plan_text_to_image(user_text: str) -> MeshyImagePlan:
    t = user_text or ""
    model = "nano-banana-pro" if _PRO_IMAGE.search(t) else "nano-banana"
    ar = "1:1"
    if re.search(r"16\s*:\s*9|широк|ландшафт|горизонт", t, re.I):
        ar = "16:9"
    elif re.search(r"9\s*:\s*16|вертик|сторис|портрет", t, re.I):
        ar = "9:16"
    multi = bool(_MULTIVIEW.search(t))
    label = f"Meshy картинка ({model})"
    return MeshyImagePlan(
        ai_model=model,
        generate_multi_view=multi,
        aspect_ratio=ar,
        label=label,
    )


def is_avito_card_request(text: str) -> bool:
    return bool(_AVITO_CARD.search(text or ""))


def should_meshy_text_to_image(text: str) -> bool:
    """Текстовая картинка через Meshy (nano-banana), не 3D и не шаблон Авито."""
    if not meshy_available():
        return False
    t = (text or "").strip()
    if not t or _AVITO_CARD.search(t):
        return False
    if _3D_PRINT.search(t) and not _CONCEPT_IMAGE.search(t):
        return False
    return bool(_CONCEPT_IMAGE.search(t))


def meshy_plan_extra_for_task(user_text: str, *, from_photo: bool, mesh_prompt: str = "") -> dict:
    if from_photo:
        p = plan_photo_to_3d(user_text)
    else:
        p = plan_text_to_3d(user_text, mesh_prompt)
    return {
        "meshy_pipeline": p.pipeline.value,
        "meshy_hint": p.status_hint(),
        "meshy_label": p.label,
    }
