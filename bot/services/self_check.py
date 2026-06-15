"""Самопроверка результата после выдачи пользователю."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from bot.config import SELF_CHECK_ENABLED, SELF_CHECK_MODEL
from bot.services.model_router import model_for_capability
from bot.services.task_plan import TaskKind, TaskPlan

logger = logging.getLogger(__name__)

_ORGANIC = re.compile(
    r"фигур|персонаж|чебурашк|животн|человек|игрушк|скulpt|statue|декоратив|мульт|cartoon",
    re.I,
)
_FUNCTIONAL = re.compile(
    r"ручк|держател|кронштейн|клип|бутыл|кроншт",
    re.I,
)
_GENERATOR = re.compile(r"гибридн.{0,15}генератор|раскадров|storyboard", re.I)
_COMPLEX_MODEL = re.compile(
    r"самол[её]т|боинг|boeing|airliner|airplane|aircraft|вертол[её]т|"
    r"ракета|rocket|дрон|drone|машин[ауы]|автомобил|car|vehicle|"
    r"корабл|ship|танк|tank|поезд|train",
    re.I,
)


@dataclass
class DeliveredFile:
    filename: str
    size_bytes: int
    kind: str = "file"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    summary: str
    files: List[DeliveredFile] = field(default_factory=list)
    text_reply: str = ""
    success: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelfCheckOutcome:
    ok: bool
    message: str
    issues: List[str] = field(default_factory=list)


def _programmatic_check(plan: TaskPlan, delivery: DeliveryResult) -> SelfCheckOutcome:
    issues: List[str] = []
    text = plan.user_text
    files = delivery.files

    if plan.kind == TaskKind.ARTICULATED_3MF:
        from bot.services.articulated_3mf import (
            expected_part_names_for_text,
            forbidden_part_names_for_text,
            openscad_articulated_kind,
            requested_subject_label,
        )

        mf = next((f for f in files if f.kind == "3mf" or f.filename.endswith(".3mf")), None)
        if not mf:
            issues.append("Articulated: 3MF не приложен.")
        elif mf.size_bytes < 50_000:
            issues.append(f"Articulated: 3MF слишком мал ({mf.size_bytes} байт).")
        parts = delivery.meta.get("parts")
        if isinstance(parts, list):
            expected_kind = openscad_articulated_kind(plan.user_text)
            delivered_kind = delivery.meta.get("kind")
            subject = requested_subject_label(plan.user_text)
            if delivered_kind and expected_kind and delivered_kind != expected_kind:
                issues.append(
                    f"{subject}: выдан шаблон «{delivered_kind}» вместо «{expected_kind}»."
                )

            expected = expected_part_names_for_text(plan.user_text)
            forbidden = forbidden_part_names_for_text(plan.user_text)
            for need in expected:
                if need not in parts:
                    issues.append(f"{subject}: нет детали «{need}».")
            for bad in forbidden:
                if bad in parts:
                    issues.append(
                        f"{subject}: лишняя деталь «{bad}» — похоже на неверный шаблон."
                    )
            if expected and len(parts) < len(expected):
                issues.append(f"Articulated: мало деталей ({len(parts)}).")
        if not issues:
            return SelfCheckOutcome(
                ok=True,
                message=f"Самопроверка: 3MF {mf.size_bytes // 1024} KB, {len(parts or [])} деталей с шарнирами.",
            )

    if plan.kind == TaskKind.AIRPLANE_3MF:
        from bot.services.airplane_3mf import (
            AIRLINER_HD_PARTS,
            AIRLINER_PRINT_TUNED_EXTRA_PARTS,
            AIRPLANE_PARTS,
        )

        mf = next((f for f in files if f.kind == "3mf" or f.filename.endswith(".3mf")), None)
        high_detail = bool(delivery.meta.get("high_detail"))
        if not mf:
            issues.append("Airplane: 3MF не приложен.")
        elif mf.size_bytes < (20_000 if high_detail else 8_000):
            issues.append(f"Airplane: 3MF слишком мал ({mf.size_bytes} байт).")

        # Real-library model: a single complete, watertight airliner solid — it is
        # NOT split into procedural part names, so validate geometry/proportions.
        if delivery.meta.get("library_model"):
            dims = delivery.meta.get("dimensions") if isinstance(delivery.meta.get("dimensions"), dict) else {}
            length = float(dims.get("length_mm") or 0.0)
            wingspan = float(dims.get("wingspan_mm") or 0.0)
            height = float(dims.get("height_mm") or 0.0)
            if not delivery.meta.get("watertight"):
                issues.append("Airplane (library): модель должна быть watertight-solid для печати.")
            if length < 80.0:
                issues.append(f"Airplane (library): длина слишком мала ({length:.1f} мм).")
            if wingspan < 0.5 * length:
                issues.append(f"Airplane (library): размах крыльев мал относительно длины ({wingspan:.1f} мм).")
            if not (0.15 * length <= height <= 0.95 * length):
                issues.append(f"Airplane (library): высота вне реалистичных пропорций ({height:.1f} мм).")
            if not issues:
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: реальная модель 747 ({mf.size_bytes // 1024} KB), "
                        f"watertight-solid, длина {length:.0f}мм, размах {wingspan:.0f}мм, "
                        f"высота {height:.0f}мм — готова к печати."
                    ),
                )

        if not delivery.meta.get("library_model"):
            parts = delivery.meta.get("parts")
            if isinstance(parts, list):
                required_parts = AIRLINER_HD_PARTS if high_detail else AIRPLANE_PARTS
                if delivery.meta.get("print_tuned") or delivery.meta.get("print_ready_v3"):
                    required_parts = [*AIRLINER_HD_PARTS, *AIRLINER_PRINT_TUNED_EXTRA_PARTS]
                for need in required_parts:
                    if need not in parts:
                        issues.append(f"самолёт: нет обязательной детали «{need}».")
            else:
                issues.append("Airplane: нет списка деталей для проверки.")
            if not delivery.meta.get("assembled"):
                issues.append("Airplane: модель должна быть собранным самолётом, а не набором деталей на столе.")
        dims = delivery.meta.get("dimensions") if isinstance(delivery.meta.get("dimensions"), dict) else {}
        if high_detail and not delivery.meta.get("library_model"):
            length = float(dims.get("length_mm") or 0.0)
            wingspan = float(dims.get("wingspan_mm") or 0.0)
            height = float(dims.get("height_mm") or 0.0)
            if not (120.0 <= length <= 175.0):
                issues.append(f"Airliner HD: длина вне допуска для 15 см запроса ({length:.1f} мм).")
            if wingspan < 95.0:
                issues.append(f"Airliner HD: размах крыльев слишком мал ({wingspan:.1f} мм).")
            if height < 35.0:
                issues.append(f"Airliner HD: высота/хвост слишком низкие ({height:.1f} мм).")
            if delivery.meta.get("print_tuned") or delivery.meta.get("print_ready_v3"):
                if delivery.meta.get("support_strategy") != "adaptive_major_minor_micro":
                    issues.append("Airliner v3: supports должны быть разделены на major/minor/micro-contact.")
                min_feature = float(delivery.meta.get("min_feature_mm") or 0.0)
                if min_feature < 0.4:
                    issues.append("Airliner v3: не зафиксирован минимум печатной детали под сопло 0.4 мм.")
        if not issues:
            return SelfCheckOutcome(
                ok=True,
                message=(
                    f"Самопроверка: 3MF {mf.size_bytes // 1024} KB, "
                    f"{'print-ready v3 ' if delivery.meta.get('print_ready_v3') else 'high-detail ' if high_detail else ''}"
                    "самолёт имеет крылья, хвост, двигатели и AMS-объекты."
                ),
            )

    if plan.kind in (TaskKind.MESHY_TEXT_3D, TaskKind.MESHY_PHOTO_3D):
        from bot.services.bambu_hints import extract_part_color_requests

        part_color_requests = delivery.meta.get("part_color_requests") or extract_part_color_requests(text)
        if delivery.meta.get("fallback_solution") and files:
            return SelfCheckOutcome(
                ok=True,
                message=(
                    "Самопроверка: основной Meshy-пайплайн не прошёл, "
                    "но бот автоматически выдал fallback-файл вместо тупика."
                ),
            )
        if delivery.meta.get("component_3mf"):
            mf = next((f for f in files if f.kind == "3mf" or f.filename.endswith(".3mf")), None)
            component_count = int(delivery.meta.get("component_count") or 0)
            if not mf:
                issues.append("Meshy component mode: multi-object 3MF не приложен.")
            elif mf.size_bytes < 3_000 or component_count < 2:
                issues.append(
                    f"Meshy component mode: 3MF подозрителен "
                    f"({mf.size_bytes} байт, {component_count} компонентов)."
                )
            elif part_color_requests and not delivery.meta.get("object_level_colors") and not delivery.meta.get("color_limitation_warning"):
                issues.append(
                    "STL разложен на компоненты, но запрошенные цвета деталей не сопоставлены с объектами "
                    "и пользователь не предупреждён."
                )
            else:
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: Meshy STL разложен в multi-object 3MF {mf.size_bytes // 1024} KB; "
                        "object-level AMS применён там, где детали удалось распознать."
                    ),
                )
            if issues:
                return SelfCheckOutcome(
                    ok=False,
                    message="Самопроверка: есть проблемы.",
                    issues=issues,
                )
        if delivery.meta.get("support_3mf"):
            mf = next((f for f in files if f.kind == "3mf" or f.filename.endswith(".3mf")), None)
            if not mf:
                issues.append("Meshy support mode: 3MF с поддержками не приложен.")
            elif mf.size_bytes < 8_000:
                issues.append(f"Meshy support mode: 3MF слишком мал ({mf.size_bytes} байт).")
            else:
                if part_color_requests and not delivery.meta.get("object_level_colors"):
                    if delivery.meta.get("color_limitation_warning"):
                        return SelfCheckOutcome(
                            ok=True,
                            message=(
                                "Самопроверка: Meshy STL обёрнут в Bambu 3MF с Tree(auto); "
                                "бот честно предупредил, что разные AMS-цвета деталей требуют отдельные объекты."
                            ),
                        )
                    issues.append(
                        "Запрошены разные цвета деталей, но Meshy STL обёрнут как один объект: "
                        "Bambu/AMS не сможет автоматически покрасить отдельные детали без сегментации."
                    )
                if issues:
                    return SelfCheckOutcome(
                        ok=False,
                        message="Самопроверка: есть проблемы.",
                        issues=issues,
                    )
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: Meshy STL обёрнут в Bambu 3MF {mf.size_bytes // 1024} KB "
                        "с Tree(auto), поддержка включена ботом."
                    ),
                )
            if issues:
                return SelfCheckOutcome(
                    ok=False,
                    message="Самопроверка: есть проблемы.",
                    issues=issues,
                )
        mesh = next((f for f in files if f.kind in ("stl", "glb", "meshy")), None)
        if not mesh:
            issues.append("Meshy: файл модели не приложен.")
        elif mesh.size_bytes < 20_000:
            issues.append(
                f"Meshy: файл слишком мал ({mesh.size_bytes} байт) — похоже на заглушку."
            )
        method = str(delivery.meta.get("meshy_method") or delivery.summary or "")
        if re.search(r"repair WARNING|non-manifold", method, re.I) and not delivery.meta.get("repair_warning_accepted"):
            issues.append("Meshy: STL всё ещё имеет non-manifold edges после repair — нужен повторный repair/генерация.")
        if part_color_requests and mesh and mesh.kind in ("stl", "meshy") and not delivery.meta.get("object_level_colors"):
            if not delivery.meta.get("color_limitation_warning"):
                issues.append(
                    "Запрошены разные цвета деталей, но выдан один Meshy STL: "
                    "нужна 3MF-сегментация/процедурная multi-object модель или честное предупреждение."
                )
        if mesh and mesh.kind == "stl":
            from bot.services.airplane_3mf import airplane_requested

            if airplane_requested(text) and not (
                delivery.meta.get("meshy_derived_print_ready") or delivery.meta.get("native_3mf")
            ):
                issues.append(
                    "Boeing: Meshy STL не считается финальным print-ready результатом; "
                    "нужен процедурный 3MF v3 с устойчивой ориентацией/опорой."
                )

    if plan.kind == TaskKind.OPENSCAD_SINGLE:
        stl = next((f for f in files if f.kind in ("stl", "scad")), None)
        if not stl:
            issues.append("OpenSCAD: не отправлен STL/SCAD.")
        elif stl.kind == "stl" and stl.size_bytes < 3_000:
            issues.append(
                f"OpenSCAD: STL слишком мал ({stl.size_bytes} байт) — вероятно примитив."
            )
        if _ORGANIC.search(text) and not _FUNCTIONAL.search(text):
            issues.append(
                "Запрос — фигурка/персонаж; нужен Meshy, не OpenSCAD-примитив."
            )
        tpl = str(delivery.meta.get("template") or "")
        if _ORGANIC.search(text) and tpl in ("plate", "box", "cube"):
            issues.append(f"Для фигурки выдан примитив «{tpl}» (пластина).")
        if not issues and stl and stl.kind == "stl" and stl.size_bytes >= 10_000:
            if tpl in ("bottle_handle", "tube_clip") or _FUNCTIONAL.search(text):
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: STL {stl.size_bytes // 1024} KB, шаблон {tpl or 'деталь'} — "
                        "похоже на реальную деталь, не заглушку."
                    ),
                )

    if plan.kind in (TaskKind.PRINT_PROJECT, TaskKind.MECHANICAL_PROJECT):
        zf = next((f for f in files if f.kind == "zip"), None)
        if zf and zf.size_bytes < 500:
            issues.append("ZIP проекта подозрительно мал.")
        if delivery.meta.get("project_kind") == "mechanical_boeing_airliner":
            from bot.services.print_project import (
                _MECHANICAL_BOEING_FIT_COUPONS,
                _MECHANICAL_BOEING_FORBIDDEN_TEMPLATES,
            )

            templates = set(delivery.meta.get("part_templates") or [])
            bad = templates & _MECHANICAL_BOEING_FORBIDDEN_TEMPLATES
            if bad:
                issues.append(
                    f"Mechanical Boeing: generic-шаблоны {sorted(bad)} — нужен airliner v3 kit."
                )
            joints = int(delivery.meta.get("kinematics_joints") or 0)
            if joints < 8:
                issues.append(
                    f"Mechanical Boeing: в кинематике {joints} узлов, ожидается ≥8."
                )
            coupon_ids = set(delivery.meta.get("fit_coupon_ids") or [])
            missing_coupons = _MECHANICAL_BOEING_FIT_COUPONS - coupon_ids
            if missing_coupons:
                issues.append(
                    f"Mechanical Boeing: нет fit-coupons {sorted(missing_coupons)}."
                )
            if delivery.meta.get("assembly_version") != "v3":
                issues.append("Mechanical Boeing: ожидается assembly_version v3.")
            if not issues and zf and zf.size_bytes >= 8_000:
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: mechanical Boeing v3 kit, {joints} kinematic joints, "
                        f"fit-first coupons, ZIP {zf.size_bytes // 1024} KB."
                    ),
                )
        if delivery.meta.get("zero_to_print"):
            contract = delivery.meta.get("print_prep_contract") if isinstance(delivery.meta.get("print_prep_contract"), dict) else {}
            if not zf:
                issues.append("Zero-to-print: ZIP проекта не приложен.")
            if not delivery.meta.get("project_kind"):
                issues.append("Zero-to-print: не указан тип проекта/стратегия.")
            if float(delivery.meta.get("min_wall_mm") or 0.0) < 0.5:
                issues.append("Zero-to-print: минимальная стенка меньше 0.5 мм.")
            for key in ("manifold_solid_required", "orientation_required", "support_strategy_required"):
                if not contract.get(key):
                    issues.append(f"Zero-to-print: в контракте нет {key}.")
            if not issues and zf and zf.size_bytes >= 500:
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        "Самопроверка: zero-to-print проект собран как CAD/kit/assembly ZIP "
                        "с print-prep контрактом, а не как сырой нейросетевой STL."
                    ),
                )
        if delivery.meta.get("fallback_solution") and zf and zf.size_bytes >= 500:
            return SelfCheckOutcome(
                ok=True,
                message="Самопроверка: выдан fallback print-pack v0, задача не оставлена тупиком.",
            )
        if _ORGANIC.search(text) and not _GENERATOR.search(text):
            issues.append("Запрос не про генератор/раскадровку — ZIP из многих деталей лишний.")
        if _COMPLEX_MODEL.search(text) and not _GENERATOR.search(text):
            if not (
                delivery.meta.get("zero_to_print")
                and delivery.meta.get("project_kind") == "mechanical_boeing_airliner"
            ):
                issues.append(
                    "Сложная модель транспорта должна идти в 3D/Meshy-пайплайн, "
                    "а не в ZIP из OpenSCAD-примитивов."
                )
        parts = delivery.meta.get("parts_count")
        if isinstance(parts, int) and parts >= 6 and _FUNCTIONAL.search(text):
            if not _GENERATOR.search(text):
                issues.append(f"Отправлено {parts} деталей вместо одной запрошенной.")

    if plan.kind == TaskKind.FILE_OUTPUT and plan.file_fmt == "stl":
        stl = next((f for f in files if f.kind == "stl"), None)
        if stl and stl.size_bytes < 20_000 and _ORGANIC.search(text):
            issues.append(
                f"STL {stl.size_bytes} байт для фигурки — похоже на шар/примитив, нужен Meshy."
            )
        shape = str(delivery.meta.get("shape") or "")
        if _ORGANIC.search(text) and shape in ("sphere", "ball", "cylinder", "box"):
            issues.append(f"Для фигурки выдан примитив «{shape}», не персонаж.")

    if issues:
        return SelfCheckOutcome(
            ok=False,
            message="Самопроверка: есть проблемы.",
            issues=issues,
        )
    return SelfCheckOutcome(ok=True, message="Самопроверка: базовые проверки пройдены.")


async def _llm_check(plan: TaskPlan, delivery: DeliveryResult) -> SelfCheckOutcome:
    from bot.services import llm

    check_model = model_for_capability("self_check", SELF_CHECK_MODEL)
    files_desc = ", ".join(
        f"{f.filename} ({f.size_bytes} B, {f.kind})" for f in delivery.files
    ) or "нет файлов"
    flags = []
    if delivery.meta.get("voice_sent"):
        flags.append("voice_sent=true")
    if delivery.meta.get("procedural"):
        flags.append("procedural=true")
    if delivery.meta.get("articulated"):
        flags.append("articulated=true")
    flags_desc = ", ".join(flags) or "нет"
    prompt = (
        f"Запрос пользователя:\n{plan.user_text[:2000]}\n\n"
        f"Тип задачи: {plan.label}\n"
        f"Что выдали: {delivery.summary}\n"
        f"Файлы: {files_desc}\n"
        f"Флаги доставки: {flags_desc}\n"
        f"Текст ответа: {delivery.text_reply[:1500]}\n\n"
        "Проверь строго:\n"
        "1. Это то, что просили по смыслу, а не совпадение по ключевым словам?\n"
        "2. Нет ли подмены предмета/формата/цветов/материала (собака вместо ангела, "
        "прямоугольник вместо фигурки, генератор вместо ручки)?\n"
        "3. Не обещано ли больше, чем реально выдано? Если выдан процедурный v0, "
        "это должно быть честно названо, а не выдано за финальный скульпт.\n"
        "4. Если voice_sent=true, НЕ ругайся на то, что ответ также был текстом: "
        "голосовое уже отправлено ботом. Проверяй смысл ответа.\n"
        "5. Если есть очевидное улучшение результата, но базовый результат верный, "
        "ok=true, а улучшение коротко добавь в confirm.\n"
        'Ответь ТОЛЬКО JSON: {"ok":true/false,"issues":["..."],"confirm":"одно предложение"}'
    )
    try:
        raw = await llm.chat_completion(
            [{"role": "user", "content": prompt}],
            check_model,
            system="Ты строгий QA бота. JSON only.",
            temperature=0.1,
        )
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            ok = bool(data.get("ok"))
            issues = [str(x) for x in (data.get("issues") or []) if x]
            confirm = str(data.get("confirm") or "").strip()
            if ok:
                return SelfCheckOutcome(
                    ok=True,
                    message=confirm or "Самопроверка: результат соответствует запросу.",
                )
            return SelfCheckOutcome(
                ok=False,
                message="Самопроверка: модель нашла несоответствие.",
                issues=issues or ["Модель не подтвердила результат."],
            )
    except Exception as e:
        logger.warning("Self-check LLM failed: %s", e)
    return SelfCheckOutcome(ok=True, message="")


async def run_self_check(plan: TaskPlan, delivery: DeliveryResult) -> SelfCheckOutcome:
    if not SELF_CHECK_ENABLED:
        return SelfCheckOutcome(ok=True, message="")
    if not delivery.success:
        return SelfCheckOutcome(
            ok=False,
            message="Задача завершилась с ошибкой.",
            issues=[delivery.summary],
        )
    if delivery.meta.get("awaiting_reference"):
        return SelfCheckOutcome(ok=True, message="Самопроверка: бот не генерировал 3D вслепую и ждёт референс/подтверждение.")
    if plan.kind == TaskKind.UNSUPPORTED_ARTICULATED_3D:
        return SelfCheckOutcome(ok=True, message="")

    prog = _programmatic_check(plan, delivery)
    if not prog.ok:
        return prog
    if prog.message and prog.message != "Самопроверка: базовые проверки пройдены.":
        return prog

    if plan.kind == TaskKind.PENDING_3D:
        return SelfCheckOutcome(ok=True, message="")

    if plan.kind == TaskKind.MESHY_IMAGE and delivery.files:
        kb = delivery.files[0].size_bytes // 1024
        return SelfCheckOutcome(
            ok=True,
            message=f"Самопроверка: концепт-картинка Meshy ~{kb} KB готова для согласования перед 3D.",
        )

    if plan.uses_meshy and delivery.files:
        kb = delivery.files[0].size_bytes // 1024
        try:
            from bot.services.airplane_3mf import airplane_requested

            if airplane_requested(plan.user_text):
                return SelfCheckOutcome(
                    ok=True,
                    message=(
                        f"Самопроверка: Meshy Boeing ~{kb} KB принят как визуальный прототип/форма. "
                        "Финальный print-ready файл после критики должен идти через CAD-like Boeing v3."
                    ),
                )
        except Exception:
            pass
        return SelfCheckOutcome(
            ok=True,
            message=f"Самопроверка: Meshy-модель ~{kb} KB — нормальный размер меша.",
        )

    if plan.kind in (
        TaskKind.OPENSCAD_SINGLE,
        TaskKind.PRINT_PROJECT,
        TaskKind.ARTICULATED_3MF,
        TaskKind.AIRPLANE_3MF,
        TaskKind.FILE_OUTPUT,
        TaskKind.CHAT,
        TaskKind.VISION_CHAT,
    ):
        llm_out = await _llm_check(plan, delivery)
        if not llm_out.ok:
            return llm_out
        if not llm_out.message:
            return llm_out
        return SelfCheckOutcome(ok=True, message=llm_out.message or prog.message)

    return prog


async def announce_task_plan(message, plan: TaskPlan) -> None:
    from bot.config import SELF_CHECK_ENABLED, TASK_ROUTER_ANNOUNCE
    from bot.services.model_catalog import model_label

    if not TASK_ROUTER_ANNOUNCE:
        return
    mlabel = model_label(plan.model)
    line = (
        f"🧭 {plan.label}\n"
        f"🤖 Модель: <b>{mlabel}</b> (<code>{plan.model}</code>)\n"
        f"📌 {plan.model_reason}"
    )
    hint = (plan.extra or {}).get("meshy_hint")
    if hint:
        line += f"\n⚙️ Meshy: {hint}"
    if SELF_CHECK_ENABLED:
        line += "\n🔍 После выдачи — самопроверка."
    await message.answer(line[:1024], parse_mode="HTML")


async def report_self_check(message, plan: TaskPlan, delivery: DeliveryResult) -> None:
    if not SELF_CHECK_ENABLED:
        return
    outcome = await run_self_check(plan, delivery)
    if not outcome.message:
        return
    if outcome.ok:
        await message.answer(f"✅ {outcome.message}"[:1024])
    else:
        issues = "\n".join(f"• {i}" for i in outcome.issues[:5])
        await message.answer(
            f"⚠️ {outcome.message}\n{issues}\n\n"
            "Файл уже отправлен, но самопроверка считает его неверным — "
            "не печатайте без ручной проверки в слайсере."
            [:1024]
        )
