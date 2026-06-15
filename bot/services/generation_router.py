"""Single 3D routing table: object class → TaskPlan.

Replaces scattered if/else chains in task_plan.py for print requests.
"""

from __future__ import annotations

import re
from typing import Optional

from bot.services.meshy_route import meshy_available, should_meshy_from_text
from bot.services.meshy_plan import meshy_plan_extra_for_task
from bot.services.object_class import ObjectClass, classify_object, has_print_intent
from bot.services.openscad import openscad_available
from bot.services.print_project import (
    is_existing_project_help_request,
    is_single_part_print_request,
    wants_print_project,
)
from bot.services.task_plan import TaskKind, TaskPlan, _pick_model


def route_3d_request(user_text: str, user_model: str) -> Optional[TaskPlan]:
    """Build TaskPlan for a 3D-print request, or None if not 3D."""
    text = (user_text or "").strip()
    if not text:
        return None

    if is_existing_project_help_request(text):
        return None

    obj_class, _subject = classify_object(text)
    if obj_class == ObjectClass.NON_3D and not has_print_intent(text):
        return None

    if obj_class == ObjectClass.HARD_SURFACE:
        return _route_hard_surface(text, user_model)

    if obj_class == ObjectClass.FUNCTIONAL:
        return _route_functional(text, user_model)

    # ORGANIC (incl. generic_3d with print intent)
    return _route_organic(text, user_model)


def _route_hard_surface(text: str, user_model: str) -> TaskPlan:
    from bot.services.airplane_3mf import airplane_requested, airplane_wants_mechanical_kit
    from bot.services.engineering_intake import mechanical_motion_requested

    if airplane_requested(text):
        if airplane_wants_mechanical_kit(text):
            model, reason = _pick_model("engineering_json", user_model, text)
            return TaskPlan(
                kind=TaskKind.MECHANICAL_PROJECT,
                label="Механический 3D-проект (hard-surface + оси/шарниры)",
                model=model,
                model_reason=reason,
                capability="engineering_json",
                user_text=text,
                file_fmt="3mf",
                extra={"mechanical": True, "object_class": ObjectClass.HARD_SURFACE.value},
            )
        return TaskPlan(
            kind=TaskKind.AIRPLANE_3MF,
            label="Boeing 747 — инженерный NACA CAD (3MF)",
            model=_pick_model("engineering_json", user_model, text)[0],
            model_reason=(
                "Hard-surface: самолёт → процедурная NACA-геометрия (фюзеляж, профиль крыла, "
                "двигатели). Без Meshy-глины и без voxel-ломания чужих mesh-моделей."
            ),
            capability="engineering_json",
            user_text=text,
            file_fmt="3mf",
            extra={
                "object_class": ObjectClass.HARD_SURFACE.value,
                "generator": "naca_hd",
                "high_detail": True,
                "procedural": True,
                "subject": "boeing_airliner",
            },
        )

    if mechanical_motion_requested(text):
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.MECHANICAL_PROJECT,
            label="Механический 3D-проект (hard-surface + оси/шарниры)",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
            file_fmt="3mf",
            extra={"mechanical": True, "object_class": ObjectClass.HARD_SURFACE.value},
        )

    # Other hard-surface (car, tank…) — organic AI mesh is wrong; use Meshy only if explicit
    if meshy_available() and re.search(r"\bmeshy\b|нейросет", text, re.I):
        from bot.services.meshy_route import meshy_prompt_from_text

        mp = meshy_prompt_from_text(text)
        extra = meshy_plan_extra_for_task(text, from_photo=False, mesh_prompt=mp)
        extra["object_class"] = ObjectClass.HARD_SURFACE.value
        return TaskPlan(
            kind=TaskKind.MESHY_TEXT_3D,
            label="Hard-surface через Meshy (явный запрос)",
            model=_pick_model("engineering_json", user_model, text)[0],
            model_reason="Явно запрошен AI-меш для техники.",
            capability="meshy",
            user_text=text,
            file_fmt="stl",
            extra=extra,
        )

    model, reason = _pick_model("engineering_json", user_model, text)
    return TaskPlan(
        kind=TaskKind.PRINT_PROJECT,
        label="Hard-surface проект (reference-guided kit)",
        model=model,
        model_reason=reason + " Hard-surface без самолёта → print-project / reference kit.",
        capability="engineering_json",
        user_text=text,
        extra={"object_class": ObjectClass.HARD_SURFACE.value},
    )


def _route_organic(text: str, user_model: str) -> TaskPlan:
    from bot.services.articulated_3mf import (
        articulation_requested,
        openscad_articulated_kind,
        requested_subject_label,
    )
    from bot.services.bambu_hints import wants_articulated_figurine

    if wants_articulated_figurine(text) and openscad_available():
        subj = openscad_articulated_kind(text) or "фигурка"
        return TaskPlan(
            kind=TaskKind.ARTICULATED_3MF,
            label=f"Артикулированная фигурка: {subj}",
            model=_pick_model("engineering_json", user_model, text)[0],
            model_reason="Organic + шарниры → процедурный OpenSCAD 3MF.",
            capability="engineering_json",
            user_text=text,
            file_fmt="3mf",
            extra={"subject": subj, "procedural": True, "object_class": ObjectClass.ORGANIC.value},
        )

    if articulation_requested(text):
        subject = requested_subject_label(text)
        return TaskPlan(
            kind=TaskKind.ARTICULATED_3MF,
            label=f"Шарнирная фигурка: {subject}",
            model=_pick_model("engineering_json", user_model, text)[0],
            model_reason="Organic + articulation → OpenSCAD 3MF.",
            capability="engineering_json",
            user_text=text,
            file_fmt="3mf",
            extra={"subject": subject, "procedural": True, "object_class": ObjectClass.ORGANIC.value},
        )

    if should_meshy_from_text(text) or has_print_intent(text):
        if not meshy_available():
            return TaskPlan(
                kind=TaskKind.CHAT,
                label="Organic 3D недоступен",
                model=_pick_model("chat", user_model, text)[0],
                model_reason="Meshy не настроен — organic 3D (банан, фигурки) недоступен.",
                capability="chat",
                user_text=text,
                extra={"refusal": "meshy_unavailable", "object_class": ObjectClass.ORGANIC.value},
            )
        from bot.services.meshy_route import meshy_prompt_from_text

        mp = meshy_prompt_from_text(text)
        extra = meshy_plan_extra_for_task(text, from_photo=False, mesh_prompt=mp)
        extra["object_class"] = ObjectClass.ORGANIC.value
        return TaskPlan(
            kind=TaskKind.MESHY_TEXT_3D,
            label=extra.get("meshy_label", "Organic 3D (Meshy text-to-3D)"),
            model=_pick_model("engineering_json", user_model, text)[0],
            model_reason=f"Organic → Meshy: {extra.get('meshy_hint', 'text-to-3D')}.",
            capability="meshy",
            user_text=text,
            file_fmt="stl",
            extra=extra,
        )

    return TaskPlan(
        kind=TaskKind.CHAT,
        label="Не 3D",
        model=_pick_model("chat", user_model, text)[0],
        model_reason="Нет явного 3D-намерения.",
        capability="chat",
        user_text=text,
    )


def _route_functional(text: str, user_model: str) -> TaskPlan:
    if wants_print_project(text):
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.PRINT_PROJECT,
            label="Функциональный проект на печать (ZIP)",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
            extra={"object_class": ObjectClass.FUNCTIONAL.value},
        )

    if is_single_part_print_request(text) and openscad_available():
        model, reason = _pick_model("engineering_json", user_model, text)
        return TaskPlan(
            kind=TaskKind.OPENSCAD_SINGLE,
            label="Функциональная деталь (OpenSCAD)",
            model=model,
            model_reason=reason,
            capability="engineering_json",
            user_text=text,
            extra={"object_class": ObjectClass.FUNCTIONAL.value},
        )

    return _route_organic(text, user_model)
