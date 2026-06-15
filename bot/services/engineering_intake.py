"""Engineering preflight for risky 3D-print requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PrinterSpec:
    key: str
    label: str
    bed_mm: Tuple[int, int, int]
    process: str = "FDM"


PRINTER_SPECS: tuple[PrinterSpec, ...] = (
    PrinterSpec("bambu_p2s", "Bambu Lab P2S", (256, 256, 256)),
    PrinterSpec("bambu_p1s", "Bambu Lab P1S", (256, 256, 256)),
    PrinterSpec("bambu_x1c", "Bambu Lab X1C", (256, 256, 256)),
    PrinterSpec("bambu_a1", "Bambu Lab A1", (256, 256, 256)),
    PrinterSpec("bambu_a1_mini", "Bambu Lab A1 mini", (180, 180, 180)),
    PrinterSpec("ender_3", "Creality Ender 3 class", (220, 220, 250)),
    PrinterSpec("prusa_mk3_mk4", "Prusa MK3/MK4 class", (250, 210, 210)),
    PrinterSpec("saturn_resin", "Elegoo Saturn resin class", (218, 123, 220), "RESIN"),
    PrinterSpec("mars_resin", "Elegoo Mars resin class", (143, 89, 175), "RESIN"),
)


MATERIAL_NOTES: Dict[str, str] = {
    "PLA": "обычный FDM: 0.20 мм слой, 2-3 периметра, стандартные зазоры 0.25-0.35 мм",
    "PETG": "больше stringing и липкость: для шарниров лучше зазор 0.35-0.45 мм",
    "ABS": "усадка/warping: закрытая камера, brim, крупные модели лучше делить",
    "ASA": "как ABS, но UV-стойкий: закрытая камера, brim, учитывать усадку",
    "NYLON": "прочный, но гигроскопичный: сушить, зазоры 0.4+ мм, лучше закруглять острые углы",
    "TPU": "гибкий: не для точных шарниров/осей, нужна малая скорость и простая геометрия",
    "RESIN": "не FDM: нужны hollowing, drain holes, ориентация, смоляные поддержки и промывка/досветка",
}


def printer_spec_from_text(text: str, profile: Optional[Dict[str, Any]] = None) -> Optional[PrinterSpec]:
    raw = f"{text or ''} {(profile or {}).get('printer') or ''}".lower()
    patterns = (
        (r"a1\s*mini", "bambu_a1_mini"),
        (r"\bp2s\b|п2с", "bambu_p2s"),
        (r"\bp1s\b", "bambu_p1s"),
        (r"\bx1c?\b", "bambu_x1c"),
        (r"\ba1\b|bambu\s+lab\s+a1", "bambu_a1"),
        (r"bambu|бамбу", "bambu_p2s"),
        (r"ender\s*3", "ender_3"),
        (r"prusa|mk3|mk4", "prusa_mk3_mk4"),
        (r"saturn|сатурн", "saturn_resin"),
        (r"mars|марс", "mars_resin"),
    )
    by_key = {p.key: p for p in PRINTER_SPECS}
    for pat, key in patterns:
        if re.search(pat, raw, re.I):
            return by_key[key]
    return None


def requested_dimensions_mm(text: str) -> Dict[str, float]:
    t = text or ""
    dims: Dict[str, float] = {}
    patterns = (
        ("length_mm", r"(?:длин[ауы]?|length)\D{0,24}(\d+(?:[,.]\d+)?)\s*(см|мм|м)\b"),
        ("height_mm", r"(?:высот[ауы]?|height|рост)\D{0,24}(\d+(?:[,.]\d+)?)\s*(см|мм|м)\b"),
        ("wingspan_mm", r"(?:размах|wingspan)\D{0,24}(\d+(?:[,.]\d+)?)\s*(см|мм|м)\b"),
        ("width_mm", r"(?:ширин[ауы]?|width)\D{0,24}(\d+(?:[,.]\d+)?)\s*(см|мм|м)\b"),
    )
    for key, pat in patterns:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        val = float(m.group(1).replace(",", "."))
        unit = m.group(2).lower()
        if unit == "см":
            val *= 10.0
        elif unit == "м":
            val *= 1000.0
        dims[key] = val
    if re.search(r"в\s+рост|ростом\s+с\s+человек|человеческ[ийого]+\s+рост", t, re.I):
        dims.setdefault("height_mm", 1700.0)
    return dims


def mechanical_motion_requested(text: str) -> bool:
    t = text or ""
    motion = re.search(r"шевел|подвиж|двига|складыва|убира|враща|крут|ось|шарнир|hinge|axle", t, re.I)
    mechanism = re.search(
        r"шасси|шосси|кол[её]с|wheel|landing\s*gear|gear|ось|шарнир|hinge|axle|"
        r"лопаст|пропеллер|винт|fan|blade|механизм|двер|крыл.*складыв|print[-\s]?in[-\s]?place",
        t,
        re.I,
    )
    return bool(motion and mechanism)


def mechanical_motion_details_provided(text: str) -> bool:
    t = text or ""
    wheel_axis = bool(re.search(r"кол[её]с.{0,50}(ось|вращ|крут)|ось.{0,50}кол[её]с", t, re.I))
    retracting_gear = bool(re.search(r"(шасси|шосси|landing\s*gear).{0,50}(складыва|убира|retract)", t, re.I))
    spinning_blades = bool(re.search(r"(лопаст|пропеллер|винт|fan|blade).{0,50}(вращ|крут|детал)", t, re.I))
    return wheel_axis or retracting_gear or spinning_blades


def engineering_drawing_requested(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(r"черт[её]ж|blueprint|cad|эскиз|технич.{0,16}рисун|схем[ауы]|размер[аы].{0,20}фото", t, re.I)
        and re.search(r"3d|3д|stl|3mf|проект|детал|печа|принтер|bambu|бамбу|модель", t, re.I)
    )


def creative_design_requested(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(r"придумай|сам.{0,12}придум|на\s+твой\s+вкус|иде[яю]|концепт", t, re.I)
        and re.search(r"фигур|игруш|детал|модель|3d|3д|stl|3mf|печа", t, re.I)
    )


def looks_like_engineering_correction(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(
            r"нет|не\s+так|поправ|измени|лучше|друг|вместо|материал|принтер|сопло|"
            r"pla|petg|abs|asa|nylon|resin|нейлон|смол|размер|длин|высот|ширин|"
            r"шасси|шосси|кол[её]с|лопаст|пропеллер|вращ|складыва|убира|шарнир|ось|ams|амс",
            t,
            re.I,
        )
        and len(t.strip()) > 6
    )


def merge_engineering_correction(original: str, correction: str) -> str:
    return (
        f"{original.strip()}\n\n"
        f"Уточнение пользователя: {correction.strip()}\n"
        "Используй уточнение как более приоритетное, если оно противоречит старому запросу."
    ).strip()


def print_request(text: str) -> bool:
    return bool(
        re.search(
            r"3d|3д|stl|3mf|bambu|бамбу|печа|принтер|слайсер|модель|фигур|черт[её]ж|cad",
            text or "",
            re.I,
        )
    )


def engineering_risks(text: str, profile: Optional[Dict[str, Any]] = None) -> List[str]:
    if not print_request(text):
        return []
    t = text or ""
    p = profile or {}
    risks: List[str] = []
    material = str(p.get("material") or "").upper()
    m = re.search(r"\b(pla|petg|abs|asa|tpu|nylon|resin)\b|нейлон|смол", t, re.I)
    if m:
        material = "NYLON" if re.search(r"нейлон|nylon", m.group(0), re.I) else "RESIN" if re.search(r"смол|resin", m.group(0), re.I) else m.group(0).upper()
    if mechanical_motion_requested(t):
        risks.append("mechanical_motion")
    if engineering_drawing_requested(t):
        risks.append("engineering_drawing")
    if creative_design_requested(t):
        risks.append("creative_brief")
    dims = requested_dimensions_mm(t)
    if any(v > 260 for v in dims.values()) or re.search(r"больш[а-я]*|огромн|ростом\s+с\s+человек", t, re.I):
        risks.append("oversize_or_split")
    spec = printer_spec_from_text(t, p)
    if spec is None and re.search(r"принтер|printer|bambu|ender|prusa|смол|resin", t, re.I):
        risks.append("unknown_printer")
    if spec and dims:
        bed = spec.bed_mm
        if max(dims.values()) > max(bed) * 0.95:
            risks.append("does_not_fit_bed")
    if material in {"ABS", "ASA", "NYLON", "TPU", "RESIN"}:
        risks.append(f"material_{material.lower()}")
    if re.search(r"\bams\b|амс|разн.{0,12}цвет|несколько\s+цвет|двигател.*цвет|хвост.*цвет", t, re.I):
        risks.append("ams_or_multicolor")
    return list(dict.fromkeys(risks))


def needs_engineering_intake(text: str, profile: Optional[Dict[str, Any]] = None) -> bool:
    return bool(engineering_risks(text, profile))


def render_engineering_intake(text: str, profile: Optional[Dict[str, Any]] = None) -> str:
    p = profile or {}
    spec = printer_spec_from_text(text, p)
    dims = requested_dimensions_mm(text)
    material = str(p.get("material") or "PLA").upper()
    m = re.search(r"\b(pla|petg|abs|asa|tpu|nylon|resin)\b|нейлон|смол", text or "", re.I)
    if m:
        material = "NYLON" if re.search(r"нейлон|nylon", m.group(0), re.I) else "RESIN" if re.search(r"смол|resin", m.group(0), re.I) else m.group(0).upper()
    lines = ["Проверю как инженер перед генерацией. Я понял так:"]
    lines.append(f"Принтер: {spec.label if spec else (p.get('printer') or 'не указан')}")
    if spec:
        lines.append(f"Стол/область печати: {spec.bed_mm[0]}x{spec.bed_mm[1]}x{spec.bed_mm[2]} мм, процесс {spec.process}")
    lines.append(f"Материал: {material} ({MATERIAL_NOTES.get(material, 'нужны параметры материала/профиля')})")
    if dims:
        readable = ", ".join(f"{k.replace('_mm', '')}={v:.0f} мм" for k, v in dims.items())
        lines.append(f"Размеры из запроса: {readable}")
    if mechanical_motion_requested(text):
        lines.append("Механика: нужны отдельные детали, оси/шарниры и зазоры, не цельный Meshy STL.")
        if mechanical_motion_details_provided(text):
            lines.append("Механика уточнена: колёса/лопасти/шасси считаю отдельными узлами с осями, посадками и зазорами.")
        else:
            lines.append("Уточните: деталь должна вращаться на оси, складываться, или просто быть отдельной после сборки?")
    if engineering_drawing_requested(text):
        lines.append("Чертёж/эскиз: сначала читаю размеры и ограничения, потом собираю инженерный STL/3MF/ZIP.")
        lines.append("Если на чертеже есть мелкие размеры, лучше прислать его как файл/PDF без сжатия.")
    if creative_design_requested(text):
        lines.append("Креативный бриф: бот может сам предложить форму, но зафиксирует допущения перед генерацией.")
    risks = engineering_risks(text, p)
    if risks:
        lines.append(f"Риски: {', '.join(risks)}")
    lines.append("Если всё верно, ответьте: «да, верно, запускай». Если нет — уточните принтер/материал/размер/механику.")
    return "\n".join(lines)
