"""Классификация входящего сообщения и выбор модели под задачу."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from bot.config import AVAILABLE_MODELS, DEFAULT_MODEL, VISION_MODEL
from bot.services.file_output import (
    resolve_output_file_format,
    should_refuse_placeholder_stl,
    wants_3d_model_from_photo,
    wants_file_output,
)
from bot.services.image_output import wants_image_output, wants_pdf_output
from bot.services.meshy_route import meshy_available, should_meshy_from_photo, should_meshy_from_text
from bot.services.meshy_plan import (
    meshy_plan_extra_for_task,
    should_meshy_text_to_image,
)
from bot.services.bambu_hints import wants_articulated_figurine
from bot.services.openscad import openscad_available
from bot.services.print_project import is_single_part_print_request, wants_print_project


class TaskKind(str, Enum):
    PENDING_3D = "pending_3d"
    MESHY_TEXT_3D = "meshy_text_3d"
    AIRPLANE_3MF = "airplane_3mf"
    ARTICULATED_3MF = "articulated_3mf"
    UNSUPPORTED_ARTICULATED_3D = "unsupported_articulated_3d"
    MECHANICAL_PROJECT = "mechanical_project"
    PORTRAIT_FIGURINE = "portrait_figurine"
    MESHY_PHOTO_3D = "meshy_photo_3d"
    MESHY_IMAGE = "meshy_image"
    OPENSCAD_SINGLE = "openscad_single"
    PRINT_PROJECT = "print_project"
    SEO_PDF = "seo_pdf"
    FILE_OUTPUT = "file_output"
    AVITO_CARD = "avito_card"
    VISION_CHAT = "vision_chat"
    CHAT = "chat"


from bot.services.model_catalog import TEXT_ONLY_MODELS, model_label, merged_available_models

# Какая модель лучше под capability (env можно переопределить в model_router)
DEFAULT_CAPABILITY_MODELS: Dict[str, str] = {
    "engineering_json": "gpt-5.4",
    "seo_copy": "gpt-5.4-mini",
    "file_doc": "gpt-5.4-mini",
    "file_xlsx": "gpt-5.4-mini",
    "stl_spec": "gpt-5.4",
    "avito_copy": "gpt-5.4-mini",
    "chat": DEFAULT_MODEL,
    "vision": VISION_MODEL,
    "self_check": "gpt-5.4-mini",
}


@dataclass
class TaskPlan:
    kind: TaskKind
    label: str
    model: str
    model_reason: str
    capability: str
    user_text: str
    file_fmt: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def uses_meshy(self) -> bool:
        return self.kind in (
            TaskKind.MESHY_TEXT_3D,
            TaskKind.MESHY_PHOTO_3D,
            TaskKind.MESHY_IMAGE,
        )

    @property
    def uses_llm(self) -> bool:
        return not self.uses_meshy and self.kind != TaskKind.PENDING_3D


def _normalize_user_model(user_model: str) -> str:
    models = merged_available_models()
    if user_model in models or user_model in TEXT_ONLY_MODELS:
        return user_model
    return DEFAULT_MODEL


def _pick_model(capability: str, user_model: str, user_text: str = "") -> tuple[str, str]:
    from bot.config import AUTO_SWITCH_MODEL
    from bot.services.model_catalog import infer_capability, pick_model_for_capability

    cap = infer_capability(user_text, base=capability) if capability == "chat" else capability
    chosen, reason = pick_model_for_capability(cap, user_model)
    user_model = _normalize_user_model(user_model)
    if not AUTO_SWITCH_MODEL and chosen != user_model and cap == "chat":
        chosen = user_model
        reason = f"Модель: {model_label(chosen)} (авто-выбор выключен)."
    return chosen, reason


def build_task_plan(
    user_text: str,
    user_model: str,
    *,
    has_photo: bool = False,
    has_pending_3d: bool = False,
) -> TaskPlan:
    text = (user_text or "").strip()
    user_model = _normalize_user_model(user_model)

    if has_pending_3d:
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.PENDING_3D,
            label="Продолжение 3D (профиль принтера)",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
        )

    if has_photo:
        from bot.services.portrait_figurine import (
            is_portrait_figurine_request,
            parse_portrait_plan,
        )

        if is_portrait_figurine_request(text) and meshy_available():
            portrait = parse_portrait_plan(text)
            return TaskPlan(
                kind=TaskKind.PORTRAIT_FIGURINE,
                label=portrait.label,
                model=VISION_MODEL,
                model_reason=(
                    "Фото человека → 2D concept → Meshy image-to-3D, "
                    "как отдельный printU-like режим."
                ),
                capability="meshy",
                user_text=text,
                file_fmt="stl",
                extra={"style": portrait.style, "posture": portrait.posture},
            )
        if should_meshy_from_photo(text):
            extra = meshy_plan_extra_for_task(text, from_photo=True)
            return TaskPlan(
                kind=TaskKind.MESHY_PHOTO_3D,
                label=extra.get("meshy_label", "3D с фото (Meshy)"),
                model=VISION_MODEL,
                model_reason=f"Meshy: {extra.get('meshy_hint', 'image-to-3D')}.",
                capability="meshy",
                user_text=text,
                extra=extra,
            )
        file_fmt = resolve_output_file_format(text)
        if not file_fmt and wants_3d_model_from_photo(text):
            file_fmt = "stl"
        if file_fmt == "stl":
            if meshy_available():
                extra = meshy_plan_extra_for_task(text, from_photo=True)
                return TaskPlan(
                    kind=TaskKind.MESHY_PHOTO_3D,
                    label=extra.get("meshy_label", "3D с фото (Meshy)"),
                    model=VISION_MODEL,
                    model_reason=f"Meshy: {extra.get('meshy_hint', 'image-to-3D')}.",
                    capability="meshy",
                    user_text=text,
                    file_fmt="stl",
                    extra=extra,
                )
            model, reason = _pick_model("stl_spec", user_model, text)
            return TaskPlan(
                kind=TaskKind.MESHY_PHOTO_3D,
                label="3D с фото (замеры + STL)",
                model=model,
                model_reason=reason,
                capability="stl_spec",
                user_text=text,
                file_fmt="stl",
            )
        if file_fmt and file_fmt != "pdf":
            cap = "file_xlsx" if file_fmt == "xlsx" else "file_doc"
            model, reason = _pick_model(cap, user_model, text)
            return TaskPlan(
                kind=TaskKind.FILE_OUTPUT,
                label=f"Файл {file_fmt.upper()} с фото",
                model=model,
                model_reason=reason,
                capability=cap,
                user_text=text,
                file_fmt=file_fmt,
            )
        if wants_image_output(text):
            model, reason = _pick_model("avito_copy", user_model, text)
            return TaskPlan(
                kind=TaskKind.AVITO_CARD,
                label="Карточка / картинка по фото",
                model=model,
                model_reason=reason,
                capability="avito_copy",
                user_text=text,
            )
        model = VISION_MODEL
        return TaskPlan(
            kind=TaskKind.VISION_CHAT,
            label="Анализ фото",
            model=model,
            model_reason=f"Vision: {AVAILABLE_MODELS.get(model, model)}.",
            capability="vision",
            user_text=text,
        )

    from bot.services.generation_router import route_3d_request

    routed = route_3d_request(text, user_model)
    if routed is not None:
        if routed.kind != TaskKind.CHAT or (routed.extra or {}).get("refusal"):
            return routed

    if should_meshy_text_to_image(text):
        return TaskPlan(
            kind=TaskKind.MESHY_IMAGE,
            label="Картинка (Meshy nano-banana)",
            model=_pick_model("chat", user_model, text)[0],
            model_reason="Генерация изображения через Meshy (без 3D).",
            capability="meshy",
            user_text=text,
        )

    if is_single_part_print_request(text):
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.OPENSCAD_SINGLE,
            label="Одна деталь OpenSCAD (ручка, кронштейн…)",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
            file_fmt="stl",
        )

    if wants_pdf_output(text) and re.search(
        r"seo|сео|pdf|пдф|объявлен|авито|карточк", text, re.I
    ):
        model, reason = _pick_model("seo_copy", user_model, text)
        return TaskPlan(
            kind=TaskKind.SEO_PDF,
            label="SEO PDF / объявление",
            model=model,
            model_reason=reason,
            capability="seo_copy",
            user_text=text,
            file_fmt="pdf",
        )

    file_fmt = resolve_output_file_format(text)
    if file_fmt == "stl" and should_refuse_placeholder_stl(text):
        if is_single_part_print_request(text):
            model, reason = _pick_model("engineering_json", user_model, text)
            return TaskPlan(
                kind=TaskKind.OPENSCAD_SINGLE,
                label="Одна деталь OpenSCAD",
                model=model,
                model_reason=reason,
                capability="engineering_json",
                user_text=text,
                file_fmt="stl",
            )
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.PRINT_PROJECT,
            label="Инженерный проект на печать",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
            file_fmt="stl",
        )

    if file_fmt and file_fmt != "pdf":
        if file_fmt == "stl" and should_meshy_from_text(text) and meshy_available():
            from bot.services.meshy_route import meshy_prompt_from_text

            mp = meshy_prompt_from_text(text)
            extra = meshy_plan_extra_for_task(text, from_photo=False, mesh_prompt=mp)
            return TaskPlan(
                kind=TaskKind.MESHY_TEXT_3D,
                label=extra.get("meshy_label", "3D по описанию (Meshy)"),
                model=_pick_model("engineering_json", user_model, text)[0],
                model_reason=f"Meshy: {extra.get('meshy_hint', 'text-to-3D')}.",
                capability="meshy",
                user_text=text,
                file_fmt="stl",
                extra=extra,
            )
        cap = "file_xlsx" if file_fmt == "xlsx" else ("stl_spec" if file_fmt == "stl" else "file_doc")
        model, reason = _pick_model(cap, user_model, text)
        return TaskPlan(
            kind=TaskKind.FILE_OUTPUT,
            label=f"Файл {file_fmt.upper()}",
            model=model,
            model_reason=reason,
            capability=cap,
            user_text=text,
            file_fmt=file_fmt,
        )

    if file_fmt == "pdf" and wants_file_output(text):
        model, reason = _pick_model("file_doc", user_model, text)
        return TaskPlan(
            kind=TaskKind.FILE_OUTPUT,
            label="PDF документ",
            model=model,
            model_reason=reason,
            capability="file_doc",
            user_text=text,
            file_fmt="pdf",
        )

    model, reason = _pick_model("chat", user_model, text)
    if user_model in TEXT_ONLY_MODELS:
        reason = (
            f"Диалог: {model_label(model)} "
            f"(выбранная {model_label(user_model)} — только текст)."
        )
    return TaskPlan(
        kind=TaskKind.CHAT,
        label="Текстовый ответ",
        model=model,
        model_reason=reason,
        capability="chat",
        user_text=text,
    )
