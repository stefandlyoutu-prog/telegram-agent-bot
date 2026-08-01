"""Распознавание уже готовой сметы/КП (отправленной клиенту раньше другим способом) →
поля карточки сделки + позиции для презентации.

В отличие от bestpaints_reports.py (бланк замера → стены/проёмы), здесь на входе — готовый
документ с суммами (скрин Excel, Word/PDF-как-фото, рукописный прайс), а на выходе —
клиент, сумма/скидка, строки КП. Переиспользуем LLM-цепочку Kupi→Groq→Gemini из reports.py.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from oracle_bot.bestpaints_reports import (
    _report_chat,  # noqa: SLF001 — тот же провайдер-фолбэк, не дублируем
    _report_vision,  # noqa: SLF001
    decode_data_url,
    enhance_report_image,
    extract_plain_from_bytes,
)
from bot.services.vision import detect_mime, to_data_url

logger = logging.getLogger(__name__)

SYSTEM = """Ты оператор BestPaints (покраска деревянных домов). Тебе показывают готовую смету/КП,
которую менеджер отправил клиенту раньше другим способом (WhatsApp/Telegram/бумага) — до этой CRM.
Извлеки данные для карточки сделки и таблицу позиций. Отвечай ТОЛЬКО валидным JSON без markdown."""

USER_PROMPT = """Разбери смету / коммерческое предложение / прайс, который уже отправляли клиенту.

Правила:
- Суммы в рублях. Запятую → точка. Убирай пробелы-разделители тысяч (150 000 → 150000).
- Если итоговая сумма явно не написана — не выдумывай, оставь null (посчитаем как сумму строк).
- Скидка — в процентах. Если в документе скидка суммой в рублях, а не в % — оставь discountPct null,
  а сумму скидки не считай отдельно (просто не заполняй discountPct).
- Не выдумывай данные: если поле не найдено в документе — пустая строка / null и понизь confidence.
- title — короткое название объекта (по адресу или типу дома), если явно не написано в документе.
- lines[] — строки таблицы работ/материалов ровно как в документе (название, кол-во, ед., цена, сумма).
  Если сумма строки не указана — посчитай qty*price. Если qty/price не разделены — можно оставить null
  и заполнить только sum.
- warrantyYears — если в документе есть гарантия (например «гарантия 5 лет»).

Верни JSON строго такой схемы:
{
  "confidence": 0.0,
  "notes": "",
  "client": {"name": "", "phone": "", "address": ""},
  "title": "",
  "warrantyYears": null,
  "subtotal": null,
  "discountPct": null,
  "total": null,
  "lines": [
    {"name": "", "qty": null, "unit": "", "price": null, "sum": null}
  ]
}
"""


def _strip_json(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
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
        return x if x == x and x >= 0 else None  # noqa: PLR0124 — NaN check
    s = str(v).strip().replace(",", ".").replace(" ", "").replace("\u00a0", "")
    s = re.sub(r"[^\d.]+", "", s)
    if not s:
        return None
    try:
        x = float(s)
        return x if x >= 0 else None
    except ValueError:
        return None


def _str(v: Any, lim: int = 300) -> str:
    return str(v or "").strip()[:lim]


def normalize_estimate(raw: dict[str, Any]) -> dict[str, Any]:
    client_in = raw.get("client") if isinstance(raw.get("client"), dict) else {}
    lines_out: list[dict[str, Any]] = []
    for ln in raw.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        name = _str(ln.get("name"), 200)
        qty = _num(ln.get("qty"))
        price = _num(ln.get("price"))
        total = _num(ln.get("sum"))
        if not name and total is None:
            continue
        if total is None and qty is not None and price is not None:
            total = round(qty * price, 2)
        if qty is None:
            qty = 1.0
        if price is None and total is not None and qty:
            price = round(total / qty, 2)
        lines_out.append(
            {
                "name": name or "Позиция",
                "qty": qty if qty is not None else 1,
                "unit": _str(ln.get("unit") or "шт", 20),
                "price": price if price is not None else (total or 0),
                "sum": total if total is not None else round((qty or 1) * (price or 0), 2),
            }
        )

    subtotal = _num(raw.get("subtotal"))
    total = _num(raw.get("total"))
    lines_sum = round(sum(l["sum"] for l in lines_out), 2) if lines_out else None
    if subtotal is None:
        subtotal = lines_sum if lines_sum is not None else total
    if total is None:
        total = subtotal

    conf = _num(raw.get("confidence")) or 0
    return {
        "confidence": round(min(1.0, conf), 2),
        "notes": _str(raw.get("notes"), 1200),
        "client": {
            "name": _str(client_in.get("name"), 120),
            "phone": _str(client_in.get("phone"), 40),
            "address": _str(client_in.get("address"), 300),
        },
        "title": _str(raw.get("title"), 120),
        "warrantyYears": _num(raw.get("warrantyYears")),
        "subtotal": subtotal,
        "discountPct": _num(raw.get("discountPct")),
        "total": total,
        "lines": lines_out,
    }


async def parse_estimate_text(text: str, *, hint: str = "") -> dict[str, Any]:
    body = (text or "").strip()
    if len(body) < 10:
        raise ValueError("Слишком мало текста в смете")
    prompt = USER_PROMPT + f"\n\n--- ТЕКСТ СМЕТЫ / КП ---\n{body[:12000]}"
    if hint.strip():
        prompt += f"\n\nПодсказка / контекст: {hint.strip()[:800]}"
    raw_text = await _report_chat(prompt, system=SYSTEM)
    try:
        raw = json.loads(_strip_json(raw_text))
    except json.JSONDecodeError as e:
        logger.warning("estimate text JSON fail: %s | %s", e, (raw_text or "")[:300])
        raise ValueError("Модель вернула не JSON по тексту сметы") from e
    if not isinstance(raw, dict):
        raise ValueError("Неожиданный ответ распознавания сметы")
    return normalize_estimate(raw)


async def parse_estimate_image(image: bytes, *, hint: str = "") -> dict[str, Any]:
    if not image or len(image) < 200:
        raise ValueError("Пустое или слишком маленькое изображение сметы")
    if len(image) > 12 * 1024 * 1024:
        raise ValueError("Файл больше 12 МБ — сожмите фото сметы")
    enhanced = enhance_report_image(image)
    data_url = to_data_url(enhanced, detect_mime(enhanced))
    prompt = USER_PROMPT
    if hint.strip():
        prompt += f"\n\nПодсказка / контекст: {hint.strip()[:800]}"
    raw_text = await _report_vision(prompt, data_url, system=SYSTEM)
    try:
        raw = json.loads(_strip_json(raw_text))
    except json.JSONDecodeError as e:
        logger.warning("estimate image JSON fail: %s | %s", e, (raw_text or "")[:400])
        raise ValueError("Модель вернула не JSON по фото сметы") from e
    if not isinstance(raw, dict):
        raise ValueError("Неожиданный ответ распознавания сметы")
    return normalize_estimate(raw)


def merge_estimates(*parts: dict[str, Any]) -> dict[str, Any]:
    """Склеить части, распознанные из нескольких файлов (страницы одной сметы / несколько фото).

    Строки (lines) конкатенируются по всем частям (а не берётся «самый длинный» список) —
    иначе позиции со страницы 2 многостраничной сметы терялись бы, если на странице 1
    случайно распозналось больше строк. Точные дубли (например, пересъёмка того же листа)
    отфильтровываются по (название, кол-во, цена, сумма).
    """
    parts = [p for p in parts if isinstance(p, dict)]
    if not parts:
        return normalize_estimate({})
    base = dict(parts[0])
    all_lines: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for p in parts:
        for ln in p.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            key = (
                str(ln.get("name") or "").strip().lower(),
                ln.get("qty"),
                ln.get("price"),
                ln.get("sum"),
            )
            if key in seen:
                continue
            seen.add(key)
            all_lines.append(ln)
    base["lines"] = all_lines
    for p in parts[1:]:
        a = dict(base.get("client") or {})
        for k, v in (p.get("client") or {}).items():
            if v and not a.get(k):
                a[k] = v
        base["client"] = a
        for k in ("title", "warrantyYears", "subtotal", "discountPct", "total"):
            if base.get(k) in (None, "") and p.get(k) not in (None, ""):
                base[k] = p.get(k)
        notes = [base.get("notes") or "", p.get("notes") or ""]
        base["notes"] = "\n".join(x for x in notes if x).strip()[:1200]
        base["confidence"] = max(float(base.get("confidence") or 0), float(p.get("confidence") or 0))
    return normalize_estimate(base)


async def parse_estimate_bundle(
    *,
    images: list[bytes] | None = None,
    texts: list[str] | None = None,
    hint: str = "",
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    errors: list[str] = []
    for img in images or []:
        try:
            parts.append(await parse_estimate_image(img, hint=hint))
        except Exception as e:
            errors.append(f"фото: {e}")
            logger.warning("estimate image part fail: %s", e)
    combined_text = "\n\n---\n\n".join(t.strip() for t in (texts or []) if t and t.strip())
    if combined_text:
        try:
            parts.append(await parse_estimate_text(combined_text, hint=hint))
        except Exception as e:
            errors.append(f"текст: {e}")
            logger.warning("estimate text part fail: %s", e)
    if not parts:
        raise ValueError(
            "Не удалось распознать смету. "
            + ("; ".join(errors) if errors else "Нужно фото/скан сметы, PDF-как-фото, DOCX или текст.")
        )
    result = merge_estimates(*parts)
    if errors:
        note = "Часть файлов не распознана AI: " + "; ".join(errors)[:300]
        result["notes"] = f"{result.get('notes') or ''}\n{note}".strip()[:1200]
    if not result["lines"] and not result["total"] and not result["client"].get("name"):
        raise ValueError("Не удалось извлечь данные из сметы — проверьте фото/файл или заполните вручную")
    return result


__all__ = [
    "decode_data_url",
    "extract_plain_from_bytes",
    "merge_estimates",
    "normalize_estimate",
    "parse_estimate_bundle",
    "parse_estimate_image",
    "parse_estimate_text",
]
