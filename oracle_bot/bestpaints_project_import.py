"""Распознавание проекта дома (архитектурная документация: планы этажей, фасады/развёртки стен,
кровля, разрезы — обычно PDF из ArchiCAD/AutoCAD/аналогов, иногда фото листов) → поля замера BestPaints.

В отличие от bestpaints_reports.py (бланк замерщика → стены/проёмы «с натуры») и
bestpaints_estimate_import.py (готовая смета с суммами), здесь на входе — проектная документация ДО
замера: клиента/телефона там обычно нет, но почти всегда есть посчитанные площади каждой стены/фасада
(программа проектирования сама подписывает лист «СтенаNN — NN.NN м²»). Это даёт возможность собрать
черновой список плоскостей под покраску без выезда замерщика — дальше лидоруб/замерщик дозаполняют
материал, состояние покрытия и клиента, а окончательные размеры проверяются на месте.

Схема результата — та же, что у bestpaints_reports.py (client/building/site/measure/walls/...),
поэтому переиспользуем normalize_report/merge_reports и весь фронтенд-код (applyReportParse) без
дублирования.
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
    merge_reports,
    normalize_report,
)
from bot.services.vision import detect_mime, to_data_url

logger = logging.getLogger(__name__)

SYSTEM = """Ты инженер-сметчик BestPaints (покраска деревянных домов).
Тебе показывают проектную документацию дома (планы этажей, развёртки/фасады стен, кровлю, разрезы —
обычно экспорт из архитектурной CAD-программы), а не бланк замерщика и не смету.
Нужно вытащить площади стен/фасадов и общий контекст объекта для черновой сметы на покраску,
до выезда замерщика. Отвечай ТОЛЬКО валидным JSON без markdown."""

USER_PROMPT = """Разбери проект дома (архитектурную документацию) для черновой заявки на покраску.

Про такие проекты важно знать:
- Обычно это многостраничный документ: обложка/план участка, планы этажей (комнаты с площадями в м²),
  разрезы/сечения (высоты в мм), план кровли (площади скатов в м²), список стен/фасадов
  («Стена01», «Стена02», …, «СтенаА», «СтенаБ», … или похоже), и для КАЖДОЙ стены — отдельный лист
  «развёртки» с её ИМЕНЕМ и уже посчитанной ПЛОЩАДЬЮ в м² (например «Стена01 \\n 26.33м2»).
- Именно эти подписи «имя стены + площадь в м²» — главное, что нужно найти. Они почти всегда идут
  рядом (имя стены на одной строке/рядом, площадь — сразу после, с «м2» или «м²»). Собери ВСЕ такие
  пары, даже если стен много (10–20 и больше для большого дома).
- Площади комнат на планах этажей (например «Кухня-Столовая 23.80м2») — это площадь ПОЛА, не стены.
  Не путай их со стенами: они идут в notes (для контекста метража дома), а не в walls[].
- Площадь кровли/скатов — тоже НЕ стена. Упомяни суммарно в notes (может понадобиться для подшивы/
  свесов), в walls[] не добавляй.
- Количество листов «План N этажа» → этажность дома — укажи в notes.
- Клиента (имя/телефон) в проектах обычно НЕТ — не выдумывай, оставляй пустым.
- Материал дома (брус/блок-хаус/бревно и т.п.) сама документация обычно явно словом не называет —
  ставь material только если слово прямо есть в тексте (например «брус», «блок-хаус», «оцилиндрованное
  бревно»). Слово «венец» (венцы) — это про сруб/брусовые дома, но само по себе не доказывает точный
  материал обшивки — просто упомяни в notes как подсказку для оператора, а material оставь пустым, если
  не сказано прямо.
- Каждой стене: label = точное имя со стены/листа (например «Стена01», «СтенаА»); areaManual = площадь
  в м²; shape = "custom" (площадь уже посчитана, длина/высота не нужны). zone = "facade" почти всегда
  (развёртки в таких проектах — это наружные стены/фасады). Ставь zone = "interior" ТОЛЬКО если на листе
  прямо написано, что это внутренняя перегородка/стена помещения (например подпись «перегородка»,
  «внутренняя стена», лист явно про интерьер комнаты) — в обычных проектах такого почти не бывает.
- В проектной документации обычно НЕТ размеров проёмов (окна/двери), длины торцов/венцов, площади подшивы,
  длины водостока/отливов/наличников — этого не выдумывай, оставляй пустым (openings = [], эти поля стены
  не заполняй). Площадь стены в проекте — уже итоговая площадь под покраску, без отдельного вычета проёмов.
  Всё это (проёмы, торцы, подшива, отливы, наличники) добавит замерщик на месте, калькулятор досчитает
  по тарифам BestPaints сам, когда эти поля заполнят в конструкторе.
- Если на одном листе несколько похожих подписей с площадью (например план стены и повторно в
  спецификации) — не дублируй, возьми площадь один раз на стену.
- confidence по каждой стене — насколько уверенно нашлась пара имя+площадь (0.5–0.95).

Верни JSON строго такой схемы (как в отчёте замерщика — те же поля, чтобы легко собрать замер):
{
  "confidence": 0.0,
  "sourceType": "drawing",
  "notes": "этажность, площадь комнат по этажам, площадь/тип кровли, любые текстовые подсказки по материалу",
  "client": {"name": "", "phone": "", "address": "", "surveyor": ""},
  "building": {
    "name": "",
    "material": "beam|log|hand_log|imit|block|board|other|",
    "materialSize": "",
    "houseType": "",
    "condition": "",
    "removalDifficulty": "",
    "colors": "",
    "oldCoatingNote": "",
    "heightRidge": null
  },
  "site": {"startWhen": "", "workHours": "", "powerFrom": "", "housing": "", "toilet": "", "shower": "", "water": "", "notes": ""},
  "attention": {},
  "extrasQty": {},
  "walls": [
    {"label": "Стена01", "areaManual": 26.33, "shape": "custom", "zone": "facade", "note": "", "confidence": 0.9}
  ],
  "openings": [],
  "measure": {"notes": ""}
}
"""


_WALL_NAME = r"Стена(?:[0-9]{1,3}|[А-ЯЁ]{1,3})"
# ищем «имя стены» + «площадь м²» независимо от того, разделены ли они пробелом или переносом строки —
# в разных PDF-экспортёрах порядок токенов на странице «склеивается» по-разному.
_WALL_AREA_RE = re.compile(
    rf"({_WALL_NAME})\s*\n?\s*(\d{{1,4}}(?:[.,]\d{{1,2}})?)\s*м[²2]",
    re.UNICODE,
)


def extract_wall_area_candidates(text: str) -> list[dict[str, Any]]:
    """Детерминированный regex-проход: находит все пары «имя стены + площадь м²» в тексте проекта.

    Служит подсказкой для LLM и страховкой — если модель упустит стену, но regex её нашёл,
    добираем её отдельно (см. normalize_project), чтобы данные с чертежа не терялись.
    """
    seen: dict[str, float] = {}
    order: list[str] = []
    labels: dict[str, str] = {}
    for m in _WALL_AREA_RE.finditer(text or ""):
        label = m.group(1).strip()
        try:
            area = float(m.group(2).replace(",", "."))
        except ValueError:
            continue
        if area <= 0 or area > 500:
            continue
        key = label.lower()
        if key not in seen:
            # если подпись повторилась с другой площадью — оставляем первую (обычно она на «своём» листе)
            order.append(key)
            seen[key] = area
            labels[key] = label
    return [{"label": labels[k], "area": seen[k]} for k in order]


_wall_candidates = extract_wall_area_candidates


def _prefilter_project_text(text: str, *, limit: int = 40000) -> str:
    """Оставляем строки с кириллицей/подписями площадей, выкидываем «шум» — цепочки размеров в мм
    (окна/двери/раскладка венцов), которых в экспорте CAD в разы больше, чем полезного текста.
    Так в промпт помещается весь список стен даже у проекта на 30+ листов.

    Дедуп только СОСЕДНИХ повторов (не глобальный!) — иначе «Стена01» из общего списка на плане
    «съедает» повторное «Стена01» на её же листе развёртки и рвётся пара имя→площадь, на которой
    держится вся логика поиска стен.
    """
    has_signal = re.compile(r"[а-яА-ЯёЁ]|м[²2]\b")
    out: list[str] = []
    prev = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or not has_signal.search(line):
            continue
        if line == prev:
            continue
        out.append(line)
        prev = line
    filtered = "\n".join(out)
    return filtered[:limit]


def normalize_project(raw: dict[str, Any], *, wall_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    result = normalize_report(raw if isinstance(raw, dict) else {})
    result["sourceType"] = result.get("sourceType") or "drawing"
    if wall_candidates:
        have = {str(w.get("label") or "").strip().lower() for w in result.get("walls") or []}
        added = 0
        for cand in wall_candidates:
            label = str(cand.get("label") or "").strip()
            key = label.lower()
            if not label or key in have:
                continue
            area = cand.get("area")
            try:
                area = round(float(area), 2)
            except (TypeError, ValueError):
                continue
            if area <= 0:
                continue
            result["walls"].append(
                {
                    "label": label,
                    "length": None,
                    "height": None,
                    "ridge": None,
                    "height2": None,
                    "areaManual": area,
                    "shape": "custom",
                    "zone": "facade",
                    "note": "найдено автоматически по подписи на листе проекта",
                    "endsLength": None,
                    "endsCount": None,
                    "soffitArea": None,
                    "ceilingArea": None,
                    "trimLength": None,
                    "doborLength": None,
                    "layoutLength": None,
                    "gutterLength": None,
                    "sillLength": None,
                    "openingsArea": None,
                    "confidence": 0.85,
                }
            )
            have.add(key)
            added += 1
        if added:
            result["confidence"] = max(result.get("confidence") or 0, 0.7)
    return result


async def parse_project_text(text: str, *, hint: str = "") -> dict[str, Any]:
    body = (text or "").strip()
    if len(body) < 20:
        raise ValueError("Слишком мало текста в проекте")
    # candidates — на сыром тексте: там имя стены и площадь гарантированно рядом (см. предупреждение
    # в _prefilter_project_text про дедуп); отфильтрованный текст — только чтобы не раздувать промпт.
    candidates = _wall_candidates(body)
    filtered = _prefilter_project_text(body)
    hint_block = ""
    if candidates:
        preview = "; ".join(f"{c['label']}={c['area']}м²" for c in candidates[:40])
        hint_block = (
            f"\n\nАвтоматически найденные подписи «стена + площадь» (для проверки, их может быть больше): {preview}"
        )
    user = USER_PROMPT + f"\n\n--- ТЕКСТ ПРОЕКТА (отфильтрован от размерных цепочек) ---\n{filtered[:30000]}" + hint_block
    if hint.strip():
        user += f"\n\nПодсказка / контекст: {hint.strip()[:800]}"
    raw_text = await _report_chat(user, system=SYSTEM)
    try:
        raw = json.loads(_strip_json(raw_text))
    except json.JSONDecodeError as e:
        logger.warning("project text JSON fail, retry: %s | %s", e, (raw_text or "")[:300])
        fix_user = "Исправь в валидный JSON без markdown. Только объект схемы проекта дома.\n\n" + (raw_text or "")[:8000]
        raw_text2 = await _report_chat(fix_user, system=SYSTEM)
        try:
            raw = json.loads(_strip_json(raw_text2))
        except json.JSONDecodeError as e2:
            logger.warning("project text JSON fail2: %s | %s", e2, (raw_text2 or "")[:300])
            raise ValueError("Модель вернула не JSON по тексту проекта") from e2
    if not isinstance(raw, dict):
        raise ValueError("Неожиданный ответ распознавания проекта")
    return normalize_project(raw, wall_candidates=candidates)


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


async def parse_project_image(image: bytes, *, hint: str = "") -> dict[str, Any]:
    if not image or len(image) < 200:
        raise ValueError("Пустое или слишком маленькое изображение проекта")
    if len(image) > 12 * 1024 * 1024:
        raise ValueError("Файл больше 12 МБ — сожмите фото листа проекта")
    enhanced = enhance_report_image(image)
    data_url = to_data_url(enhanced, detect_mime(enhanced))
    user = USER_PROMPT
    if hint.strip():
        user += f"\n\nПодсказка / контекст: {hint.strip()[:800]}"
    raw_text = await _report_vision(user, data_url, system=SYSTEM)
    try:
        raw = json.loads(_strip_json(raw_text))
    except json.JSONDecodeError as e:
        logger.warning("project image JSON fail: %s | %s", e, (raw_text or "")[:400])
        raise ValueError("Модель вернула не JSON по фото листа проекта") from e
    if not isinstance(raw, dict):
        raise ValueError("Неожиданный ответ распознавания проекта")
    return normalize_project(raw)


async def parse_project_bundle(
    *,
    images: list[bytes] | None = None,
    texts: list[str] | None = None,
    hint: str = "",
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    errors: list[str] = []
    empty_pdf_hint = False
    for img in images or []:
        try:
            parts.append(await parse_project_image(img, hint=hint))
        except Exception as e:
            errors.append(f"фото: {e}")
            logger.warning("project image part fail: %s", e)
    combined_text = "\n\n---\n\n".join(t.strip() for t in (texts or []) if t and t.strip())
    if combined_text:
        try:
            parts.append(await parse_project_text(combined_text, hint=hint))
        except Exception as e:
            errors.append(f"текст: {e}")
            logger.warning("project text part fail: %s", e)
    elif texts:
        # были файлы (например PDF), но текст не извлёкся — вероятно, скан без текстового слоя
        empty_pdf_hint = True
    if not parts:
        msg = "Не удалось распознать проект. "
        if empty_pdf_hint:
            msg += "PDF без текстового слоя (скан) — прикрепите фото/скан нужных листов (планы + развёртки стен)."
        else:
            msg += "; ".join(errors) if errors else "Нужны файлы проекта (PDF с текстом, фото листов, DOCX или текст)."
        raise ValueError(msg)
    result = merge_reports(*parts)
    if errors:
        note = "Часть файлов не распознана AI: " + "; ".join(errors)[:300]
        result["notes"] = f"{result.get('notes') or ''}\n{note}".strip()[:1200]
    if not result["walls"] and not result["notes"]:
        raise ValueError("Не удалось извлечь площади стен из проекта — проверьте файлы или заполните вручную")
    return result


__all__ = [
    "decode_data_url",
    "extract_plain_from_bytes",
    "extract_wall_area_candidates",
    "normalize_project",
    "parse_project_bundle",
    "parse_project_image",
    "parse_project_text",
]
