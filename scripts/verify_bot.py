#!/usr/bin/env python3
"""Проверка маршрутизации и самопроверки без Telegram."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.services.bambu_hints import meshy_export_filename
from bot.services.meshy_route import meshy_available, meshy_prompt_from_text, should_meshy_from_photo
from bot.services.meshy_plan import (
    Meshy3DPipeline,
    plan_text_to_3d,
    should_meshy_text_to_image,
    wants_glb_output,
)
from bot.services.print_project import _fallback_single_part, export_single_part_stl
from bot.services.self_check import DeliveryResult, DeliveredFile, run_self_check
from bot.services.task_plan import TaskKind, build_task_plan


CASES = [
    (
        "Сделай 3д модель для печати на принтере бамбулаб п2с . Ручка для 5л бутылок",
        TaskKind.OPENSCAD_SINGLE,
    ),
    (
        "Сделай мне 3d модель для принтера bambu. Чебурашка чёрного цвета с зелёными глазами.",
        TaskKind.MESHY_TEXT_3D,
    ),
    (
        "Хочу 3d модель на принтере распечатать. Фигурка лабрадора. "
        "У которого могут шевелиться ноги и голова и хвост. Примерно 50гр. AMS Pro.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Хочу 3д модель на принтере распечатать. Фигурка ангела. "
        "У которого могут шевелиться крылья. Ангел белый, глаза красные, крылья чёрные.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Хочу 3д модель дракона с подвижными крыльями, чтобы открыть в Bambu Studio.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Сделай летучую мышь с шевелящимися крыльями для печати 3D.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Сделай Чебурашку с подвижными руками для 3D печати.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Хочу неизвестного монстра с шевелящимися крыльями для 3D печати.",
        TaskKind.ARTICULATED_3MF,
    ),
    (
        "Хочу 3d модель на принтере распечатать. Фигурка лабрадора. "
        "Примерно 50гр. AMS Pro. Лабрадор чёрный, глаза белые.",
        TaskKind.MESHY_TEXT_3D,
    ),
    (
        # Realistic airplane → crisp procedural NACA CAD airliner (AIRPLANE_3MF
        # high_detail). text-to-3D AI produces "clay" on hard-surface aircraft,
        # so airplanes use the deterministic NACA-lofted generator.
        "Мне нужен 3д проект для бамбулаб п2с. Самолет боенг. Белого цвета. "
        "Максимальная детализация. У меня есть 50гр филамента. AMS Pro. "
        "Пришли проект, чтобы просто залил в Bambu Studio и нажал на печать",
        TaskKind.AIRPLANE_3MF,
    ),
    (
        "Сделай процедурный v2 самолёт боинг без референса для Bambu Studio, 50гр AMS Pro",
        TaskKind.AIRPLANE_3MF,
    ),
    (
        "гибридный генератор проект на печать storyboard",
        TaskKind.PRINT_PROJECT,
    ),
    (
        "Привет, как дела?",
        TaskKind.CHAT,
    ),
    (
        "Нарисуй концепт чёрного лабрадора, референс для 3D",
        TaskKind.MESHY_IMAGE,
    ),
    (
        "Сделай flexi print-in-place alien для печати",
        TaskKind.PRINT_PROJECT,
    ),
    (
        "Привет. у меня есть проект с описанием, мне нужна помощь по его печати и сборки. ты это умеешь?",
        TaskKind.CHAT,
    ),
]

PHOTO_CASES = [
    (
        "Сделай по фото портретную фигурку bobblehead, поза как на фото, для Bambu P2S 0.4",
        TaskKind.PORTRAIT_FIGURINE,
    ),
    (
        "Сделай chibi 3D фигурку человека по фото",
        TaskKind.PORTRAIT_FIGURINE,
    ),
    (
        "Сделай 3D модель с фото для печати",
        TaskKind.MESHY_PHOTO_3D,
    ),
]


def test_meshy_plan() -> None:
    print("\n=== Meshy plan ===")
    p = plan_text_to_3d(
        "лабрадор чёрный глаза белые AMS",
        meshy_prompt_from_text("лабрадор чёрный"),
    )
    assert p.use_refine, p.pipeline == Meshy3DPipeline.PRINT_TEXTURED
    assert p.deliver_glb, "Textured Meshy must keep GLB visual asset"
    p_glb = plan_text_to_3d(
        "лабрадор чёрный глаза белые AMS, пришли ещё GLB preview",
        meshy_prompt_from_text("лабрадор чёрный"),
    )
    assert wants_glb_output("пришли GLB preview") and p_glb.deliver_glb
    p2 = plan_text_to_3d("быстрый черновик фигурки", "dog")
    assert p2.pipeline == Meshy3DPipeline.PRINT_FAST
    p_high = plan_text_to_3d("максимальная детализация реалистичная фигурка", "realistic figurine")
    assert p_high.target_polycount == 250000
    assert p_high.hd_texture and p_high.preserve_source_mesh
    assert should_meshy_text_to_image("нарисуй картинку заката")
    from bot.services.meshy_plan import rig_animation_intent
    from bot.services.meshy_route import meshy_available

    assert rig_animation_intent("сделай 3d героя с анимацией ходьбы")
    assert not rig_animation_intent("лабрадор с шевелящимися лапами")
    if meshy_available():
        p3 = plan_text_to_3d("герой с анимацией бега", "knight character")
        assert p3.pipeline.value == "rig_animate"
    from bot.services.stl_postprocess import target_height_mm_from_text, target_length_mm_from_text

    assert target_height_mm_from_text("длина 15 см, высота 5 см, 50гр") == 50.0
    assert target_length_mm_from_text("длина 15 см, высота 5 см, 50гр") == 150.0
    from bot.services.engineering_intake import (
        creative_design_requested,
        engineering_drawing_requested,
        engineering_risks,
        looks_like_engineering_correction,
        merge_engineering_correction,
        mechanical_motion_requested,
        mechanical_motion_details_provided,
        needs_engineering_intake,
        printer_spec_from_text,
        render_engineering_intake,
        requested_dimensions_mm,
    )
    assert printer_spec_from_text("Bambu Lab P2S") and printer_spec_from_text("Bambu Lab P2S").bed_mm == (256, 256, 256)
    assert printer_spec_from_text("бамбулаб п2с") and printer_spec_from_text("бамбулаб п2с").key == "bambu_p2s"
    assert requested_dimensions_mm("длина 15 см, высота 5 см")["length_mm"] == 150.0
    assert mechanical_motion_requested("самолет boeing, чтобы шасси шевелилось")
    assert mechanical_motion_details_provided("деталь колеса вращаются на оси, а сами шосси складываются как у настоящего самолета")
    assert engineering_drawing_requested("по чертежу сделай 3D STL деталь для Bambu")
    assert not should_meshy_from_photo("по чертежу сделай 3D STL деталь")
    assert needs_engineering_intake("фигура ростом с человека для смолы")
    assert "material_resin" in engineering_risks("фигура ростом с человека для resin")
    assert looks_like_engineering_correction("нет, материал PETG и принтер A1 mini")
    merged = merge_engineering_correction("сделай деталь из PLA", "нет, материал PETG")
    assert "PETG" in merged and "приоритетное" in merged
    boeing_mech_original = (
        "Мне нужен 3д проект для бамбулаб п2с. Самолет боинг. "
        "Хочу что б длина была 20 см а высота 15 см. "
        "двигатель с лопастями крутящимися, шосси убираются."
    )
    boeing_mech_updated = merge_engineering_correction(
        boeing_mech_original,
        "деталь колеса вращаются на оси, а сами шосси складываются как у настоящего самолета. "
        "и про хорошую детализацию лопастей не забудь",
    )
    boeing_mech_render = render_engineering_intake(boeing_mech_updated)
    assert "Bambu Lab P2S" in boeing_mech_render, boeing_mech_render
    assert "Механика уточнена" in boeing_mech_render, boeing_mech_render
    assert "Уточните: деталь должна вращаться" not in boeing_mech_render, boeing_mech_render
    # Gear words alone no longer trap Boeing into MECHANICAL_PROJECT — crisp NACA CAD.
    gear_plan = build_task_plan("Boeing для Bambu P2S, чтобы шасси складывалось", "gpt-5.4")
    assert gear_plan.kind == TaskKind.AIRPLANE_3MF, gear_plan
    assert (gear_plan.extra or {}).get("high_detail"), gear_plan.extra
    mechanical_plan = build_task_plan(
        "механический кит Boeing с подвижным шасси на осях для Bambu P2S", "gpt-5.4"
    )
    assert mechanical_plan.kind == TaskKind.MECHANICAL_PROJECT, mechanical_plan
    assert creative_design_requested("придумай игрушку дракона для 3d печати")
    if meshy_available():
        creative_plan = build_task_plan("придумай игрушку дракона для 3d печати", "gpt-5.4")
        assert creative_plan.kind == TaskKind.MESHY_TEXT_3D, creative_plan
    test2_plan = build_task_plan("тест 2", "gpt-5.4")
    assert test2_plan.kind == TaskKind.CHAT, test2_plan
    assert not test2_plan.extra.get("temporary_shortcut")
    from bot.services.airplane_3mf import airplane_concept_prompt
    from bot.services.bambu_hints import (
        extract_part_color_requests,
        part_color_prompt_fragment,
    )

    boeing_prompt = airplane_concept_prompt(
        "Белый Boeing, двигатели чёрные, хвост красный, максимальная детализация"
    )
    assert "black engine" in boeing_prompt, boeing_prompt
    assert "red tail" in boeing_prompt, boeing_prompt
    generic_colors = extract_part_color_requests(
        "Фигурка дракона: крылья чёрные, глаза красные, тело зелёное"
    )
    assert generic_colors["wings"] == "black", generic_colors
    assert generic_colors["eyes"] == "red", generic_colors
    assert generic_colors["body"] == "green", generic_colors
    assert "black wings" in part_color_prompt_fragment("крылья чёрные, глаза красные")
    textured = plan_text_to_3d(
        "фигурка дракона, крылья чёрные, глаза красные",
        "dragon figurine",
    )
    assert "black wings" in textured.texture_prompt, textured.texture_prompt
    assert "red eyes" in textured.texture_prompt, textured.texture_prompt
    from bot.handlers.chat_logic import (
        _concept_approval_intent,
        _is_print_instruction_request,
        _looks_like_3d_asset_command,
        _looks_like_new_project_request,
    )

    full_boeing_request = (
        "Мне нужен 3д проект для бамбулаб п2с . Самолет боенг. Белого цвета . "
        "Максимальная детализация. У меня есть 50гр филамента. Хочу что б длина была 15 см "
        "а высота 5 см. Размах крыльев по смыслу. Так же есть система амс про. "
        "Двигатели - чёрные. У меня есть ещё красный, пусть хвост будет красным. "
        "Пришли проект мне , что бы просто залил в бамбустудио и нажал на печать"
    )
    assert _looks_like_new_project_request(full_boeing_request)
    assert _concept_approval_intent(full_boeing_request) == ""
    assert not _looks_like_3d_asset_command(full_boeing_request)
    mechanical_boeing_request = (
        "Мне нужен 3д проект для бамбулаб п2с . Самолет боинг. Белого цвета . "
        "Максимальная детализация , максимум естественности, двигатель с лопастями крутящимися, "
        "шосси убираются, т.е весь предел фантазий который ты можешь воплотить. "
        "Хочу что б длина была 20 см а высота 15 см. Размах крыльев по смыслу. "
        "Пришли проект мне , что бы просто залил в бамбустудио и нажал на печать"
    )
    assert _looks_like_new_project_request(mechanical_boeing_request)
    assert not _looks_like_3d_asset_command(mechanical_boeing_request)
    mechanical_boeing_plan = build_task_plan(mechanical_boeing_request, "gpt-5.4")
    assert mechanical_boeing_plan.kind == TaskKind.AIRPLANE_3MF, mechanical_boeing_plan
    assert (mechanical_boeing_plan.extra or {}).get("high_detail"), mechanical_boeing_plan.extra
    from bot.handlers.chat_logic import _engineering_intake_intent
    from bot.services.print_project import preview_project_build

    assert _engineering_intake_intent(mechanical_boeing_request) == ""
    assert _engineering_intake_intent("да, верно, запускай") == "approve"
    assert _engineering_intake_intent("да всё верно, запускай") == "approve"
    explicit_mech_kit = (
        "механический кит Boeing: подвижное шасси на осях, лопасти вращаются, "
        "Bambu P2S, длина 20 см"
    )
    n_preview, label, _ = preview_project_build(explicit_mech_kit, explicit_mech_kit)
    assert n_preview >= 22, (n_preview, label)
    assert "mechanical Boeing v3" in label
    assert _concept_approval_intent("Мало детализации, сделай больше") == "refine"
    assert _concept_approval_intent("норм, делай 3D по этой картинке") == "approve"
    assert _concept_approval_intent("Мне нравится, запускай в работу") == "approve"
    assert _concept_approval_intent("мне нравится, запускай") == "approve"
    assert _looks_like_3d_asset_command(
        "усиль шасси и пилоны, добавь окна/панели, сохрани Meshy-форму, не делай procedural"
    )
    assert _is_print_instruction_request("отлично а инструкцию как запустить на печать еще дай")
    assert _concept_approval_intent("отлично а инструкцию как запустить на печать еще дай") == ""
    assert _concept_approval_intent("не то, переделай") == "refine"
    assert (
        _concept_approval_intent(
            "Нет не устраивает, много лишних объектов на самолёте, выглядит не по настоящему"
        )
        == "refine"
    )
    assert (
        _concept_approval_intent(
            "Мне не нравится эта модель. Сделай лучше, добавь больше деталей и окон"
        )
        == "refine"
    )
    assert _concept_approval_intent("мне не нравится") == "reject"
    assert _concept_approval_intent("отмена, не надо делать 3D") == "cancel"
    from bot.services.bambu_hints import needs_auto_support_project

    assert needs_auto_support_project("Сделай фигурку дракона с крыльями для Bambu")
    assert needs_auto_support_project("Портретная bobblehead фигурка человека")
    assert not needs_auto_support_project("Ручка для 5л бутылки")
    from bot.services.bambu_hints import bambu_print_steps

    steps = bambu_print_steps("белый Boeing, двигатели красные", file_kind="3mf")
    assert "Slice plate" in steps and "Print plate" in steps and "engines" in steps
    from bot.services.print_project import wants_print_project

    assert wants_print_project("Сделай flexi print-in-place alien для печати")
    assert wants_print_project("Сделай micro wheel fidget spinner")
    assert wants_print_project("Сделай modular figure с pin connectors")
    print("OK meshy_plan")


def test_meshy_candidate_score_prefers_visual_quality() -> None:
    print("\n=== Meshy candidate scoring ===")
    import trimesh
    from bot.services.meshy_3d import MeshyDelivery, MeshyFile, score_meshy_delivery

    mesh = trimesh.creation.icosphere(subdivisions=4, radius=20)
    stl = mesh.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    plain = MeshyDelivery(
        files=[MeshyFile(data=stl, ext="stl", role="primary")],
        method="meshy/image-to-3d",
    )
    visual = MeshyDelivery(
        files=[
            MeshyFile(data=stl, ext="stl", role="primary"),
            MeshyFile(data=b"glb" * 200_000, ext="glb", role="preview_color"),
        ],
        method="meshy/image-to-3d",
    )
    plain_score = score_meshy_delivery(plain, "Boeing high detail")
    visual_score = score_meshy_delivery(visual, "Boeing high detail")
    print(f"plain={plain_score['score']} visual={visual_score['score']}")
    assert visual_score["score"] > plain_score["score"], (plain_score, visual_score)


def test_mesh_cache_roundtrip() -> None:
    print("\n=== Mesh cache для 3D ассетов ===")
    from bot.services.mesh_cache import load_mesh_asset, save_mesh_asset

    user_id = 999777
    save_mesh_asset(
        user_id,
        "boeing_airliner_last_meshy",
        data=b"solid cached-boeing\nendsolid cached-boeing\n",
        filename="boeing-airliner-meshy.stl",
        meta={"final_repair_ok": True},
    )
    cached = load_mesh_asset(user_id, "boeing_airliner_last_meshy")
    assert cached is not None
    assert cached.filename == "boeing-airliner-meshy.stl"
    assert cached.meta["final_repair_ok"] is True


def test_boeing_prompt_does_not_leak_old_part_colors() -> None:
    print("\n=== Boeing prompt does not leak old engine/tail colors ===")
    from bot.services.airplane_3mf import airplane_concept_prompt
    from bot.services.bambu_hints import extract_part_color_requests
    from bot.services.meshy_route import meshy_prompt_from_text

    user = (
        "Мне нужен 3д проект для бамбулаб п2с. Самолет боенг. Белого цвета. "
        "Максимальная детализация, максимум естественности. Длина 15 см, высота 5 см."
    )
    prompt = meshy_prompt_from_text(user)
    assert extract_part_color_requests(user) == {}
    assert "white engine nacelles" in prompt
    assert "no black engines" in prompt
    assert "no red tail" in prompt
    assert "black engine" not in prompt.replace("no black engines", "")
    concept_prompt = airplane_concept_prompt(user)
    assert "white engine nacelles" in concept_prompt
    assert "no black engines" in concept_prompt
    assert "no red tail" in concept_prompt
    assert "black engine nacelles" not in concept_prompt
    print("OK prompt:", prompt[:160])


def test_meshy_strict_repair_prefers_lower_non_manifold_count() -> None:
    print("\n=== Meshy strict repair chooses improved Bambu candidate ===")
    from bot.services.meshy_3d import (
        _has_repair_warning,
        _repair_candidate_is_better,
        _repair_warning_count,
    )

    first = "meshy/image-to-3d · repair WARNING: 297 non-manifold edges"
    improved = "meshy/image-to-3d strict · repair WARNING: 42 non-manifold edges"
    fixed = "meshy/image-to-3d strict · repair OK (pymeshfix)"
    worse = "meshy/image-to-3d strict · repair WARNING: 391 non-manifold edges"

    assert _repair_warning_count(first) == 297
    assert _repair_candidate_is_better(first, improved)
    assert _repair_candidate_is_better(first, fixed)
    assert not _repair_candidate_is_better(first, worse)
    assert not _repair_candidate_is_better(fixed, improved)
    assert _has_repair_warning("meshy/native · repair skip: worker timeout")
    print("OK strict repair selection")


def test_large_meshy_postprocess_keeps_scaled_file_when_repair_times_out() -> None:
    print("\n=== Large Meshy STL keeps scaled file if repair times out ===")
    import bot.services.stl_postprocess as sp

    original_normalize = sp.normalize_meshy_stl
    original_manifold_repair = sp.manifold_repair_stl_mesh
    original_repair = sp.repair_stl_mesh
    try:
        sp.normalize_meshy_stl = lambda data, user_text="": sp.StlNormalizeResult(
            data=b"scaled-stl",
            width_mm=150.0,
            depth_mm=135.0,
            height_mm=50.0,
            scale_applied=1000.0,
            note="масштаб ×1000.0000 → длина ~150 мм",
        )
        sp.manifold_repair_stl_mesh = lambda data: (data, "manifold repair skip: worker timeout")
        sp.repair_stl_mesh = lambda data: (data, "repair skip: worker timeout")
        res = sp._prepare_large_meshy_stl_for_bambu(b"raw-stl", user_text="Boeing длина 15 см")
    finally:
        sp.normalize_meshy_stl = original_normalize
        sp.manifold_repair_stl_mesh = original_manifold_repair
        sp.repair_stl_mesh = original_repair

    assert res.data == b"scaled-stl"
    assert round(res.width_mm) == 150
    assert "manifold repair skip: worker timeout" in res.note
    print("OK large STL timeout preserves normalized data")


def test_short_3d_command_guard() -> None:
    print("\n=== Short 3D command guard ===")
    from bot.handlers.chat_logic import (
        _concept_approval_intent,
        _is_ambiguous_short_3d_command,
        _needs_reference_before_meshy,
    )

    assert _is_ambiguous_short_3d_command("делай 3д")
    assert _is_ambiguous_short_3d_command("сделай 3д модель")
    assert not _is_ambiguous_short_3d_command("сделай 3д модель лабрадора")
    assert not _is_ambiguous_short_3d_command("Boeing 15 см максимальная детализация")
    assert not _needs_reference_before_meshy(
        "Мне нужен 3д проект для бамбулаб п2с. Ангел белого цвета. "
        "Максимальная детализация, высота 15 см, 50гр, AMS Pro."
    )
    assert _needs_reference_before_meshy("сделай максимально похожую 3д копию как на фото")
    assert _concept_approval_intent("норм, делай 3д") == "approve"
    assert _concept_approval_intent("делай 3д по этой картинке") == "approve"
    print("OK short 3D guard")


def test_engineering_contract() -> None:
    print("\n=== Инженерный контракт системного промпта ===")
    from bot.config import SYSTEM_PROMPT

    required = (
        "распознай истинную цель",
        "лучший достижимый путь",
        "Не выдавай мечту за факт",
        "предложи его ненавязчиво",
        "Самопроверяйся",
    )
    missing = [needle for needle in required if needle not in SYSTEM_PROMPT]
    assert not missing, missing
    print("OK: prompt требует понимать цель, говорить правду и самопроверяться")


def test_portrait_figurine_prompt() -> None:
    print("\n=== Portrait figurine prompt ===")
    from bot.services.portrait_figurine import (
        concept_prompt_from_facts,
        is_portrait_figurine_request,
        parse_portrait_plan,
    )

    msg = PHOTO_CASES[0][0]
    assert is_portrait_figurine_request(msg)
    p = parse_portrait_plan(msg)
    assert p.style == "bobblehead", p
    assert p.posture == "image pose", p
    prompt = concept_prompt_from_facts(
        "young man, short hair, dark vest, shirt, hands in pockets",
        msg,
    )
    assert "bobblehead" in prompt.lower(), prompt
    assert "reference photo" in prompt.lower(), prompt
    print("OK portrait prompt:", prompt[:100])


def test_routing() -> None:
    print("=== Маршрутизация ===")
    ok = True
    for msg, expected in CASES:
        plan = build_task_plan(msg, "gpt-5.4-mini")
        status = "OK" if plan.kind == expected else "FAIL"
        if plan.kind != expected:
            ok = False
        print(f"{status} | {expected.value:20} | got {plan.kind.value:20} | {msg[:50]}")
        print(f"      model={plan.model} | {plan.label}")
    if not ok:
        sys.exit(1)

    text_only_plan = build_task_plan("Привет, кто ты?", "deepseek-chat")
    assert text_only_plan.kind == TaskKind.CHAT
    assert "DeepSeek" in text_only_plan.model_reason

    print("\n=== Маршрутизация фото ===")
    for msg, expected in PHOTO_CASES:
        plan = build_task_plan(msg, "gpt-5.4-mini", has_photo=True)
        status = "OK" if plan.kind == expected else "FAIL"
        print(f"{status} | {expected.value:20} | got {plan.kind.value:20} | {msg[:60]}")
        assert plan.kind == expected, (msg, plan.kind, expected)


async def test_openscad_handle() -> None:
    print("\n=== OpenSCAD ручка ===")
    msg = CASES[0][0]
    specs = _fallback_single_part(msg)
    stl, fn, _, part = await export_single_part_stl(specs)
    assert stl and len(stl) > 10_000, f"handle stl too small: {len(stl or b'')}"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    dr = DeliveryResult(
        summary="Отправлена одна деталь: Ручка для 5л бутылки",
        files=[DeliveredFile(filename=fn, size_bytes=len(stl), kind="stl")],
        meta={"template": part.get("template")},
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"self-check ok={check.ok}: {check.message}")
    assert check.ok, check.issues


async def test_cheburashka_plate_fails_check() -> None:
    print("\n=== Самопроверка ловит пластину вместо Чебурашки ===")
    msg = CASES[1][0]
    plan = build_task_plan(msg, "gpt-5.4-mini")
    dr = DeliveryResult(
        summary="Отправлена одна деталь: plate",
        files=[DeliveredFile(filename="x.stl", size_bytes=1503, kind="stl")],
        meta={"template": "plate"},
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"self-check ok={check.ok}: {check.issues}")
    assert not check.ok, "plate for cheburashka should fail self-check"


async def test_meshy_repair_warning_fails_check() -> None:
    print("\n=== Самопроверка ловит non-manifold после repair ===")
    msg = "Сделай 3D модель Boeing для Bambu"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_PHOTO_3D
    dr = DeliveryResult(
        summary="Meshy model",
        files=[DeliveredFile(filename="boeing-airliner-meshy.stl", size_bytes=800_000, kind="stl")],
        meta={"meshy_method": "meshy/photo_textured · repair WARNING: 25 non-manifold edges"},
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"self-check ok={check.ok}: {check.issues}")
    assert not check.ok, "non-manifold Meshy STL should fail self-check"


async def test_meshy_image_self_check_is_concept() -> None:
    print("\n=== Самопроверка Meshy image не называет концепт 3D-моделью ===")
    # Use a dedicated concept-image request (airplanes now go straight to
    # Meshy text-to-3D, so they no longer produce a concept image).
    msg = "Нарисуй концепт чёрного лабрадора, референс для 3D"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    assert plan.kind == TaskKind.MESHY_IMAGE
    dr = DeliveryResult(
        summary="Meshy image",
        files=[DeliveredFile(filename="boeing-concept.png", size_bytes=827_000, kind="image")],
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"image self-check ok={check.ok}: {check.message}")
    assert check.ok
    assert "концепт-картинка" in check.message
    assert "Meshy-модель" not in check.message


async def test_boeing_meshy_stl_is_not_final() -> None:
    print("\n=== Boeing Meshy STL не считается финальным print-ready ===")
    msg = "Сделай 3D модель Boeing для Bambu"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_PHOTO_3D
    dr = DeliveryResult(
        summary="Meshy model",
        files=[DeliveredFile(filename="boeing-airliner-meshy.stl", size_bytes=827_000, kind="stl")],
        meta={"meshy_method": "meshy/image-to-3d repaired"},
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"boeing meshy final ok={check.ok}: {check.issues}")
    assert not check.ok
    assert any("3MF v3" in issue for issue in check.issues)


async def test_boeing_meshy_derived_repair_warning_is_kept() -> None:
    print("\n=== Boeing Meshy-derived файл не заменяется fallback при repair warning ===")
    msg = "Сделай 3D модель Boeing для Bambu"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_PHOTO_3D
    dr = DeliveryResult(
        summary="Meshy-derived repaired STL",
        files=[DeliveredFile(filename="boeing-airliner-meshy.stl", size_bytes=827_000, kind="meshy")],
        meta={
            "meshy_method": "meshy/image-to-3d · repair WARNING: 12 non-manifold edges",
            "meshy_derived_print_ready": True,
            "repair_warning_accepted": True,
            "native_3mf": True,
            "color_limitation_warning": True,
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"boeing Meshy-derived warning ok={check.ok}: {check.message}")
    assert check.ok, check.issues


async def test_meshy_support_3mf_passes_check() -> None:
    print("\n=== Meshy STL для фигурки оборачивается в 3MF с supports ===")
    import trimesh
    from bot.services.support_3mf import wrap_stl_as_support_3mf

    msg = "Сделай фигурку дракона с крыльями для Bambu"
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=20)
    stl = mesh.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    data, fname = wrap_stl_as_support_3mf(
        stl,
        stl_filename="dragon-figurine-meshy.stl",
        user_text=msg,
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4},
    )
    assert fname == "dragon-figurine-bambu-supports.3mf", fname
    assert len(data) > 12_000, len(data)
    assert b"enable_support" in data or b"model_settings.config" in data
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_TEXT_3D
    dr = DeliveryResult(
        summary="3D Meshy wrapped as support 3MF",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={"support_3mf": True, "meshy_method": "meshy/text-to-3d repaired"},
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"support 3mf self-check ok={check.ok}: {check.message}")
    assert check.ok, check.issues
    assert "Tree(auto)" in check.message


async def test_meshy_component_3mf_for_part_colors() -> None:
    print("\n=== Meshy STL компоненты превращаются в multi-object 3MF ===")
    import trimesh
    from bot.services.support_3mf import wrap_stl_as_component_3mf

    def box(extents, xyz):
        mesh = trimesh.creation.box(extents=extents)
        mesh.apply_translation(xyz)
        return mesh

    meshes = [
        box((100, 10, 10), (0, 0, 12)),
        box((10, 6, 6), (10, 18, 4)),
        box((10, 6, 6), (10, -18, 4)),
        box((8, 4, 25), (-48, 0, 28)),
    ]
    combined = trimesh.util.concatenate(meshes)
    stl = combined.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    msg = "Белый Boeing, двигатели чёрные, хвост красный"
    data, fname, meta = wrap_stl_as_component_3mf(
        stl,
        stl_filename="boeing-airliner-meshy.stl",
        user_text=msg,
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
    )
    assert fname == "boeing-airliner-components-ams.3mf", fname
    assert meta["component_count"] >= 4, meta
    assert meta["object_level_colors"], meta
    assert any("engine" in name for name in meta["component_names"]), meta
    assert any("tail" in name for name in meta["component_names"]), meta
    plan = build_task_plan(msg + " для Bambu", "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_TEXT_3D
    dr = DeliveryResult(
        summary="Meshy component 3MF",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={
            "component_3mf": True,
            "object_level_colors": True,
            "component_count": meta["component_count"],
            "part_color_requests": {"engines": "black", "tail": "red"},
            "meshy_method": "meshy/text-to-3d repaired",
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"component 3mf ok={check.ok}: {check.message}")
    assert check.ok, check.issues


async def test_component_3mf_rejects_zero_volume_shards() -> None:
    print("\n=== Component 3MF отклоняет zero-volume Meshy shards ===")
    import numpy as np
    import trimesh
    from bot.services.support_3mf import wrap_stl_as_component_3mf

    shards = []
    for i in range(4):
        vertices = np.array(
            [
                [i * 10.0, 0.0, 0.0],
                [i * 10.0 + 80.0, 0.0, 0.0],
                [i * 10.0, 80.0, 0.0],
            ]
        )
        shards.append(trimesh.Trimesh(vertices=vertices, faces=[[0, 1, 2]], process=False))
    combined = trimesh.util.concatenate(shards)
    stl = combined.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    try:
        wrap_stl_as_component_3mf(
            stl,
            stl_filename="boeing-airliner-meshy.stl",
            user_text="Белый Boeing, двигатели чёрные, хвост красный",
            profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
        )
    except Exception as e:
        print(f"OK rejected bad components: {str(e)[:120]}")
        assert "component 3MF worker failed" in str(e) or "not print-solid" in str(e)
    else:
        raise AssertionError("zero-volume shard split must not be exported as Bambu 3MF")


def test_meshy_normalize_scales_explicit_length_up() -> None:
    print("\n=== Meshy STL масштабируется вверх по явной длине ===")
    import trimesh
    from bot.services.stl_postprocess import normalize_meshy_stl

    mesh = trimesh.creation.box(extents=(0.15, 0.03, 0.05))
    stl = mesh.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    res = normalize_meshy_stl(stl, user_text="Самолет Boeing длина 15 см, высота 5 см")
    longest_xy = max(res.width_mm, res.depth_mm)
    print(f"scaled dims={res.width_mm:.1f}x{res.depth_mm:.1f}x{res.height_mm:.1f}; {res.note}")
    assert 145.0 <= longest_xy <= 155.0
    assert res.height_mm > 10.0


async def test_meshy_single_object_rejected_before_delivery() -> None:
    print("\n=== Boeing Meshy отдаёт STL вместо components-ams / procedural fallback ===")
    import trimesh
    from bot.handlers.chat_logic import _meshy_requires_object_level_result, _send_meshy_3d_files
    from bot.services.meshy_3d import MeshyDelivery, MeshyFile

    class FakeMessage:
        def __init__(self):
            self.messages = []
            self.documents = []

        async def answer(self, text, **kwargs):
            self.messages.append((text, kwargs))

        async def answer_document(self, document, **kwargs):
            self.documents.append((document, kwargs))

    mesh = trimesh.creation.box(extents=(150, 50, 50))
    stl = mesh.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    fake = FakeMessage()
    msg = "Bambu P2S Boeing белый, двигатели чёрные, хвост красный, AMS Pro"
    delivery = MeshyDelivery(
        files=[MeshyFile(data=stl, ext="stl", role="primary")],
        method="meshy/image-to-3d",
        plan_label="test",
    )
    dr = await _send_meshy_3d_files(
        fake,
        delivery,
        base_caption="candidate",
        primary_fname="boeing-airliner-meshy.stl",
        user_id=999001,
        history_user=msg,
        history_assistant="candidate",
        user_text_for_support=msg,
        support_profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
        require_object_level_colors=True,
    )
    print(f"Boeing delivery success={dr.success}: {dr.meta}")
    assert dr.success, "Boeing must deliver Meshy-derived STL instead of blocking for AMS"
    names = [getattr(doc, "filename", "") for doc, _ in fake.documents]
    assert names and names[0] == "boeing-airliner-meshy.stl", names
    assert any("boeing-airliner-meshy.stl" in n for n in names), names
    assert not any("components-ams" in n for n in names), names
    assert not any(n.endswith("-bambu-supports.3mf") for n in names), names

    native_fake = FakeMessage()
    native_delivery = MeshyDelivery(
        files=[
            MeshyFile(data=stl, ext="stl", role="primary"),
            MeshyFile(data=b"native-3mf" * 1000, ext="3mf", role="native_3mf"),
        ],
        method="meshy/image-to-3d native",
        plan_label="test",
    )
    native_dr = await _send_meshy_3d_files(
        native_fake,
        native_delivery,
        base_caption="candidate",
        primary_fname="boeing-airliner-meshy.stl",
        user_id=999001,
        history_user=msg,
        history_assistant="candidate",
        user_text_for_support=msg,
        support_profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
        require_object_level_colors=True,
    )
    assert native_dr.success
    assert native_dr.meta.get("native_3mf")
    native_names = [getattr(doc, "filename", "") for doc, _ in native_fake.documents]
    assert native_names[0] == "boeing-airliner-meshy.stl", native_names
    assert any(name.endswith("-meshy-native.3mf") for name in native_names), native_names

    generic_msg = "Дракон для Bambu: крылья чёрные, глаза красные, AMS Pro"
    assert _meshy_requires_object_level_result(generic_msg)
    generic_fake = FakeMessage()
    generic_dr = await _send_meshy_3d_files(
        generic_fake,
        delivery,
        base_caption="candidate",
        primary_fname="dragon-meshy.stl",
        user_id=999001,
        history_user=generic_msg,
        history_assistant="candidate",
        user_text_for_support=generic_msg,
        support_profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
        require_object_level_colors=_meshy_requires_object_level_result(generic_msg),
    )
    assert generic_dr.success, "generic AMS request should still deliver Meshy STL with warning"
    generic_names = [getattr(doc, "filename", "") for doc, _ in generic_fake.documents]
    assert generic_names, "generic Meshy STL should be delivered"
    assert generic_names[0] == "dragon-meshy.stl", generic_names
    assert not any("components-ams" in n for n in generic_names), generic_names
    assert not any(n.endswith("-bambu-supports.3mf") for n in generic_names), generic_names


async def test_meshy_failure_no_fallback() -> None:
    print("\n=== Meshy failure: no generator substitution ===")
    from unittest.mock import AsyncMock, patch

    from bot.handlers.chat_logic import _reply_printable_fallback_after_meshy_failure
    from bot.services import history
    from bot.services.task_plan import TaskKind

    class FakeBot:
        async def send_chat_action(self, *args, **kwargs):
            return None

    class FakeStatusMessage:
        async def edit_text(self, *args, **kwargs):
            return None

        async def delete(self):
            return None

    class FakeUser:
        id = 999_003

    class FakeChat:
        id = 999_003

    class FakeMessage:
        def __init__(self):
            self.from_user = FakeUser()
            self.chat = FakeChat()
            self.bot = FakeBot()
            self.messages = []
            self.documents = []

        async def answer(self, text, **kwargs):
            self.messages.append((text, kwargs))
            return FakeStatusMessage()

        async def answer_document(self, document, **kwargs):
            self.documents.append((document, kwargs))
            return FakeStatusMessage()

    await history.init_db()

    fake2 = FakeMessage()
    boeing_msg = (
        "Сделай реалистичный Boeing для печати, белый, максимальная детализация, 15 см"
    )
    plan2, dr2 = await _reply_printable_fallback_after_meshy_failure(
        fake2,
        boeing_msg,
        "gpt-5.4-mini",
        reason="Meshy timeout",
    )
    print(f"boeing no-fallback kind={plan2.kind}, success={dr2.success}, docs={len(fake2.documents)}")
    assert plan2.kind == TaskKind.MESHY_TEXT_3D, plan2
    assert not dr2.success
    assert dr2.meta.get("no_fallback")
    assert len(fake2.documents) == 0, "must not deliver substitute file on Meshy failure"
    assert any("не отправлен" in text.lower() for text, _ in fake2.messages)

    dragon_fake = FakeMessage()
    dragon_msg = (
        "Сделай дракона с подвижными крыльями для Bambu: крылья чёрные, глаза красные, AMS Pro."
    )
    dragon_plan, dragon_dr = await _reply_printable_fallback_after_meshy_failure(
        dragon_fake,
        dragon_msg,
        "gpt-5.4-mini",
        reason="generic quality gate rejected single-object Meshy STL",
    )
    print(f"dragon no-fallback kind={dragon_plan.kind}, success={dragon_dr.success}, docs={len(dragon_fake.documents)}")
    assert dragon_plan.kind == TaskKind.MESHY_TEXT_3D
    assert not dragon_dr.success
    assert not dragon_fake.documents, "must not deliver procedural substitute"


async def test_print_project_network_error_uses_local_fallback() -> None:
    print("\n=== Print-project fallback при proxy timeout ===")
    from bot.services import llm
    from bot.services.print_project import generate_project_specs

    old_chat = llm.chat_completion

    async def fail_chat(*args, **kwargs):
        raise RuntimeError("Proxy connection timed out: 15")

    llm.chat_completion = fail_chat
    try:
        specs = await generate_project_specs(
            "Сделай проект на печать по случайному файлу",
            "неподходящий контекст",
            "gpt-5.4",
            part_count=4,
        )
    finally:
        llm.chat_completion = old_chat

    assert specs.get("parts"), specs
    assert any("fallback" in str(a).lower() or "прокси" in str(a).lower() for a in specs.get("assumptions", [])), specs
    print(f"OK fallback project: {specs.get('project_name')}")


async def test_meshy_single_mesh_part_colors_fail_check() -> None:
    print("\n=== Самопроверка ловит single-mesh при цветах деталей ===")
    msg = "Сделай дракона для Bambu: крылья чёрные, глаза красные"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_TEXT_3D
    dr = DeliveryResult(
        summary="Meshy STL single mesh",
        files=[DeliveredFile(filename="dragon-meshy.stl", size_bytes=900_000, kind="stl")],
        meta={
            "meshy_method": "meshy/text-to-3d repaired",
            "part_color_requests": {"wings": "black", "eyes": "red"},
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"single mesh colors ok={check.ok}: {check.issues}")
    assert not check.ok
    assert any("цвет" in issue or "AMS" in issue for issue in check.issues)

    warned = DeliveryResult(
        summary="Meshy STL single mesh with explicit warning",
        files=[DeliveredFile(filename="dragon-meshy.stl", size_bytes=900_000, kind="stl")],
        meta={
            "meshy_method": "meshy/text-to-3d repaired",
            "part_color_requests": {"wings": "black", "eyes": "red"},
            "color_limitation_warning": True,
        },
        success=True,
    )
    warned_check = await run_self_check(plan, warned)
    print(f"single mesh colors warned ok={warned_check.ok}: {warned_check.message}")
    assert warned_check.ok, warned_check.issues


async def test_meshy_fallback_passes_check() -> None:
    print("\n=== Самопроверка принимает fallback вместо тупика Meshy ===")
    msg = "Сделай 3D модель лабрадора для Bambu"
    plan = build_task_plan(msg, "gpt-5.4-mini")
    plan.kind = TaskKind.MESHY_TEXT_3D
    dr = DeliveryResult(
        summary="Articulated 3MF fallback after Meshy repair failure",
        files=[DeliveredFile(filename="labrador-fallback.3mf", size_bytes=220_000, kind="3mf")],
        meta={
            "fallback_solution": True,
            "fallback_reason": "Meshy STL still had non-manifold edges after repair.",
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"fallback self-check ok={check.ok}: {check.message}")
    assert check.ok, check.issues


async def test_print_pack_fallback_passes_check() -> None:
    print("\n=== Generic print-pack fallback не считается тупиком ===")
    msg = "Сделай сложную декоративную 3D модель неизвестного персонажа для печати"
    plan = build_task_plan("гибридный генератор проект на печать storyboard", "gpt-5.4-mini")
    plan.user_text = msg
    plan.kind = TaskKind.PRINT_PROJECT
    dr = DeliveryResult(
        summary="Инженерный print-pack v0 (fallback)",
        files=[DeliveredFile(filename="generic-print-pack-v0.zip", size_bytes=80_000, kind="zip")],
        meta={
            "parts_count": 8,
            "has_stl": True,
            "fallback_solution": True,
            "fallback_reason": "Meshy failed printable repair.",
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"print-pack fallback self-check ok={check.ok}: {check.message}")
    assert check.ok, check.issues


def test_gemini_llm_helpers() -> None:
    print("\n=== Gemini fallback helpers ===")
    from bot.services.gemini_llm import openai_messages_to_gemini
    from bot.services.llm import _should_try_gemini_fallback, LLMError

    sys_inst, contents = openai_messages_to_gemini(
        [
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте"},
            {"role": "user", "content": "Как печатать PETG?"},
        ],
        system="Ты инженер 3D-печати",
    )
    assert sys_inst and "инженер" in sys_inst["parts"][0]["text"]
    assert len(contents) == 3
    assert contents[1]["role"] == "model"
    assert _should_try_gemini_fallback(LLMError("Таймаут KupiAPI (30 сек)"))
    assert not _should_try_gemini_fallback(LLMError("API (401): invalid api key"))
    print("OK gemini message conversion + retryable detection")


def test_stl_format_not_triggered_by_bambu_alone() -> None:
    print("\n=== STL: bambu/печать ≠ авто-файл .stl ===")
    from bot.services.file_output import (
        detect_file_format,
        explicit_stl_file_requested,
        resolve_output_file_format,
    )
    from bot.services.task_plan import TaskKind, build_task_plan

    cases_no_stl = [
        "Сделай Boeing белый 20 см для Bambu P2S",
        "банан для 3d печати bambu",
        "Привет. у меня есть проект, нужна помощь по его печати и сборки",
    ]
    for msg in cases_no_stl:
        assert detect_file_format(msg) is None, msg
        assert resolve_output_file_format(msg) is None, msg
        plan = build_task_plan(msg, "gpt-5.4-mini")
        assert plan.kind != TaskKind.FILE_OUTPUT, (msg, plan.kind)

    assert explicit_stl_file_requested("пришли stl 50x50x80 мм")
    assert not explicit_stl_file_requested("Boeing для Bambu P2S")
    print("OK: bambu/3d-print requests use 3D router, not primitive STL file")


async def test_self_check_llm_timeout_is_silent() -> None:
    print("\n=== Self-check LLM timeout не отправляет пользователю шум ===")
    from bot.services import llm

    async def fail_chat_completion(*args, **kwargs):
        raise llm.LLMError("Proxy connection timed out: 15")

    old_chat_completion = llm.chat_completion
    llm.chat_completion = fail_chat_completion
    try:
        plan = build_task_plan("Привет, просто текстовый вопрос", "gpt-5.4-mini")
        dr = DeliveryResult(summary="Обычный текстовый ответ", success=True)
        check = await run_self_check(plan, dr)
    finally:
        llm.chat_completion = old_chat_completion
    print(f"self-check timeout ok={check.ok}, message={check.message!r}")
    assert check.ok
    assert check.message == ""


async def test_zero_to_print_project_pipeline() -> None:
    print("\n=== Zero-to-print CAD/kit pipeline ===")
    import json
    import zipfile
    from io import BytesIO

    import bot.services.print_project as print_project
    from bot.services.print_project import (
        build_project_zip,
        generate_project_specs,
        wants_print_project,
        zero_to_print_requested,
    )

    cases = [
        ("Сделай с нуля rugged box с защёлкой как на Printables", "rugged_box", "bottom_shell"),
        ("Сделай Star Destroyer kit-card для печати", "kit_card", "kit_card_frame"),
        ("Сделай Willys jeep как набор деталей CAD с нуля", "vehicle_kit", "body_tub"),
        ("Сделай mechanical planetarium с шестернями и тестом зацепления", "mechanical_planetarium", "gear_mesh_coupon"),
        ("Сделай DNA helix pencil holder с full/split/support вариантами", "dna_helix_holder", "helix_full"),
        ("Сделай impossible cube optical illusion чистым solid", "impossible_cube", "illusion_cube_body"),
        ("Сделай puzzle chess board с tabs slots и тестом посадки", "puzzle_chess_board", "tab_slot_coupon"),
        ("Сделай spiral chess set без supports", "spiral_chess_set", "pawn_spiral"),
        ("Сделай Greek meander lamp с базой, LED каналом и рассеивателем", "lamp_project", "lamp_shade"),
        ("Сделай Olaf MMU AMS персонажа отдельными цветными объектами без supports", "mmu_character", "body_white"),
        ("Сделай plant space rocket planter с liner и drainage", "planter_project", "inner_pot_liner"),
        ("Сделай detailed Oreo decorative box с крышкой и fit coupon", "decorative_container", "lid_fit_coupon"),
        ("Сделай low-poly heart vase в vase mode с тестом стенки", "vase_shell", "wall_coupon"),
        ("Сделай AmeraLabs SLA resin calibration town с exposure ladder", "sla_calibration", "exposure_ladder"),
        ("Сделай Easter egg variant family low-poly wavy voronoi", "variant_family", "egg_low_poly"),
        ("Сделай jewellery tree holder с split panels и устойчивой базой", "jewellery_tree", "weighted_base"),
        ("Сделай Deadpool bust как hollow collectible с display base", "character_bust", "hollow_support_coupon"),
        ("Сделай Halloween Stitch character kit с cape hands pumpkin и split parts", "accessory_character_kit", "prop_accessory"),
        ("Сделай Baby Yoda Grogu paintable miniature pack с eyes hands nails", "paintable_miniature_pack", "eyes_color_parts"),
        ("Сделай collectible character kit с full preview keyed torso head ears hands", "split_collectible_character", "pin_fit_coupon"),
        ("Сделай Starter Plant Grower seed starter kit с drainage и humidity dome", "seed_starter_kit", "cell_tray"),
        ("Сделай Key Holder wall fixing system с screw clearance и load test", "wall_mount_system", "screw_clearance_coupon"),
        ("Сделай Ender 3 V2 Tool Holder под профиль принтера и hex keys", "printer_tool_holder", "rail_fit_coupon"),
        ("Сделай stackable crate modular storage system и screw box modules", "modular_storage_system", "stacking_coupon"),
        ("Сделай Pegstr pegboard wizard ecosystem с hook box caliper flashlight modules", "pegboard_ecosystem", "peg_spacing_coupon"),
        ("Сделай EGG ROLL BASKET perforated basket с rib strength coupon", "perforated_basket", "rib_strength_coupon"),
        ("Сделай Charizard Pokemon winged creature statue split wings tail base", "winged_creature_statue", "support_scar_coupon"),
        (
            "Сделай механический кит Boeing: лопасти крутящиеся, шосси убираются, "
            "колеса вращаются на оси",
            "mechanical_boeing_airliner",
            "hinge_fit_coupon",
        ),
    ]
    min_parts = {
        "impossible_cube": 2,
        "lamp_project": 3,
        "vase_shell": 2,
        "decorative_container": 3,
        "sla_calibration": 3,
        "character_bust": 4,
        "perforated_basket": 4,
        "mechanical_boeing_airliner": 22,
    }
    for text, kind, part_id in cases:
        assert zero_to_print_requested(text), text
        assert wants_print_project(text), text
        plan = build_task_plan(text, "gpt-5.4-mini")
        expected_plan_kind = TaskKind.MECHANICAL_PROJECT if kind == "mechanical_boeing_airliner" else TaskKind.PRINT_PROJECT
        assert plan.kind == expected_plan_kind, plan
        specs = await generate_project_specs(text, text, "gpt-5.4-mini")
        assert specs.get("project_kind") == kind, specs
        assert specs.get("print_prep_contract", {}).get("manifold_solid_required"), specs
        assert any(p.get("id") == part_id for p in specs.get("parts", [])), specs.get("parts")
        if kind == "mechanical_boeing_airliner":
            from bot.services.print_project import validate_mechanical_boeing_specs

            assert specs.get("assembly_version") == "v3", specs
            assert len(specs.get("kinematics") or []) >= 8, specs
            assert not validate_mechanical_boeing_specs(specs), validate_mechanical_boeing_specs(specs)
            templates = {p.get("template") for p in specs.get("parts", [])}
            assert {
                "airliner_fuselage_section",
                "airliner_wing_half",
                "airliner_engine_pod_single",
                "airliner_fan_rotor_single",
                "airliner_vert_stab",
                "airliner_horz_stab_half",
                "airliner_gear_strut",
                "airliner_wheel_revolute",
                "airliner_wheel_fit_coupon",
            }.issubset(templates), templates
            fit_ids = {p.get("id") for p in specs.get("parts", []) if p.get("frame_number", 99) <= 3}
            assert {"hinge_fit_coupon", "wheel_fit_coupon", "fan_blade_coupon"}.issubset(fit_ids), fit_ids
        old_openscad_available = print_project.openscad_available
        print_project.openscad_available = lambda: False
        try:
            data, fname, _caption, n_parts, _has_stl, _ordered = await build_project_zip(
                specs,
                {"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4},
            )
        finally:
            print_project.openscad_available = old_openscad_available
        assert fname.endswith("-print-pack.zip"), fname
        assert n_parts >= min_parts.get(kind, 4), (kind, n_parts)
        with zipfile.ZipFile(BytesIO(data), "r") as zf:
            names = set(zf.namelist())
            assert "engineering/print_prep_contract.json" in names, names
            if kind == "mechanical_boeing_airliner":
                assert "engineering/kinematics.json" in names, names
                assert "engineering/kinematics.md" in names, names
                assert "engineering/fit_first_print_order.txt" in names, names
                kin = json.loads(zf.read("engineering/kinematics.json"))
                assert len(kin.get("joints") or []) >= 8, kin
            contract = json.loads(zf.read("engineering/print_prep_contract.json"))
            assert contract["manifold_solid_required"] is True
            assert any(name.startswith("scad/") for name in names), names
        dr = DeliveryResult(
            summary=f"Zero-to-print {kind}",
            files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="zip")],
            meta={
                "parts_count": n_parts,
                "has_stl": _has_stl,
                "project_kind": specs.get("project_kind"),
                "strategy": specs.get("strategy"),
                "min_wall_mm": specs.get("min_wall_mm"),
                "print_prep_contract": specs.get("print_prep_contract"),
                "zero_to_print": True,
                "assembly_version": specs.get("assembly_version"),
                "kinematics_joints": len(specs.get("kinematics") or []),
                "fit_coupon_ids": specs.get("fit_first_coupon_ids") or [],
                "part_templates": [p.get("template") for p in specs.get("parts", [])],
                "part_ids": [p.get("id") for p in specs.get("parts", [])],
            },
            success=True,
        )
        check = await run_self_check(plan, dr)
        print(f"{kind}: parts={n_parts}, zip={len(data)//1024} KB, check={check.ok}")
        assert check.ok, check.issues


def test_mechanical_boeing_assembly_preview() -> None:
    print("\n=== Mechanical Boeing assembly preview STL ===")
    import trimesh
    from bot.services.assembly_preview import build_mechanical_boeing_previews
    from bot.services.print_project import _mechanical_boeing_airliner_specs

    specs = _mechanical_boeing_airliner_specs(
        "Boeing 20 см, шасси, лопасти, колёса на оси"
    )
    box = trimesh.creation.box([18.0, 10.0, 6.0])
    stl = box.export(file_type="stl")
    entries = []
    for part in specs["parts"]:
        fn = int(part.get("frame_number") or len(entries) + 1)
        pid = part["id"]
        entries.append((fn, stl, f"{fn:02d}-{pid}", part.get("name") or pid, ""))
    previews = build_mechanical_boeing_previews(entries, specs)
    # Pose is always present: either semantic (real STLs) or NACA reference
    assert "preview/assembly_pose.stl" in previews, list(previews)
    assert len(previews["preview/assembly_pose.stl"]) > 10_000, \
        f"pose STL suspiciously small: {len(previews['preview/assembly_pose.stl'])} bytes"
    # Parts layout replaces old assembly_exploded.stl
    layout_key = "preview/parts_layout_print_orientation.stl"
    if layout_key in previews:
        layout_kb = len(previews[layout_key]) // 1024
    else:
        layout_kb = 0
    pose_kb = len(previews["preview/assembly_pose.stl"]) // 1024
    print(f"OK preview pose={pose_kb} KB parts_layout={layout_kb} KB")


def test_3d_zip_inventory_audit() -> None:
    print("\n=== ZIP-аудит 3D архива ===")
    import io
    import zipfile

    import trimesh
    from bot.handlers.files import _zip_3d_inventory

    mesh = trimesh.creation.box(extents=[20, 10, 5])
    stl = mesh.export(file_type="stl")
    if isinstance(stl, str):
        stl = stl.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", "Print in PLA, no supports required. Assembly after print.")
        zf.writestr("files/test_part.stl", stl)
        zf.writestr("files/broken.stl", b"not a valid stl")
        zf.writestr("files/source.step", "ISO-10303-21;")
    inv = _zip_3d_inventory(buf.getvalue())
    assert inv["model_files_count"] == 3, inv
    assert inv["stl_count"] == 2, inv
    assert inv["metrics"] and inv["metrics"][0]["watertight"] is True, inv["metrics"]
    assert len(inv["metrics"]) == 2, inv["metrics"]
    assert any("error" in m for m in inv["metrics"]), inv["metrics"]
    assert inv["readme_snippets"], inv
    print(f"OK zip audit: {inv['extensions']}, metrics={inv['metrics'][0]}")


def test_labrador_prompt() -> None:
    print("\n=== Промпт лабрадор (статичный) ===")
    msg = CASES[8][0]
    prompt = meshy_prompt_from_text(msg)
    fn = meshy_export_filename(msg)
    assert "labrador" in prompt.lower(), prompt
    assert fn == "labrador-figurine-meshy.stl", fn
    print(f"OK prompt: {prompt[:90]}…")
    print(f"OK file: {fn}")
    assert meshy_export_filename("Самолет боинг белый", ext="stl") == "boeing-airliner-meshy.stl"

    print("\n=== Маршрут articulated ===")
    art_msg = CASES[2][0]
    plan = build_task_plan(art_msg, "gpt-5.4-mini")
    assert plan.kind == TaskKind.ARTICULATED_3MF, plan.kind
    print(f"OK kind: {plan.kind.value}")


async def test_boeing_not_zip_project() -> None:
    print("\n=== Boeing → чёткий NACA CAD (не глина Meshy, не примитивы) ===")
    # Max-detail airplane → crisp procedural NACA airliner (high_detail), since
    # text-to-3D AI produces "clay" on hard-surface aircraft.
    max_msg = CASES[9][0]
    max_plan = build_task_plan(max_msg, "gpt-5.4-mini")
    assert max_plan.kind == TaskKind.AIRPLANE_3MF, max_plan.kind
    assert (max_plan.extra or {}).get("high_detail"), max_plan.extra

    test3_plan = build_task_plan("тест 3", "gpt-5.4-mini")
    assert test3_plan.kind == TaskKind.CHAT, test3_plan
    assert not test3_plan.extra.get("temporary_shortcut")

    # Criticism wording ("каша", "тонкие элементы", "v3") → still the crisp NACA
    # CAD airliner, never primitive cones and never Meshy clay.
    v3_plan = build_task_plan(
        "Boeing после критики: нейросетевая каша, тонкие элементы, сделай print-ready CAD-like v3",
        "gpt-5.4-mini",
    )
    assert v3_plan.kind == TaskKind.AIRPLANE_3MF, v3_plan.kind
    assert (v3_plan.extra or {}).get("high_detail"), v3_plan.extra

    # Explicit "процедурный … без референса" stays AIRPLANE_3MF deterministic 3MF.
    msg = CASES[10][0]
    plan = build_task_plan(msg, "gpt-5.4-mini")
    assert plan.kind == TaskKind.AIRPLANE_3MF, plan.kind
    prompt = meshy_prompt_from_text(msg)
    assert "boeing" in prompt.lower() and "airliner" in prompt.lower(), prompt
    assert "sitting pose" not in prompt.lower(), prompt

    import numpy as np
    from bot.services.airplane_3mf import (
        AIRLINER_HD_PARTS,
        AIRLINER_PRINT_TUNED_EXTRA_PARTS,
        AIRPLANE_PARTS,
        _make_parts,
        _scale_from_text,
        airplane_print_tuned_requested,
        build_airliner_hd_3mf,
        build_airliner_print_tuned_3mf,
        build_airplane_3mf,
    )

    data, fname, parts, desc = await build_airplane_3mf(
        "Самолет боенг белого цвета длина 15 см высота 5 см 50гр",
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
    )
    colored_data, _, _, _ = await build_airplane_3mf(
        "Белый Boeing, двигатели красные, окна чёрные, хвост красный, длина 15 см",
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
    )
    named = _make_parts(_scale_from_text("Самолет боенг белого цвета длина 15 см высота 5 см 50гр"))
    mins = np.array([mesh.bounds[0] for _, mesh in named]).min(axis=0)
    maxs = np.array([mesh.bounds[1] for _, mesh in named]).max(axis=0)
    size = maxs - mins
    assert 140 <= size[0] <= 160, size
    assert 42 <= size[2] <= 55, size
    tail_cone = next(mesh for name, mesh in named if name == "tail_cone")
    assert tail_cone.bounds[0][0] < -70, tail_cone.bounds
    assert "clumping" in desc.lower(), desc
    assert fname.endswith(".3mf"), fname
    assert len(data) > 12_000, len(data)
    assert "собран" in desc.lower(), desc

    import json
    import zipfile
    from io import BytesIO
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(BytesIO(colored_data), "r") as zf:
        project_settings = json.loads(zf.read("Metadata/project_settings.config"))
        model_settings = zf.read("Metadata/model_settings.config")
    colors = project_settings["filament_colour"]
    assert "#FFFFFFFF" in colors, colors
    assert "#C12E1FFF" in colors, colors
    assert "#161616FF" in colors, colors
    root = ET.fromstring(model_settings)
    extruders_by_name = {}
    for obj in root.findall("object"):
        name = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "name"), "")
        ext = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "extruder"), "")
        extruders_by_name[name] = int(ext)
    assert colors[extruders_by_name["airframe_white"] - 1] == "#FFFFFFFF", extruders_by_name
    assert colors[extruders_by_name["engines"] - 1] == "#C12E1FFF", extruders_by_name
    assert colors[extruders_by_name["tail_red"] - 1] == "#C12E1FFF", extruders_by_name
    assert colors[extruders_by_name["windows_black"] - 1] == "#161616FF", extruders_by_name

    for need in AIRPLANE_PARTS:
        assert need in parts, (need, parts)
    good = DeliveryResult(
        summary=f"Airplane procedural 3MF ({len(parts)} parts)",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={"parts": parts, "procedural": True, "assembled": True, "kind": "airplane"},
        success=True,
    )
    good_check = await run_self_check(plan, good)
    print(f"airplane self-check ok={good_check.ok}: {good_check.message}")
    assert good_check.ok, good_check.issues

    hd_msg = (
        "Мне нужен 3д проект для Bambu Lab P2S. Самолет Boeing белый, "
        "максимальная детализация, двигатели чёрные, хвост красный, AMS Pro, длина 15 см."
    )
    hd_data, hd_fname, hd_parts, hd_desc, hd_dims = await build_airliner_hd_3mf(
        hd_msg,
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
    )
    assert hd_fname == "boeing-airliner-hd-bambu.3mf", hd_fname
    assert len(hd_data) > len(data), (len(hd_data), len(data))
    assert "high-detail" in hd_desc.lower(), hd_desc
    assert 120 <= hd_dims["length_mm"] <= 175, hd_dims
    assert hd_dims["wingspan_mm"] >= 95, hd_dims
    assert hd_dims["height_mm"] >= 35, hd_dims
    for need in AIRLINER_HD_PARTS:
        assert need in hd_parts, (need, hd_parts)
    with zipfile.ZipFile(BytesIO(hd_data), "r") as zf:
        hd_project_settings = json.loads(zf.read("Metadata/project_settings.config"))
        hd_model_settings = zf.read("Metadata/model_settings.config")
    hd_colors = hd_project_settings["filament_colour"]
    hd_root = ET.fromstring(hd_model_settings)
    hd_extruders_by_name = {}
    for obj in hd_root.findall("object"):
        name = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "name"), "")
        ext = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "extruder"), "")
        hd_extruders_by_name[name] = int(ext)
    assert colors[extruders_by_name["airframe_white"] - 1] == "#FFFFFFFF", extruders_by_name
    assert hd_colors[hd_extruders_by_name["airframe_white"] - 1] == "#FFFFFFFF", hd_extruders_by_name
    assert hd_colors[hd_extruders_by_name["engines_black"] - 1] == "#161616FF", hd_extruders_by_name
    assert hd_colors[hd_extruders_by_name["tail_red"] - 1] == "#C12E1FFF", hd_extruders_by_name
    hd_good = DeliveryResult(
        summary=f"Airplane HD procedural 3MF ({len(hd_parts)} parts)",
        files=[DeliveredFile(filename=hd_fname, size_bytes=len(hd_data), kind="3mf")],
        meta={
            "parts": hd_parts,
            "procedural": True,
            "assembled": True,
            "high_detail": True,
            "dimensions": hd_dims,
            "object_level_colors": True,
            "kind": "airplane",
        },
        success=True,
    )
    hd_check = await run_self_check(plan, hd_good)
    print(f"airliner HD self-check ok={hd_check.ok}: {hd_check.message}")
    assert hd_check.ok, hd_check.issues

    tuned_msg = (
        "После печати улучши Boeing v2 для Bambu Lab P2S: supports были грубые, "
        "двигатели и пилоны хрупкие, длина 15 см, AMS Pro."
    )
    assert airplane_print_tuned_requested(tuned_msg)
    assert not airplane_print_tuned_requested("Белый Boeing, двигатели чёрные, хвост красный, длина 15 см")
    assert not airplane_print_tuned_requested("Сделай процедурный v2 самолёт боинг без референса для Bambu")
    # "после печати улучши… supports грубые… хрупкие" is criticism → crisp NACA
    # CAD airliner (high_detail), never primitive cones, never Meshy clay.
    tuned_plan = build_task_plan(tuned_msg, "gpt-5.4-mini")
    assert tuned_plan.kind == TaskKind.AIRPLANE_3MF, tuned_plan.kind
    assert (tuned_plan.extra or {}).get("high_detail"), tuned_plan.extra
    # The procedural print-tuned generator still works as an explicit builder:
    tuned_data, tuned_fname, tuned_parts, tuned_desc, tuned_dims = await build_airliner_print_tuned_3mf(
        tuned_msg,
        profile={"printer": "Bambu Lab P2S", "material": "PLA", "nozzle_mm": 0.4, "ams": True},
    )
    assert tuned_fname == "boeing-airliner-print-ready-v3.3mf", tuned_fname
    assert len(tuned_data) > len(hd_data), (len(tuned_data), len(hd_data))
    assert "print-ready boeing v3" in tuned_desc.lower() and "breakaway" in tuned_desc.lower(), tuned_desc
    assert "polygon mush" in tuned_desc.lower(), tuned_desc
    for need in [*AIRLINER_HD_PARTS, *AIRLINER_PRINT_TUNED_EXTRA_PARTS]:
        assert need in tuned_parts, (need, tuned_parts)
    assert 135 <= tuned_dims["length_mm"] <= 165, tuned_dims
    assert tuned_dims["wingspan_mm"] >= hd_dims["wingspan_mm"], (tuned_dims, hd_dims)
    with zipfile.ZipFile(BytesIO(tuned_data), "r") as zf:
        tuned_project_settings = json.loads(zf.read("Metadata/project_settings.config"))
        tuned_model_settings = zf.read("Metadata/model_settings.config")
    assert tuned_project_settings["enable_support"] == "0", tuned_project_settings
    assert tuned_project_settings["support_type"] == "normal(auto)", tuned_project_settings
    tuned_root = ET.fromstring(tuned_model_settings)
    tuned_names = {
        next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "name"), "")
        for obj in tuned_root.findall("object")
    }
    assert "major_breakaway_supports" in tuned_names, tuned_names
    assert "minor_detail_supports" in tuned_names, tuned_names
    assert "micro_contact_supports" in tuned_names, tuned_names
    assert "engine_intake_lips_gray" in tuned_names, tuned_names
    assert "engine_fans_printable_black" in tuned_names, tuned_names
    assert "windows_black_individual" in tuned_names, tuned_names
    tuned_good = DeliveryResult(
        summary=f"Airplane print-tuned procedural 3MF ({len(tuned_parts)} parts)",
        files=[DeliveredFile(filename=tuned_fname, size_bytes=len(tuned_data), kind="3mf")],
        meta={
            "parts": tuned_parts,
            "procedural": True,
            "assembled": True,
            "high_detail": True,
            "print_tuned": True,
            "print_ready_v3": True,
            "support_strategy": "adaptive_major_minor_micro",
            "min_feature_mm": 0.4,
            "dimensions": tuned_dims,
            "object_level_colors": True,
            "kind": "airplane",
        },
        success=True,
    )
    # tuned_good is a procedural 3MF delivery, so validate it against a
    # procedural airplane plan (the explicit fallback route), not the realistic
    # Meshy plan that the criticism text now produces.
    proc_plan = build_task_plan(
        "Сделай процедурный самолёт боинг без референса для Bambu Studio, 50гр AMS Pro",
        "gpt-5.4-mini",
    )
    assert proc_plan.kind == TaskKind.AIRPLANE_3MF, proc_plan.kind
    tuned_check = await run_self_check(proc_plan, tuned_good)
    print(
        "print-tuned diff: "
        f"old=single Meshy STL/no named objects; hd={len(hd_parts)} parts/{len(hd_data)//1024} KB; "
        f"v2={len(tuned_parts)} parts/{len(tuned_data)//1024} KB, auto_support={tuned_project_settings['enable_support']}"
    )
    assert tuned_check.ok, tuned_check.issues

    loose = DeliveryResult(
        summary="Airplane procedural 3MF as loose parts",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={"parts": parts, "procedural": True, "kind": "airplane"},
        success=True,
    )
    loose_check = await run_self_check(plan, loose)
    assert not loose_check.ok, "loose airplane parts should fail self-check"

    bad = DeliveryResult(
        summary="Отправлен проект на печать (8 дет., ZIP).",
        files=[DeliveredFile(filename="boeing_airliner_p2s_v0-print-pack.zip", size_bytes=80_000, kind="zip")],
        meta={"parts_count": 8, "has_stl": True},
        success=True,
    )
    bad_plan = build_task_plan("гибридный генератор проект на печать storyboard", "gpt-5.4-mini")
    bad_plan.user_text = msg
    bad_plan.kind = TaskKind.PRINT_PROJECT
    check = await run_self_check(bad_plan, bad)
    print(f"self-check ok={check.ok}: {check.issues}")
    assert not check.ok, "Boeing ZIP primitives should fail self-check"


async def test_articulated_subject_guard() -> None:
    print("\n=== Самопроверка ловит подмену ангела собакой ===")
    msg = CASES[3][0]
    plan = build_task_plan(msg, "gpt-5.4-mini")
    assert plan.kind == TaskKind.ARTICULATED_3MF, plan.kind
    dr = DeliveryResult(
        summary="Articulated 3MF (9 parts)",
        files=[DeliveredFile(filename="angel-articulated.3mf", size_bytes=220_000, kind="3mf")],
        meta={
            "parts": [
                "body",
                "head",
                "leg_front_left",
                "leg_front_right",
                "leg_back_left",
                "leg_back_right",
                "tail",
                "eye_left",
                "eye_right",
            ],
            "kind": "quadruped",
            "subject": "ангел",
        },
        success=True,
    )
    check = await run_self_check(plan, dr)
    print(f"self-check ok={check.ok}: {check.issues}")
    assert not check.ok, "dog parts for angel should fail self-check"

    print("\n=== Ангел имеет крылья, без лап и хвоста ===")
    from bot.services.articulated_3mf import (
        expected_part_names_for_text,
        forbidden_part_names_for_text,
        openscad_articulated_kind,
    )

    assert openscad_articulated_kind(msg) == "angel"
    expected = expected_part_names_for_text(msg)
    forbidden = forbidden_part_names_for_text(msg)
    assert "wing_left" in expected and "wing_right" in expected, expected
    assert "tail" in forbidden and "leg_front_left" in forbidden, forbidden
    print(f"OK expected: {expected}")

    print("\n=== Процедурные шаблоны для новых предметов ===")
    from bot.services.articulated_3mf import openscad_articulated_kind

    assert openscad_articulated_kind(CASES[4][0]) == "dragon"
    assert openscad_articulated_kind(CASES[5][0]) == "bat"
    assert openscad_articulated_kind(CASES[6][0]) == "cheburashka"
    assert openscad_articulated_kind(CASES[7][0]) == "generic_winged"
    for idx, kind in ((4, "dragon"), (5, "bat"), (6, "cheburashka"), (7, "generic_winged")):
        plan = build_task_plan(CASES[idx][0], "gpt-5.4-mini")
        assert plan.kind == TaskKind.ARTICULATED_3MF, (idx, plan.kind)
        assert kind in plan.label.lower() or "процедур" in plan.label.lower(), plan.label
    print("OK: dragon/bat/cheburashka/generic route to procedural 3MF")


def test_reset_clears_pending_concept() -> None:
    print("\n=== Reset должен чистить pending concept ===")
    from bot.services.pending_3d import (
        PendingConcept3DJob,
        clear_pending,
        clear_pending_concept,
        get_pending_concept,
        set_pending_concept,
    )

    user_id = 999_001
    set_pending_concept(
        user_id,
        PendingConcept3DJob(
            image_bytes=b"fake",
            mime="image/png",
            prompt="old Boeing concept",
            original_text="Белый Boeing",
            subject="boeing_airliner",
        ),
    )
    assert get_pending_concept(user_id) is not None
    clear_pending(user_id)
    clear_pending_concept(user_id)
    assert get_pending_concept(user_id) is None
    print("OK reset clears pending concept")


async def test_pending_concept_persists_in_db() -> None:
    print("\n=== Pending concept сохраняется в DB после перезапуска ===")
    from bot.services import history

    user_id = 999_002
    await history.init_db()
    await history.clear_pending_concept(user_id)
    await history.save_pending_concept(
        user_id,
        image_bytes=b"fake-image-bytes",
        mime="image/png",
        prompt="fresh Boeing concept prompt",
        original_text="Белый Boeing 15 см максимальная детализация",
        subject="boeing_airliner",
    )
    stored = await history.get_pending_concept(user_id)
    assert stored is not None
    assert stored["image_bytes"] == b"fake-image-bytes"
    assert stored["subject"] == "boeing_airliner"
    await history.clear_pending_concept(user_id)
    assert await history.get_pending_concept(user_id) is None
    print("OK pending concept db persistence")


def test_object_name_colors_drive_ams_slots() -> None:
    print("\n=== Цвета из имён деталей назначаются в AMS ===")
    from bot.services.articulated_3mf import _COLOR_HEX, _object_extruder_map

    colors = []
    objects = [
        {"id": "1", "name": "Fig_Ddpl_Arm_01_Black"},
        {"id": "2", "name": "Fig_Ddpl_Head_04_White"},
        {"id": "3", "name": "Fig_Ddpl_Hand_02_Red"},
        {"id": "4", "name": "Blade_Grey"},
        {"id": "5", "name": "tail_red"},
        {"id": "6", "name": "wing_left"},
        {"id": "7", "name": "eye_left"},
    ]
    mapping = _object_extruder_map(
        objects,
        "самолёт Boeing, хвост красный, крылья чёрные, глаза красные",
        colors,
    )
    assert colors[mapping["1"] - 1] == _COLOR_HEX["black"], (mapping, colors)
    assert colors[mapping["2"] - 1] == _COLOR_HEX["white"], (mapping, colors)
    assert colors[mapping["3"] - 1] == _COLOR_HEX["red"], (mapping, colors)
    assert colors[mapping["4"] - 1] == _COLOR_HEX["gray"], (mapping, colors)
    assert colors[mapping["5"] - 1] == _COLOR_HEX["red"], (mapping, colors)
    assert colors[mapping["6"] - 1] == _COLOR_HEX["black"], (mapping, colors)
    assert colors[mapping["7"] - 1] == _COLOR_HEX["red"], (mapping, colors)
    print("OK object-name colors:", mapping)


def test_meshy_level3_mood_board_and_split() -> None:
    from bot.services.meshy_level3 import build_meshy_level3_plan
    from bot.services.meshy_reference_split import split_stl_by_blueprint
    from bot.services.reference_geometry import build_geometry_profile
    from bot.services.reference_render import render_mood_board_png
    from bot.services.stl_postprocess import _write_binary_stl
    import numpy as np

    slug = "airplane_gzumwalt_tudwzl"
    png = render_mood_board_png(slug)
    assert png and len(png) > 500, len(png or b"")

    plan = build_meshy_level3_plan(
        "Сделай детальный RC самолёт как скачанный kit, разбей на части для Bambu"
    )
    assert plan.enabled and plan.slug == slug
    assert plan.use_image_to_3d or plan.apply_split

    prof = build_geometry_profile(slug)
    assert prof and prof.get("part_count", 0) >= 3
    # synthetic box mesh
    tris = np.array(
        [
            [[0, 0, 0], [50, 0, 0], [0, 30, 0]],
            [[50, 0, 0], [50, 30, 0], [0, 30, 0]],
        ],
        dtype=np.float64,
    )
    stl = _write_binary_stl(tris)
    parts = split_stl_by_blueprint(stl, prof, min_faces=1)
    assert len(parts) >= 1
    print("OK meshy level3:", plan.use_image_to_3d, plan.apply_split, "split parts", len(parts))


def test_reference_geometry_level2() -> None:
    from bot.services.reference_geometry import build_geometry_profile, try_build_specs_from_reference
    from bot.services.reference_library import llm_reference_context, meshy_style_fragment
    from bot.services.print_project import zero_to_print_specs

    slug = "airplane_gzumwalt_tudwzl"
    prof = build_geometry_profile(slug)
    assert prof and prof.get("part_count", 0) >= 3, prof
    assert any(p.get("role") == "wing" for p in prof.get("parts") or []), prof.get("roles_present")

    specs = zero_to_print_specs("Сделай RC самолёт Extra 300 как скачанный kit для Bambu")
    assert specs and specs.get("project_kind") in {
        "rc_aircraft_kit",
        "reference_guided_kit",
    }, specs.get("project_kind")
    if specs.get("reference_blueprint"):
        assert len(specs.get("parts") or []) >= 3
        assert specs["parts"][0].get("reference_source")

    ctx = llm_reference_context("FPV дрон 5 дюймов карбон")
    assert "REFERENCE KIT" in ctx or len(ctx) == 0

    frag = meshy_style_fragment("самолёт RC gzumwalt aviation")
    assert frag and len(frag) > 20

    built = try_build_specs_from_reference(
        "дрон",
        slug=slug,
        project_kind="rc_aircraft_kit",
        strategy="test",
        project_name="test",
        requirements=["test"],
    )
    assert built and len(built.get("parts") or []) >= 3
    print("OK reference geometry level2:", prof.get("part_count"), "parts from", slug)


def test_mesh_engineering_physics() -> None:
    """Validate the engineering physics layer against closed-form solutions."""
    import math

    import trimesh

    from bot.services import mesh_engineering as ME

    print("\n=== Инженерная физика: масс-инерция, устойчивость, нависания ===")

    # 1) Solid box: volume, mass, inertia must match analytic formulas.
    box = trimesh.creation.box(extents=[20, 40, 60])
    mp = ME.mass_properties(box, "pla")
    assert abs(mp.volume_mm3 - 48000.0) < 1.0, mp.volume_mm3
    assert abs(mp.mass_g - 59.52) < 0.05, mp.mass_g          # 48 cm³ × 1.24
    m = mp.mass_g
    expect = sorted([
        m / 12 * (40**2 + 60**2),
        m / 12 * (20**2 + 60**2),
        m / 12 * (20**2 + 40**2),
    ])
    got = sorted(mp.principal_moments_g_mm2)
    for a, b in zip(expect, got):
        assert abs(a - b) / a < 0.02, (a, b)
    assert abs(mp.solidity - 1.0) < 0.01 and mp.is_watertight

    # 2) Upright cylinder: CoM at half height, stable, no overhang (cap on bed).
    cyl = trimesh.creation.cylinder(radius=10, height=50, sections=64)
    cyl.apply_translation([0, 0, -cyl.bounds[0][2]])
    st = ME.stability(cyl)
    assert abs(st.com_height_mm - 25.0) < 0.5, st.com_height_mm
    assert st.com_inside_base and st.verdict == "stable", st
    ov = ME.overhangs(cyl)
    assert ov.overhang_fraction < 0.02, ov.overhang_fraction

    # 3) Tall thin cylinder must be flagged tippy.
    tall = trimesh.creation.cylinder(radius=3, height=120, sections=48)
    tall.apply_translation([0, 0, -tall.bounds[0][2]])
    st2 = ME.stability(tall)
    assert st2.verdict in ("tippy", "unstable"), st2.verdict
    assert st2.topple_angle_deg < 10.0, st2.topple_angle_deg

    # 4) Sphere: ~14.6% of area is a sub-45° overhang cap; thickness≈diameter.
    sph = trimesh.creation.icosphere(subdivisions=3, radius=15)
    sph.apply_translation([0, 0, -sph.bounds[0][2]])
    ov3 = ME.overhangs(sph)
    assert 0.10 < ov3.overhang_fraction < 0.20, ov3.overhang_fraction
    th = ME.wall_thickness(sph, min_wall_mm=1.2)
    assert th is not None and abs(th.median_thickness_mm - 30.0) < 2.0, th

    # 5) Orientation optimiser: an oversized barrel must NOT be printed upright.
    long_box = trimesh.creation.box(extents=[400, 30, 30])
    best, cands = ME.best_orientation(long_box)
    assert best is not None
    assert best.height_mm <= 60.0, best.height_mm   # laid down, not 400 tall

    # 6) Full report + kit report smoke.
    rep = ME.analyze_mesh(box, material="petg")
    txt = ME.format_report_text(rep, "тест-куб")
    assert "Инженерный анализ" in txt and "масса" in txt
    kit = ME.kit_engineering_report([("box", box), ("cyl", cyl)], material="pla")
    assert "ИНЖЕНЕРНЫЙ ОТЧЁТ" in kit and "Расчётная масса" in kit

    # 7) Hydraulic kit ZIP must now embed the engineering report.
    import tempfile
    import zipfile

    from bot.services.hydraulic_cylinder_geometry import export_kit_zip

    zp = tempfile.mktemp(suffix=".zip")
    export_kit_zip(zp)
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        assert "engineering_report.txt" in names, names
        body = zf.read("engineering_report.txt").decode("utf-8")
        assert "масса" in body.lower()

    print("OK physics: box inertia exact, stability/overhang/thickness/orientation, "
          "kit report embedded")


def test_autofix_and_fea() -> None:
    """B: closed-loop auto-fix (orient/split/gate). C: FEA-lite beam check."""
    import trimesh

    from bot.services import mesh_engineering as ME

    print("\n=== B+C: автопочинка (ориентация/разрезка/гейт) + FEA-lite ===")

    # Split: a 400 mm bar must become bed-sized watertight pieces.
    bar = trimesh.creation.box(extents=[400, 120, 120])
    pieces = ME.split_oversized(bar, bed_mm=(256, 256, 256))
    assert len(pieces) >= 2, len(pieces)
    assert all(p.is_watertight for p in pieces), "split pieces must be solid"
    assert all(float(p.extents[0]) <= 256 for p in pieces), "pieces must fit bed"

    # Gate must BLOCK an oversized bar and PASS a small cube.
    rep_big = ME.analyze_mesh(bar, material="petg", bed_mm=(256, 256, 256))
    gate_big = ME.printability_gate(rep_big, bed_mm=(256, 256, 256))
    assert gate_big.severity == "block" and not gate_big.passed, gate_big.summary()

    cube = trimesh.creation.box(extents=[30, 30, 30])
    rep_small = ME.analyze_mesh(cube, material="petg")
    gate_small = ME.printability_gate(rep_small)
    assert gate_small.passed, gate_small.summary()

    # auto_prepare on an oversized bar must split AND report the action.
    res = ME.auto_prepare(bar, name="балка", material="petg",
                          bed_mm=(256, 256, 256))
    assert len(res.parts) >= 2, [n for n, _ in res.parts]
    assert any("разрезка" in a for a in res.actions), res.actions

    # FEA-lite: a flimsy PETG shelf (3 mm thick, 80 mm arm) must FAIL under 10 kg,
    # and stress/deflection must follow the closed-form beam formulas.
    fea = ME.beam_cantilever_fea(arm_mm=80, load_N=10 * ME.GRAVITY,
                                 section_w_mm=40, section_h_mm=3,
                                 material="petg")
    S = 40 * 3 ** 2 / 6.0
    I = 40 * 3 ** 3 / 12.0
    sigma_expected = (10 * ME.GRAVITY * 80) / S
    assert abs(fea.max_stress_mpa - sigma_expected) / sigma_expected < 1e-6, fea
    assert abs(fea.section_modulus_mm3 - S) < 1e-6
    assert abs(fea.area_moment_mm4 - I) < 1e-6
    assert fea.verdict == "fail", fea.verdict        # 3 mm shelf can't hold 10 kg

    # A thick PLA block must comfortably hold the same load.
    fea_ok = ME.beam_cantilever_fea(arm_mm=40, load_N=10 * ME.GRAVITY,
                                    section_w_mm=40, section_h_mm=20,
                                    material="pla")
    assert fea_ok.verdict == "ok" and fea_ok.safety_factor > 2.0, fea_ok

    # Load-capacity ballpark is monotone in solidity.
    mp_solid = ME.mass_properties(cube, "pla")
    cap = ME.safe_cantilever_load_kg(mp_solid, "pla")
    assert cap > 0.0, cap

    print("OK autofix+FEA: split watertight & bed-fit, gate block/pass, "
          f"beam σ exact, shelf fails / block ok (cap≈{cap:.1f}kg)")


def test_cad_kernel_kit() -> None:
    """A: real B-rep CAD kit via the out-of-process OCCT kernel."""
    import tempfile
    import zipfile

    from bot.services import cad_kernel as CK

    print("\n=== A: CAD-кернел (OpenCASCADE) — кронштейн с фаской+counterbore ===")
    if not CK.available():
        print("SKIP: CadQuery/OCP не установлен")
        return

    zp = tempfile.mktemp(suffix=".zip")
    specs = [{"name": "angle_bracket", "generator": "mounting_bracket",
              "params": {"arm_a": 70, "arm_b": 55, "width": 40,
                         "thickness": 5, "fillet": 6}}]
    res = CK.build_kit_zip_safe(zp, specs, material="petg", timeout=150,
                                attempts=3)
    assert res.get("ok"), f"CAD kit build failed: {res.get('error')}"
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        assert any(n.endswith(".stl") and n.startswith("parts/") for n in names), names
        assert any(n.endswith(".step") for n in names), names
        assert "engineering_report.txt" in names, names
        body = zf.read("engineering_report.txt").decode("utf-8")
        assert "Printability gate" in body, "gate must be in CAD report"
        assert "Несущая способность" in body, "FEA load must be in CAD report"
    # The bracket must be a real solid with many faces (fillet/gusset/cbore).
    counts = res.get("counts", {})
    assert any(v > 200 for v in counts.values()), counts
    print(f"OK CAD kit: STL+STEP+отчёт, грани={counts}, attempts={res.get('attempts')}")


async def test_hybrid_full_pack() -> None:
    import zipfile
    from io import BytesIO

    from bot.services.hybrid_consultation import (
        build_consultation_messages,
        build_hybrid_presentation_pdf,
        build_v1_step_by_step,
        build_v2_step_by_step,
    )
    from bot.services.hybrid_generator import (
        build_hybrid_generator_print_pack,
        hybrid_generator_parts,
        hybrid_generator_v2_parts,
    )

    msgs = build_consultation_messages(None)
    assert len(msgs) >= 2, "consultation should be multi-part"
    assert any("v2" in m.lower() for m in msgs)
    pdf = build_hybrid_presentation_pdf(None)
    assert len(pdf) > 2000, "PDF too small"
    assert pdf[:4] == b"%PDF"
    assert "v1" in build_v1_step_by_step(None).lower()
    assert "u-петл" in build_v2_step_by_step().lower()

    data, name, n, has = await build_hybrid_generator_print_pack({})
    assert has, "expected 3MF in pack"
    assert n == len(hybrid_generator_parts()) + len(hybrid_generator_v2_parts())
    assert name == "hybrid-generator-full-pack.zip"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        assert "pdf/hybrid-generator-presentation.pdf" in names
        assert "guides/v1-step-by-step.txt" in names
        assert "guides/v2-step-by-step.txt" in names
        assert any(n.startswith("v1-storyboard/3mf/") and n.endswith(".3mf") for n in names)
        assert any(n.startswith("v2-improved/3mf/") and n.endswith(".3mf") for n in names)
    print(f"OK hybrid pack: {n} parts, pdf+guides+v1+v2 3mf")


async def test_v3_corpus_pdf() -> None:
    from bot.services.hybrid_v3_figure8_corpus import (
        build_v3_corpus_pdf,
        default_figure8_spec,
        is_v3_3mf_request,
        is_v3_figure8_corpus_request,
        is_v3_print_approval,
    )

    assert is_v3_figure8_corpus_request("3я проверка корпус восьмерки из пластика")
    assert is_v3_figure8_corpus_request("корпус восьмерки из пластика реально 8 трубка")
    assert not is_v3_3mf_request("присылай 3мф", pending_preview=False)
    assert is_v3_3mf_request("присылай 3мф", pending_preview=True)
    assert is_v3_3mf_request("присылай 3MF v3", pending_preview=False)
    assert is_v3_print_approval("ок, присылай 3mf")
    assert not is_v3_figure8_corpus_request("присылай 3MF v3")
    spec = default_figure8_spec()
    assert spec.fits_p2s()
    assert len(spec.stand_cradle_xy_mm()) == 4
    pdf = build_v3_corpus_pdf(spec)
    assert pdf[:4] == b"%PDF" and len(pdf) > 8000
    print("OK v3 corpus PDF preview")


async def test_v3_print_pack() -> None:
    import zipfile
    from io import BytesIO

    from bot.services.hybrid_v3_figure8_corpus import V4_PDF_NAME, build_v3_print_pack

    data, filename, n_parts, has_3mf = await build_v3_print_pack()
    assert filename.endswith(".zip") and n_parts == 2
    with zipfile.ZipFile(BytesIO(data), "r") as zf:
        names = zf.namelist()
        assert f"pdf/{V4_PDF_NAME}" in names or "pdf/figure8-corpus-v4.pdf" in names
        assert "guides/print_order.txt" in names
        assert any(n.startswith("scad/") and n.endswith(".scad") for n in names)
        if has_3mf:
            assert sum(1 for n in names if n.startswith("3mf/") and n.endswith(".3mf")) == 2
    print(f"OK v3 print pack: 3mf={has_3mf}")


async def main() -> None:
    test_mesh_engineering_physics()
    test_autofix_and_fea()
    test_cad_kernel_kit()
    test_meshy_level3_mood_board_and_split()
    test_reference_geometry_level2()
    test_meshy_plan()
    test_meshy_candidate_score_prefers_visual_quality()
    test_mesh_cache_roundtrip()
    test_boeing_prompt_does_not_leak_old_part_colors()
    test_meshy_strict_repair_prefers_lower_non_manifold_count()
    test_large_meshy_postprocess_keeps_scaled_file_when_repair_times_out()
    test_short_3d_command_guard()
    test_engineering_contract()
    test_gemini_llm_helpers()
    test_stl_format_not_triggered_by_bambu_alone()
    test_portrait_figurine_prompt()
    test_routing()
    test_labrador_prompt()
    await test_openscad_handle()
    await test_cheburashka_plate_fails_check()
    await test_meshy_repair_warning_fails_check()
    await test_meshy_image_self_check_is_concept()
    await test_boeing_meshy_stl_is_not_final()
    await test_boeing_meshy_derived_repair_warning_is_kept()
    await test_meshy_support_3mf_passes_check()
    await test_meshy_component_3mf_for_part_colors()
    await test_component_3mf_rejects_zero_volume_shards()
    test_meshy_normalize_scales_explicit_length_up()
    await test_meshy_single_object_rejected_before_delivery()
    await test_meshy_failure_no_fallback()
    await test_print_project_network_error_uses_local_fallback()
    await test_meshy_single_mesh_part_colors_fail_check()
    await test_meshy_fallback_passes_check()
    await test_print_pack_fallback_passes_check()
    await test_self_check_llm_timeout_is_silent()
    await test_zero_to_print_project_pipeline()
    test_mechanical_boeing_assembly_preview()
    test_3d_zip_inventory_audit()
    await test_boeing_not_zip_project()
    await test_articulated_subject_guard()
    test_reset_clears_pending_concept()
    await test_pending_concept_persists_in_db()
    test_object_name_colors_drive_ams_slots()
    await test_hybrid_full_pack()
    await test_v3_corpus_pdf()
    await test_v3_print_pack()
    print("\n✅ Все проверки пройдены")


if __name__ == "__main__":
    asyncio.run(main())
