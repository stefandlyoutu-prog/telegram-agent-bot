"""Подсказки для Bambu Studio / AMS под профиль пользователя."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_ARTICULATED = re.compile(
    r"шевел|подвиж|шарнир|articul|movable|moving|поворотн",
    re.IGNORECASE,
)

_SUBJECT_SLUG = (
    (re.compile(r"лабрадор|labrador", re.I), "labrador-figurine"),
    (re.compile(r"чебурашк", re.I), "cheburashka-figurine"),
    (re.compile(r"ангел|angel", re.I), "angel-figurine"),
    (re.compile(r"собак|dog|retriever", re.I), "dog-figurine"),
    (re.compile(r"кот|cat", re.I), "cat-figurine"),
)

_COLOR_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ч[её]рн|black", "black"),
    (r"бел|white", "white"),
    (r"красн|red", "red"),
    (r"син|голуб|blue", "blue"),
    (r"зел[её]н|green", "green"),
    (r"коричн|brown", "brown"),
    (r"ж[её]лт|yellow", "yellow"),
    (r"оранж|orange", "orange"),
    (r"сер|gray|grey|silver", "gray"),
)

_PART_COLOR_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("engines", r"двигател|engine|мотор|турбин", "engine nacelles"),
    ("tail", r"хвост|tail|киль|стабилизатор", "tail"),
    ("wings", r"крыл|wing", "wings"),
    ("eyes", r"глаз|eye", "eyes"),
    ("body", r"корпус|тело|body|torso|фюзеляж|fuselage", "body"),
    ("head", r"голов|head", "head"),
    ("arms", r"рук|arm|hand", "arms"),
    ("legs", r"ног|leg|лап|paw", "legs"),
    ("wheels", r"кол[её]с|wheel", "wheels"),
)


def color_words_from_text(text: str) -> List[str]:
    """Return normalized colors mentioned anywhere in the request."""
    t = (text or "").lower()
    colors: List[str] = []
    for pattern, color in _COLOR_PATTERNS:
        if re.search(pattern, t) and color not in colors:
            colors.append(color)
    return colors


def part_color_from_text(text: str, part_pattern: str, default: Optional[str] = None) -> Optional[str]:
    """Extract a color assigned to a specific part, e.g. 'engines black, tail red'.

    Clause-first parsing prevents a nearby color for one part from leaking into another
    part when the user lists several requirements in one sentence.
    """
    t = (text or "").lower()
    clauses = [c for c in re.split(r"[,.;!?\n]\s*", t) if re.search(part_pattern, c)]
    for pattern, color in _COLOR_PATTERNS:
        if any(re.search(pattern, clause) for clause in clauses):
            return color
    for pattern, color in _COLOR_PATTERNS:
        if (
            re.search(rf"(?:{part_pattern}).{{0,45}}(?:{pattern})", t)
            or re.search(rf"(?:{pattern}).{{0,45}}(?:{part_pattern})", t)
        ):
            return color
    return default


def extract_part_color_requests(text: str) -> Dict[str, str]:
    """Map normalized part names to normalized colors for all supported subjects."""
    out: Dict[str, str] = {}
    for key, pattern, _label in _PART_COLOR_PATTERNS:
        color = part_color_from_text(text, pattern)
        if color:
            out[key] = color
    return out


def part_color_prompt_fragment(text: str) -> str:
    """Human-readable fragment for Meshy prompts: 'black engines, red tail'."""
    requests = extract_part_color_requests(text)
    parts: List[str] = []
    for key, _pattern, label in _PART_COLOR_PATTERNS:
        color = requests.get(key)
        if color:
            parts.append(f"{color} {label}")
    return ", ".join(parts)


def color_for_object_name(user_text: str, object_name: str) -> Optional[str]:
    """Infer requested color for a Bambu object from generic part-color rules."""
    low = (object_name or "").lower()
    for _key, pattern, _label in _PART_COLOR_PATTERNS:
        if re.search(pattern, low):
            color = part_color_from_text(user_text, pattern)
            if color:
                return color
    return None


def wants_articulated_figurine(text: str) -> bool:
    from bot.services.articulated_3mf import openscad_articulated_supported

    return openscad_articulated_supported(text)


def articulated_3mf_filename(user_text: str) -> str:
    from bot.services.articulated_3mf import _subject_slug

    return f"{_subject_slug(user_text)}-articulated.3mf"


def meshy_export_filename(user_text: str, *, ext: str = "stl") -> str:
    """ASCII-имя файла без кириллицы (Bambu / macOS)."""
    t = user_text or ""
    if re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", t, re.I):
        return f"boeing-airliner-meshy.{ext}"
    for pat, slug in _SUBJECT_SLUG:
        if pat.search(t):
            return f"{slug}-meshy.{ext}"
    return f"figurine-meshy.{ext}"


def parse_ams_from_text(text: str) -> bool:
    return bool(re.search(r"\bams\b|ams\s*pro|амс", text or "", re.I))


def merge_bambu_profile(
    profile: Dict[str, Any],
    user_text: str,
) -> Dict[str, Any]:
    """Дополняет профиль: P2S → сопло 0.4, AMS, Bambu Studio."""
    from bot.services.print_profile import empty_profile, merge_profiles, parse_print_profile

    p = merge_profiles(profile, parse_print_profile(user_text))
    t = (user_text or "").lower()
    if re.search(r"p2s|bambu|бамбу", t) and not p.get("nozzle_mm"):
        p["nozzle_mm"] = 0.4
    if re.search(r"сопло\s*0\.?4|0\.4\s*мм\s*сопл|nozzle\s*0\.4", t, re.I):
        p["nozzle_mm"] = 0.4
    if parse_ams_from_text(user_text):
        p["ams"] = True
    if re.search(r"bambu\s*studio|бамбу\s*студио|bambustudio", t, re.I):
        p["slicer"] = "Bambu Studio"
    if re.search(r"\bpla\b", t, re.I) and not p.get("material"):
        p["material"] = "PLA"
    return p


def bambu_slicer_hint(profile: Dict[str, Any]) -> str:
    nozzle = float(profile.get("nozzle_mm") or 0.4)
    lines = [
        "⚙️ Bambu Studio:",
        f"• Профиль под сопло **{nozzle:g} мм** (слой **{nozzle / 2:g} мм**).",
    ]
    if abs(nozzle - 0.4) < 0.05:
        lines.append("• Не выбирайте пресет «0.2 nozzle», если физически стоит 0.4 мм.")
    elif abs(nozzle - 0.2) < 0.05:
        lines.append("• Нужно сопло 0.2 мм в принтере — иначе смените на 0.4 мм в профиле.")
    mat = (profile.get("material") or "PLA").upper()
    lines.append(f"• Материал: **{mat}** (фигурка — PLA или PETG; TPU только для гибких деталей).")
    if profile.get("ams"):
        lines.append("• AMS Pro: назначьте цвета в слайсере (см. подсказку ниже).")
    lines.append(
        "• Поддержки: если файл 3MF — бот задаёт Tree(auto) в проекте; "
        "если STL — включите Tree(auto) только когда Bambu Studio показывает красные свесы."
    )
    return "\n".join(lines)


def bambu_print_steps(user_text: str, *, file_kind: str = "3mf") -> str:
    if file_kind == "3mf":
        return (
            "🧭 Как печатать в Bambu Studio:\n"
            "1. Откройте файл .3mf двойным кликом или File → Open Project.\n"
            "2. Проверьте слева Plate 1 и выбранный принтер/сопло.\n"
            "3. Нажмите Slice plate.\n"
            "4. Проверьте Preview: вес, время, поддержки и красные свесы.\n"
            "5. Нажмите Print plate / Send.\n\n"
            "🎨 Как поменять цвет: выделите объект справа → Filament/Color → выберите слот AMS. "
            "Для Boeing: airframe_white — корпус, engines — двигатели, tail_red — красный хвост, windows_black — окна."
        )
    return (
        "🧭 Как печатать STL в Bambu Studio:\n"
        "1. Перетащите STL на стол.\n"
        "2. Выберите принтер/сопло и материал.\n"
        "3. Если есть красные свесы — включите Support → Tree(auto).\n"
        "4. Нажмите Slice plate → проверьте Preview → Print plate / Send.\n\n"
        "🎨 Цвет STL: один STL обычно один цвет; выберите объект → Filament/Color → слот AMS."
    )


def support_decision_hint(user_text: str, *, file_kind: str = "stl") -> str:
    """Clear support decision for users who do not want to guess slicer settings."""
    t = (user_text or "").lower()
    if file_kind == "3mf":
        if re.search(r"самол[её]т|боинг|airplane|boeing|фигур|ангел|дракон|летуч", t):
            return (
                "🧱 Поддержки: **включены Tree(auto)** в 3MF. "
                "Для самолёта/фигурки это безопаснее, чем печатать свесы вслепую."
            )
        return "🧱 Поддержки: **auto** в 3MF; проверьте красные свесы в Preview."
    if re.search(r"самол[её]т|боинг|airplane|boeing|фигур|персонаж|животн|дракон", t):
        return (
            "🧱 Поддержки для STL: **включить Tree(auto)**, Build plate only — сначала ON; "
            "если Bambu Studio показывает свесы внутри модели, переключить OFF."
        )
    return "🧱 Поддержки: для простой плоской детали обычно **OFF**; включайте только при красных свесах."


def needs_auto_support_project(user_text: str) -> bool:
    """True when a Meshy STL should be delivered as a support-enabled Bambu 3MF."""
    t = (user_text or "").lower()
    if not t:
        return False
    if re.search(
        r"ручк|держател|кронштейн|клипс?|зажим|колпач|крышк|заглуш|адаптер|"
        r"пластин|плоск|без\s+поддерж|support\s*off",
        t,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"фигур|персонаж|человек|портрет|bobblehead|chibi|статуэт|игрушк|"
            r"животн|собак|лабрадор|dog|cat|кот|дракон|ангел|монстр|маск|бюст|"
            r"крыл|рук|ног|хвост|лап|рог|уш|оруж|меч|плащ|"
            r"самол[её]т|боинг|airplane|aircraft|helicopter|вертол[её]т|"
            r"машин|автомобил|vehicle|корабл|ship|танк|tank|сложн",
            t,
            re.I,
        )
    )


def nozzle_material_warnings(profile: Dict[str, Any], user_text: str) -> str:
    """Явное предупреждение, если для задачи лучше другое сопло/материал."""
    t = (user_text or "").lower()
    nozzle = float(profile.get("nozzle_mm") or 0.4)
    material = str(profile.get("material") or "").upper()
    notes: List[str] = []
    if wants_articulated_figurine(user_text):
        notes.append(
            "🧩 **Подвижная фигурка** — один **3MF**: все детали на столе, шарниры после сборки."
        )
    if re.search(r"мелк|детал|глаз|0\.2\s*мм", t) and nozzle >= 0.35:
        notes.append(
            "💡 Мелкие детали (белые глаза): сопло **0.4 мм** обычно достаточно; "
            "0.2 мм — только если уже установлено и готовы печатать дольше."
        )
    if re.search(r"labrador|лабрадор|собак|фигур", t, re.I) and nozzle >= 0.6:
        notes.append("💡 Для фигурок лучше сопло **0.4 мм**, не 0.6/0.8.")
    if material in {"ABS", "ASA"}:
        notes.append("⚠️ ABS/ASA: нужна закрытая камера, brim и учёт усадки; крупную модель лучше делить.")
    if material in {"NYLON", "PA"} or re.search(r"нейлон|nylon", t, re.I):
        notes.append("⚠️ Nylon/PA: филамент сушить; для осей/шарниров закладывайте зазор 0.4+ мм.")
    if material == "PETG":
        notes.append("💡 PETG: для посадок и шарниров лучше зазор 0.35-0.45 мм, не tight-fit как PLA.")
    if material == "RESIN" or re.search(r"смол|resin", t, re.I):
        notes.append("⚠️ Resin: это не FDM-проект — нужны hollowing, drain holes, ориентация и смоляные поддержки.")
    return "\n".join(notes)


def plastic_weight_hint(text: str, *, density: float = 1.24) -> str:
    m = re.search(r"(\d+)\s*г(?:р|рамм)?", text or "", re.I)
    if not m:
        return ""
    grams = max(1, int(m.group(1)))
    return (
        f"📏 Ориентир **~{grams} г** филамента: infill **15–22%**, 2–3 периметра. "
        "Поддержки бот выбирает отдельно; они могут добавить вес. "
        f"Смотрите «вес» в Bambu Studio после слайса — если больше {grams} г, уменьшите масштаб на 5–10%."
    )


def color_ams_hint(text: str, profile: Dict[str, Any]) -> str:
    t = (text or "").lower()
    if not re.search(r"цвет|бел|чёрн|черн|зелён|зелен|красн|оранж|сер|чёрн", t):
        return ""

    lines: List[str] = ["🎨 Цвета (3MF / AMS Pro):"]
    part_requests = extract_part_color_requests(text)
    if part_requests:
        readable = ", ".join(f"{part}={color}" for part, color in part_requests.items())
        lines.append(f"• Запрошенные цвета деталей: {readable}. Бот применяет их к Meshy prompt и object-level AMS, где детали доступны как отдельные объекты.")

    if re.search(r"лабрадор|labrador", t, re.I):
        lines.extend(
            [
                "• **Чёрный PLA** — body, head, leg_*, tail.",
                "• **Белый PLA** — eye_left, eye_right (или покраска после печати).",
                "• В Bambu: выделите объект → назначьте филамент из AMS.",
            ]
        )
    elif re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", t, re.I):
        lines.extend(
            [
                "• **airframe_white** — корпус и крылья (обычно белый PLA).",
                "• **engines** — двигатели; если просили чёрные/красные/серые двигатели, в 3MF назначен нужный слот AMS.",
                "• **tail_red** — хвост, если просили красный хвост.",
                "• **windows_black** — окна/кабина (чёрный PLA).",
                "• **gear_doors_black** — шасси/двери (чёрный PLA).",
                "• Цвет можно поменять: справа выберите объект → Filament/Color → нужный слот AMS.",
            ]
        )
    elif re.search(r"ангел|angel", t, re.I):
        lines.extend(
            [
                "• **Белый PLA** — body, head.",
                "• **Чёрный PLA** — wing_left, wing_right.",
                "• **Красный PLA** — eye_left, eye_right.",
                "• В Bambu Studio: объект → филамент AMS (3MF без пресета Bambu — это нормально).",
            ]
        )
    else:
        colors: List[str] = []
        if re.search(r"ч[ёе]рн|black", t):
            colors.append("чёрный")
        if re.search(r"бел|white", t):
            colors.append("белый")
        if re.search(r"зел[её]н", t):
            colors.append("зелёный")
        if re.search(r"красн|red", t):
            colors.append("красный")
        if colors:
            lines.append(f"• Запрошено: {', '.join(colors)} — назначьте филаменты в AMS.")
        lines.append("• Один STL — один цвет на деталь; детали цвета — покраска или отдельные объекты.")

    if profile.get("ams"):
        lines.append("• AMS Pro: загрузите филаменты → «Sync» → проверьте слоты перед печатью.")
    return "\n".join(lines)
