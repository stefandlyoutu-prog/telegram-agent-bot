"""Профиль 3D-печати пользователя (принтер, материал, сопло)."""

import json
import re
from typing import Any, Dict, List, Optional

# Известные принтеры → примерный объём стола (мм)
PRINTER_BEDS: Dict[str, tuple] = {
    "p2s": (256, 256, 256),
    "p1s": (256, 256, 256),
    "x1": (256, 256, 256),
    "x1c": (256, 256, 256),
    "a1": (256, 256, 256),
    "a1 mini": (180, 180, 180),
    "bambu": (256, 256, 256),
    "ender": (220, 220, 250),
    "prusa": (250, 210, 210),
    "saturn": (218, 123, 220),
    "mars": (143, 89, 175),
}


def default_profile_from_config() -> Dict[str, Any]:
    from bot.config import (
        DEFAULT_AMS,
        DEFAULT_MATERIAL,
        DEFAULT_NOZZLE_MM,
        DEFAULT_PRINTER,
        DEFAULT_SLICER,
    )

    p = empty_profile()
    if DEFAULT_PRINTER:
        p["printer"] = DEFAULT_PRINTER
    if DEFAULT_MATERIAL:
        p["material"] = DEFAULT_MATERIAL
    if DEFAULT_NOZZLE_MM:
        p["nozzle_mm"] = DEFAULT_NOZZLE_MM
    if DEFAULT_SLICER:
        p["slicer"] = DEFAULT_SLICER
    if DEFAULT_AMS:
        p["ams"] = True
    return p


def ensure_profile(
    base: Optional[Dict[str, Any]],
    extra_text: str = "",
) -> Dict[str, Any]:
    """Профиль для печати: сохранённый + из текста + дефолты из .env."""
    p = merge_profiles(default_profile_from_config(), base or {})
    if extra_text:
        p = merge_profiles(p, parse_print_profile(extra_text))
    if not (p.get("printer") or "").strip():
        p["printer"] = "Bambu Lab P2S"
    if not (p.get("material") or "").strip():
        p["material"] = "PLA"
    if not p.get("nozzle_mm"):
        p["nozzle_mm"] = 0.4
    if not (p.get("slicer") or "").strip():
        p["slicer"] = "Bambu Studio"
    return p


def empty_profile() -> Dict[str, Any]:
    return {
        "printer": "",
        "material": "",
        "nozzle_mm": 0.4,
        "slicer": "",
        "notes": "",
    }


def parse_print_profile(text: str) -> Dict[str, Any]:
    """Извлечь настройки печати из текста / подписи."""
    p = empty_profile()
    if not text:
        return p
    t = text.lower()

    m = re.search(
        r"(bambu\s*lab\s*)?(p[12]s|x1c?|a1\s*mini|a1)\b|bambu|ender\s*3|prusa|saturn|mars|elegoo",
        t,
        re.I,
    )
    if m:
        p["printer"] = m.group(0).strip()

    m = re.search(r"\b(pla|petg|abs|asa|tpu|nylon|resin)\b", t, re.I)
    if m:
        p["material"] = m.group(1).upper()

    m = re.search(r"сопло\s*[:=]?\s*0?\.(\d)|nozzle\s*[:=]?\s*0?\.(\d)|0\.(2|4|6|8)\s*мм", t)
    if m:
        val = next(g for g in m.groups() if g)
        p["nozzle_mm"] = float(f"0.{val}")

    if re.search(r"bambu\s*studio|бамбу\s*студио", t, re.I):
        p["slicer"] = "Bambu Studio"

    if re.search(r"\bams\b|ams\s*pro|амс", t, re.I):
        p["ams"] = True

    m = re.search(
        r"(?:высот[аы]|размер|высотой)\s*[:=]?\s*(\d{1,4})\s*мм|(\d{1,4})\s*мм\s*высот",
        t,
        re.I,
    )
    if m:
        p["target_height_mm"] = float(next(g for g in m.groups() if g))

    m = re.search(r"(?:допуск|точност[ьи])\s*[:=]?\s*[±+\-]?\s*(0?[.,]\d+|\d{1,2})\s*мм", t, re.I)
    if m:
        p["tolerance_mm"] = float(m.group(1).replace(",", "."))

    m = re.search(r"(?:масштаб|scale)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*[:/]\s*(\d+(?:[.,]\d+)?)", t, re.I)
    if m:
        p["scale"] = f"{m.group(1)}:{m.group(2)}"

    return p


def merge_profiles(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = empty_profile()
    out.update({k: v for k, v in (base or {}).items() if v})
    for k, v in (extra or {}).items():
        if v:
            out[k] = v
    return out


def missing_fields(profile: Dict[str, Any]) -> List[str]:
    miss: List[str] = []
    if not (profile.get("printer") or "").strip():
        miss.append("printer")
    if not (profile.get("material") or "").strip():
        miss.append("material")
    return miss


def format_profile(profile: Dict[str, Any]) -> str:
    p = profile or empty_profile()
    lines = []
    if p.get("printer"):
        lines.append(f"Принтер: {p['printer']}")
    if p.get("material"):
        lines.append(f"Материал: {p['material']}")
    if p.get("nozzle_mm"):
        lines.append(f"Сопло: {p['nozzle_mm']} мм")
    if p.get("slicer"):
        lines.append(f"Слайсер: {p['slicer']}")
    if p.get("ams"):
        lines.append("AMS: да")
    if p.get("target_height_mm"):
        lines.append(f"Целевой размер: {p['target_height_mm']} мм")
    if p.get("tolerance_mm"):
        lines.append(f"Допуск: ±{p['tolerance_mm']} мм")
    if p.get("scale"):
        lines.append(f"Масштаб: {p['scale']}")
    if p.get("notes"): 
        lines.append(f"Заметки: {p['notes']}")
    return "\n".join(lines) if lines else "не задан"


def format_questionnaire() -> str:
    return (
        "🖨 Чтобы сделать STL под вашу печать, ответьте одним сообщением:\n\n"
        "1. **Принтер** (например: Bambu Lab P2S)\n"
        "2. **Материал** (PLA / PETG / ABS …)\n"
        "3. **Сопло** (0.4 мм — если не знаете, так и напишите)\n"
        "4. **Слайсер** (Bambu Studio / Orca / Cura)\n"
        "5. **Размер модели в мм** — если знаете точную высоту фигурки\n"
        "6. **Допуск/масштаб** — если важно точно (например: допуск 0.2 мм, масштаб 1:1)\n\n"
        "Пример:\n"
        "`Bambu P2S, PETG, сопло 0.4, Bambu Studio, высота 120 мм, допуск 0.2 мм, масштаб 1:1`\n\n"
        "Сохраню настройки — в следующий раз спрашивать не буду.\n"
        "Команда `/printer` — посмотреть или изменить профиль."
    )


def profile_to_json(profile: Dict[str, Any]) -> str:
    return json.dumps(profile or empty_profile(), ensure_ascii=False)


def profile_from_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return empty_profile()
    try:
        data = json.loads(raw)
        return merge_profiles(empty_profile(), data if isinstance(data, dict) else {})
    except json.JSONDecodeError:
        return empty_profile()
