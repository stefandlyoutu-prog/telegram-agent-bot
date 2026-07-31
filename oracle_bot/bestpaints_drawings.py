"""Распознавание чертежей заказчика → структура замера BestPaints."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bot.services.vision import detect_mime, to_data_url
from oracle_bot.kupi_direct import vision as kupi_vision

logger = logging.getLogger(__name__)

SYSTEM = """Ты инженер-сметчик BestPaints (покраска деревянных домов).
По фото/скану чертежа, фасада, плана или экспликации извлеки размеры для замера.
Отвечай ТОЛЬКО валидным JSON без markdown и комментариев."""

USER_PROMPT = """Разбери чертёж деревянного дома / фасада / плана.

Правила:
- Размеры в метрах (если мм — дели на 1000, если см — на 100).
- Стены фасада: label на русском (Фасад А, Север, Торцы и т.п.), length, height, shape (rect|gable|trap).
- Для фронтона: ridge = высота до конька, height = высота стен.
- Проёмы: wallLabel (как у стены), label, width, height, kind (window|door|other).
- Если размер нечитаем — не выдумывай точное число, поставь null и confidence ниже.
- notes — кратко что видно на чертеже.
- scaleHint — если есть масштабная линейка или подпись масштаба.

Верни JSON строго такой схемы:
{
  "confidence": 0.0,
  "drawingType": "elevation|plan|section|photo|mixed|unknown",
  "notes": "",
  "scaleHint": "",
  "suggestedHouseType": "new|non_film|film|",
  "suggestedMaterial": "beam|log|hand_log|imit|block|board|other|",
  "walls": [
    {"label":"Фасад А","length":12.0,"height":3.0,"ridge":null,"height2":null,"shape":"rect","zone":"facade","confidence":0.8}
  ],
  "openings": [
    {"wallLabel":"Фасад А","label":"Окно 1","width":1.2,"height":1.4,"kind":"window","confidence":0.7}
  ],
  "extras": {
    "soffitArea": null,
    "fasciaArea": null,
    "endsLength": null,
    "overhangArea": null
  }
}
"""


def _strip_json(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    # вырезать первый объект
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        return t[start : end + 1]
    return t


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if x > 0 else None
    s = str(v).strip().replace(",", ".").replace(" ", "")
    s = re.sub(r"[^\d.]+$", "", s)
    try:
        x = float(s)
        return x if x > 0 else None
    except ValueError:
        return None


def normalize_parse(raw: dict[str, Any]) -> dict[str, Any]:
    walls_out = []
    for w in raw.get("walls") or []:
        if not isinstance(w, dict):
            continue
        length = _num(w.get("length"))
        height = _num(w.get("height"))
        if length is None and height is None and _num(w.get("areaManual")) is None:
            continue
        shape = str(w.get("shape") or "rect").lower()
        if shape not in ("rect", "gable", "trap", "custom"):
            shape = "rect"
        walls_out.append(
            {
                "label": str(w.get("label") or f"Стена {len(walls_out) + 1}")[:80],
                "length": length,
                "height": height,
                "ridge": _num(w.get("ridge")),
                "height2": _num(w.get("height2")),
                "shape": shape,
                "zone": "interior" if str(w.get("zone") or "").lower() == "interior" else "facade",
                "confidence": float(w.get("confidence") or 0) or 0.5,
            }
        )

    openings_out = []
    for o in raw.get("openings") or []:
        if not isinstance(o, dict):
            continue
        width = _num(o.get("width"))
        height = _num(o.get("height"))
        if width is None or height is None:
            continue
        openings_out.append(
            {
                "wallLabel": str(o.get("wallLabel") or "")[:80],
                "label": str(o.get("label") or "Проём")[:80],
                "width": width,
                "height": height,
                "kind": str(o.get("kind") or "window")[:40],
                "confidence": float(o.get("confidence") or 0) or 0.5,
            }
        )

    extras_in = raw.get("extras") if isinstance(raw.get("extras"), dict) else {}
    extras = {
        "soffitArea": _num(extras_in.get("soffitArea")),
        "fasciaArea": _num(extras_in.get("fasciaArea")),
        "endsLength": _num(extras_in.get("endsLength")),
        "overhangArea": _num(extras_in.get("overhangArea")),
    }

    conf = _num(raw.get("confidence")) or 0
    if walls_out:
        conf = max(conf, sum(w["confidence"] for w in walls_out) / len(walls_out))

    return {
        "confidence": round(min(1.0, conf), 2),
        "drawingType": str(raw.get("drawingType") or "unknown")[:40],
        "notes": str(raw.get("notes") or "")[:800],
        "scaleHint": str(raw.get("scaleHint") or "")[:200],
        "suggestedHouseType": str(raw.get("suggestedHouseType") or "")[:20],
        "suggestedMaterial": str(raw.get("suggestedMaterial") or "")[:20],
        "walls": walls_out,
        "openings": openings_out,
        "extras": extras,
    }


async def parse_drawing_bytes(image: bytes, *, hint: str = "") -> dict[str, Any]:
    if not image or len(image) < 200:
        raise ValueError("Пустое или слишком маленькое изображение")
    if len(image) > 12 * 1024 * 1024:
        raise ValueError("Файл больше 12 МБ — сожмите чертёж")

    data_url = to_data_url(image, detect_mime(image))
    user = USER_PROMPT
    if hint.strip():
        user += f"\n\nПодсказка замерщика: {hint.strip()[:500]}"

    text = await kupi_vision(user, data_url, system=SYSTEM, temperature=0.1)
    try:
        raw = json.loads(_strip_json(text))
    except json.JSONDecodeError as e:
        logger.warning("drawing parse JSON fail: %s | %s", e, (text or "")[:400])
        raise ValueError("Модель вернула не JSON — попробуйте более чёткий чертёж") from e
    if not isinstance(raw, dict):
        raise ValueError("Неожиданный ответ распознавания")

    result = normalize_parse(raw)
    if not result["walls"]:
        raise ValueError(
            "Не удалось найти размеры стен на чертеже. "
            "Загрузите фасад с размерами или введите вручную / через масштаб."
        )
    return result
