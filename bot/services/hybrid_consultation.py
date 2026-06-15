"""Консультация, пошаговые планы и PDF-презентация — гибридный генератор v1 + v2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from bot.services.hybrid_generator import (
    hybrid_generator_parts,
    hybrid_generator_v2_parts,
    _frame_rows,
)


def build_consultation_messages(
    frames: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Сообщения для Telegram (как инженерная консультация), ≤4096 символов."""
    chunks: List[str] = []
    for block in (
        _msg_intro(frames),
        _msg_v1_assessment(),
        _msg_v2_proposal(),
        _msg_what_you_get(),
    ):
        if block.strip():
            chunks.extend(_split_telegram(block))
    return chunks


def build_hybrid_presentation_pdf(
    frames: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    from bot.services.seo_pdf import build_seo_pdf

    sections: List[Tuple[str, str]] = [
        ("О проекте", _pdf_about()),
        ("Оценка конструкции v1 (storyboard)", _pdf_v1_assessment()),
        ("Пошаговый план v1", build_v1_step_by_step(frames)),
        ("Улучшенная конструкция v2", _pdf_v2_design()),
        ("Пошаговый план v2", build_v2_step_by_step()),
        ("Сравнение v1 и v2", _pdf_comparison()),
        ("Важно: энергетический баланс", _pdf_energy_note()),
        ("Содержимое архива", _pdf_archive_contents()),
    ]
    return build_seo_pdf(
        "Гибридный электромагнитный генератор",
        sections,
        method_note="v1 (раскадровка) + v2 (инженерное улучшение) · Bambu 3MF · 2026",
    )


def build_v1_step_by_step(frames: Optional[List[Dict[str, Any]]] = None) -> str:
    parts = hybrid_generator_parts()
    frame_rows = _frame_rows(frames or [])
    lines = [
        "ВЕРСИЯ 1 — по вашей раскадровке («восьмёрка»)",
        "",
        "ШАГ 0. Закупка (не печатается)",
        "• Силиконовая трубка Ø8–10 мм, ~80 см",
        "• Неодим Ø4–5 мм, эпоксидка, дистиллированная вода",
        "• Нихром 0.3 мм, керамический стержень, резистор 10 Ω",
        "• Пьезо Ø40 мм + драйвер 40 kHz + акустический гель",
        "• Медь 0.15 мм, феррит, DB107, конденсатор 100 µF",
        "",
        "ШАГ 1. Печать (папка v1-storyboard/3mf/)",
    ]
    for idx, p in enumerate(parts, start=1):
        qty = int(p.get("print_qty") or 1)
        mat = p.get("bambu_material") or p.get("material") or "PETG"
        lines.append(
            f"  {idx}. {p['name']} — {idx:02d}-{p['id']}.3mf · {mat} · ×{qty}"
        )
        lines.append(f"     Ожидание: {p.get('purpose') or '—'}")
    lines.extend(
        [
            "",
            "ШАГ 2. Что должно получиться после печати",
            "• Корпус 200×120×60 с полостью под трубку",
            "• 6 клипс под Ø10 мм, 2 бобины, площадка пьezo, ASA-держатель нагрева, отсек электроники",
            "",
            "ШАГ 3. Сборка (порядок)",
            "1. Уложить трубку «восьмёркой» в корпус, закрепить клипсами",
            "2. Залить жидкость через заливное отверстие; сделать 2–3 капсулы (магнит+эпоксид, нейтральная плавучесть)",
            "3. Вставить капсулы в трубку; проверить, что проходят перекрёсток",
            "4. Нихром в heater_mount → в нижнее колено; питание 12 V отдельно",
            "5. Пьezo на piezo_mount + гель к трубке; драйвер 40 kHz",
            "6. Намотать 2× бобины (~1000 витков); установить на петли; феррит",
            "7. DB107 + конденсатор в electronics_box; провода к катушкам",
            "8. Закрыть body_upper; мультиметр AC mV на катушках, затем DC на выходе",
            "",
            "Кадры раскадровки:",
        ]
    )
    for row in frame_rows:
        lines.append(f"  Кадр {row['frame']}: {row['note']}")
    return "\n".join(lines)


def build_v2_step_by_step() -> str:
    parts = hybrid_generator_v2_parts()
    lines = [
        "ВЕРСИЯ 2 — улучшенная «U-петля» (без перекрёстка)",
        "",
        "ШАГ 0. Закупка",
        "• Акриловая/поликарбонатная трубка Ø12–14 мм (жёсткая, прозрачная), ~50 см",
        "• Неодим Ø6 мм ×1 (в поршень), O-ring Ø12×2 мм",
        "• Жидкость: вода + 5–10 % глицерин",
        "• Нихром, NTC 10k (опционально), Hall SS49E + LED",
        "• Медь 0.15 мм, DB107, 100 µF — как в v1",
        "• Пьezo — только после успеха конвекции (фаза C)",
        "",
        "ШАГ 1. Печать (папка v2-improved/3mf/)",
    ]
    for idx, p in enumerate(parts, start=1):
        qty = int(p.get("print_qty") or 1)
        mat = p.get("bambu_material") or p.get("material") or "PETG"
        lines.append(
            f"  {idx}. {p['name']} — {idx:02d}-{p['id']}.3mf · {mat} · ×{qty}"
        )
        lines.append(f"     Ожидание: {p.get('purpose') or '—'}")
    lines.extend(
        [
            "",
            "ШАГ 2. Что должно получиться",
            "• Корпус-петля без «×»: прямой участок для катушки + камера нагрева снизу",
            "• Один магнитный поршень (не 3 капсулы) — стабильнее",
            "• Катушка коаксиально на прямом участке трубы",
            "",
            "ШАГ 3. Сборка",
            "1. Вставить трубку в U-канал корпуса, 2 направляющие клипсы",
            "2. Вставить поршень с магнитом и O-ring; проверить ход вручную",
            "3. Залить жидкость; закрыть крышку с заливным port",
            "4. Нагреватель в heater_chamber (ASA); цель 45–50 °C",
            "5. Hall-датчик: LED должен мигать при проходе поршня",
            "6. Намотать 1 катушку на coil_bobbin_v2; зафиксировать coil_mount на прямом участке",
            "7. Мультиметр AC mV → при стабильном потоке подключить DB107",
            "8. (Опционально) пьezo на piezo_mount_v2",
            "",
            "Фазы проверки: A — движение (Hall), B — AC mV, C — выпрямление, D — пьezo.",
        ]
    )
    return "\n".join(lines)


def build_v1_bom_txt() -> str:
    return (
        "BOM v1 — storyboard «восьмёрка»\n"
        "================================\n\n"
        "ПЕЧАТЬ (PETG unless noted):\n"
        "  body_lower ×1, body_upper ×1, tube_clip ×6, coil_bobbin ×2,\n"
        "  piezo_mount ×1, heater_mount ×1 (ASA), electronics_box ×1, end_cap ×1\n\n"
        "КУПИТЬ:\n"
        "  Силиконовая трубка Ø8–10 мм ~80 см\n"
        "  Неодим Ø4–5 мм (3+ шт), эпоксидка\n"
        "  Пьezo Ø40 мм, драйвер 40 kHz, гель УЗ\n"
        "  Нихром 0.3 мм, медь 0.15 мм, феррит\n"
        "  DB107, конденсатор 100 µF 16 V, провода\n\n"
        "СДЕЛАТЬ РУКАМИ:\n"
        "  Магнитные капсулы, намотка катушек, нагреватель, пайка моста\n"
    )


def build_v2_bom_txt() -> str:
    return (
        "BOM v2 — U-петля (улучшение)\n"
        "==============================\n\n"
        "ПЕЧАТЬ:\n"
        "  loop_base ×1, loop_lid ×1, tube_guide ×2, magnetic_piston ×1,\n"
        "  coil_bobbin_v2 ×1, coil_mount ×1, heater_chamber ×1 (ASA),\n"
        "  electronics_box ×1, hall_mount ×1, piezo_mount_v2 ×1 (опц.)\n\n"
        "КУПИТЬ:\n"
        "  Трубка акрил/PC Ø12–14 мм ~50 см\n"
        "  Неодим Ø6 мм ×1, O-ring 12×2\n"
        "  Hall SS49E, LED, резистор 220 Ω\n"
        "  NTC 10k (термоконтроль), остальное как v1\n\n"
        "СДЕЛАТЬ РУКАМИ:\n"
        "  Установка магнита в поршень, 1 катушка, нагреватель, пайка\n"
    )


def _msg_intro(frames: Optional[List[Dict[str, Any]]]) -> str:
    return (
        "📋 Гибридный генератор — инженерная консультация\n\n"
        "Разобрал вашу конструкцию. Ниже — оценка v1 (storyboard) и улучшенная v2.\n"
        "После текста пришлю:\n"
        "• PDF-презентацию\n"
        "• ZIP: v1-storyboard/ и v2-improved/ с 3MF для Bambu\n"
        "• Пошаговые планы печати и сборки\n\n"
        "⚠️ Это демонстратор индукции, не источник «бесплатной» энергии: "
        "нагрев + пьezo потребляют больше, чем дадут катушки."
    )


def _msg_v1_assessment() -> str:
    return (
        "▸ v1 — ваша «восьмёрка» (storyboard)\n\n"
        "✅ Верно: магнит через катушку → ЭДС (Фарадей)\n"
        "✅ Хорошо для первого макета и визуализации\n\n"
        "⚠️ Слабые места:\n"
        "• Перекрёсток «×» — капсулы застревают\n"
        "• Два привода (нагрев + 40 kHz) без фазировки\n"
        "• Катушки «над» петлями, не на траектории магнита\n"
        "• Ручные капсулы — разная плавучесть при нагреве\n\n"
        "Оценка: 6/10 как макет, 3/10 как «генератор».\n"
        "Рекомендую собрать v1 для опыта, параллельно — v2."
    )


def _msg_v2_proposal() -> str:
    return (
        "▸ v2 — улучшенная U-петля\n\n"
        "Что изменилось:\n"
        "• Нет перекрёстка — один магнитный поршень\n"
        "• Одна катушка на прямом участке (макс. dΦ/dt)\n"
        "• Жёсткая трубка Ø12 — видно движение\n"
        "• Сначала только нагрев; Hall+LED → потом AC mV → потом мост\n"
        "• Пьezo — опционально после стабильного потока\n\n"
        "Печать: папка v2-improved/3mf/ в архиве."
    )


def _msg_what_you_get() -> str:
    return (
        "▸ Что сейчас соберу\n\n"
        "1. PDF — презентация v1+v2, таблицы, планы\n"
        "2. ZIP:\n"
        "   v1-storyboard/3mf/ — 8 деталей (как в storyboard)\n"
        "   v2-improved/3mf/ — 10 деталей (U-петля)\n"
        "   guides/ — пошаговые txt\n\n"
        "Сначала рекомендую v2 для первых милливольт; v1 — если хотите "
        "точно повторить раскадровку."
    )


def _pdf_about() -> str:
    return (
        "Два варианта одного учебного проекта: движущийся магнит в жидкости "
        "индуцирует напряжение в катушке. v1 повторяет HTML-раскадровку "
        "(силиконовая «восьмёрка», капсулы, нагрев + пьezo). v2 — инженерное "
        "упрощение: U-образная петля, один поршень, катушка на прямом участке."
    )


def _pdf_v1_assessment() -> str:
    return _msg_v1_assessment().replace("▸", "").replace("✅", "+").replace("⚠️", "!")


def _pdf_v2_design() -> str:
    return (
        "Геометрия: корпус 220×140×70 мм с каналом под жёсткую трубу. "
        "Нагреватель в нижней камере (ASA). Поршень с неодимом и уплотнением. "
        "Катушечный кронштейн фиксирует бобину на прямом участке. "
        "Hall-датчик на hall_mount подтверждает движение до измерения ЭДС."
    )


def _pdf_comparison() -> str:
    return (
        "v1: восьмёрка, 3+ капсулы, 2 катушки, 2 привода — сложнее, риск заклинивания.\n"
        "v2: U-петля, 1 поршень, 1 катушка, 1 привод — проще отладка.\n\n"
        "v1: силикон Ø10, ~80 см.\n"
        "v2: акрил Ø12–14, ~50 см.\n\n"
        "v1: piezo сразу.\n"
        "v2: piezo после фазы B.\n\n"
        "Оба: DB107 + 100 µF, экспериментальный КПД << 100%."
    )


def _pdf_energy_note() -> str:
    return (
        "Вход: 12 V на нихром (ватты) + драйвер пьezo. Выход: милливольты–сотни мВ "
        "с катушки. Это нормально для демонстрации закона Фарадея, но устройство "
        "не является автономным генератором энергии."
    )


def _pdf_archive_contents() -> str:
    return (
        "hybrid-generator-full-pack.zip:\n"
        "- pdf/hybrid-generator-presentation.pdf\n"
        "- guides/v1-step-by-step.txt, v2-step-by-step.txt\n"
        "- guides/v1-bom.txt, v2-bom.txt, v1-print-order.txt, v2-print-order.txt\n"
        "- v1-storyboard/3mf/, stl/, scad/\n"
        "- v2-improved/3mf/, stl/, scad/"
    )


def _split_telegram(text: str, limit: int = 4000) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    buf: List[str] = []
    size = 0
    for line in text.splitlines():
        add = len(line) + 1
        if size + add > limit and buf:
            parts.append("\n".join(buf))
            buf = []
            size = 0
        buf.append(line)
        size += add
    if buf:
        parts.append("\n".join(buf))
    return parts
