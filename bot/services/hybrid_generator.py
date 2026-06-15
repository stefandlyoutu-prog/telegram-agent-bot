"""Гибридный электромагнитный генератор: детали, превью плана, Bambu 3MF-пак."""

from __future__ import annotations

import asyncio
import io
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

_HYBRID = re.compile(r"гибридн.{0,20}генератор|hybrid.{0,12}generator", re.I)


def is_hybrid_generator_storyboard(
    frames: Optional[List[Dict[str, Any]]] = None,
    text: str = "",
) -> bool:
    blob = text or ""
    if frames:
        blob += " " + " ".join(
            f"{f.get('title', '')} {f.get('description', '')}" for f in frames
        )
    return bool(_HYBRID.search(blob))


def hybrid_generator_parts() -> List[Dict[str, Any]]:
    """Печатаемые CAD-детали корпуса (не «коробки по кадрам»)."""
    return [
        {
            "id": "body_lower",
            "name": "Нижняя половина корпуса",
            "template": "hollow_box",
            "params": {"width_mm": 200, "depth_mm": 120, "height_mm": 60, "wall_mm": 3},
            "material": "PETG",
            "orientation": "дном на стол",
            "purpose": "Основная база 200×120×60 мм с полостью под трубку и узлы.",
            "assembly_step": "1. Уложить силиконовую трубку «восьмёркой», закрепить клипсами.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "body_upper",
            "name": "Верхняя крышка",
            "template": "plate",
            "params": {"width_mm": 200, "depth_mm": 120, "height_mm": 8},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Закрывает корпус, фиксирует проводку.",
            "assembly_step": "⑥ Закрыть корпус после укладки проводов.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "tube_clip",
            "name": "Клипса трубки",
            "template": "tube_clip",
            "params": {"width_mm": 24, "depth_mm": 18, "height_mm": 12, "radius_mm": 5.5},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Фиксирует силиконовую трубку Ø10 мм вдоль «восьмёрки».",
            "assembly_step": "① 4–6 шт. вдоль канала трубки.",
            "print_qty": 6,
            "bambu_material": "PETG",
        },
        {
            "id": "coil_bobbin",
            "name": "Катушечная бобина",
            "template": "bobbin",
            "params": {"radius_mm": 14, "height_mm": 18, "wall_mm": 2},
            "material": "PETG",
            "orientation": "основанием на стол",
            "purpose": "Намотка медного провода 0.15 мм (~1000 витков).",
            "assembly_step": "⑤ Намотать провод → вставить в гнёзда корпуса, 2 шт.",
            "print_qty": 2,
            "bambu_material": "PETG",
        },
        {
            "id": "piezo_mount",
            "name": "Площадка пьезо",
            "template": "plate",
            "params": {"width_mm": 48, "depth_mm": 48, "height_mm": 6, "hole_mm": 40},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Посадка купленного пьезоэлемента Ø40 мм.",
            "assembly_step": "④ Пьезо + акустический гель к стенке трубки.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "heater_mount",
            "name": "Держатель нагревателя",
            "template": "hollow_box",
            "params": {"width_mm": 30, "depth_mm": 22, "height_mm": 26, "wall_mm": 2.5},
            "material": "ASA",
            "orientation": "дном на стол",
            "purpose": "Изолирует нихромовый нагреватель от PETG корпуса.",
            "assembly_step": "③ Нагреватель в нижнее «колено» восьмёрки.",
            "print_qty": 1,
            "bambu_material": "ASA",
        },
        {
            "id": "electronics_box",
            "name": "Отсек электроники",
            "template": "hollow_box",
            "params": {"width_mm": 54, "depth_mm": 34, "height_mm": 22, "wall_mm": 2},
            "material": "PETG",
            "orientation": "дном на стол",
            "purpose": "Диодный мост DB107, конденсатор 100 µF, разъём DC.",
            "assembly_step": "⑤ Пайка моста и конденсатора → крепление сбоку корпуса.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "end_cap",
            "name": "Торцевая заглушка",
            "template": "plate",
            "params": {"width_mm": 120, "depth_mm": 8, "height_mm": 60},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Закрывает торец корпуса, вывод проводов.",
            "assembly_step": "⑥ После прокладки проводов.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
    ]


def hybrid_generator_v2_parts() -> List[Dict[str, Any]]:
    """v2: U-петля, один поршень, катушка на прямом участке."""
    return [
        {
            "id": "loop_base",
            "name": "Корпус U-петли (нижняя часть)",
            "template": "hollow_box",
            "params": {"width_mm": 220, "depth_mm": 140, "height_mm": 70, "wall_mm": 3.5},
            "material": "PETG",
            "orientation": "дном на стол",
            "purpose": "База с полостью под жёсткую трубу Ø12–14 мм, без перекрёстка.",
            "assembly_step": "① Установить трубку в U-канал, закрепить tube_guide.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "loop_lid",
            "name": "Крышка U-петли с заливным port",
            "template": "plate",
            "params": {"width_mm": 220, "depth_mm": 140, "height_mm": 10, "hole_mm": 12},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Закрывает контур; отверстие Ø12 мм для заливки жидкости.",
            "assembly_step": "③ После заливки жидкости и проверки поршня.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "tube_guide",
            "name": "Направляющая трубки",
            "template": "tube_clip",
            "params": {"width_mm": 28, "depth_mm": 22, "height_mm": 14, "radius_mm": 6.5},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Фиксирует акриловую трубку на прямом и изогнутом участках.",
            "assembly_step": "① 2 шт. на прямой участок и на изгиб.",
            "print_qty": 2,
            "bambu_material": "PETG",
        },
        {
            "id": "magnetic_piston",
            "name": "Магнитный поршень",
            "template": "cylinder",
            "params": {"radius_mm": 5.5, "height_mm": 16, "wall_mm": 1.5},
            "material": "PETG",
            "orientation": "основанием на стол",
            "purpose": "Корпус поршня под неодим Ø6 мм + O-ring (сборка руками).",
            "assembly_step": "② Вставить магнит, уплотнение; проверить скольжение в трубе.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "coil_bobbin_v2",
            "name": "Бобина на прямом участке",
            "template": "bobbin",
            "params": {"radius_mm": 18, "height_mm": 22, "wall_mm": 2.5},
            "material": "PETG",
            "orientation": "основанием на стол",
            "purpose": "Намотка ~800–1200 витков; ось совпадает с движением поршня.",
            "assembly_step": "⑥ Намотать → установить через coil_mount.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "coil_mount",
            "name": "Кронштейн катушки",
            "template": "plate",
            "params": {"width_mm": 56, "depth_mm": 56, "height_mm": 8, "hole_mm": 16},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Крепит бобину коаксиально с трубкой на прямом участке.",
            "assembly_step": "⑥ Совместить с coil_bobbin_v2 на прямом участке.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "heater_chamber",
            "name": "Камера нагревателя",
            "template": "hollow_box",
            "params": {"width_mm": 36, "depth_mm": 28, "height_mm": 30, "wall_mm": 2.5},
            "material": "ASA",
            "orientation": "дном на стол",
            "purpose": "ASA-изоляция нихрома от PETG; нижнее «колено» петли.",
            "assembly_step": "④ Нагреватель + термозазор; цель 45–50 °C.",
            "print_qty": 1,
            "bambu_material": "ASA",
        },
        {
            "id": "electronics_box",
            "name": "Отсек электроники",
            "template": "hollow_box",
            "params": {"width_mm": 54, "depth_mm": 34, "height_mm": 22, "wall_mm": 2},
            "material": "PETG",
            "orientation": "дном на стол",
            "purpose": "DB107, конденсатор, разъём DC.",
            "assembly_step": "⑦ После стабильного AC mV на катушке.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "hall_mount",
            "name": "Площадка Hall-датчика",
            "template": "plate",
            "params": {"width_mm": 24, "depth_mm": 18, "height_mm": 4},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Крепление SS49E + LED — проверка движения поршня (фаза A).",
            "assembly_step": "⑤ До подключения мультиметра к катушке.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
        {
            "id": "piezo_mount_v2",
            "name": "Площадка пьezo (опционально)",
            "template": "plate",
            "params": {"width_mm": 48, "depth_mm": 48, "height_mm": 6, "hole_mm": 40},
            "material": "PETG",
            "orientation": "плоской стороной на стол",
            "purpose": "Опционально после фазы B — усиление потока 40 kHz.",
            "assembly_step": "⑧ Только если конвекция уже работает.",
            "print_qty": 1,
            "bambu_material": "PETG",
        },
    ]


def hybrid_generator_specs(
    frames: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "project_name": "hybrid-generator-v0",
        "mode": "hybrid-storyboard",
        "project_kind": "hybrid_electromagnetic_generator",
        "source": "storyboard.html",
        "requirements": [
            "Корпус PETG 200×120×60 мм по раскадровке",
            "Печать только механических деталей; электроника и трубка — покупка/ручная сборка",
        ],
        "assumptions": [
            "Геометрия v0 — параметрический OpenSCAD; каналы под трубку упрощены",
            "Работоспособность генератора — экспериментальный макет, КПД не гарантируется",
        ],
        "parts": hybrid_generator_parts(),
        "storyboard_frames": frames or [],
    }


def _frame_rows(frames: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Кадр → что делать (не путать с STL по кадру)."""
    rows: List[Dict[str, str]] = []
    rules = [
        (r"общий вид|восьмёрк", "reference", "Схема — не печатается"),
        (r"трубк|силикон", "buy", "Купить: силиконовая трубка Ø8–10 мм, ~80 см"),
        (r"магнит|капсул", "diy", "Сделать руками: неодим Ø5 мм + эпоксидка в трубку"),
        (r"нагрев|нихром", "diy+print", "Нихром намотать; печать: heater_mount.stl (ASA)"),
        (r"пьezo|пьезо", "buy+print", "Купить пьезо Ø40 мм; печать: piezo_mount.stl"),
        (r"катуш|индукц", "diy+print", "Намотка меди; печать: coil_bobbin.stl ×2"),
        (r"выход|мост|цеп", "buy+print", "Купить DB107 + 100 µF; печать: electronics_box.stl"),
        (r"итог|готовое", "reference", "Сборка всех узлов — не печатается"),
    ]
    for f in frames:
        title = str(f.get("title") or "")
        desc = str(f.get("description") or "")
        blob = f"{title} {desc}".lower()
        action, note = "—", title
        for pat, act, n in rules:
            if re.search(pat, blob, re.I):
                action, note = act, n
                break
        rows.append({"frame": str(f.get("frame") or "?"), "title": title, "action": action, "note": note})
    return rows


def build_storyboard_preview_message(
    frames: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Человекочитаемый план до генерации файлов (как в консультации)."""
    parts = hybrid_generator_parts()
    frame_rows = _frame_rows(frames or [])

    lines = [
        "📋 План по вашей раскадровке — гибридный генератор",
        "",
        "Сначала — что будет сделано, потом пришлю файлы для Bambu.",
        "",
        "▸ Три категории",
        "• Печать (3MF) — корпус, крышка, бобины, клипсы, площадки",
        "• Купить — трубка, магниты, пьезо, провод, DB107, конденсатор",
        "• Сделать руками — капсулы, намотка, нихром, пайка",
        "",
        "▸ Кадры раскадровки (что означает каждый)",
    ]
    for row in frame_rows:
        lines.append(f"  {row['frame']}. {row['title'][:55]}")
        lines.append(f"     → {row['note']}")
    lines.extend(
        [
            "",
            "▸ Что напечатаю (3MF → Bambu Studio → Печать)",
            "",
            "| № | Деталь | Файл | Мат. | Кол-во |",
            "|---|--------|------|------|--------|",
        ]
    )
    for idx, p in enumerate(parts, start=1):
        pid = p["id"]
        qty = int(p.get("print_qty") or 1)
        mat = p.get("bambu_material") or p.get("material") or "PETG"
        lines.append(
            f"| {idx} | {p['name']} | {idx:02d}-{pid}.3mf | {mat} | {qty} |"
        )
    lines.extend(
        [
            "",
            "▸ Настройки печати (дефолт)",
            "• Слой 0.2 мм, заполнение 20–25 %",
            "• PETG: сопло 240–250 °C, стол 80 °C",
            "• ASA (держатель нагревателя): 260 °C, стол 90 °C",
            "",
            "▸ Порядок сборки",
            "① Корпус + трубка + клипсы",
            "② Магнитные капсулы в трубку",
            "③ Нагреватель в heater_mount",
            "④ Пьезо на piezo_mount",
            "⑤ Катушки + электроника",
            "⑥ Крышка body_upper",
            "",
            "⚠️ Это экспериментальный макет — бот не проверяет физику генератора.",
            "",
            "Сейчас соберу ZIP с 3MF и инструкциями…",
        ]
    )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + "\n\n…(продолжение в README внутри архива)"
    return text


def build_hybrid_bom_txt() -> str:
    lines = [
        "СПИСОК ЗАКУПКИ (не печатается)",
        "==============================",
        "",
        "• Силиконовая трубка Ø8–10 мм, длина ~80 см",
        "• Неодимовые магниты Ø5 мм (для капсул в трубке)",
        "• Эпоксидная смола",
        "• Нихромовая проволока 0.3 мм + керамическая основа",
        "• Пьезоэлемент Ø40 мм + драйвер ~40 kHz",
        "• Медный провод 0.15 мм (≈2000 витков суммарно)",
        "• Ферритовые кольца (по схеме)",
        "• Диодный мост DB107",
        "• Конденсатор 100 µF",
        "• Разъём питания, провода, термоусадка",
        "",
        "ПЕЧАТЬ — см. папку 3mf/ и print_order.txt",
    ]
    return "\n".join(lines)


def build_hybrid_print_order_txt() -> str:
    lines = [
        "ПОРЯДОК ПЕЧАТИ — Bambu Studio",
        "==============================",
        "",
        "Откройте каждый 3MF → проверьте материал → Печать.",
        "Детали с qty>1: в слайсере укажите количество копий.",
        "",
    ]
    for idx, p in enumerate(hybrid_generator_parts(), start=1):
        pid = p["id"]
        qty = int(p.get("print_qty") or 1)
        mat = p.get("bambu_material") or p.get("material") or "PETG"
        lines.append(f"{idx}. {p['name']} — v1-storyboard/3mf/{idx:02d}-{pid}.3mf")
        lines.append(f"   Материал: {mat} | Копий: {qty}")
        lines.append(f"   Ориентация: {p.get('orientation') or '—'}")
        lines.append(f"   {p.get('purpose') or ''}")
        lines.append("")
    lines.append("После печати — assembly.md в архиве.")
    return "\n".join(lines)


def build_v2_print_order_txt() -> str:
    lines = [
        "ПОРЯДОК ПЕЧАТИ v2 — U-петля",
        "==============================",
        "",
    ]
    for idx, p in enumerate(hybrid_generator_v2_parts(), start=1):
        pid = p["id"]
        qty = int(p.get("print_qty") or 1)
        mat = p.get("bambu_material") or p.get("material") or "PETG"
        lines.append(f"{idx}. {p['name']} — v2-improved/3mf/{idx:02d}-{pid}.3mf")
        lines.append(f"   Материал: {mat} | Копий: {qty}")
        lines.append(f"   {p.get('purpose') or ''}")
        lines.append("")
    return "\n".join(lines)


async def _export_parts_bundle(
    zf: zipfile.ZipFile,
    prefix: str,
    parts: List[Dict[str, Any]],
    profile: Dict[str, Any],
    project_name: str,
) -> Tuple[int, int]:
    from bot.services.openscad import (
        build_assembly_md,
        build_scad_source,
        export_stl_from_scad,
        openscad_available,
        sanitize_id,
    )
    from bot.services.support_3mf import wrap_stl_as_support_3mf

    import tempfile
    from pathlib import Path

    stl_count = 0
    threed_count = 0
    for idx, part in enumerate(parts, start=1):
        pid = sanitize_id(str(part.get("id") or f"part-{idx:02d}"))
        ordered = f"{idx:02d}-{pid}"
        scad_src = build_scad_source(part).encode("utf-8")
        zf.writestr(f"{prefix}/scad/{ordered}.scad", scad_src)

        if not openscad_available():
            continue

        with tempfile.TemporaryDirectory() as td:
            stl_path = Path(td) / f"{ordered}.stl"
            if not await export_stl_from_scad(scad_src, stl_path):
                continue
            stl_bytes = stl_path.read_bytes()
            zf.writestr(f"{prefix}/stl/{ordered}.stl", stl_bytes)
            stl_count += 1

            mat = part.get("bambu_material") or part.get("material") or "PETG"
            part_profile = {**profile, "material": mat}
            user_hint = f"гибридный генератор {part.get('name')} {mat}"
            try:
                mf_bytes, _ = wrap_stl_as_support_3mf(
                    stl_bytes,
                    stl_filename=f"{ordered}.stl",
                    user_text=user_hint,
                    profile=part_profile,
                )
                zf.writestr(f"{prefix}/3mf/{ordered}.3mf", mf_bytes)
                threed_count += 1
            except Exception:
                pass

    zf.writestr(f"{prefix}/assembly.md", build_assembly_md(project_name, parts))
    return stl_count, threed_count


async def build_hybrid_generator_print_pack(
    profile: Optional[Dict[str, Any]] = None,
    *,
    frames: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bytes, str, int, bool]:
    """Полный ZIP: v1 + v2 + PDF + пошаговые guides."""
    from bot.services.hybrid_consultation import (
        build_hybrid_presentation_pdf,
        build_v1_bom_txt,
        build_v1_step_by_step,
        build_v2_bom_txt,
        build_v2_step_by_step,
    )

    prof = profile or {}
    v1_parts = hybrid_generator_parts()
    v2_parts = hybrid_generator_v2_parts()
    buf = io.BytesIO()
    v1_3mf = v2_3mf = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _, v1_3mf = await _export_parts_bundle(
            zf, "v1-storyboard", v1_parts, prof, "hybrid-generator-v1"
        )
        _, v2_3mf = await _export_parts_bundle(
            zf, "v2-improved", v2_parts, prof, "hybrid-generator-v2"
        )

        zf.writestr("pdf/hybrid-generator-presentation.pdf", build_hybrid_presentation_pdf(frames))
        zf.writestr("guides/v1-step-by-step.txt", build_v1_step_by_step(frames))
        zf.writestr("guides/v2-step-by-step.txt", build_v2_step_by_step())
        zf.writestr("guides/v1-bom.txt", build_v1_bom_txt())
        zf.writestr("guides/v2-bom.txt", build_v2_bom_txt())
        zf.writestr("guides/v1-print-order.txt", build_hybrid_print_order_txt())
        zf.writestr("guides/v2-print-order.txt", build_v2_print_order_txt())
        zf.writestr("preview-plan.txt", build_storyboard_preview_message(frames))
        zf.writestr("bom.txt", build_hybrid_bom_txt())
        zf.writestr("README.txt", _full_pack_readme(v1_3mf, v2_3mf, len(v1_parts), len(v2_parts)))

    name = "hybrid-generator-full-pack.zip"
    total_parts = len(v1_parts) + len(v2_parts)
    return buf.getvalue(), name, total_parts, (v1_3mf + v2_3mf) > 0


def _full_pack_readme(v1_3mf: int, v2_3mf: int, v1_n: int, v2_n: int) -> str:
    return (
        "Гибридный генератор — полный пакет v1 + v2\n"
        "==========================================\n\n"
        f"v1-storyboard: {v1_n} деталей, {v1_3mf} файлов 3MF (раскадровка «восьмёрка»)\n"
        f"v2-improved:   {v2_n} деталей, {v2_3mf} файлов 3MF (U-петля, рекомендуется)\n\n"
        "НАЧНИТЕ С:\n"
        "1. pdf/hybrid-generator-presentation.pdf — презентация и сравнение\n"
        "2. guides/v2-step-by-step.txt — если хотите быстрее увидеть результат\n"
        "   guides/v1-step-by-step.txt — если повторяете storyboard\n"
        "3. v2-improved/3mf/ или v1-storyboard/3mf/ → Bambu Studio → Печать\n\n"
        "Структура:\n"
        "• pdf/ — презентация\n"
        "• guides/ — пошаговые планы, BOM, print_order\n"
        "• v1-storyboard/ — 3mf, stl, scad, assembly.md\n"
        "• v2-improved/ — 3mf, stl, scad, assembly.md\n"
    )


def _pack_readme(stl_count: int, threed_count: int) -> str:
    return (
        "Гибридный электромагнитный генератор — пакет для печати\n"
        "========================================================\n\n"
        f"3MF (готово для Bambu Studio): {threed_count} файлов в 3mf/\n"
        f"STL (резерв): {stl_count} файлов в stl/\n"
        "SCAD (параметры): scad/\n\n"
        "КАК ПЕЧАТАТЬ:\n"
        "1. Откройте Bambu Studio\n"
        "2. File → Import → выберите 3mf/01-body_lower.3mf (и далее по print_order.txt)\n"
        "3. Проверьте материал (PETG / ASA для heater_mount)\n"
        "4. Для tube_clip и coil_bobbin — количество копий 6 и 2\n"
        "5. Нажмите Печать\n\n"
        "Файлы:\n"
        "• print_order.txt — порядок и настройки\n"
        "• bom.txt — что купить (не печатается)\n"
        "• assembly.md — сборка после печати\n"
        "• preview-plan.txt — полный план до печати\n"
    )
