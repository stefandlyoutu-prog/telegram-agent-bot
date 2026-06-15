"""Локальный «проект на печать»: OpenSCAD + план + ZIP (+ STL если openscad есть)."""

import io
import json
import logging
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from bot.services.openscad import (
    build_assembly_md,
    build_bom_csv,
    build_print_plan,
    build_scad_source,
    export_stl_from_scad,
    openscad_available,
    sanitize_id,
)

logger = logging.getLogger(__name__)

_PRINT_BASE_PATTERN = re.compile(
    r"stl|3d[\s-]?печат|3d[\s-]?модел|модел.{0,20}печат|печат|принтер|bambu|бамбу|"
    r"слайсер|загрузить.{0,20}(принтер|слайсер|bambu)",
    re.IGNORECASE,
)

# Пользователь уже имеет проект/файлы и просит консультацию — не генерировать ZIP/STL.
_EXISTING_PROJECT_HELP = re.compile(
    r"(?:"
    r"у\s+меня\s+есть|имею\s+(?:у\s+себя\s+)?|есть\s+у\s+меня|"
    r"готов(?:ый|ая|ое|ые)\s+(?:проект|stl|3mf|модел|файл|архив)|"
    r"скачал|скачан|с\s+thingiverse|с\s+printables|с\s+makerworld|"
    r"проект\s+с\s+описан|описани(?:е|я)\s+(?:проект|модел)"
    r")|(?:"
    r"помощ[ьи]\s+(?:по|с)|нужна\s+помощ|помог(?:и|ите)\s+(?:с|по)|"
    r"подскаж(?:и|ите)|совет(?:уй|ы)?\s+(?:по|как)|консультац|"
    r"как\s+(?:печат|собир|настро|запуст|скле|клеить)|"
    r"инструкци.{0,16}(?:печат|сборк)|"
    r"ты\s+(?:это\s+)?умеешь|можешь\s+(?:пом|подсказ)|"
    r"help\s+with\s+(?:print|assembl)"
    r")",
    re.IGNORECASE,
)

_CREATE_PRINT_PROJECT = re.compile(
    r"сделай|создай|сгенерир|собери|пришли|отправь|"
    r"нужен\s+(?:новый\s+)?проект|хочу\s+(?:проект|zip|архив)|"
    r"make\s+me|generate|build\s+me",
    re.IGNORECASE,
)


def is_existing_project_help_request(text: Optional[str]) -> bool:
    """Consultation about an existing model/project — not «generate print pack»."""
    t = (text or "").strip()
    if not t:
        return False
    if not _EXISTING_PROJECT_HELP.search(t):
        return False
    if _CREATE_PRINT_PROJECT.search(t) and re.search(
        r"проект|zip|архив|stl|3mf|модел|раскадров|storyboard|print[\s-]?pack",
        t,
        re.I,
    ):
        return False
    return True

MULTI_PART_PRINT_PATTERN = re.compile(
    r"на\s+каждую\s+детал|отдельн.{0,20}(stl|файл|детал)|"
    r"проект\s+на\s+печат|раскадров|storyboard|"
    r"гибридн.{0,15}генератор|"
    r"print[\s-]?in[\s-]?place|flexi|флекси|гибк.{0,12}фигур|"
    r"fidget|фиджет|spinner|спиннер|spinning|крутилк|"
    r"modular|модульн|pin|peg|штифт|соединител|"
    r"dice|кубик|кубик.{0,12}кости|"
    r"покадров|(?:сделай|создай|собери|проект).{0,30}сборк|"
    r"сборк.{0,20}(?:инструк|порядок|guide|kit)|"
    r"собираются|комплект|"
    r"\d+\s*детал|несколько\s+детал|"
    r"openscad|\.scad|черт[eё]ж|деталировк|"
    r"инженер|тех\s*задан|\bтз\b|спецификац|bom|ведомост|"
    r"корпус|механизм|ксеноморф",
    re.IGNORECASE,
)

ZERO_TO_PRINT_PATTERN = re.compile(
    r"kit[\s-]?card|кит[\s-]?кард|карточк.{0,16}детал|"
    r"rugged\s+box|parametric\s+box|параметрическ.{0,20}короб|коробк.{0,24}(защёл|защел|snap|петл|hinge)|"
    r"willys|jeep|джип|машин[ауы].{0,40}(kit|набор|сборк|детал|cad|с\s+0|с\s+нуля)|"
    r"planetarium|планетар|gear|шестер|редуктор|механизм|"
    r"puzzle.{0,20}(board|chess)|пазл.{0,30}(доск|шахмат)|шахмат.{0,30}(пазл|доск|набор)|"
    r"dna|днк|helix|спирал.{0,20}(подстав|держател|карандаш)|карандашниц|"
    r"impossible\s+cube|невозможн.{0,20}куб|оптическ.{0,20}иллюз|illusion|"
    r"spiral.{0,20}chess|спиральн.{0,20}шахмат|no\s+supports|без\s+поддерж|"
    r"lamp|ламп|светиль|абажур|\bled\b|ночник|"
    r"mmu|многоцвет|multi[\s-]?color|olaf|ams.{0,30}(цвет|объект|персонаж)|персонаж.{0,30}(цвет|ams|mmu)|"
    r"plant\s+pot|planter|кашпо|горш|вазон|дренаж|"
    r"oreo|box.{0,20}(decor|cookie)|декоративн.{0,20}короб|шкатул|контейнер|"
    r"vase|ваза|vase\s+mode|low[\s-]?poly.{0,20}vase|тонкостенн|"
    r"sla|resin|смол|calibration|калибров|amera|"
    r"easter\s+egg|пасхальн.{0,20}яйц|voronoi|variant\s+family|family\s+of\s+variants|семейств.{0,20}вариант|"
    r"jewellery|jewelry|украшен|дерев.{0,20}украшен|"
    r"deadpool|bust|бюст|collectible|коллекционн|miniature\s+pack|paintable\s+miniature|"
    r"split.{0,25}character|character.{0,25}kit|разборн.{0,30}персонаж|"
    r"stitch|halloween.{0,20}stitch|baby\s+yoda|grogu|гро[гг]у|йода|"
    r"starter.{0,20}plant|seed.{0,20}starter|plant.{0,20}grower|рассад|проращив|"
    r"key[\s_-]?holder|wall[\s_-]?fixing|wall[\s_-]?mount|настенн.{0,20}креп|креплен.{0,20}стен|"
    r"ender.{0,20}tool|tool[\s_-]?holder|держател.{0,20}инструмент|"
    r"stackable.{0,20}crate|screw[\s_-]?box|modular.{0,20}storage|ящик.{0,20}винт|органайзер|"
    r"pegstr|pegboard|перфорированн.{0,20}панел|"
    r"egg[\s_-]?roll.{0,20}basket|perforated.{0,20}basket|корзин|"
    r"charizard|pokemon|pok[eé]mon|winged.{0,20}creature|крылат.{0,20}(существ|дракон)|"
    r"(?:boeing|боинг|самол[её]т).{0,160}(?:шасси|шосси|landing\s*gear|лопаст|кол[её]с|ось|крут|вращ|убира|складыва)|"
    r"уровн.{0,30}(thingiverse|printables|скачан|интернет)|"
    r"с\s+нуля.{0,80}(kit|набор|сборк|короб|джип|машин|модель)",
    re.IGNORECASE,
)

SINGLE_PART_PRINT_PATTERN = re.compile(
    r"ручк|держател|кронштейн|крюч|клип|клипс|зажим|"
    r"колпач|крышк|заглуш|адаптер|насадк|фиксатор|"
    r"подставк|опор[ау]|кольц[оо]|втулк|"
    r"одн[ау]\s+детал|одну\s+детал|один\s+stl|"
    r"для\s+\d+\s*л\s*бутыл|\d+\s*л\s*бутыл|бутыл",
    re.IGNORECASE,
)

EXPLICIT_GENERATOR_PATTERN = re.compile(
    r"гибридн.{0,15}генератор|\bгенератор\b",
    re.IGNORECASE,
)


def _should_use_hybrid_fallback(text: Optional[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    return bool(
        re.search(r"гибридн.{0,15}генератор|hybrid.{0,12}generator", text, re.I)
        or "hybrid-generator" in low
    )


def is_openscad_suitable_part(text: Optional[str]) -> bool:
    """Функциональные детали, которые OpenSCAD может сделать осмысленно."""
    if not text:
        return False
    return bool(SINGLE_PART_PRINT_PATTERN.search(text))


def is_single_part_print_request(text: Optional[str]) -> bool:
    """Одна деталь (ручка, кронштейн…) — OpenSCAD, не ZIP и не Meshy."""
    if not text:
        return False
    if EXPLICIT_GENERATOR_PATTERN.search(text) and MULTI_PART_PRINT_PATTERN.search(text):
        return False
    return is_openscad_suitable_part(text)


def wants_print_project(text: Optional[str]) -> bool:
    """Многодетальный проект: раскадровка, «на каждую деталь», гибридный генератор."""
    if not text:
        return False
    if is_existing_project_help_request(text):
        return False
    if ZERO_TO_PRINT_PATTERN.search(text):
        return True
    if is_single_part_print_request(text):
        if not re.search(
            r"раскадров|storyboard|на\s+каждую\s+детал|проект\s+на\s+печат",
            text,
            re.I,
        ):
            return False
    return bool(MULTI_PART_PRINT_PATTERN.search(text)) or bool(
        EXPLICIT_GENERATOR_PATTERN.search(text)
        and re.search(r"проект|раскадров|storyboard|печат|stl|детал", text, re.I)
    )


def parse_project_specs(raw: str) -> Optional[Dict[str, Any]]:
    block = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    text = block.group(1).strip() if block else raw.strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_object_label(text: str) -> str:
    t = (text or "").strip()
    for pat in (
        r"(?:сделай|создай|нужн[ао]?|хочу)\s+(?:мне\s+)?(?:3d[\s-]?)?(?:модел[ьи]?|stl)?\s*(?:для\s+(?:печати|принтер[ае]))?\s*(?:на\s+[\w\s\-]+)?\s*[:\-]?\s*(.+)",
        r"(?:ручк[аи]|держател[ьи]|кронштейн|клип|крюч[оа]k)\s*(?:для\s+)?(.+)",
    ):
        m = re.search(pat, t, re.I | re.DOTALL)
        if m:
            label = re.sub(r"\s+", " ", m.group(1)).strip(" .")
            label = re.split(r"\?\s*|\n", label, maxsplit=1)[0].strip()
            if len(label) >= 3:
                return label[:120]
    return "detail_v0"


def _fallback_single_part(user_request: str) -> Dict[str, Any]:
    t = (user_request or "").lower()
    label = _extract_object_label(user_request)
    slug = sanitize_id(label, "single-part-v0")

    if re.search(r"ручк|handle", t) and re.search(r"бутыл|5\s*л|5л|канистр", t):
        return {
            "project_name": "handle_for_5l_bottle_v0",
            "mode": "fallback_single",
            "parts": [
                {
                    "id": "bottle_handle_5l",
                    "name": "Ручка для 5л бутылки",
                    "template": "bottle_handle",
                    "params": {
                        "width_mm": 130,
                        "depth_mm": 10,
                        "height_mm": 28,
                        "neck_radius_mm": 26,
                        "wall_mm": 3,
                    },
                    "material": "PETG",
                    "orientation": "лежит на боку, хват сверху",
                    "purpose": "Удобный захват канистры 5л за горловину.",
                    "assembly_step": "Надеть на горловину канистры (~52 мм).",
                    "tolerance_mm": 0.3,
                }
            ],
            "assumptions": [
                "Горловина стандартной 5л канистры ~48–52 мм наружный диаметр.",
                "v0 — проверьте посадку на вашей бутылке перед массовой печатью.",
            ],
            "requirements": ["Одна печатаемая ручка для переноски 5л бутылки."],
        }

    return {
        "project_name": slug,
        "mode": "fallback_single",
        "parts": [
            {
                "id": slug,
                "name": label[:80],
                "template": "plate",
                "params": {"width_mm": 80, "depth_mm": 40, "height_mm": 12, "wall_mm": 3},
                "material": "PETG",
                "orientation": "плоской стороной на стол",
                "purpose": f"Черновая v0 деталь: {label[:60]}.",
                "assembly_step": "Проверить размеры на реальном узле.",
                "tolerance_mm": 0.2,
            }
        ],
        "assumptions": [
            "Точные размеры не указаны — сделана инженерная v0 по 0.",
            "Пришлите фото или размеры в мм для уточнения.",
        ],
        "requirements": [f"Одна деталь для 3D-печати: {label[:80]}."],
    }


def specs_is_unprintable_fallback(specs: Dict[str, Any], user_request: str) -> Optional[str]:
    """Block generic plate ZIP when user did not ask to generate a new project."""
    mode = str(specs.get("mode") or "")
    if mode not in ("fallback_single", "fallback", "fallback-network"):
        return None
    if is_existing_project_help_request(user_request):
        return (
            "Это запрос консультации по уже существующему проекту — "
            "я не генерирую новый STL/ZIP вместо ответа."
        )
    if zero_to_print_requested(user_request) or _should_use_hybrid_fallback(user_request):
        return None
    parts = specs.get("parts") or []
    if len(parts) == 1 and str((parts[0] or {}).get("template") or "") == "plate":
        return (
            "Не удалось собрать инженерный проект (LLM/сеть). "
            "Generic-пластину 80×40 мм не отправляю — уточните объект, размеры и материал."
        )
    return None


def zero_to_print_requested(text: Optional[str]) -> bool:
    """Requests that should be built as CAD-like print projects, not raw neural meshes."""
    return bool(ZERO_TO_PRINT_PATTERN.search(text or ""))


def preview_project_build(user_request: str, context: str = "") -> Tuple[int, str, Optional[Dict[str, Any]]]:
    """Part count and status label for progress messages (matches deterministic specs)."""
    from bot.services.hybrid_generator import hybrid_generator_specs, is_hybrid_generator_storyboard

    blob = f"{user_request}\n{context or user_request}"
    if is_hybrid_generator_storyboard(None, blob) or _should_use_hybrid_fallback(blob):
        specs = hybrid_generator_specs()
        return len(specs["parts"]), "hybrid generator (CAD)", specs

    specs = zero_to_print_specs(blob)
    if specs and isinstance(specs.get("parts"), list) and specs["parts"]:
        n = len(specs["parts"])
        kind = str(specs.get("project_kind") or specs.get("strategy") or "проект")
        if kind == "mechanical_boeing_airliner":
            label = "mechanical Boeing v3 (CLERX split, fit-first)"
        else:
            label = kind.replace("_", " ")
        return n, label, specs
    return 0, "проект", None


def _with_print_contract(specs: Dict[str, Any], *, strategy: str, project_kind: str, min_wall_mm: float = 0.8) -> Dict[str, Any]:
    specs = dict(specs)
    assumptions = list(specs.get("assumptions") or [])
    assumptions.extend(
        [
            "Урок print-prep: нейросетевой STL можно использовать как референс, но финал должен быть CAD-like solid.",
            "Не склеивать всё вслепую в один mesh: детали оставляются раздельно, если это улучшает печать и сборку.",
            f"Минимальная стенка/контакт для FDM: {min_wall_mm:.1f} мм или больше, мелкие декоративные элементы утолщаются.",
            "Каждая STL/SCAD-деталь должна быть закрытым solid без внутренних мусорных стенок и с понятной ориентацией.",
        ]
    )
    specs["assumptions"] = assumptions
    specs["mode"] = specs.get("mode") or "zero_to_print"
    specs["project_kind"] = project_kind
    specs["strategy"] = strategy
    specs["min_wall_mm"] = min_wall_mm
    specs["print_prep_contract"] = {
        "manifold_solid_required": True,
        "avoid_internal_zero_thickness_walls": True,
        "separate_parts_when_assembly_is_better": True,
        "orientation_required": True,
        "support_strategy_required": True,
    }
    return specs


def _rugged_box_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "rugged-snap-box-cad-v0",
            "requirements": [
                "Параметрическая ударная коробка с крышкой, защёлкой, петлёй и тестом посадки.",
                "Печатать как отдельные solids, не как один слитый mesh.",
            ],
            "critical_dimensions": [
                {"name": "наружный размер корпуса", "value_mm": "120×60×35", "tolerance_mm": 0.4},
                {"name": "толщина стенки", "value_mm": 2.4, "tolerance_mm": 0.2},
                {"name": "зазор защёлки/крышки", "value_mm": 0.35, "tolerance_mm": 0.15},
            ],
            "parts": [
                {
                    "id": "bottom_shell",
                    "name": "Нижняя половина rugged box",
                    "template": "rugged_box_bottom",
                    "params": {"width_mm": 120, "depth_mm": 60, "height_mm": 25, "wall_mm": 2.4, "radius_mm": 5},
                    "material": "PETG",
                    "orientation": "дном на стол, без supports",
                    "purpose": "Несущий корпус с усиленными бортами и посадкой крышки.",
                    "assembly_step": "После печати удалить brim, проверить посадку крышки.",
                    "tolerance_mm": 0.35,
                },
                {
                    "id": "top_lid",
                    "name": "Крышка с внутренней губой",
                    "template": "rugged_box_lid",
                    "params": {"width_mm": 120, "depth_mm": 60, "height_mm": 10, "wall_mm": 2.2, "radius_mm": 5},
                    "material": "PETG",
                    "orientation": "верхом на стол или губой вверх после теста",
                    "purpose": "Закрывает корпус, имеет печатную губу под зазор.",
                    "assembly_step": "Проверить люфт, при тугой посадке увеличить XY compensation на -0.1 мм.",
                    "tolerance_mm": 0.35,
                },
                {
                    "id": "snap_latch",
                    "name": "Защёлка snap-fit",
                    "template": "snap_latch",
                    "params": {"width_mm": 36, "depth_mm": 10, "height_mm": 7, "wall_mm": 2.0},
                    "material": "PETG",
                    "orientation": "плашмя на стол, слои вдоль изгиба",
                    "purpose": "Пружинящая защёлка с утолщённым основанием.",
                    "assembly_step": "Поставить после теста посадки, не пережать.",
                    "tolerance_mm": 0.25,
                },
                {
                    "id": "hinge_pin",
                    "name": "Ось петли",
                    "template": "cylinder",
                    "params": {"radius_mm": 1.6, "height_mm": 58, "wall_mm": 1.0, "segments": 48},
                    "material": "PETG",
                    "orientation": "лежа на столе или вертикально при хорошем охлаждении",
                    "purpose": "Печатная ось петли; при желании заменить металлическим штифтом Ø3 мм.",
                    "assembly_step": "Вставить через петли крышки и корпуса.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "fit_test_coupon",
                    "name": "Тест посадки защёлки",
                    "template": "fit_test_coupon",
                    "params": {"width_mm": 34, "depth_mm": 18, "height_mm": 5, "wall_mm": 2.0},
                    "material": "PETG",
                    "orientation": "плоской стороной на стол",
                    "purpose": "Малый тест перед печатью всей коробки.",
                    "assembly_step": "Напечатать первым и проверить зазор.",
                    "tolerance_mm": 0.2,
                },
            ],
        },
        strategy="parametric_cad_assembly",
        project_kind="rugged_box",
        min_wall_mm=0.8,
    )


def _kit_card_specs(text: str) -> Dict[str, Any]:
    subject = "star-destroyer" if re.search(r"destroyer|зв[её]здн|star", text, re.I) else "kit-card-model"
    return _with_print_contract(
        {
            "project_name": f"{subject}-kit-card-cad-v0",
            "requirements": [
                "Kit-card: плоская карточка с выламываемыми деталями и отдельным stand.",
                "Толщина деталей 1.2–1.8 мм, перемычки маленькие, но не нитки.",
            ],
            "critical_dimensions": [
                {"name": "толщина карточки", "value_mm": 1.6, "tolerance_mm": 0.15},
                {"name": "минимальная перемычка", "value_mm": 0.8, "tolerance_mm": 0.1},
            ],
            "parts": [
                {
                    "id": "kit_card_frame",
                    "name": "Kit-card рамка",
                    "template": "kit_card_frame",
                    "params": {"width_mm": 150, "depth_mm": 95, "height_mm": 1.6, "wall_mm": 2.0},
                    "material": "PLA",
                    "orientation": "плашмя на стол, без supports",
                    "purpose": "Рамка удерживает детали как подарочную карточку.",
                    "assembly_step": "Выломать детали после печати.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "hull_top",
                    "name": "Верх корпуса",
                    "template": "kit_card_wedge",
                    "params": {"width_mm": 92, "depth_mm": 28, "height_mm": 1.8, "wall_mm": 1.2},
                    "material": "PLA",
                    "orientation": "в карточке, плашмя",
                    "purpose": "Главная узнаваемая плоскость модели.",
                    "assembly_step": "Вставить в центральный паз stand.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "hull_bottom",
                    "name": "Низ корпуса",
                    "template": "kit_card_wedge",
                    "params": {"width_mm": 78, "depth_mm": 24, "height_mm": 1.8, "wall_mm": 1.2},
                    "material": "PLA",
                    "orientation": "в карточке, плашмя",
                    "purpose": "Вторая плоскость корпуса, добавляет объём.",
                    "assembly_step": "Скрестить с верхом корпуса через паз.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "bridge",
                    "name": "Надстройка",
                    "template": "plate",
                    "params": {"width_mm": 28, "depth_mm": 12, "height_mm": 2.0, "wall_mm": 1.2},
                    "material": "PLA",
                    "orientation": "плашмя",
                    "purpose": "Декоративная надстройка без тонких антенн.",
                    "assembly_step": "Вклеить или вставить в паз корпуса.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "display_stand",
                    "name": "Подставка",
                    "template": "slot_stand",
                    "params": {"width_mm": 50, "depth_mm": 28, "height_mm": 4.0, "wall_mm": 2.0, "hole_mm": 2.0},
                    "material": "PLA",
                    "orientation": "плоской стороной на стол",
                    "purpose": "Подставка с пазом под собранную модель.",
                    "assembly_step": "Вставить корпус в паз.",
                    "tolerance_mm": 0.25,
                },
            ],
        },
        strategy="flat_kit_card_with_breakaway_tabs",
        project_kind="kit_card",
        min_wall_mm=0.8,
    )


def _vehicle_kit_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "willys-style-vehicle-kit-cad-v0",
            "requirements": [
                "Модель уровня набора: отдельные печатные детали, как интернет-модели, но CAD-like.",
                "Не сырой нейро-STL: корпус, шасси, колёса, сиденья и мелкие детали разделены для печати.",
            ],
            "critical_dimensions": [
                {"name": "длина модели", "value_mm": 150, "tolerance_mm": 2.0},
                {"name": "минимальная толщина декоративных деталей", "value_mm": 0.8, "tolerance_mm": 0.1},
                {"name": "минимальная несущая толщина", "value_mm": 1.2, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "body_tub", "name": "Кузов-ванна", "template": "vehicle_body_tub", "params": {"width_mm": 92, "depth_mm": 46, "height_mm": 18, "wall_mm": 2.0}, "material": "PLA", "orientation": "дном на стол, supports только под арки если нужны", "purpose": "Главная форма открытого джипа.", "assembly_step": "Поставить на шасси после зачистки.", "tolerance_mm": 0.3},
                {"id": "chassis", "name": "Шасси", "template": "vehicle_chassis", "params": {"width_mm": 105, "depth_mm": 42, "height_mm": 5, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя, без supports", "purpose": "Несущая плита с местами под оси.", "assembly_step": "Вставить оси и колёса.", "tolerance_mm": 0.25},
                {"id": "hood", "name": "Капот", "template": "plate", "params": {"width_mm": 38, "depth_mm": 42, "height_mm": 4, "wall_mm": 1.6}, "material": "PLA", "orientation": "плашмя", "purpose": "Передняя узнаваемая часть Willys-style.", "assembly_step": "Приклеить к кузову.", "tolerance_mm": 0.2},
                {"id": "windshield", "name": "Рамка стекла", "template": "kit_card_frame", "params": {"width_mm": 42, "depth_mm": 24, "height_mm": 1.8, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Утолщённая печатная рамка без тонких проволок.", "assembly_step": "Вставить/приклеить в паз кузова.", "tolerance_mm": 0.2},
                {"id": "front_seat", "name": "Переднее сиденье", "template": "seat_block", "params": {"width_mm": 32, "depth_mm": 14, "height_mm": 13, "wall_mm": 1.4}, "material": "PLA", "orientation": "спинкой вверх или боком", "purpose": "Интерьер без нулевой толщины.", "assembly_step": "Приклеить в кузов.", "tolerance_mm": 0.25},
                {"id": "rear_seat", "name": "Заднее сиденье", "template": "seat_block", "params": {"width_mm": 36, "depth_mm": 14, "height_mm": 12, "wall_mm": 1.4}, "material": "PLA", "orientation": "спинкой вверх или боком", "purpose": "Интерьер.", "assembly_step": "Приклеить в кузов.", "tolerance_mm": 0.25},
                {"id": "wheel_fl", "name": "Колесо переднее левое", "template": "cylinder", "params": {"radius_mm": 8, "height_mm": 5, "wall_mm": 1.2, "segments": 64}, "material": "PLA", "orientation": "на боковой плоскости", "purpose": "Колесо цельным solid.", "assembly_step": "Надеть на ось.", "tolerance_mm": 0.25},
                {"id": "wheel_fr", "name": "Колесо переднее правое", "template": "cylinder", "params": {"radius_mm": 8, "height_mm": 5, "wall_mm": 1.2, "segments": 64}, "material": "PLA", "orientation": "на боковой плоскости", "purpose": "Колесо цельным solid.", "assembly_step": "Надеть на ось.", "tolerance_mm": 0.25},
                {"id": "wheel_rl", "name": "Колесо заднее левое", "template": "cylinder", "params": {"radius_mm": 8, "height_mm": 5, "wall_mm": 1.2, "segments": 64}, "material": "PLA", "orientation": "на боковой плоскости", "purpose": "Колесо цельным solid.", "assembly_step": "Надеть на ось.", "tolerance_mm": 0.25},
                {"id": "wheel_rr", "name": "Колесо заднее правое", "template": "cylinder", "params": {"radius_mm": 8, "height_mm": 5, "wall_mm": 1.2, "segments": 64}, "material": "PLA", "orientation": "на боковой плоскости", "purpose": "Колесо цельным solid.", "assembly_step": "Надеть на ось.", "tolerance_mm": 0.25},
                {"id": "axle_front", "name": "Передняя ось", "template": "cylinder", "params": {"radius_mm": 1.6, "height_mm": 48, "wall_mm": 1.0, "segments": 32}, "material": "PETG", "orientation": "лежа, brim по желанию", "purpose": "Ось колёс.", "assembly_step": "Вставить в шасси.", "tolerance_mm": 0.2},
                {"id": "axle_rear", "name": "Задняя ось", "template": "cylinder", "params": {"radius_mm": 1.6, "height_mm": 48, "wall_mm": 1.0, "segments": 32}, "material": "PETG", "orientation": "лежа, brim по желанию", "purpose": "Ось колёс.", "assembly_step": "Вставить в шасси.", "tolerance_mm": 0.2},
            ],
        },
        strategy="multi_part_vehicle_assembly",
        project_kind="vehicle_kit",
        min_wall_mm=0.8,
    )


def _mechanical_planetarium_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "mechanical-planetarium-cad-v0",
            "requirements": [
                "Механический учебный планетарий: шестерни, оси, arms, база, тест зазора.",
                "Сначала проверить gear mesh coupon, потом печатать полный механизм.",
            ],
            "critical_dimensions": [
                {"name": "модуль зубьев", "value_mm": 1.25, "tolerance_mm": 0.05},
                {"name": "зазор ось/отверстие", "value_mm": 0.25, "tolerance_mm": 0.1},
                {"name": "минимальная толщина зуба", "value_mm": 0.9, "tolerance_mm": 0.1},
            ],
            "parts": [
                {"id": "base_plate", "name": "База планетария", "template": "plate", "params": {"width_mm": 160, "depth_mm": 110, "height_mm": 5, "wall_mm": 2.4}, "material": "PLA", "orientation": "плоско на стол, без supports", "purpose": "Несущая плита с местами под оси.", "assembly_step": "Печатать первой, проверить плоскость.", "tolerance_mm": 0.25},
                {"id": "sun_drive_gear", "name": "Ведущая шестерня Sun 32T", "template": "spur_gear", "params": {"teeth": 32, "module_mm": 1.25, "height_mm": 6, "hole_mm": 5.2, "wall_mm": 1.0}, "material": "PLA", "orientation": "плашмя, brim по желанию", "purpose": "Ведущая шестерня механизма.", "assembly_step": "Надеть на центральную ось.", "tolerance_mm": 0.15},
                {"id": "earth_gear", "name": "Шестерня Earth 48T", "template": "spur_gear", "params": {"teeth": 48, "module_mm": 1.25, "height_mm": 6, "hole_mm": 5.2, "wall_mm": 1.0}, "material": "PLA", "orientation": "плашмя, без supports", "purpose": "Передача для Earth arm.", "assembly_step": "Проверить свободное вращение.", "tolerance_mm": 0.15},
                {"id": "mars_gear", "name": "Шестерня Mars 36T", "template": "spur_gear", "params": {"teeth": 36, "module_mm": 1.25, "height_mm": 6, "hole_mm": 5.2, "wall_mm": 1.0}, "material": "PLA", "orientation": "плашмя, без supports", "purpose": "Передача для Mars arm.", "assembly_step": "Проверить mesh с idler.", "tolerance_mm": 0.15},
                {"id": "idler_gear", "name": "Промежуточная шестерня 24T", "template": "spur_gear", "params": {"teeth": 24, "module_mm": 1.25, "height_mm": 6, "hole_mm": 3.4, "wall_mm": 1.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Idler для развязки вращения.", "assembly_step": "Ставится на отдельную ось.", "tolerance_mm": 0.15},
                {"id": "earth_arm", "name": "Планетный рычаг Earth", "template": "planet_arm", "params": {"width_mm": 90, "depth_mm": 11, "height_mm": 4, "hole_mm": 5.2, "radius_mm": 4}, "material": "PETG", "orientation": "плашмя, без supports", "purpose": "Рычаг с утолщёнными посадками.", "assembly_step": "Собрать после теста шестерён.", "tolerance_mm": 0.25},
                {"id": "mars_arm", "name": "Планетный рычаг Mars", "template": "planet_arm", "params": {"width_mm": 70, "depth_mm": 10, "height_mm": 4, "hole_mm": 5.2, "radius_mm": 4}, "material": "PETG", "orientation": "плашмя", "purpose": "Второй рычаг механизма.", "assembly_step": "Собрать после Earth arm.", "tolerance_mm": 0.25},
                {"id": "axle_set", "name": "Набор осей/пегов", "template": "axle_peg_set", "params": {"width_mm": 120, "depth_mm": 34, "height_mm": 5, "radius_mm": 2.4, "wall_mm": 1.0}, "material": "PETG", "orientation": "плашмя или вертикально по тесту", "purpose": "Оси для сборки.", "assembly_step": "Подобрать по свободному вращению.", "tolerance_mm": 0.15},
                {"id": "gear_mesh_coupon", "name": "Тест зацепления шестерён", "template": "gear_mesh_coupon", "params": {"width_mm": 70, "depth_mm": 36, "height_mm": 4, "wall_mm": 2.0}, "material": "PLA", "orientation": "плоско", "purpose": "Проверить clearance до полного проекта.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="mechanical_gear_train_with_test_coupon",
        project_kind="mechanical_planetarium",
        min_wall_mm=0.9,
    )


def _dna_helix_holder_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "dna-helix-pencil-holder-cad-v0",
            "requirements": [
                "Функциональная скульптура: карандашница DNA helix с вариантами full/split/support-test.",
                "Декор должен быть утолщён и printable, не как тонкая нейросетевая проволока.",
            ],
            "critical_dimensions": [
                {"name": "наружный диаметр", "value_mm": 96, "tolerance_mm": 1.0},
                {"name": "минимальный диаметр спиральной стойки", "value_mm": 2.2, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "helix_full", "name": "DNA holder full body", "template": "dna_helix_holder", "params": {"width_mm": 96, "depth_mm": 96, "height_mm": 120, "radius_mm": 36, "wall_mm": 2.2}, "material": "PLA", "orientation": "вертикально, tree supports только если нужен высокий вариант", "purpose": "Полная декоративная карандашница.", "assembly_step": "Печатать как основной вариант.", "tolerance_mm": 0.4},
                {"id": "helix_split_a", "name": "DNA holder split A", "template": "dna_helix_half", "params": {"width_mm": 96, "depth_mm": 48, "height_mm": 120, "radius_mm": 36, "wall_mm": 2.2}, "material": "PLA", "orientation": "плоской стороной к столу", "purpose": "Половина для низкого принтера/лучшей печати.", "assembly_step": "Склеить с split B по штифтам.", "tolerance_mm": 0.35},
                {"id": "helix_split_b", "name": "DNA holder split B", "template": "dna_helix_half", "params": {"width_mm": 96, "depth_mm": 48, "height_mm": 120, "radius_mm": 36, "wall_mm": 2.2}, "material": "PLA", "orientation": "плоской стороной к столу", "purpose": "Вторая половина.", "assembly_step": "Склеить с split A.", "tolerance_mm": 0.35},
                {"id": "u_snap_set", "name": "Optional U-snaps", "template": "snap_latch", "params": {"width_mm": 18, "depth_mm": 10, "height_mm": 5, "wall_mm": 1.8}, "material": "PETG", "orientation": "плашмя", "purpose": "Опциональные защёлки/фиксаторы.", "assembly_step": "Использовать только после проверки посадки.", "tolerance_mm": 0.25},
                {"id": "support_test", "name": "Тест поддержки спирали", "template": "dna_support_coupon", "params": {"width_mm": 38, "depth_mm": 38, "height_mm": 45, "wall_mm": 2.0}, "material": "PLA", "orientation": "вертикально", "purpose": "Проверить bridges/supports перед полной печатью.", "assembly_step": "Печатать первым при новом профиле.", "tolerance_mm": 0.3},
            ],
        },
        strategy="functional_sculpture_with_full_split_support_variants",
        project_kind="dna_helix_holder",
        min_wall_mm=0.8,
    )


def _impossible_cube_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "impossible-cube-illusion-cad-v0",
            "requirements": [
                "Оптическая illusion-модель: один чистый watertight solid, без лишней детализации.",
                "Профессиональность здесь в чистой геометрии, масштабе и ориентации.",
            ],
            "critical_dimensions": [
                {"name": "габарит", "value_mm": 90, "tolerance_mm": 1.0},
                {"name": "толщина балки", "value_mm": 10, "tolerance_mm": 0.3},
            ],
            "parts": [
                {"id": "illusion_cube_body", "name": "Impossible cube single solid", "template": "impossible_cube", "params": {"width_mm": 90, "depth_mm": 10, "height_mm": 90, "wall_mm": 2.0}, "material": "PLA", "orientation": "на длинной плоскости, supports по минимуму", "purpose": "Один цельный illusion solid.", "assembly_step": "Не требует сборки.", "tolerance_mm": 0.25},
                {"id": "angle_test_bar", "name": "Тест угла/моста", "template": "illusion_bar_coupon", "params": {"width_mm": 45, "depth_mm": 10, "height_mm": 28, "wall_mm": 2.0}, "material": "PLA", "orientation": "как основной угол", "purpose": "Проверить качество наклонной балки.", "assembly_step": "Печатать первым при сомнительном профиле.", "tolerance_mm": 0.25},
            ],
        },
        strategy="single_watertight_optical_illusion_with_coupon",
        project_kind="impossible_cube",
        min_wall_mm=1.0,
    )


def _puzzle_chess_board_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "puzzle-chess-board-cad-v0",
            "requirements": [
                "Puzzle chess board: повторяемые плитки с tabs/slots и упрощённые printable фигуры.",
                "Главный риск — посадки, поэтому нужен tolerance coupon.",
            ],
            "critical_dimensions": [
                {"name": "зазор tab/slot", "value_mm": 0.25, "tolerance_mm": 0.1},
                {"name": "толщина плитки", "value_mm": 6.0, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "center_tile", "name": "Центральная puzzle-плитка", "template": "puzzle_tile_center", "params": {"width_mm": 50, "depth_mm": 50, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "лицом вверх, без supports", "purpose": "Повторяемая центральная плитка.", "assembly_step": "Печатать 32 шт при полной доске.", "tolerance_mm": 0.2},
                {"id": "edge_tab_tile", "name": "Крайняя плитка tab", "template": "puzzle_tile_tab", "params": {"width_mm": 50, "depth_mm": 32, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "лицом вверх", "purpose": "Край с выступом.", "assembly_step": "Собрать после теста посадки.", "tolerance_mm": 0.2},
                {"id": "edge_slot_tile", "name": "Крайняя плитка slot", "template": "puzzle_tile_slot", "params": {"width_mm": 50, "depth_mm": 32, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "лицом вверх", "purpose": "Край с пазом.", "assembly_step": "Собрать с tab tile.", "tolerance_mm": 0.2},
                {"id": "corner_tile", "name": "Угловая puzzle-плитка", "template": "puzzle_tile_corner", "params": {"width_mm": 50, "depth_mm": 50, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "лицом вверх", "purpose": "Угол доски.", "assembly_step": "Поставить по углам.", "tolerance_mm": 0.2},
                {"id": "pawn_piece", "name": "Пешка spiral/no-support", "template": "spiral_chess_piece", "params": {"radius_mm": 14, "height_mm": 36, "wall_mm": 1.2}, "material": "PLA", "orientation": "основанием на стол", "purpose": "Фигура без supports.", "assembly_step": "Печатать 16 шт.", "tolerance_mm": 0.25},
                {"id": "king_piece", "name": "Король spiral/no-support", "template": "spiral_chess_piece", "params": {"radius_mm": 16, "height_mm": 64, "wall_mm": 1.2}, "material": "PLA", "orientation": "основанием на стол", "purpose": "Высокая фигура без supports.", "assembly_step": "Печатать медленнее для качества.", "tolerance_mm": 0.25},
                {"id": "tab_slot_coupon", "name": "Тест tab/slot", "template": "tab_slot_coupon", "params": {"width_mm": 55, "depth_mm": 22, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "лицом вверх", "purpose": "Проверить посадку плиток.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="modular_puzzle_board_with_tolerance_coupon",
        project_kind="puzzle_chess_board",
        min_wall_mm=0.8,
    )


def _spiral_chess_set_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "spiral-chess-set-no-support-cad-v0",
            "requirements": [
                "Spiral chess set: фигуры специально проектируются без supports.",
                "Формы должны использовать 3D-печать как процесс, а не имитировать литьё.",
            ],
            "critical_dimensions": [
                {"name": "слой", "value_mm": 0.2, "tolerance_mm": 0.05},
                {"name": "минимальная спиральная стенка", "value_mm": 1.2, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "pawn_spiral", "name": "Spiral pawn", "template": "spiral_chess_piece", "params": {"radius_mm": 13, "height_mm": 34, "wall_mm": 1.2}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Пешка без поддержек.", "assembly_step": "Печатать медленно внешний периметр.", "tolerance_mm": 0.2},
                {"id": "bishop_spiral", "name": "Spiral bishop", "template": "spiral_chess_piece", "params": {"radius_mm": 14, "height_mm": 48, "wall_mm": 1.2}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Слон без поддержек.", "assembly_step": "Проверить cooling.", "tolerance_mm": 0.2},
                {"id": "rook_spiral", "name": "Spiral rook", "template": "spiral_chess_piece", "params": {"radius_mm": 15, "height_mm": 45, "wall_mm": 1.3}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Ладья без поддержек.", "assembly_step": "Печатать 2 шт на цвет.", "tolerance_mm": 0.2},
                {"id": "queen_spiral", "name": "Spiral queen", "template": "spiral_chess_piece", "params": {"radius_mm": 16, "height_mm": 58, "wall_mm": 1.3}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Ферзь без поддержек.", "assembly_step": "Проверить время печати.", "tolerance_mm": 0.2},
                {"id": "king_spiral", "name": "Spiral king", "template": "spiral_chess_piece", "params": {"radius_mm": 17, "height_mm": 64, "wall_mm": 1.3}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Король без поддержек.", "assembly_step": "Печатать отдельно для качества.", "tolerance_mm": 0.2},
            ],
        },
        strategy="supportless_decorative_set",
        project_kind="spiral_chess_set",
        min_wall_mm=1.0,
    )


def _lamp_project_specs(text: str) -> Dict[str, Any]:
    greek = bool(re.search(r"greek|meander|греческ|меандр", text, re.I))
    nuke = bool(re.search(r"nuke|ядер|гриб", text, re.I))
    name = "greek-meander-lamp-cad-v0" if greek else "nuke-lamp-cad-v0" if nuke else "led-lamp-cad-v0"
    shade_template = "greek_meander_shade" if greek else "lamp_shade_shell"
    return _with_print_contract(
        {
            "project_name": name,
            "requirements": [
                "LED lamp project: shade + base + cable channel + heat warning.",
                "Только LED/низкая температура; не использовать лампы накаливания рядом с PLA.",
            ],
            "critical_dimensions": [
                {"name": "толщина стенки абажура", "value_mm": 1.2, "tolerance_mm": 0.2},
                {"name": "кабельный канал", "value_mm": 6.0, "tolerance_mm": 0.4},
                {"name": "зазор под LED модуль", "value_mm": 0.4, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "lamp_shade", "name": "Абажур/рассеиватель", "template": shade_template, "params": {"width_mm": 82, "depth_mm": 82, "height_mm": 110, "wall_mm": 1.2, "radius_mm": 38}, "material": "PETG", "orientation": "вертикально, seam сзади, supports OFF если узор самонесущий", "purpose": "Тонкая оболочка для LED-света.", "assembly_step": "Надеть на базу после проверки температуры.", "tolerance_mm": 0.35},
                {"id": "lamp_base", "name": "База лампы", "template": "lamp_base", "params": {"width_mm": 88, "depth_mm": 88, "height_mm": 18, "wall_mm": 2.4, "hole_mm": 6}, "material": "PETG", "orientation": "дном на стол", "purpose": "Основание с каналом под провод и LED.", "assembly_step": "Вставить LED, вывести кабель через канал.", "tolerance_mm": 0.3},
                {"id": "led_fit_coupon", "name": "Тест посадки LED/кабеля", "template": "led_fit_coupon", "params": {"width_mm": 38, "depth_mm": 24, "height_mm": 8, "wall_mm": 2.0, "hole_mm": 6}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить кабель и LED до полной печати.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.2},
            ],
        },
        strategy="led_lamp_shade_base_heat_safe",
        project_kind="lamp_project",
        min_wall_mm=0.8,
    )


def _mmu_character_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "mmu-character-no-support-cad-v0",
            "requirements": [
                "MMU/AMS персонаж: отдельные цветовые solids + общий 3MF/assembly plan.",
                "No-support ориентация и крупные контактные поверхности между цветами.",
            ],
            "critical_dimensions": [
                {"name": "минимальный цветной элемент", "value_mm": 1.0, "tolerance_mm": 0.2},
                {"name": "контактная площадь вставки", "value_mm": 8.0, "tolerance_mm": 1.0},
            ],
            "parts": [
                {"id": "body_white", "name": "Тело белое", "template": "character_body", "params": {"width_mm": 64, "depth_mm": 48, "height_mm": 92, "wall_mm": 2.0, "radius_mm": 24}, "material": "PLA white", "orientation": "основанием на стол, supports OFF", "purpose": "Главная форма персонажа.", "assembly_step": "Печатать основным цветом.", "tolerance_mm": 0.3},
                {"id": "nose_orange", "name": "Нос оранжевый", "template": "character_insert", "params": {"width_mm": 18, "depth_mm": 10, "height_mm": 10, "wall_mm": 1.2}, "material": "PLA orange", "orientation": "плашмя", "purpose": "Цветовая вставка.", "assembly_step": "AMS object или вклейка.", "tolerance_mm": 0.2},
                {"id": "eyes_black", "name": "Глаза чёрные", "template": "button_set", "params": {"width_mm": 28, "depth_mm": 10, "height_mm": 3, "wall_mm": 1.0, "radius_mm": 3.2}, "material": "PLA black", "orientation": "плашмя", "purpose": "Чёрные детали лица.", "assembly_step": "AMS object/paint или вклейка.", "tolerance_mm": 0.2},
                {"id": "buttons_black", "name": "Пуговицы", "template": "button_set", "params": {"width_mm": 36, "depth_mm": 12, "height_mm": 3, "wall_mm": 1.0, "radius_mm": 3.4}, "material": "PLA black", "orientation": "плашмя", "purpose": "Передние пуговицы.", "assembly_step": "Печатать как отдельные объекты.", "tolerance_mm": 0.2},
                {"id": "arms_brown", "name": "Руки/веточки коричневые", "template": "branch_arm_set", "params": {"width_mm": 70, "depth_mm": 22, "height_mm": 4, "wall_mm": 1.4}, "material": "PLA brown", "orientation": "плашмя, brim", "purpose": "Утолщённые веточки без тонких проволок.", "assembly_step": "Вставить в боковые посадки.", "tolerance_mm": 0.25},
                {"id": "color_fit_coupon", "name": "Тест цветовой вставки", "template": "fit_test_coupon", "params": {"width_mm": 32, "depth_mm": 18, "height_mm": 5, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверить посадку multi-part/AMS.", "assembly_step": "Печатать перед полной фигурой.", "tolerance_mm": 0.15},
            ],
        },
        strategy="mmu_ams_named_color_objects_no_support",
        project_kind="mmu_character",
        min_wall_mm=1.0,
    )


def _planter_project_specs(text: str) -> Dict[str, Any]:
    rocket = bool(re.search(r"rocket|space|ракета", text, re.I))
    aztec = bool(re.search(r"aztec|temple|ацтек|храм", text, re.I))
    return _with_print_contract(
        {
            "project_name": "rocket-planter-cad-v0" if rocket else "aztec-temple-planter-cad-v0" if aztec else "planter-cad-v0",
            "requirements": [
                "Planter mode: внешний декоративный корпус + внутренний pot/liner + drainage/ring.",
                "Вода/почва требуют PETG/ASA или внутренний liner; PLA без защиты не считать долговечным.",
            ],
            "critical_dimensions": [
                {"name": "дренажные отверстия", "value_mm": 4.0, "tolerance_mm": 0.4},
                {"name": "толщина стенки", "value_mm": 2.0, "tolerance_mm": 0.25},
            ],
            "parts": [
                {"id": "outer_shell", "name": "Декоративный внешний корпус", "template": "rocket_planter_shell" if rocket else "temple_planter_shell", "params": {"width_mm": 92, "depth_mm": 92, "height_mm": 120, "wall_mm": 2.2, "radius_mm": 42}, "material": "PETG", "orientation": "дном на стол, supports по декору", "purpose": "Внешняя форма кашпо.", "assembly_step": "Печатать после liner test.", "tolerance_mm": 0.4},
                {"id": "inner_pot_liner", "name": "Внутренний горшок/liner", "template": "plant_pot_liner", "params": {"width_mm": 74, "depth_mm": 74, "height_mm": 78, "wall_mm": 1.8, "radius_mm": 34, "hole_mm": 4}, "material": "PETG", "orientation": "дном на стол", "purpose": "Контактирует с землёй/водой.", "assembly_step": "Вставить во внешний корпус.", "tolerance_mm": 0.35},
                {"id": "drainage_ring", "name": "Дренажное кольцо/поддон", "template": "drainage_ring", "params": {"width_mm": 84, "depth_mm": 84, "height_mm": 8, "wall_mm": 2.0, "hole_mm": 4}, "material": "PETG", "orientation": "плашмя", "purpose": "Отвод воды и устойчивость.", "assembly_step": "Поставить под liner.", "tolerance_mm": 0.25},
                {"id": "drainage_coupon", "name": "Тест дренажа", "template": "drainage_coupon", "params": {"width_mm": 36, "depth_mm": 36, "height_mm": 5, "wall_mm": 2.0, "hole_mm": 4}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить отверстия/flow.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.2},
            ],
        },
        strategy="decorative_planter_with_liner_and_drainage",
        project_kind="planter_project",
        min_wall_mm=1.2,
    )


def _decorative_container_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "decorative-cookie-box-cad-v0",
            "requirements": [
                "Decorative container: outer shell, inner filling/liner, lid fit, relief detail.",
                "Печатность важнее микрорельефа: декор утолщается, посадка проверяется coupon.",
            ],
            "critical_dimensions": [
                {"name": "зазор крышки", "value_mm": 0.35, "tolerance_mm": 0.15},
                {"name": "минимальная высота рельефа", "value_mm": 0.8, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "outer_cookie_shell", "name": "Наружная декоративная оболочка", "template": "decorative_box_shell", "params": {"width_mm": 86, "depth_mm": 86, "height_mm": 18, "wall_mm": 2.0, "radius_mm": 40}, "material": "PLA", "orientation": "декором вверх", "purpose": "Верх/низ коробки с крупным рельефом.", "assembly_step": "Печатать медленно внешний периметр.", "tolerance_mm": 0.3},
                {"id": "inner_filling_liner", "name": "Внутренняя вставка/filling", "template": "box_liner", "params": {"width_mm": 76, "depth_mm": 76, "height_mm": 12, "wall_mm": 1.8, "radius_mm": 35}, "material": "PLA", "orientation": "плоско", "purpose": "Внутренний объём/посадка.", "assembly_step": "Проверить зазор с shell.", "tolerance_mm": 0.25},
                {"id": "lid_fit_coupon", "name": "Тест посадки крышки", "template": "ring_fit_coupon", "params": {"width_mm": 42, "depth_mm": 42, "height_mm": 6, "wall_mm": 2.0, "radius_mm": 18}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверка зазора крышки.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="decorative_container_with_lid_fit_coupon",
        project_kind="decorative_container",
        min_wall_mm=0.8,
    )


def _vase_shell_specs(text: str) -> Dict[str, Any]:
    low_poly = bool(re.search(r"low[\s-]?poly|низкопол", text, re.I))
    return _with_print_contract(
        {
            "project_name": "low-poly-heart-vase-cad-v0" if low_poly or re.search(r"heart|серд", text, re.I) else "vase-shell-cad-v0",
            "requirements": [
                "Vase/shell mode: open top, controlled wall thickness, spiral/vase-mode option.",
                "Проверять water-tight только если нужна ваза для воды; декоративная shell может быть open-top.",
            ],
            "critical_dimensions": [
                {"name": "толщина стенки", "value_mm": 1.0, "tolerance_mm": 0.2},
                {"name": "толщина дна", "value_mm": 2.4, "tolerance_mm": 0.3},
            ],
            "parts": [
                {"id": "vase_shell", "name": "Low-poly vase shell", "template": "low_poly_vase_shell", "params": {"width_mm": 82, "depth_mm": 70, "height_mm": 110, "wall_mm": 1.0, "radius_mm": 36}, "material": "PLA", "orientation": "дном на стол, vase mode/spiralize optional", "purpose": "Тонкостенная декоративная ваза.", "assembly_step": "Проверить seam и дно.", "tolerance_mm": 0.3},
                {"id": "wall_coupon", "name": "Тест стенки vase mode", "template": "vase_wall_coupon", "params": {"width_mm": 30, "depth_mm": 24, "height_mm": 38, "wall_mm": 1.0}, "material": "PLA", "orientation": "дном на стол", "purpose": "Проверить толщину/flow.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="thin_shell_vase_mode_with_wall_coupon",
        project_kind="vase_shell",
        min_wall_mm=0.8,
    )


def _sla_calibration_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "sla-calibration-town-v0",
            "requirements": [
                "SLA/resin calibration: separate from FDM logic, includes unsupported/supported/attachment variants.",
                "Не масштабировать без причины: тестовая геометрия должна сохранять размеры.",
            ],
            "critical_dimensions": [
                {"name": "fine detail posts", "value_mm": 0.2, "tolerance_mm": 0.05},
                {"name": "attachment layer", "value_mm": 0.3, "tolerance_mm": 0.05},
            ],
            "parts": [
                {"id": "calibration_town_raw", "name": "SLA town raw calibration", "template": "sla_calibration_town", "params": {"width_mm": 35, "depth_mm": 20, "height_mm": 28, "wall_mm": 0.6}, "material": "Resin", "orientation": "flat/0 degree for exposure benchmark", "purpose": "Проверка экспозиции и мелких деталей.", "assembly_step": "Печатать без масштабирования.", "tolerance_mm": 0.05},
                {"id": "calibration_town_supported", "name": "SLA town supported variant", "template": "sla_supported_variant", "params": {"width_mm": 35, "depth_mm": 20, "height_mm": 34, "wall_mm": 0.6}, "material": "Resin", "orientation": "наклон 25–35°, supports", "purpose": "Проверка supports и отрыва.", "assembly_step": "Сравнить с raw.", "tolerance_mm": 0.05},
                {"id": "exposure_ladder", "name": "Exposure ladder coupon", "template": "sla_exposure_ladder", "params": {"width_mm": 45, "depth_mm": 16, "height_mm": 3, "wall_mm": 0.5}, "material": "Resin", "orientation": "flat", "purpose": "Быстрый тест экспозиции.", "assembly_step": "Печатать перед большим тестом.", "tolerance_mm": 0.05},
            ],
        },
        strategy="sla_resin_calibration_variants",
        project_kind="sla_calibration",
        min_wall_mm=0.5,
    )


def _variant_family_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "decorative-egg-variant-family-v0",
            "requirements": [
                "Variant family: low-poly, wavy, voronoi/support-needed and simple/no-support variants.",
                "Бот должен явно помечать, какие варианты требуют supports или тонкой настройки.",
            ],
            "critical_dimensions": [
                {"name": "минимальная перемычка voronoi", "value_mm": 1.0, "tolerance_mm": 0.2},
                {"name": "высота яйца", "value_mm": 70, "tolerance_mm": 1.0},
            ],
            "parts": [
                {"id": "egg_low_poly", "name": "Low-poly egg no-support", "template": "egg_low_poly", "params": {"width_mm": 48, "depth_mm": 48, "height_mm": 70, "wall_mm": 1.2, "radius_mm": 24}, "material": "PLA", "orientation": "основанием на стол, supports OFF", "purpose": "Быстрый простой вариант.", "assembly_step": "Печатать первым для проверки масштаба.", "tolerance_mm": 0.3},
                {"id": "egg_wavy", "name": "Wavy decorative egg", "template": "egg_wavy", "params": {"width_mm": 50, "depth_mm": 50, "height_mm": 72, "wall_mm": 1.2, "radius_mm": 24}, "material": "PLA", "orientation": "основанием на стол", "purpose": "Декоративная волнистая версия.", "assembly_step": "Печатать медленнее внешний периметр.", "tolerance_mm": 0.3},
                {"id": "egg_voronoi_safe", "name": "Voronoi-safe egg", "template": "egg_voronoi_safe", "params": {"width_mm": 50, "depth_mm": 50, "height_mm": 72, "wall_mm": 1.4, "radius_mm": 24}, "material": "PLA", "orientation": "основанием на стол, возможно supports", "purpose": "Безопасная имитация voronoi без микропроволоки.", "assembly_step": "Проверить thin-risk.", "tolerance_mm": 0.3},
                {"id": "thin_bridge_coupon", "name": "Тест тонкой перемычки", "template": "thin_bridge_coupon", "params": {"width_mm": 40, "depth_mm": 20, "height_mm": 6, "wall_mm": 1.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверить минимальные перемычки.", "assembly_step": "Печатать перед voronoi.", "tolerance_mm": 0.15},
            ],
        },
        strategy="variant_family_with_support_labels",
        project_kind="variant_family",
        min_wall_mm=0.8,
    )


def _jewellery_tree_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "jewellery-tree-split-balanced-v0",
            "requirements": [
                "Flat/split ornamental holder: front/back/base, balance and branch-thickness checks.",
                "Хрупкие ветки утолщаются, база проверяется на опрокидывание.",
            ],
            "critical_dimensions": [
                {"name": "минимальная ветка", "value_mm": 2.0, "tolerance_mm": 0.2},
                {"name": "толщина базы", "value_mm": 8.0, "tolerance_mm": 0.3},
            ],
            "parts": [
                {"id": "tree_front", "name": "Jewellery tree front", "template": "jewellery_tree_panel", "params": {"width_mm": 120, "depth_mm": 6, "height_mm": 170, "wall_mm": 2.2}, "material": "PLA", "orientation": "плашмя, brim", "purpose": "Передняя декоративная панель.", "assembly_step": "Вставить в базу.", "tolerance_mm": 0.3},
                {"id": "tree_back", "name": "Jewellery tree back", "template": "jewellery_tree_panel", "params": {"width_mm": 120, "depth_mm": 6, "height_mm": 170, "wall_mm": 2.2}, "material": "PLA", "orientation": "плашмя, brim", "purpose": "Задняя панель для объёма.", "assembly_step": "Скрестить/склеить с front.", "tolerance_mm": 0.3},
                {"id": "weighted_base", "name": "Устойчивая база", "template": "jewellery_tree_base", "params": {"width_mm": 120, "depth_mm": 70, "height_mm": 10, "wall_mm": 2.4, "hole_mm": 6}, "material": "PLA", "orientation": "дном на стол", "purpose": "Устойчивость и паз под дерево.", "assembly_step": "Проверить баланс с украшениями.", "tolerance_mm": 0.25},
                {"id": "branch_coupon", "name": "Тест ветки/крючка", "template": "branch_arm_set", "params": {"width_mm": 50, "depth_mm": 18, "height_mm": 4, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверить прочность веток.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.2},
            ],
        },
        strategy="flat_split_ornamental_holder_with_balance_check",
        project_kind="jewellery_tree",
        min_wall_mm=1.0,
    )


def _character_bust_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "character-bust-hollow-display-v0",
            "requirements": [
                "High-detail bust workflow: sculpt-like outer form, display base, hollowing/drain plan, support orientation.",
                "Органический sculpt не делается как один сырой mesh: добавляется база, hollow coupon и предупреждение по supports.",
            ],
            "critical_dimensions": [
                {"name": "минимальная стенка hollow bust", "value_mm": 1.6, "tolerance_mm": 0.25},
                {"name": "дренаж/escape отверстие", "value_mm": 5.0, "tolerance_mm": 0.4},
                {"name": "зазор посадки бюст-база", "value_mm": 0.35, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "bust_head_torso", "name": "Character bust head and shoulders", "template": "bust_head_torso", "params": {"width_mm": 84, "depth_mm": 68, "height_mm": 112, "wall_mm": 1.8, "radius_mm": 30, "hole_mm": 5}, "material": "PLA/PETG or resin", "orientation": "наклон назад 20–30°, supports на затылок/плечи, лицо не в supports", "purpose": "Основной органический бюст с утолщённой оболочкой.", "assembly_step": "Печатать после hollow/support coupon.", "tolerance_mm": 0.3},
                {"id": "display_base", "name": "Display base with keyed socket", "template": "display_base_keyed", "params": {"width_mm": 86, "depth_mm": 70, "height_mm": 16, "wall_mm": 2.4, "hole_mm": 10}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Постамент и посадочное место под бюст.", "assembly_step": "Вклеить бюст в keyed socket.", "tolerance_mm": 0.25},
                {"id": "nameplate", "name": "Front nameplate", "template": "nameplate_blank", "params": {"width_mm": 58, "depth_mm": 8, "height_mm": 2.4, "wall_mm": 1.2}, "material": "PLA contrast color", "orientation": "лицом вверх", "purpose": "Табличка/цветовая деталь.", "assembly_step": "Вклеить в паз базы.", "tolerance_mm": 0.2},
                {"id": "hollow_support_coupon", "name": "Hollow/support coupon", "template": "hollow_support_coupon", "params": {"width_mm": 36, "depth_mm": 28, "height_mm": 32, "wall_mm": 1.6, "hole_mm": 5}, "material": "same as bust", "orientation": "как бюст", "purpose": "Проверить стенку, drain holes и support scars.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="organic_bust_hollowed_with_display_base",
        project_kind="character_bust",
        min_wall_mm=1.2,
    )


def _split_collectible_character_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "split-collectible-character-kit-v0",
            "requirements": [
                "Split collectible: full preview + separated head/torso/ears/hands/accessories for clean print orientation.",
                "Каждая крупная часть имеет keyed pin/socket, чтобы модель собиралась после покраски или AMS.",
            ],
            "critical_dimensions": [
                {"name": "зазор keyed pin/socket", "value_mm": 0.25, "tolerance_mm": 0.1},
                {"name": "минимальная толщина ушей/пальцев", "value_mm": 1.4, "tolerance_mm": 0.2},
                {"name": "диаметр сборочного пина", "value_mm": 4.0, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "full_preview", "name": "Full character preview/reference", "template": "collectible_full_preview", "params": {"width_mm": 70, "depth_mm": 52, "height_mm": 105, "wall_mm": 2.0, "radius_mm": 24}, "material": "PLA", "orientation": "не основной print; preview/reference", "purpose": "Цельная контрольная форма для понимания сборки.", "assembly_step": "Использовать как визуальный референс.", "tolerance_mm": 0.4},
                {"id": "keyed_torso", "name": "Keyed torso", "template": "keyed_character_torso", "params": {"width_mm": 58, "depth_mm": 42, "height_mm": 62, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA/PETG", "orientation": "спиной на стол или дном, supports только сзади", "purpose": "Основной корпус с посадками.", "assembly_step": "Собрать после теста pin coupon.", "tolerance_mm": 0.25},
                {"id": "keyed_head", "name": "Keyed head", "template": "keyed_character_head", "params": {"width_mm": 58, "depth_mm": 48, "height_mm": 48, "wall_mm": 1.8, "hole_mm": 4}, "material": "PLA/PETG", "orientation": "лицо вверх/назад, избегать supports на лице", "purpose": "Голова с socket/pin посадкой.", "assembly_step": "Надеть на torso pin.", "tolerance_mm": 0.25},
                {"id": "ears_pair", "name": "Separated ears pair", "template": "character_ears_pair", "params": {"width_mm": 70, "depth_mm": 14, "height_mm": 34, "wall_mm": 1.6, "hole_mm": 3}, "material": "PLA", "orientation": "плашмя, brim", "purpose": "Тонкие уши печатаются отдельно для прочности.", "assembly_step": "Вклеить в sockets головы.", "tolerance_mm": 0.2},
                {"id": "hands_pair", "name": "Separated hands pair", "template": "character_hands_pair", "params": {"width_mm": 44, "depth_mm": 18, "height_mm": 16, "wall_mm": 1.4, "hole_mm": 3}, "material": "PLA", "orientation": "плашмя/под углом, supports minimal", "purpose": "Руки/кисти отдельными solids.", "assembly_step": "Вклеить в torso sockets.", "tolerance_mm": 0.2},
                {"id": "pin_connector_set", "name": "Pin connector set", "template": "pin_connector_set", "params": {"width_mm": 70, "depth_mm": 12, "height_mm": 4, "wall_mm": 1.2, "radius_mm": 2.0}, "material": "PLA/PETG", "orientation": "плашмя", "purpose": "Запасные пины разных длин.", "assembly_step": "Подогнать после fit test.", "tolerance_mm": 0.1},
                {"id": "pin_fit_coupon", "name": "Pin/socket fit coupon", "template": "pin_socket_coupon", "params": {"width_mm": 38, "depth_mm": 18, "height_mm": 8, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA/PETG", "orientation": "плашмя", "purpose": "Проверить зазор пинов до полной печати.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.08},
            ],
        },
        strategy="organic_split_character_with_keyed_connectors",
        project_kind="split_collectible_character",
        min_wall_mm=1.0,
    )


def _accessory_character_kit_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "accessory-character-kit-v0",
            "requirements": [
                "Character kit with costume/accessory parts: body, head, hands, cape/sleeves and prop separated for color/paint.",
                "Аксессуар не должен быть тонкой ломкой декорацией: добавляются утолщение, keyed base и отдельный fit coupon.",
            ],
            "critical_dimensions": [
                {"name": "минимальная толщина аксессуара", "value_mm": 1.2, "tolerance_mm": 0.2},
                {"name": "зазор аксессуар-персонаж", "value_mm": 0.3, "tolerance_mm": 0.12},
            ],
            "parts": [
                {"id": "costume_torso", "name": "Costume torso", "template": "keyed_character_torso", "params": {"width_mm": 56, "depth_mm": 42, "height_mm": 58, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA main color", "orientation": "спиной/дном на стол", "purpose": "Корпус с посадками под голову/руки/костюм.", "assembly_step": "Собрать после fit coupon.", "tolerance_mm": 0.25},
                {"id": "character_head", "name": "Character head", "template": "keyed_character_head", "params": {"width_mm": 56, "depth_mm": 48, "height_mm": 46, "wall_mm": 1.8, "hole_mm": 4}, "material": "PLA main color", "orientation": "лицо без support scars", "purpose": "Голова отдельной деталью.", "assembly_step": "Вклеить/посадить на pin.", "tolerance_mm": 0.25},
                {"id": "cape_or_cloak", "name": "Cape/cloak", "template": "cape_shell", "params": {"width_mm": 66, "depth_mm": 18, "height_mm": 60, "wall_mm": 1.4}, "material": "PLA contrast color", "orientation": "внешней стороной вверх, supports minimal", "purpose": "Костюмная деталь отдельным цветом.", "assembly_step": "Приклеить к спине.", "tolerance_mm": 0.25},
                {"id": "sleeves_pair", "name": "Sleeves pair", "template": "sleeves_pair", "params": {"width_mm": 48, "depth_mm": 14, "height_mm": 18, "wall_mm": 1.4, "hole_mm": 3}, "material": "PLA contrast color", "orientation": "плашмя", "purpose": "Отдельные рукава/цветовые зоны.", "assembly_step": "Вклеить вокруг рук.", "tolerance_mm": 0.2},
                {"id": "hands_pair", "name": "Hands pair", "template": "character_hands_pair", "params": {"width_mm": 42, "depth_mm": 18, "height_mm": 15, "wall_mm": 1.4, "hole_mm": 3}, "material": "PLA skin color", "orientation": "плашмя", "purpose": "Руки отдельными solids.", "assembly_step": "Собрать после покраски.", "tolerance_mm": 0.2},
                {"id": "prop_accessory", "name": "Pumpkin/prop accessory", "template": "prop_pumpkin", "params": {"width_mm": 34, "depth_mm": 34, "height_mm": 30, "wall_mm": 1.6, "radius_mm": 15}, "material": "PLA orange", "orientation": "дном на стол", "purpose": "Аксессуар/тыква/предмет в руке.", "assembly_step": "Печатать отдельным цветом.", "tolerance_mm": 0.2},
                {"id": "accessory_fit_coupon", "name": "Accessory fit coupon", "template": "pin_socket_coupon", "params": {"width_mm": 38, "depth_mm": 18, "height_mm": 8, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверить посадку аксессуаров.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.08},
            ],
        },
        strategy="split_character_with_costume_and_accessories",
        project_kind="accessory_character_kit",
        min_wall_mm=1.0,
    )


def _paintable_miniature_pack_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "paintable-miniature-pack-v0",
            "requirements": [
                "Premium miniature pack: base/body/head/eyes/hands/nails split for painting or AMS assignment.",
                "Мелкие цветные детали выдаются отдельными named solids, чтобы Bambu Studio/AMS и ручная покраска были понятными.",
            ],
            "critical_dimensions": [
                {"name": "минимальная цветовая вставка", "value_mm": 0.9, "tolerance_mm": 0.15},
                {"name": "зазор head/body", "value_mm": 0.25, "tolerance_mm": 0.1},
                {"name": "base socket", "value_mm": 4.0, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "collectible_base", "name": "Collectible display base", "template": "collectible_display_base", "params": {"width_mm": 86, "depth_mm": 62, "height_mm": 12, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA neutral", "orientation": "дном на стол", "purpose": "База с keyed sockets.", "assembly_step": "Собрать последней.", "tolerance_mm": 0.25},
                {"id": "mini_body", "name": "Miniature body", "template": "keyed_character_torso", "params": {"width_mm": 54, "depth_mm": 38, "height_mm": 58, "wall_mm": 1.8, "hole_mm": 4}, "material": "PLA robe/main", "orientation": "спиной на стол", "purpose": "Тело/одежда.", "assembly_step": "Вставить в base.", "tolerance_mm": 0.25},
                {"id": "mini_head", "name": "Miniature head", "template": "keyed_character_head", "params": {"width_mm": 58, "depth_mm": 46, "height_mm": 44, "wall_mm": 1.6, "hole_mm": 4}, "material": "PLA skin", "orientation": "лицо вверх/назад, supports не на лице", "purpose": "Голова отдельной деталью.", "assembly_step": "Собрать после eye fit.", "tolerance_mm": 0.25},
                {"id": "eyes_color_parts", "name": "Eyes color inserts", "template": "color_eye_set", "params": {"width_mm": 32, "depth_mm": 10, "height_mm": 3, "wall_mm": 1.0, "radius_mm": 3.2}, "material": "PLA black/gloss", "orientation": "плашмя", "purpose": "Глаза отдельным цветом/вклейкой.", "assembly_step": "Вклеить после покраски.", "tolerance_mm": 0.12},
                {"id": "hands_color_parts", "name": "Hands color parts", "template": "character_hands_pair", "params": {"width_mm": 44, "depth_mm": 18, "height_mm": 16, "wall_mm": 1.3, "hole_mm": 3}, "material": "PLA skin", "orientation": "плашмя", "purpose": "Руки отдельными цветными деталями.", "assembly_step": "Вклеить в sleeves/body.", "tolerance_mm": 0.18},
                {"id": "nails_claws", "name": "Nails/claws detail set", "template": "nail_claw_set", "params": {"width_mm": 42, "depth_mm": 12, "height_mm": 3, "wall_mm": 0.9}, "material": "PLA contrast", "orientation": "плашмя, brim", "purpose": "Мелкие ногти/когти утолщены для печати.", "assembly_step": "Печатать медленно или заменить покраской.", "tolerance_mm": 0.1},
                {"id": "paint_swatches", "name": "Paint/AMS swatches", "template": "paint_swatch_strip", "params": {"width_mm": 64, "depth_mm": 14, "height_mm": 2.4, "wall_mm": 1.0}, "material": "all planned colors", "orientation": "плашмя", "purpose": "Проверка цветов/слоя/paint adhesion.", "assembly_step": "Печатать перед фигуркой.", "tolerance_mm": 0.1},
                {"id": "mini_fit_coupon", "name": "Miniature connector coupon", "template": "pin_socket_coupon", "params": {"width_mm": 38, "depth_mm": 18, "height_mm": 8, "wall_mm": 2.0, "hole_mm": 4}, "material": "PLA", "orientation": "плашмя", "purpose": "Проверить соединения base/body/head.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.08},
            ],
        },
        strategy="paintable_collectible_with_named_color_parts",
        project_kind="paintable_miniature_pack",
        min_wall_mm=0.8,
    )


def _seed_starter_kit_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "seed-starter-grower-system-v0",
            "requirements": [
                "Seed starter kit: cell tray, water base, humidity dome, soil press and drainage coupon.",
                "Это функциональная система для воды/земли: PETG предпочтительнее PLA, нужны дренаж и gap для воды.",
            ],
            "critical_dimensions": [
                {"name": "дренажные отверстия", "value_mm": 3.0, "tolerance_mm": 0.3},
                {"name": "зазор water base/tray", "value_mm": 0.4, "tolerance_mm": 0.15},
                {"name": "минимальная стенка ячейки", "value_mm": 1.2, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "cell_tray", "name": "Seed cell tray 2x3", "template": "seed_cell_tray", "params": {"width_mm": 132, "depth_mm": 88, "height_mm": 42, "wall_mm": 1.4, "hole_mm": 3}, "material": "PETG", "orientation": "дном на стол, supports OFF", "purpose": "Ячейки для рассады с дренажем.", "assembly_step": "Поставить на water base.", "tolerance_mm": 0.3},
                {"id": "water_gap_base", "name": "Water gap base", "template": "water_gap_base", "params": {"width_mm": 140, "depth_mm": 96, "height_mm": 14, "wall_mm": 2.0}, "material": "PETG", "orientation": "дном на стол", "purpose": "Поддон с зазором для воды.", "assembly_step": "Печатать после drainage coupon.", "tolerance_mm": 0.3},
                {"id": "humidity_dome", "name": "Humidity dome", "template": "humidity_dome", "params": {"width_mm": 138, "depth_mm": 94, "height_mm": 52, "wall_mm": 1.0, "hole_mm": 6}, "material": "PETG transparent", "orientation": "нижней кромкой на стол, brim", "purpose": "Крышка/парник с вентиляцией.", "assembly_step": "Накрывать без герметизации.", "tolerance_mm": 0.35},
                {"id": "soil_press", "name": "Soil press", "template": "soil_press", "params": {"width_mm": 38, "depth_mm": 28, "height_mm": 20, "wall_mm": 2.0}, "material": "PETG", "orientation": "ручкой вверх", "purpose": "Пресс для одинаковой глубины грунта.", "assembly_step": "Использовать перед посадкой.", "tolerance_mm": 0.2},
                {"id": "drainage_coupon", "name": "Drainage/gap coupon", "template": "drainage_coupon", "params": {"width_mm": 42, "depth_mm": 28, "height_mm": 6, "wall_mm": 2.0, "hole_mm": 3}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить отверстия и flow.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.15},
            ],
        },
        strategy="seed_starter_system_with_water_gap_and_drainage",
        project_kind="seed_starter_kit",
        min_wall_mm=1.0,
    )


def _wall_mount_system_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "wall-mount-key-holder-system-v0",
            "requirements": [
                "Wall mount system: wall-side plate + object-side/key holder + screw/no-screw variants + load coupon.",
                "Нужны screw clearance, countersink, ориентация по слоям и честное ограничение нагрузки.",
            ],
            "critical_dimensions": [
                {"name": "screw clearance", "value_mm": 4.2, "tolerance_mm": 0.15},
                {"name": "countersink", "value_mm": 8.0, "tolerance_mm": 0.25},
                {"name": "зацеп wall/object halves", "value_mm": 0.35, "tolerance_mm": 0.12},
            ],
            "parts": [
                {"id": "wall_side_plate", "name": "Wall-side fixing plate", "template": "wall_plate", "params": {"width_mm": 72, "depth_mm": 10, "height_mm": 92, "wall_mm": 3.0, "hole_mm": 4.2}, "material": "PETG", "orientation": "плашмя, слои вдоль нагрузки", "purpose": "Половина крепления на стену.", "assembly_step": "Крепить двумя винтами.", "tolerance_mm": 0.2},
                {"id": "object_side_half", "name": "Object-side sliding half", "template": "object_mount_half", "params": {"width_mm": 66, "depth_mm": 12, "height_mm": 76, "wall_mm": 2.6}, "material": "PETG", "orientation": "плашмя", "purpose": "Ответная половина с sliding lock.", "assembly_step": "Надвинуть сверху вниз.", "tolerance_mm": 0.2},
                {"id": "key_hook_bar", "name": "Key hook bar", "template": "key_hook_bar", "params": {"width_mm": 94, "depth_mm": 18, "height_mm": 28, "wall_mm": 3.0, "radius_mm": 4}, "material": "PETG", "orientation": "крючками вверх, supports minimal", "purpose": "Крючки для ключей.", "assembly_step": "Прикрутить/вклеить в object half.", "tolerance_mm": 0.25},
                {"id": "screw_clearance_coupon", "name": "Screw clearance coupon", "template": "screw_clearance_coupon", "params": {"width_mm": 40, "depth_mm": 12, "height_mm": 24, "wall_mm": 2.4, "hole_mm": 4.2}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверка винта и countersink.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.1},
                {"id": "load_test_bar", "name": "Load test bar", "template": "load_test_bar", "params": {"width_mm": 90, "depth_mm": 12, "height_mm": 12, "wall_mm": 3.0}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверка прогиба/нагрузки.", "assembly_step": "Тестировать до монтажа.", "tolerance_mm": 0.2},
            ],
        },
        strategy="two_part_wall_mount_with_load_and_screw_coupons",
        project_kind="wall_mount_system",
        min_wall_mm=1.2,
    )


def _printer_tool_holder_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "ender-printer-tool-holder-system-v0",
            "requirements": [
                "Printer tool holder: printer-specific rail, mirrored variants, slots for nozzle keys, hex keys, scraper and pliers.",
                "Не универсальная коробка: посадки привязаны к профилю принтера и имеют тестовый coupon.",
            ],
            "critical_dimensions": [
                {"name": "V-slot rail clearance", "value_mm": 0.3, "tolerance_mm": 0.12},
                {"name": "tool slot clearance", "value_mm": 0.4, "tolerance_mm": 0.15},
            ],
            "parts": [
                {"id": "printer_rail_mount", "name": "Ender-style rail mount", "template": "printer_tool_holder_rail", "params": {"width_mm": 118, "depth_mm": 24, "height_mm": 28, "wall_mm": 2.6, "hole_mm": 5}, "material": "PETG", "orientation": "плашмя, зацеп не вдоль слабых слоёв", "purpose": "Крепление на профиль принтера.", "assembly_step": "Проверить rail coupon.", "tolerance_mm": 0.2},
                {"id": "nozzle_slot_block", "name": "Nozzle slot block", "template": "nozzle_slot_block", "params": {"width_mm": 64, "depth_mm": 22, "height_mm": 14, "wall_mm": 2.0, "hole_mm": 6}, "material": "PETG", "orientation": "плашмя", "purpose": "Гнёзда под сопла/ключи.", "assembly_step": "Вставить в rail mount.", "tolerance_mm": 0.15},
                {"id": "hex_key_rack", "name": "Hex key rack", "template": "hex_key_rack", "params": {"width_mm": 72, "depth_mm": 18, "height_mm": 22, "wall_mm": 2.0}, "material": "PETG", "orientation": "плашмя", "purpose": "Набор пазов под шестигранники.", "assembly_step": "Проверить размеры ключей.", "tolerance_mm": 0.2},
                {"id": "scraper_hook", "name": "Scraper hook", "template": "scraper_hook", "params": {"width_mm": 38, "depth_mm": 24, "height_mm": 32, "wall_mm": 3.0}, "material": "PETG", "orientation": "на боку для прочности крюка", "purpose": "Крюк под скребок/кусачки.", "assembly_step": "Печатать с повышенными периметрами.", "tolerance_mm": 0.25},
                {"id": "mirror_mount", "name": "Mirrored rail mount", "template": "printer_tool_holder_rail", "params": {"width_mm": 118, "depth_mm": 24, "height_mm": 28, "wall_mm": 2.6, "hole_mm": 5}, "material": "PETG", "orientation": "mirror variant", "purpose": "Левая/правая версия.", "assembly_step": "Выбрать сторону установки.", "tolerance_mm": 0.2},
                {"id": "rail_fit_coupon", "name": "Rail fit coupon", "template": "rail_fit_coupon", "params": {"width_mm": 38, "depth_mm": 18, "height_mm": 16, "wall_mm": 2.0, "hole_mm": 5}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить посадку на профиль.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.1},
            ],
        },
        strategy="printer_specific_tool_holder_with_mirror_and_fit_coupon",
        project_kind="printer_tool_holder",
        min_wall_mm=1.2,
    )


def _modular_storage_system_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "modular-storage-crate-screw-box-v0",
            "requirements": [
                "Modular storage system: stackable crate, mesh/solid variants, half/quarter modules, dividers and label tabs.",
                "Система должна быть совместимой сама с собой: единый шаг, stacking lip и тест посадки.",
            ],
            "critical_dimensions": [
                {"name": "stacking lip clearance", "value_mm": 0.35, "tolerance_mm": 0.12},
                {"name": "divider slot", "value_mm": 1.6, "tolerance_mm": 0.15},
                {"name": "минимальная перемычка mesh", "value_mm": 1.2, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "stackable_crate", "name": "Stackable crate body", "template": "stackable_crate_body", "params": {"width_mm": 120, "depth_mm": 80, "height_mm": 48, "wall_mm": 2.0}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Основной модуль с stacking lip.", "assembly_step": "Проверить stacking coupon.", "tolerance_mm": 0.3},
                {"id": "mesh_crate_variant", "name": "Mesh crate variant", "template": "crate_mesh_side", "params": {"width_mm": 120, "depth_mm": 80, "height_mm": 48, "wall_mm": 1.6}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Вентилируемый/лёгкий вариант.", "assembly_step": "Печатать после rib coupon.", "tolerance_mm": 0.3},
                {"id": "half_module", "name": "Half-width storage module", "template": "screw_compartment_box", "params": {"width_mm": 60, "depth_mm": 80, "height_mm": 36, "wall_mm": 1.8}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Половинный модуль.", "assembly_step": "Комбинировать с full crate.", "tolerance_mm": 0.25},
                {"id": "quarter_module", "name": "Quarter screw box", "template": "screw_compartment_box", "params": {"width_mm": 60, "depth_mm": 40, "height_mm": 28, "wall_mm": 1.6}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Малый модуль под винты/биты.", "assembly_step": "Добавить label tab.", "tolerance_mm": 0.25},
                {"id": "storage_divider", "name": "Removable divider", "template": "storage_divider", "params": {"width_mm": 76, "depth_mm": 2, "height_mm": 30, "wall_mm": 1.6}, "material": "PLA", "orientation": "плашмя", "purpose": "Перегородка.", "assembly_step": "Вставить в divider slots.", "tolerance_mm": 0.15},
                {"id": "label_tabs", "name": "Label tabs", "template": "label_tab", "params": {"width_mm": 54, "depth_mm": 10, "height_mm": 2.4, "wall_mm": 1.0}, "material": "PLA contrast", "orientation": "лицом вверх", "purpose": "Маркировка ячеек.", "assembly_step": "Вклеить или вставить.", "tolerance_mm": 0.1},
                {"id": "stacking_coupon", "name": "Stacking lip coupon", "template": "stacking_lip_coupon", "params": {"width_mm": 42, "depth_mm": 24, "height_mm": 12, "wall_mm": 2.0}, "material": "PLA/PETG", "orientation": "плашмя", "purpose": "Проверить посадку stackable lip.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.1},
            ],
        },
        strategy="modular_stackable_storage_family_with_shared_grid",
        project_kind="modular_storage_system",
        min_wall_mm=1.0,
    )


def _pegboard_ecosystem_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "pegboard-parametric-ecosystem-v0",
            "requirements": [
                "Pegboard ecosystem: common peg spacing, hooks, boxes, caliper holder, flashlight clip and spacing coupon.",
                "Главный урок Pegstr: делать не одну модель, а совместимую parametric family.",
            ],
            "critical_dimensions": [
                {"name": "peg spacing", "value_mm": 25.4, "tolerance_mm": 0.1},
                {"name": "peg diameter", "value_mm": 6.0, "tolerance_mm": 0.12},
                {"name": "hook wall", "value_mm": 2.4, "tolerance_mm": 0.2},
            ],
            "parts": [
                {"id": "pegboard_base_plate", "name": "Pegboard base plate", "template": "pegboard_base_plate", "params": {"width_mm": 102, "depth_mm": 6, "height_mm": 76, "wall_mm": 2.4, "hole_mm": 6}, "material": "PETG", "orientation": "плашмя", "purpose": "Контрольная панель с сеткой.", "assembly_step": "Проверить spacing.", "tolerance_mm": 0.15},
                {"id": "peg_hook_module", "name": "Peg hook module", "template": "peg_hook_module", "params": {"width_mm": 54, "depth_mm": 34, "height_mm": 28, "wall_mm": 2.4, "hole_mm": 6}, "material": "PETG", "orientation": "на боку для прочности крюка", "purpose": "Крюк под инструмент.", "assembly_step": "Тестировать нагрузкой.", "tolerance_mm": 0.2},
                {"id": "peg_box_module", "name": "Peg small box module", "template": "peg_box_module", "params": {"width_mm": 68, "depth_mm": 42, "height_mm": 36, "wall_mm": 1.8, "hole_mm": 6}, "material": "PETG", "orientation": "дном на стол", "purpose": "Коробка на pegboard.", "assembly_step": "Повесить на два pegs.", "tolerance_mm": 0.25},
                {"id": "peg_caliper_holder", "name": "Caliper holder", "template": "peg_caliper_holder", "params": {"width_mm": 72, "depth_mm": 28, "height_mm": 54, "wall_mm": 2.2, "hole_mm": 6}, "material": "PETG", "orientation": "плашмя/на боку", "purpose": "Держатель штангенциркуля.", "assembly_step": "Проверить баланс.", "tolerance_mm": 0.25},
                {"id": "peg_flashlight_clip", "name": "Flashlight clip", "template": "peg_flashlight_clip", "params": {"width_mm": 54, "depth_mm": 32, "height_mm": 34, "wall_mm": 2.0, "radius_mm": 12, "hole_mm": 6}, "material": "PETG", "orientation": "на боку", "purpose": "Клипса фонарика.", "assembly_step": "Проверить диаметр.", "tolerance_mm": 0.25},
                {"id": "peg_spacing_coupon", "name": "Peg spacing coupon", "template": "peg_spacing_coupon", "params": {"width_mm": 64, "depth_mm": 10, "height_mm": 28, "wall_mm": 2.0, "hole_mm": 6}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить сетку pegboard.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.08},
            ],
        },
        strategy="parametric_pegboard_module_ecosystem",
        project_kind="pegboard_ecosystem",
        min_wall_mm=1.0,
    )


def _perforated_basket_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "perforated-basket-food-safe-v0",
            "requirements": [
                "Perforated basket: controlled ribs, handles, drainage/perforation and food-contact warning.",
                "Food/contact use требует материала и постобработки; PLA porous surface не считается пищевой безопасностью автоматически.",
            ],
            "critical_dimensions": [
                {"name": "минимальная перемычка корзины", "value_mm": 1.2, "tolerance_mm": 0.2},
                {"name": "радиус ручки", "value_mm": 4.0, "tolerance_mm": 0.25},
            ],
            "parts": [
                {"id": "basket_shell", "name": "Perforated basket shell", "template": "perforated_basket_shell", "params": {"width_mm": 118, "depth_mm": 84, "height_mm": 54, "wall_mm": 1.4, "hole_mm": 8}, "material": "PETG", "orientation": "дном на стол, supports OFF если свесы <45°", "purpose": "Корзина с отверстиями и рёбрами.", "assembly_step": "Печатать после rib coupon.", "tolerance_mm": 0.35},
                {"id": "basket_handle_left", "name": "Left handle", "template": "basket_handle", "params": {"width_mm": 42, "depth_mm": 12, "height_mm": 24, "wall_mm": 3.0, "radius_mm": 4}, "material": "PETG", "orientation": "плашмя", "purpose": "Съёмная/вклеиваемая ручка.", "assembly_step": "Вставить в side sockets.", "tolerance_mm": 0.2},
                {"id": "basket_handle_right", "name": "Right handle", "template": "basket_handle", "params": {"width_mm": 42, "depth_mm": 12, "height_mm": 24, "wall_mm": 3.0, "radius_mm": 4}, "material": "PETG", "orientation": "плашмя", "purpose": "Вторая ручка.", "assembly_step": "Вставить симметрично.", "tolerance_mm": 0.2},
                {"id": "rib_strength_coupon", "name": "Thin rib strength coupon", "template": "rib_strength_coupon", "params": {"width_mm": 48, "depth_mm": 18, "height_mm": 10, "wall_mm": 1.2}, "material": "PETG", "orientation": "плашмя", "purpose": "Проверить thin ribs/perforation.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.12},
            ],
        },
        strategy="perforated_basket_with_rib_coupon_and_food_contact_warning",
        project_kind="perforated_basket",
        min_wall_mm=1.0,
    )


def _winged_creature_statue_specs(text: str) -> Dict[str, Any]:
    return _with_print_contract(
        {
            "project_name": "winged-creature-statue-split-v0",
            "requirements": [
                "Winged creature statue: body, wing pair, tail, base, pins and support-scar coupon.",
                "Это organic statue, не чистый CAD: финал должен использовать sculpt/Meshy форму как reference и инженерно разрезать на печатные solids.",
            ],
            "critical_dimensions": [
                {"name": "wing root pin", "value_mm": 4.0, "tolerance_mm": 0.15},
                {"name": "минимальная кромка крыла", "value_mm": 1.2, "tolerance_mm": 0.2},
                {"name": "tail connector clearance", "value_mm": 0.25, "tolerance_mm": 0.1},
            ],
            "parts": [
                {"id": "creature_body", "name": "Winged creature body", "template": "winged_body_statue", "params": {"width_mm": 74, "depth_mm": 52, "height_mm": 86, "wall_mm": 2.0, "radius_mm": 24, "hole_mm": 4}, "material": "PLA/PETG or resin", "orientation": "спиной/хвостом к supports, лицо не в supports", "purpose": "Корпус статуи с sockets.", "assembly_step": "Собрать после fit coupon.", "tolerance_mm": 0.3},
                {"id": "wing_pair", "name": "Split wing pair", "template": "wing_pair_split", "params": {"width_mm": 112, "depth_mm": 8, "height_mm": 64, "wall_mm": 1.4, "hole_mm": 4}, "material": "PLA/PETG", "orientation": "плашмя/под углом, brim", "purpose": "Крылья отдельными деталями.", "assembly_step": "Вклеить в wing sockets.", "tolerance_mm": 0.25},
                {"id": "tail_segment", "name": "Tail segment", "template": "tail_segment", "params": {"width_mm": 84, "depth_mm": 18, "height_mm": 22, "wall_mm": 1.6, "hole_mm": 3}, "material": "PLA/PETG", "orientation": "плашмя, supports minimal", "purpose": "Хвост отдельной деталью.", "assembly_step": "Вставить в body socket.", "tolerance_mm": 0.2},
                {"id": "creature_base", "name": "Rock/display base", "template": "creature_base", "params": {"width_mm": 92, "depth_mm": 72, "height_mm": 16, "wall_mm": 2.6, "hole_mm": 4}, "material": "PLA/PETG", "orientation": "дном на стол", "purpose": "Устойчивая база.", "assembly_step": "Вклеить ноги/корпус.", "tolerance_mm": 0.25},
                {"id": "wing_pin_set", "name": "Wing/tail pin set", "template": "pin_connector_set", "params": {"width_mm": 62, "depth_mm": 12, "height_mm": 4, "wall_mm": 1.2, "radius_mm": 2.0}, "material": "PETG", "orientation": "плашмя", "purpose": "Запасные пины.", "assembly_step": "Подогнать после coupon.", "tolerance_mm": 0.1},
                {"id": "support_scar_coupon", "name": "Wing support-scar coupon", "template": "support_scar_coupon", "params": {"width_mm": 46, "depth_mm": 18, "height_mm": 28, "wall_mm": 1.2}, "material": "same as statue", "orientation": "как wing root", "purpose": "Проверить supports на тонкой organic детали.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.12},
            ],
        },
        strategy="split_winged_statue_with_pins_base_and_support_coupon",
        project_kind="winged_creature_statue",
        min_wall_mm=1.0,
    )


_MECHANICAL_BOEING_FORBIDDEN_TEMPLATES = frozenset(
    {"cylinder", "spur_gear", "wing_pair_split", "planet_arm", "gear_mesh_coupon"}
)
_MECHANICAL_BOEING_REQUIRED_TEMPLATES = frozenset(
    {
        "airliner_fuselage_section",
        "airliner_wing_half",
        "airliner_vert_stab",
        "airliner_horz_stab_half",
        "airliner_engine_pod_single",
        "airliner_fan_rotor_single",
        "airliner_gear_strut",
        "airliner_wheel_revolute",
        "pin_socket_coupon",
        "airliner_wheel_fit_coupon",
        "airliner_fan_blade_coupon",
    }
)
_MECHANICAL_BOEING_FIT_COUPONS = frozenset(
    {"hinge_fit_coupon", "wheel_fit_coupon", "fan_blade_coupon"}
)


def _mechanical_boeing_kinematics() -> List[Dict[str, Any]]:
    """Explicit joint model for assembly.md / engineering/kinematics.json."""
    return [
        {
            "joint_id": "fan_L1",
            "type": "revolute",
            "axis": "+Y",
            "parent": "engine_pod_L1",
            "child": "fan_disc_L1",
            "motion": "free_spin",
            "clearance_mm": 0.15,
            "note": "Декоративное вращение лопастей на оси; не тянуть силой.",
        },
        {
            "joint_id": "fan_R1",
            "type": "revolute",
            "axis": "+Y",
            "parent": "engine_pod_R1",
            "child": "fan_disc_R1",
            "motion": "free_spin",
            "clearance_mm": 0.15,
            "note": "Симметричный узел правого двигателя.",
        },
        {
            "joint_id": "fan_L2",
            "type": "revolute",
            "axis": "+Y",
            "parent": "engine_pod_L2",
            "child": "fan_disc_L2",
            "motion": "free_spin",
            "clearance_mm": 0.15,
            "note": "Внутренний левый двигатель.",
        },
        {
            "joint_id": "fan_R2",
            "type": "revolute",
            "axis": "+Y",
            "parent": "engine_pod_R2",
            "child": "fan_disc_R2",
            "motion": "free_spin",
            "clearance_mm": 0.15,
            "note": "Внутренний правый двигатель.",
        },
        {
            "joint_id": "gear_nose",
            "type": "revolute",
            "axis": "+X",
            "parent": "fuselage_fwd",
            "child": "nose_gear_strut",
            "motion": "fold_up",
            "range_deg": "0..78",
            "clearance_mm": 0.35,
            "note": "Носовая стойка убирается вверх/назад после hinge coupon.",
        },
        {
            "joint_id": "gear_main_left",
            "type": "revolute",
            "axis": "+X",
            "parent": "fuselage_fwd",
            "child": "main_gear_left",
            "motion": "fold_up",
            "range_deg": "0..72",
            "clearance_mm": 0.35,
            "note": "Левая основная стойка складывается как у airliner.",
        },
        {
            "joint_id": "gear_main_right",
            "type": "revolute",
            "axis": "+X",
            "parent": "fuselage_fwd",
            "child": "main_gear_right",
            "motion": "fold_up",
            "range_deg": "0..72",
            "clearance_mm": 0.35,
            "note": "Правая основная стойка — зеркально левой.",
        },
        {
            "joint_id": "wheel_nose",
            "type": "revolute",
            "axis": "+Y",
            "parent": "nose_gear_strut",
            "child": "wheel_nose",
            "motion": "free_spin",
            "clearance_mm": 0.25,
            "note": "Носовое колесо вращается на pin после wheel fit coupon.",
        },
        {
            "joint_id": "wheel_main_left",
            "type": "revolute",
            "axis": "+Y",
            "parent": "main_gear_left",
            "child": "wheel_main_left",
            "motion": "free_spin",
            "clearance_mm": 0.25,
            "note": "Левое основное колесо.",
        },
        {
            "joint_id": "wheel_main_right",
            "type": "revolute",
            "axis": "+Y",
            "parent": "main_gear_right",
            "child": "wheel_main_right",
            "motion": "free_spin",
            "clearance_mm": 0.25,
            "note": "Правое основное колесо.",
        },
    ]


def validate_mechanical_boeing_specs(specs: Dict[str, Any]) -> List[str]:
    """Programmatic gate: reject generic primitives masquerading as mechanical Boeing."""
    issues: List[str] = []
    parts = [p for p in (specs.get("parts") or []) if isinstance(p, dict)]
    templates = {str(p.get("template") or "") for p in parts}
    part_ids = {str(p.get("id") or "") for p in parts}
    bad = templates & _MECHANICAL_BOEING_FORBIDDEN_TEMPLATES
    if bad:
        issues.append(
            f"Mechanical Boeing: запрещённые generic-шаблоны {sorted(bad)} — нужен specialized airliner kit v2."
        )
    missing = _MECHANICAL_BOEING_REQUIRED_TEMPLATES - templates
    if missing:
        issues.append(f"Mechanical Boeing: нет обязательных шаблонов {sorted(missing)}.")
    missing_coupons = _MECHANICAL_BOEING_FIT_COUPONS - part_ids
    if missing_coupons:
        issues.append(f"Mechanical Boeing: нет fit-coupons {sorted(missing_coupons)} (fit-first).")
    kinematics = specs.get("kinematics") if isinstance(specs.get("kinematics"), list) else []
    if len(kinematics) < 8:
        issues.append(f"Mechanical Boeing: мало узлов кинематики ({len(kinematics)}), нужно ≥8.")
    if len(parts) < 18:
        issues.append(f"Mechanical Boeing: мало деталей ({len(parts)}), v3 kit ожидает ≥18.")
    fit_frames = [
        int(p.get("frame_number") or 99)
        for p in parts
        if str(p.get("id") or "") in _MECHANICAL_BOEING_FIT_COUPONS
    ]
    if fit_frames and max(fit_frames) > 3:
        issues.append("Mechanical Boeing: fit-coupons должны печататься первыми (frame 1–3).")
    return issues


def build_kinematics_json(specs: Dict[str, Any]) -> str:
    payload = {
        "assembly_version": specs.get("assembly_version") or "v2",
        "project_kind": specs.get("project_kind"),
        "strategy": specs.get("strategy"),
        "joints": specs.get("kinematics") or [],
        "fit_first_coupons": sorted(_MECHANICAL_BOEING_FIT_COUPONS),
        "notes": [
            "Revolute joints are printable separate parts + pins, not CAD constraint solver.",
            "Fold range is indicative; tune after hinge_fit_coupon on your printer.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_kinematics_md(specs: Dict[str, Any]) -> str:
    lines = [
        "# Кинематика сборки",
        "",
        f"Версия: **{specs.get('assembly_version') or 'v2'}**",
        f"Стратегия: `{specs.get('strategy') or ''}`",
        "",
        "## Fit-first (печатать до полной сборки)",
        "1. `hinge_fit_coupon` — зазор шарнира шасси",
        "2. `wheel_fit_coupon` — зазор оси колеса",
        "3. `fan_blade_coupon` — толщина/деталь лопасти",
        "",
        "## Узлы",
        "| joint | type | parent → child | motion | clearance |",
        "|---|---|---|---|---|",
    ]
    for j in specs.get("kinematics") or []:
        if not isinstance(j, dict):
            continue
        lines.append(
            f"| {j.get('joint_id')} | {j.get('type')} | "
            f"{j.get('parent')} → {j.get('child')} | {j.get('motion')} | "
            f"{j.get('clearance_mm', '—')} мм |"
        )
    lines.extend(
        [
            "",
            "## Сборка (кратко)",
            "1. Подобрать pins по coupons.",
            "2. Собрать шасси на fuselage hinge bays.",
            "3. Установить колёса на оси.",
            "4. Приклеить крылья/хвост/двигатели.",
            "5. Посадить fan rotors в pods (вращение вручную).",
            "",
            "⚠️ Это инженерный kit v2, не финальный CAD Boeing. Для «магической» внешности нужен Meshy shell поверх этого каркаса.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_fit_first_print_order(parts: List[Dict[str, Any]]) -> str:
    ordered = sorted(
        enumerate(parts, start=1),
        key=lambda item: (int(item[1].get("frame_number") or item[0]), item[0]),
    )
    lines = [
        "FIT-FIRST PRINT ORDER",
        "===================",
        "Сначала coupons, потом шасси/колёса/лопасти, затем корпус и крылья.",
        "",
    ]
    for idx, part in ordered:
        pid = part.get("id") or f"part-{idx}"
        frame = part.get("frame_number") or idx
        lines.append(
            f"{int(frame):02d}. {pid} — {part.get('name') or pid} "
            f"[{part.get('template')}]"
        )
    return "\n".join(lines) + "\n"


def _mechanical_boeing_airliner_specs(text: str) -> Dict[str, Any]:
    from bot.services.engineering_intake import requested_dimensions_mm

    dims = requested_dimensions_mm(text)
    length_mm = float(dims.get("length_mm") or 200.0)
    height_mm = float(dims.get("height_mm") or min(150.0, length_mm * 0.45))
    wingspan_mm = float(dims.get("wingspan_mm") or length_mm * 0.95)
    fuse_depth = max(24.0, min(36.0, length_mm * 0.14))
    fuse_height = max(22.0, min(34.0, height_mm * 0.22))
    wing_chord = max(42.0, wingspan_mm * 0.28)
    pin_mm = 3.0 if length_mm >= 180 else 2.6
    wheel_r = max(3.5, length_mm * 0.02)

    specs = _with_print_contract(
        {
            "project_name": "mechanical-boeing-airliner-assembly-v3",
            "assembly_version": "v3",
            "reference_kit": "clerx_boeing_747sp",
            "requirements": [
                "Mechanical Boeing airliner v3: CLERX-style split (fuselage fwd/aft, wings L/R, 4 pods, 4 fan discs).",
                "Explicit kinematics: revolute fans, folding gear, spinning wheels.",
                "Fit-first: hinge / wheel / fan coupons печатаются до полного kit.",
                "Инженерный printable kit под Bambu P2S; внешность — OpenSCAD, не Meshy sculpt.",
            ],
            "critical_dimensions": [
                {"name": "target length", "value_mm": length_mm, "tolerance_mm": 2.0},
                {"name": "target height", "value_mm": height_mm, "tolerance_mm": 2.0},
                {"name": "wingspan (semantic)", "value_mm": wingspan_mm, "tolerance_mm": 3.0},
                {"name": "wheel axle clearance", "value_mm": 0.25, "tolerance_mm": 0.08},
                {"name": "landing gear hinge clearance", "value_mm": 0.35, "tolerance_mm": 0.1},
                {"name": "fan rotor clearance", "value_mm": 0.15, "tolerance_mm": 0.08},
                {"name": "wing root pin", "value_mm": pin_mm, "tolerance_mm": 0.12},
            ],
            "kinematics": _mechanical_boeing_kinematics(),
            "fit_first_coupon_ids": sorted(_MECHANICAL_BOEING_FIT_COUPONS),
            "parts": [
                {
                    "id": "hinge_fit_coupon",
                    "frame_number": 1,
                    "name": "Landing gear hinge fit coupon",
                    "template": "pin_socket_coupon",
                    "params": {"width_mm": 40, "depth_mm": 18, "height_mm": 8, "wall_mm": 2.0, "hole_mm": pin_mm},
                    "material": "PETG/PLA",
                    "orientation": "плашмя",
                    "purpose": "Проверить зазор folding hinge до печати шасси.",
                    "assembly_step": "Печатать первым; подобрать pin 3.0→2.8 мм при заедании.",
                    "tolerance_mm": 0.08,
                },
                {
                    "id": "wheel_fit_coupon",
                    "frame_number": 2,
                    "name": "Wheel axle fit coupon",
                    "template": "airliner_wheel_fit_coupon",
                    "params": {"width_mm": 36, "depth_mm": 16, "height_mm": 8, "wall_mm": 1.2, "radius_mm": wheel_r, "hole_mm": pin_mm * 0.72},
                    "material": "PETG/PLA black",
                    "orientation": "плашмя",
                    "purpose": "Проверить вращение колеса на оси.",
                    "assembly_step": "Печатать вторым.",
                    "tolerance_mm": 0.08,
                },
                {
                    "id": "fan_blade_coupon",
                    "frame_number": 3,
                    "name": "Fan blade detail coupon",
                    "template": "airliner_fan_blade_coupon",
                    "params": {"width_mm": 42, "depth_mm": 20, "height_mm": 4, "wall_mm": 1.0, "radius_mm": max(7.0, length_mm * 0.04)},
                    "material": "PLA black/white",
                    "orientation": "лицом вверх, 0.12–0.16 mm layer",
                    "purpose": "Проверить толщину лопастей на сопле 0.4.",
                    "assembly_step": "Печатать третьим.",
                    "tolerance_mm": 0.08,
                },
                {
                    "id": "nose_gear_strut",
                    "frame_number": 4,
                    "name": "Nose landing gear strut (folding)",
                    "template": "airliner_gear_strut",
                    "params": {"width_mm": 28, "depth_mm": fuse_depth * 0.9, "height_mm": height_mm * 0.22, "wall_mm": 1.6, "hole_mm": pin_mm, "radius_mm": wheel_r},
                    "material": "PETG/PLA",
                    "orientation": "плашмя, 4 perimeters",
                    "purpose": "Носовая стойка с hinge boss и wheel boss.",
                    "assembly_step": "Собрать на pin в fuselage bay после hinge coupon.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "main_gear_left",
                    "frame_number": 5,
                    "name": "Main landing gear left (folding)",
                    "template": "airliner_gear_strut",
                    "params": {"width_mm": 32, "depth_mm": fuse_depth, "height_mm": height_mm * 0.28, "wall_mm": 1.8, "hole_mm": pin_mm, "radius_mm": wheel_r * 1.05},
                    "material": "PETG/PLA",
                    "orientation": "плашмя, 4–5 perimeters",
                    "purpose": "Левая основная стойка, revolute fold joint.",
                    "assembly_step": "Зеркально правой; не перепутать стороны.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "main_gear_right",
                    "frame_number": 6,
                    "name": "Main landing gear right (folding)",
                    "template": "airliner_gear_strut",
                    "params": {"width_mm": 32, "depth_mm": fuse_depth, "height_mm": height_mm * 0.28, "wall_mm": 1.8, "hole_mm": pin_mm, "radius_mm": wheel_r * 1.05},
                    "material": "PETG/PLA",
                    "orientation": "плашмя, 4–5 perimeters",
                    "purpose": "Правая основная стойка.",
                    "assembly_step": "Симметрично левой.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "fan_disc_L1",
                    "frame_number": 7,
                    "name": "Fan disc L1 (revolute)",
                    "template": "airliner_fan_rotor_single",
                    "params": {"width_mm": 24, "depth_mm": 24, "height_mm": 5, "wall_mm": 1.0, "radius_mm": max(7.0, length_mm * 0.038), "hole_mm": pin_mm * 0.65, "x_offset_mm": 0},
                    "material": "PLA black",
                    "orientation": "лицом вверх",
                    "purpose": "Левый внешний fan rotor.",
                    "assembly_step": "Посадить в engine_pod_L1 после fan coupon.",
                    "tolerance_mm": 0.1,
                },
                {
                    "id": "fan_disc_R1",
                    "frame_number": 7,
                    "name": "Fan disc R1 (revolute)",
                    "template": "airliner_fan_rotor_single",
                    "params": {"width_mm": 24, "depth_mm": 24, "height_mm": 5, "wall_mm": 1.0, "radius_mm": max(7.0, length_mm * 0.038), "hole_mm": pin_mm * 0.65, "x_offset_mm": 0},
                    "material": "PLA black",
                    "orientation": "лицом вверх",
                    "purpose": "Правый внешний fan rotor.",
                    "assembly_step": "Посадить в engine_pod_R1.",
                    "tolerance_mm": 0.1,
                },
                {
                    "id": "fan_disc_L2",
                    "frame_number": 7,
                    "name": "Fan disc L2 (revolute)",
                    "template": "airliner_fan_rotor_single",
                    "params": {"width_mm": 24, "depth_mm": 24, "height_mm": 5, "wall_mm": 1.0, "radius_mm": max(7.0, length_mm * 0.038), "hole_mm": pin_mm * 0.65, "x_offset_mm": 0},
                    "material": "PLA black",
                    "orientation": "лицом вверх",
                    "purpose": "Левый внутренний fan rotor.",
                    "assembly_step": "Посадить в engine_pod_L2.",
                    "tolerance_mm": 0.1,
                },
                {
                    "id": "fan_disc_R2",
                    "frame_number": 7,
                    "name": "Fan disc R2 (revolute)",
                    "template": "airliner_fan_rotor_single",
                    "params": {"width_mm": 24, "depth_mm": 24, "height_mm": 5, "wall_mm": 1.0, "radius_mm": max(7.0, length_mm * 0.038), "hole_mm": pin_mm * 0.65, "x_offset_mm": 0},
                    "material": "PLA black",
                    "orientation": "лицом вверх",
                    "purpose": "Правый внутренний fan rotor.",
                    "assembly_step": "Посадить в engine_pod_R2.",
                    "tolerance_mm": 0.1,
                },
                {
                    "id": "engine_pod_L1",
                    "frame_number": 8,
                    "name": "Engine pod L1 (outer)",
                    "template": "airliner_engine_pod_single",
                    "params": {"width_mm": 28, "depth_mm": 32, "height_mm": 16, "wall_mm": 1.2, "radius_mm": max(7.5, length_mm * 0.04), "hole_mm": pin_mm * 0.7, "x_offset_mm": 0},
                    "material": "PLA white",
                    "orientation": "pod на боку",
                    "purpose": "Гондола L1 с седлом под fan.",
                    "assembly_step": "Приклеить к wing_left; rotor не клеить.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "engine_pod_L2",
                    "frame_number": 8,
                    "name": "Engine pod L2 (inner)",
                    "template": "airliner_engine_pod_single",
                    "params": {"width_mm": 28, "depth_mm": 32, "height_mm": 16, "wall_mm": 1.2, "radius_mm": max(7.5, length_mm * 0.04), "hole_mm": pin_mm * 0.7, "x_offset_mm": 0},
                    "material": "PLA white",
                    "orientation": "pod на боку",
                    "purpose": "Гондола L2.",
                    "assembly_step": "Приклеить к wing_left.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "engine_pod_R1",
                    "frame_number": 8,
                    "name": "Engine pod R1 (outer)",
                    "template": "airliner_engine_pod_single",
                    "params": {"width_mm": 28, "depth_mm": 32, "height_mm": 16, "wall_mm": 1.2, "radius_mm": max(7.5, length_mm * 0.04), "hole_mm": pin_mm * 0.7, "x_offset_mm": 0},
                    "material": "PLA white",
                    "orientation": "pod на боку",
                    "purpose": "Гондола R1.",
                    "assembly_step": "Приклеить к wing_right.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "engine_pod_R2",
                    "frame_number": 8,
                    "name": "Engine pod R2 (inner)",
                    "template": "airliner_engine_pod_single",
                    "params": {"width_mm": 28, "depth_mm": 32, "height_mm": 16, "wall_mm": 1.2, "radius_mm": max(7.5, length_mm * 0.04), "hole_mm": pin_mm * 0.7, "x_offset_mm": 0},
                    "material": "PLA white",
                    "orientation": "pod на боку",
                    "purpose": "Гондола R2.",
                    "assembly_step": "Приклеить к wing_right.",
                    "tolerance_mm": 0.12,
                },
                {
                    "id": "wheel_set",
                    "frame_number": 9,
                    "name": "Nose + main wheels (revolute)",
                    "template": "airliner_wheel_revolute",
                    "params": {"width_mm": 70, "depth_mm": 18, "height_mm": 8, "wall_mm": 1.2, "radius_mm": wheel_r, "hole_mm": pin_mm * 0.72},
                    "material": "PLA/PETG black",
                    "orientation": "колёса вверх",
                    "purpose": "Три колеса с осями.",
                    "assembly_step": "Собрать после wheel_fit_coupon.",
                    "tolerance_mm": 0.1,
                },
                {
                    "id": "axle_pin_set",
                    "frame_number": 10,
                    "name": "Gear and wheel axle pins",
                    "template": "pin_connector_set",
                    "params": {"width_mm": 78, "depth_mm": 12, "height_mm": 4, "wall_mm": 1.2, "radius_mm": pin_mm * 0.45},
                    "material": "PETG",
                    "orientation": "плашмя",
                    "purpose": "Pins для шасси и колёс.",
                    "assembly_step": "Подобрать длину по coupons.",
                    "tolerance_mm": 0.08,
                },
                {
                    "id": "fuselage_fwd",
                    "frame_number": 11,
                    "name": "Fuselage forward section (CLERX-style)",
                    "template": "airliner_fuselage_section",
                    "params": {"section": "fwd", "width_mm": length_mm * 0.58, "depth_mm": fuse_depth, "height_mm": fuse_height, "wall_mm": 2.0, "hole_mm": pin_mm},
                    "material": "PLA white",
                    "orientation": "на боку, seam вниз",
                    "purpose": "Передняя часть фюзеляжа с wing sockets и nose gear bay.",
                    "assembly_step": "Стыковать с fuselage_aft по шпангоуту/pin.",
                    "tolerance_mm": 0.3,
                },
                {
                    "id": "fuselage_aft",
                    "frame_number": 11,
                    "name": "Fuselage aft section",
                    "template": "airliner_fuselage_section",
                    "params": {"section": "aft", "width_mm": length_mm * 0.48, "depth_mm": fuse_depth, "height_mm": fuse_height * 0.92, "wall_mm": 2.0, "hole_mm": pin_mm},
                    "material": "PLA white",
                    "orientation": "на боку, seam вниз",
                    "purpose": "Задняя часть фюзеляжа с tail socket.",
                    "assembly_step": "Стыковать с fuselage_fwd.",
                    "tolerance_mm": 0.3,
                },
                {
                    "id": "wing_left",
                    "frame_number": 12,
                    "name": "Left wing half",
                    "template": "airliner_wing_half",
                    "params": {"side": "left", "width_mm": wingspan_mm * 0.5, "depth_mm": wing_chord, "height_mm": 4.2, "wall_mm": 1.6, "hole_mm": pin_mm},
                    "material": "PLA white",
                    "orientation": "плашмя, brim",
                    "purpose": "Левое крыло с hardpoints под pods.",
                    "assembly_step": "Вклеить/закрепить к fuselage_fwd.",
                    "tolerance_mm": 0.22,
                },
                {
                    "id": "wing_right",
                    "frame_number": 12,
                    "name": "Right wing half",
                    "template": "airliner_wing_half",
                    "params": {"side": "right", "width_mm": wingspan_mm * 0.5, "depth_mm": wing_chord, "height_mm": 4.2, "wall_mm": 1.6, "hole_mm": pin_mm},
                    "material": "PLA white",
                    "orientation": "плашмя, brim",
                    "purpose": "Правое крыло.",
                    "assembly_step": "Зеркально левому.",
                    "tolerance_mm": 0.22,
                },
                {
                    "id": "vert_stab",
                    "frame_number": 13,
                    "name": "Vertical stabilizer",
                    "template": "airliner_vert_stab",
                    "params": {"width_mm": max(52.0, length_mm * 0.28), "depth_mm": 32, "height_mm": height_mm * 0.32, "wall_mm": 1.4, "hole_mm": pin_mm * 0.85},
                    "material": "PLA white",
                    "orientation": "плашмя",
                    "purpose": "Киль.",
                    "assembly_step": "Вклеить в tail slot fuselage_aft.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "horz_stab_left",
                    "frame_number": 13,
                    "name": "Horizontal stabilizer left",
                    "template": "airliner_horz_stab_half",
                    "params": {"side": "left", "width_mm": max(48.0, length_mm * 0.22), "depth_mm": 32, "height_mm": height_mm * 0.12, "wall_mm": 1.4, "hole_mm": pin_mm * 0.85},
                    "material": "PLA white",
                    "orientation": "плашмя",
                    "purpose": "Левый стабилизатор.",
                    "assembly_step": "Вклеить к килю.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "horz_stab_right",
                    "frame_number": 13,
                    "name": "Horizontal stabilizer right",
                    "template": "airliner_horz_stab_half",
                    "params": {"side": "right", "width_mm": max(48.0, length_mm * 0.22), "depth_mm": 32, "height_mm": height_mm * 0.12, "wall_mm": 1.4, "hole_mm": pin_mm * 0.85},
                    "material": "PLA white",
                    "orientation": "плашмя",
                    "purpose": "Правый стабилизатор.",
                    "assembly_step": "Зеркально левому.",
                    "tolerance_mm": 0.2,
                },
                {
                    "id": "assembly_pin_set",
                    "frame_number": 14,
                    "name": "Wing/tail/fuselage assembly pin set",
                    "template": "pin_connector_set",
                    "params": {"width_mm": 82, "depth_mm": 12, "height_mm": 4, "wall_mm": 1.2, "radius_mm": pin_mm * 0.5},
                    "material": "PETG/PLA",
                    "orientation": "плашмя",
                    "purpose": "Pins для стыковки секций (как CLERX pin.stl).",
                    "assembly_step": "Только после fit coupons.",
                    "tolerance_mm": 0.08,
                },
            ],
        },
        strategy="specialized_airliner_kinematics_v3_clerx_split_fit_first",
        project_kind="mechanical_boeing_airliner",
        min_wall_mm=1.0,
    )
    issues = validate_mechanical_boeing_specs(specs)
    if issues:
        import logging

        logging.getLogger(__name__).warning("Mechanical Boeing spec validation: %s", issues)
        specs["spec_validation_warnings"] = issues
    return specs


def _scale_parts(base: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    if target <= len(base):
        return base[:target]
    out = list(base)
    i = 0
    while len(out) < target:
        src = base[i % len(base)]
        clone = dict(src)
        clone["id"] = f"{src['id']}_{len(out) + 1}"
        clone["name"] = f"{src['name']} (вариант {len(out) + 1})"
        out.append(clone)
        i += 1
    return out


def _library_archetype_specs(
    text: str,
    *,
    project_kind: str,
    strategy: str,
    project_name: str,
    requirements: List[str],
    part_blueprint: List[Dict[str, Any]],
    min_wall_mm: float = 0.8,
) -> Dict[str, Any]:
    from bot.services.reference_geometry import try_build_specs_from_reference
    from bot.services.reference_library import enrich_specs, find_best_kits

    kits = find_best_kits(text, limit=1)
    if kits and int(kits[0].get("stl_count") or 0) >= 4:
        ref_specs = try_build_specs_from_reference(
            text,
            slug=kits[0]["slug"],
            category=kits[0].get("category") or "general_kit",
            project_kind=project_kind,
            strategy=strategy,
            project_name=project_name,
            requirements=list(requirements),
        )
        if ref_specs:
            return enrich_specs(ref_specs, text)

    target = len(part_blueprint)
    if kits:
        ref_n = int(kits[0].get("stl_count") or 0)
        if ref_n >= 4:
            target = max(len(part_blueprint), min(ref_n, 28))
    specs = _with_print_contract(
        {
            "project_name": project_name,
            "requirements": list(requirements),
            "critical_dimensions": [
                {"name": "целевой масштаб", "value_mm": 180, "tolerance_mm": 2.0},
                {"name": "минимальная стенка", "value_mm": min_wall_mm, "tolerance_mm": 0.1},
            ],
            "parts": _scale_parts(part_blueprint, target),
        },
        strategy=strategy,
        project_kind=project_kind,
        min_wall_mm=min_wall_mm,
    )
    return enrich_specs(specs, text)


def _rc_aircraft_kit_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="rc_aircraft_kit",
        strategy="rc_aircraft_split_with_control_surfaces",
        project_name="rc-aircraft-kit-cad-v0",
        requirements=[
            "RC/модель самолёта: фюзеляж, крылья, хвост, мотогондола/проп, шасси — отдельные solids.",
            "Сначала fit-coupons, затем крупные силовые детали; ориентация под FDM без лишних supports.",
        ],
        part_blueprint=[
            {"id": "fit_coupon_a", "name": "Тест посадки шарнира", "template": "fit_test_coupon", "params": {"width_mm": 28, "depth_mm": 14, "height_mm": 5, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Калибровка зазора.", "assembly_step": "Печатать первым.", "tolerance_mm": 0.2},
            {"id": "fuselage_fwd", "name": "Фюзеляж перед", "template": "airliner_fuselage_section", "params": {"length_mm": 95, "radius_mm": 14, "wall_mm": 2.0}, "material": "PLA", "orientation": "носом вверх", "purpose": "Передняя секция.", "assembly_step": "Соединить с задней секцией.", "tolerance_mm": 0.3},
            {"id": "fuselage_aft", "name": "Фюзеляж зад", "template": "airliner_fuselage_section", "params": {"length_mm": 75, "radius_mm": 12, "wall_mm": 2.0}, "material": "PLA", "orientation": "носом вверх", "purpose": "Хвостовая секция.", "assembly_step": "Установить хвост.", "tolerance_mm": 0.3},
            {"id": "wing_left", "name": "Крыло левое", "template": "airliner_wing_half", "params": {"span_mm": 120, "chord_mm": 32, "wall_mm": 1.8}, "material": "PLA", "orientation": "кромкой на стол", "purpose": "Несущее крыло.", "assembly_step": "Приклеить/закрепить.", "tolerance_mm": 0.25},
            {"id": "wing_right", "name": "Крыло правое", "template": "airliner_wing_half", "params": {"span_mm": 120, "chord_mm": 32, "wall_mm": 1.8}, "material": "PLA", "orientation": "кромкой на стол", "purpose": "Несущее крыло.", "assembly_step": "Зеркально к левому.", "tolerance_mm": 0.25},
            {"id": "vert_stab", "name": "Киль", "template": "airliner_vert_stab", "params": {"height_mm": 38, "chord_mm": 22, "wall_mm": 1.6}, "material": "PLA", "orientation": "ребром на стол", "purpose": "Вертикальное оперение.", "assembly_step": "На хвост.", "tolerance_mm": 0.2},
            {"id": "horz_stab", "name": "Стабилизатор", "template": "airliner_horz_stab_half", "params": {"span_mm": 48, "chord_mm": 18, "wall_mm": 1.6}, "material": "PLA", "orientation": "плашмя", "purpose": "Горизонтальное оперение.", "assembly_step": "Симметрично.", "tolerance_mm": 0.2},
            {"id": "engine_pod", "name": "Мотогондола", "template": "airliner_engine_pod_single", "params": {"length_mm": 42, "radius_mm": 9, "wall_mm": 1.8}, "material": "PLA", "orientation": "осью вверх", "purpose": "Двигатель/гондола.", "assembly_step": "Под крыло.", "tolerance_mm": 0.25},
            {"id": "prop_disc", "name": "Проп/вентилятор", "template": "airliner_fan_rotor_single", "params": {"radius_mm": 11, "height_mm": 2, "wall_mm": 1.2}, "material": "PLA", "orientation": "плашмя", "purpose": "Декоративный ротор.", "assembly_step": "На ось.", "tolerance_mm": 0.2},
            {"id": "landing_gear", "name": "Шасси", "template": "cylinder", "params": {"radius_mm": 2, "height_mm": 28, "wall_mm": 1.4, "segments": 24}, "material": "PETG", "orientation": "вертикально", "purpose": "Стойка шасси.", "assembly_step": "После теста посадки.", "tolerance_mm": 0.25},
            {"id": "wheel_set", "name": "Колёса", "template": "cylinder", "params": {"radius_mm": 6, "height_mm": 4, "wall_mm": 1.2, "segments": 48}, "material": "PLA", "orientation": "на боку", "purpose": "Колёса.", "assembly_step": "На ось шасси.", "tolerance_mm": 0.25},
        ],
    )


def _drone_fpv_kit_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="drone_fpv_kit",
        strategy="fpv_frame_modular_arms_and_stack",
        project_name="fpv-drone-kit-cad-v0",
        requirements=[
            "FPV/квадрокоптер: центральная плита, 4 луча, защита пропов, крепёж стека.",
            "Лёгкие стенки, PETG/PLA, печать лучей плашмя или ребром.",
        ],
        part_blueprint=[
            {"id": "frame_plate", "name": "Центральная плита", "template": "plate", "params": {"width_mm": 52, "depth_mm": 52, "height_mm": 3, "wall_mm": 2.0}, "material": "PETG", "orientation": "плашмя", "purpose": "Стек FC/ESC.", "assembly_step": "База сборки.", "tolerance_mm": 0.25},
            {"id": "arm_fl", "name": "Луч FL", "template": "plate", "params": {"width_mm": 95, "depth_mm": 12, "height_mm": 3, "wall_mm": 1.8}, "material": "PETG", "orientation": "плашмя", "purpose": "Несущий луч.", "assembly_step": "4× симметрично.", "tolerance_mm": 0.2},
            {"id": "motor_mount", "name": "Мотор-маунт", "template": "hollow_box", "params": {"width_mm": 20, "depth_mm": 20, "height_mm": 6, "wall_mm": 2.0}, "material": "PETG", "orientation": "дном на стол", "purpose": "Посадка мотора.", "assembly_step": "На конец луча.", "tolerance_mm": 0.2},
            {"id": "prop_guard", "name": "Защита пропа", "template": "kit_card_frame", "params": {"width_mm": 58, "depth_mm": 58, "height_mm": 2, "wall_mm": 1.6}, "material": "TPU", "orientation": "плашмя", "purpose": "Защита лопастей.", "assembly_step": "Опционально.", "tolerance_mm": 0.3},
            {"id": "camera_bumper", "name": "Бампер камеры", "template": "plate", "params": {"width_mm": 28, "depth_mm": 18, "height_mm": 4, "wall_mm": 2.0}, "material": "TPU", "orientation": "плашмя", "purpose": "Защита носа.", "assembly_step": "Спереди плиты.", "tolerance_mm": 0.25},
            {"id": "battery_strap_clip", "name": "Клипса АКБ", "template": "tube_clip", "params": {"width_mm": 24, "depth_mm": 14, "height_mm": 10, "radius_mm": 6}, "material": "PETG", "orientation": "плашмя", "purpose": "Фиксация АКБ.", "assembly_step": "На верх плиты.", "tolerance_mm": 0.25},
        ],
    )


def _rc_tracked_vehicle_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="rc_tracked_vehicle",
        strategy="tracked_rc_hull_suspension_and_turret",
        project_name="rc-tracked-vehicle-cad-v0",
        requirements=["RC танк/гусеницы: корпус, гусеницы, башня, орудие — раздельная печать."],
        part_blueprint=[
            {"id": "hull_lower", "name": "Корпус нижний", "template": "vehicle_body_tub", "params": {"width_mm": 80, "depth_mm": 48, "height_mm": 16, "wall_mm": 2.2}, "material": "PLA", "orientation": "дном на стол", "purpose": "База.", "assembly_step": "Первый.", "tolerance_mm": 0.3},
            {"id": "hull_upper", "name": "Корпус верх", "template": "plate", "params": {"width_mm": 78, "depth_mm": 46, "height_mm": 6, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Верхняя крышка.", "assembly_step": "На корпус.", "tolerance_mm": 0.25},
            {"id": "track_left", "name": "Гусеница левая", "template": "kit_card_frame", "params": {"width_mm": 72, "depth_mm": 18, "height_mm": 2.4, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Гусеница.", "assembly_step": "По бокам.", "tolerance_mm": 0.2},
            {"id": "track_right", "name": "Гусеница правая", "template": "kit_card_frame", "params": {"width_mm": 72, "depth_mm": 18, "height_mm": 2.4, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Гусеница.", "assembly_step": "Зеркально.", "tolerance_mm": 0.2},
            {"id": "turret", "name": "Башня", "template": "hollow_box", "params": {"width_mm": 34, "depth_mm": 30, "height_mm": 18, "wall_mm": 2.0}, "material": "PLA", "orientation": "дном на стол", "purpose": "Поворотная башня.", "assembly_step": "На корпус.", "tolerance_mm": 0.25},
            {"id": "gun_barrel", "name": "Ствол", "template": "cylinder", "params": {"radius_mm": 3, "height_mm": 42, "wall_mm": 1.4, "segments": 32}, "material": "PLA", "orientation": "лежа", "purpose": "Орудие.", "assembly_step": "В башню.", "tolerance_mm": 0.2},
        ],
    )


def _robot_mechanism_kit_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="robot_mechanism_kit",
        strategy="robot_arm_links_gripper_and_pin_fit",
        project_name="robot-mechanism-kit-cad-v0",
        requirements=["Робот-манипулятор: звенья, суставы, клешня, тест штифта."],
        part_blueprint=[
            {"id": "base", "name": "База", "template": "hollow_box", "params": {"width_mm": 60, "depth_mm": 60, "height_mm": 12, "wall_mm": 2.4}, "material": "PETG", "orientation": "дном на стол", "purpose": "Основание.", "assembly_step": "1.", "tolerance_mm": 0.25},
            {"id": "link_1", "name": "Звено 1", "template": "plate", "params": {"width_mm": 18, "depth_mm": 55, "height_mm": 12, "wall_mm": 2.0}, "material": "PETG", "orientation": "ребром", "purpose": "Плечо.", "assembly_step": "2.", "tolerance_mm": 0.25},
            {"id": "link_2", "name": "Звено 2", "template": "plate", "params": {"width_mm": 16, "depth_mm": 48, "height_mm": 10, "wall_mm": 2.0}, "material": "PETG", "orientation": "ребром", "purpose": "Предплечье.", "assembly_step": "3.", "tolerance_mm": 0.25},
            {"id": "gripper_body", "name": "Корпус клешни", "template": "hollow_box", "params": {"width_mm": 28, "depth_mm": 22, "height_mm": 14, "wall_mm": 2.0}, "material": "PETG", "orientation": "дном на стол", "purpose": "Захват.", "assembly_step": "4.", "tolerance_mm": 0.25},
            {"id": "gripper_jaw_l", "name": "Челюсть L", "template": "kit_card_wedge", "params": {"width_mm": 14, "depth_mm": 22, "height_mm": 4, "wall_mm": 1.6}, "material": "PETG", "orientation": "плашмя", "purpose": "Губка.", "assembly_step": "5.", "tolerance_mm": 0.2},
            {"id": "gripper_jaw_r", "name": "Челюсть R", "template": "kit_card_wedge", "params": {"width_mm": 14, "depth_mm": 22, "height_mm": 4, "wall_mm": 1.6}, "material": "PETG", "orientation": "плашмя", "purpose": "Губка.", "assembly_step": "6.", "tolerance_mm": 0.2},
            {"id": "pin_set", "name": "Штифты", "template": "cylinder", "params": {"radius_mm": 1.5, "height_mm": 24, "wall_mm": 1.0, "segments": 24}, "material": "PETG", "orientation": "вертикально", "purpose": "Оси.", "assembly_step": "7.", "tolerance_mm": 0.2},
        ],
    )


def _architecture_miniature_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="architecture_miniature",
        strategy="modular_architecture_blocks_and_landmark_slices",
        project_name="architecture-miniature-cad-v0",
        requirements=["Архитектурная миниатюра: модульные блоки, башни, основание — для HO/N scale декора."],
        part_blueprint=[
            {"id": "base_plate", "name": "Основание", "template": "plate", "params": {"width_mm": 120, "depth_mm": 80, "height_mm": 4, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Площадка.", "assembly_step": "1.", "tolerance_mm": 0.2},
            {"id": "tower_core", "name": "Башня ядро", "template": "hollow_box", "params": {"width_mm": 28, "depth_mm": 28, "height_mm": 55, "wall_mm": 1.8}, "material": "PLA", "orientation": "дном на стол", "purpose": "Вертикаль.", "assembly_step": "2.", "tolerance_mm": 0.2},
            {"id": "facade_panel_a", "name": "Фасад A", "template": "plate", "params": {"width_mm": 30, "depth_mm": 2, "height_mm": 50, "wall_mm": 1.6}, "material": "PLA", "orientation": "плашмя", "purpose": "Деталь фасада.", "assembly_step": "3.", "tolerance_mm": 0.15},
            {"id": "roof_cap", "name": "Крыша", "template": "plate", "params": {"width_mm": 34, "depth_mm": 34, "height_mm": 3, "wall_mm": 1.6}, "material": "PLA", "orientation": "плашмя", "purpose": "Верх.", "assembly_step": "4.", "tolerance_mm": 0.15},
            {"id": "annex_block", "name": "Пристройка", "template": "hollow_box", "params": {"width_mm": 40, "depth_mm": 24, "height_mm": 22, "wall_mm": 1.8}, "material": "PLA", "orientation": "дном на стол", "purpose": "Боковой объём.", "assembly_step": "5.", "tolerance_mm": 0.2},
        ],
    )


def _hydraulic_cylinder_kit_specs(text: str) -> Dict[str, Any]:
    """
    Industrial hydraulic cylinder D80/D70 — 7-part scaled assembly.
    Proportions verified against the imported reference (Гидроцилиндр dnl3986).
    Default print scale is ~25% so the kit fits a 300×300 bed.
    """
    return _library_archetype_specs(
        text,
        project_kind="hydraulic_cylinder_kit",
        strategy="industrial_hydraulic_actuator_with_clevis_eyes_and_seal_stack",
        project_name="hydraulic-cylinder-D80-rod-D70-v0",
        requirements=[
            "Промышленный гидроцилиндр Ø80/Ø70, ход ~600 мм (масштаб 25%).",
            "Архитектура: проушина — гильза — поршень — шток — грундбукса — гайка — проушина.",
            "Стандартные уплотнения: KPD 80 (поршень), А70×80 (шток), SAG 70 (грязесъёмник), FE 80 (направляющее кольцо).",
        ],
        part_blueprint=[
            {"id": "rear_clevis", "name": "Проушина стенки",
             "template": "plate",
             "params": {"width_mm": 32, "depth_mm": 45, "height_mm": 11, "wall_mm": 2.0},
             "material": "PETG", "orientation": "плашмя",
             "purpose": "Заднее монтажное ушко, соединяется со штангой.",
             "assembly_step": "1. Запрессовать палец Ø8 в отверстие.",
             "tolerance_mm": 0.25},
            {"id": "barrel", "name": "Гильза Ø23.8",
             "template": "cylinder",
             "params": {"radius_mm": 12, "height_mm": 162, "wall_mm": 2.5, "segments": 36},
             "material": "PETG", "orientation": "лежа",
             "purpose": "Гильза гидроцилиндра, рабочая полость Ø20.",
             "assembly_step": "2. Установить рядом с проушиной.",
             "tolerance_mm": 0.25},
            {"id": "piston_head", "name": "Поршень",
             "template": "cylinder",
             "params": {"radius_mm": 9.9, "height_mm": 8, "wall_mm": 1.5, "segments": 32},
             "material": "PETG", "orientation": "плашмя",
             "purpose": "Поршень с канавкой под KPD-уплотнение.",
             "assembly_step": "3. Запрессовать на шток в среднюю позицию.",
             "tolerance_mm": 0.20},
            {"id": "rod", "name": "Шток Ø17.5",
             "template": "cylinder",
             "params": {"radius_mm": 8.7, "height_mm": 168, "wall_mm": 0, "segments": 32},
             "material": "PLA", "orientation": "лежа",
             "purpose": "Хромированный шток, длина 168 мм (масштаб 25%).",
             "assembly_step": "4. Вставить в гильзу через грундбуксу.",
             "tolerance_mm": 0.20},
            {"id": "gland_bushing", "name": "Грундбукса",
             "template": "cylinder",
             "params": {"radius_mm": 14, "height_mm": 18, "wall_mm": 3.0, "segments": 32},
             "material": "PETG", "orientation": "плашмя",
             "purpose": "Передняя букса с местами под SAG 70 + А70/80 + FE 80.",
             "assembly_step": "5. Накрутить на гильзу через резьбу М23×1.",
             "tolerance_mm": 0.25},
            {"id": "lock_nut", "name": "Контргайка ГОСТ 5915-70",
             "template": "cylinder",
             "params": {"radius_mm": 7, "height_mm": 6, "wall_mm": 0, "segments": 6},
             "material": "PETG", "orientation": "плашмя",
             "purpose": "Шестигранная гайка, фиксирует переднюю проушину.",
             "assembly_step": "6. Затянуть после установки проушины.",
             "tolerance_mm": 0.20},
            {"id": "front_clevis", "name": "Проушина вала",
             "template": "plate",
             "params": {"width_mm": 28, "depth_mm": 38, "height_mm": 11, "wall_mm": 2.0},
             "material": "PETG", "orientation": "плашмя",
             "purpose": "Переднее ушко на штоке, поворот относительно заднего на 90°.",
             "assembly_step": "7. Навинтить на шток, контргайка фиксирует.",
             "tolerance_mm": 0.25},
        ],
    )


def _organizer_box_specs(text: str) -> Dict[str, Any]:
    """Small desk-scale storage organizer (drawer cabinet pattern)."""
    return _library_archetype_specs(
        text,
        project_kind="organizer_box",
        strategy="small_storage_box_with_drawers_thin_walls_no_supports",
        project_name="storage-organizer-cabinet-v0",
        requirements=[
            "Настольный органайзер: корпус + 2 выдвижных ящика 60×60×60.",
            "Стенки 2.2 мм, ровно по измеренным референсам.",
            "Печать без поддержек, дном вниз.",
        ],
        part_blueprint=[
            {"id": "cabinet_shell", "name": "Корпус",
             "template": "hollow_box",
             "params": {"width_mm": 60, "depth_mm": 60, "height_mm": 60, "wall_mm": 2.4},
             "material": "PLA", "orientation": "дном на стол",
             "purpose": "Внешний корпус с двумя отсеками.",
             "assembly_step": "1. Печать целиком.",
             "tolerance_mm": 0.30},
            {"id": "drawer_top", "name": "Ящик верхний",
             "template": "hollow_box",
             "params": {"width_mm": 54, "depth_mm": 27, "height_mm": 27, "wall_mm": 1.6},
             "material": "PLA", "orientation": "дном на стол",
             "purpose": "Верхний выдвижной отсек.",
             "assembly_step": "2. Вдвинуть в верхний паз корпуса.",
             "tolerance_mm": 0.30},
            {"id": "drawer_bottom", "name": "Ящик нижний",
             "template": "hollow_box",
             "params": {"width_mm": 54, "depth_mm": 27, "height_mm": 27, "wall_mm": 1.6},
             "material": "PLA", "orientation": "дном на стол",
             "purpose": "Нижний выдвижной отсек.",
             "assembly_step": "3. Вдвинуть в нижний паз корпуса.",
             "tolerance_mm": 0.30},
            {"id": "handle", "name": "Ручка",
             "template": "cylinder",
             "params": {"radius_mm": 2, "height_mm": 12, "wall_mm": 0, "segments": 16},
             "material": "PLA", "orientation": "лежа",
             "purpose": "Шпонка-ручка для ящика.",
             "assembly_step": "4. Вклеить в торец ящика по центру.",
             "tolerance_mm": 0.15},
        ],
    )


def _stencil_plate_specs(text: str) -> Dict[str, Any]:
    """Flat stencil / sign plate — 2.5 mm thick, long-narrow."""
    return _library_archetype_specs(
        text,
        project_kind="stencil_plate",
        strategy="flat_stencil_with_cutouts_thin_plate",
        project_name="stencil-plate-v0",
        requirements=[
            "Плоский трафарет 100×36×2.5 мм с прорезями для фигур.",
            "Минимальная ширина прорези 0.8 мм (2 × сопло 0.4).",
            "Печать дном на стол, 3 периметра, 4 сплошных слоя.",
        ],
        part_blueprint=[
            {"id": "main_plate", "name": "Основная пластина",
             "template": "plate",
             "params": {"width_mm": 100, "depth_mm": 36, "height_mm": 2.5, "wall_mm": 1.6},
             "material": "PLA", "orientation": "плашмя",
             "purpose": "Несущая пластина с вырезами.",
             "assembly_step": "1. Печать одним куском.",
             "tolerance_mm": 0.10},
            {"id": "demo_card", "name": "Демо-карточка",
             "template": "plate",
             "params": {"width_mm": 53, "depth_mm": 35, "height_mm": 2.5, "wall_mm": 1.6},
             "material": "PLA", "orientation": "плашмя",
             "purpose": "Меньшая версия для проверки на тестовой бумаге.",
             "assembly_step": "2. Печать рядом с основной.",
             "tolerance_mm": 0.10},
        ],
    )


def _reference_guided_kit_specs(text: str) -> Dict[str, Any]:
    return _library_archetype_specs(
        text,
        project_kind="reference_guided_kit",
        strategy="reference_library_informed_multi_part_cad",
        project_name="reference-guided-kit-cad-v0",
        requirements=[
            "Универсальный набор по ближайшему референсу из локальной библиотеки STL.",
            "Имена и количество деталей подстраиваются под скачанный kit.",
        ],
        part_blueprint=[
            {"id": "main_body", "name": "Основной корпус", "template": "hollow_box", "params": {"width_mm": 80, "depth_mm": 50, "height_mm": 30, "wall_mm": 2.0}, "material": "PLA", "orientation": "дном на стол", "purpose": "Главный объём.", "assembly_step": "1.", "tolerance_mm": 0.3},
            {"id": "detail_a", "name": "Деталь A", "template": "plate", "params": {"width_mm": 40, "depth_mm": 24, "height_mm": 6, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Модуль.", "assembly_step": "2.", "tolerance_mm": 0.25},
            {"id": "detail_b", "name": "Деталь B", "template": "plate", "params": {"width_mm": 36, "depth_mm": 20, "height_mm": 5, "wall_mm": 1.8}, "material": "PLA", "orientation": "плашмя", "purpose": "Модуль.", "assembly_step": "3.", "tolerance_mm": 0.25},
            {"id": "connector_pins", "name": "Штифты", "template": "cylinder", "params": {"radius_mm": 1.4, "height_mm": 20, "wall_mm": 1.0, "segments": 24}, "material": "PETG", "orientation": "вертикально", "purpose": "Соединение.", "assembly_step": "4.", "tolerance_mm": 0.2},
            {"id": "fit_coupon", "name": "Тест посадки", "template": "fit_test_coupon", "params": {"width_mm": 30, "depth_mm": 16, "height_mm": 5, "wall_mm": 2.0}, "material": "PLA", "orientation": "плашмя", "purpose": "Калибровка.", "assembly_step": "0.", "tolerance_mm": 0.2},
        ],
    )


_LIBRARY_KIND_BUILDERS = {
    "rc_aircraft_kit": _rc_aircraft_kit_specs,
    "drone_fpv_kit": _drone_fpv_kit_specs,
    "rc_tracked_vehicle": _rc_tracked_vehicle_specs,
    "rc_truck_kit": _vehicle_kit_specs,
    "robot_mechanism_kit": _robot_mechanism_kit_specs,
    "architecture_miniature": _architecture_miniature_specs,
    "articulated_wearable": _reference_guided_kit_specs,
    "train_track_system": _reference_guided_kit_specs,
    "toy_mechanism": _reference_guided_kit_specs,
    "kinetic_decor": _reference_guided_kit_specs,
    "display_stand_kit": _reference_guided_kit_specs,
    "reference_guided_kit": _reference_guided_kit_specs,
    "hydraulic_cylinder_kit": _hydraulic_cylinder_kit_specs,
    "mechanism_kit": _hydraulic_cylinder_kit_specs,
    "organizer_box": _organizer_box_specs,
    "stencil_plate": _stencil_plate_specs,
}


def _parse_two_dims(text: str) -> Optional[Tuple[float, float]]:
    m = re.search(r"(\d{2,3})\s*[x×х*]\s*(\d{2,3})", text or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def _cad_functional_kit_specs(text: str) -> Dict[str, Any]:
    """Real B-rep CAD parts (CadQuery/OCCT): angle bracket, filleted box,
    flanged bushing. Produces `cad_specs` consumed by build_project_zip's CAD
    short-circuit, which builds STL+STEP via the out-of-process kernel.
    """
    t = (text or "").lower()
    cad_specs: List[Dict[str, Any]] = []
    project = "cad-functional-kit"
    label = "CAD-набор"

    def _num(pat: str, default: float) -> float:
        m = re.search(pat, t)
        try:
            return float(m.group(1).replace(",", ".")) if m else default
        except Exception:
            return default

    if re.search(r"кронштейн|уголок|angle\s*bracket|\bbracket\b|полкодержат|"
                 r"крепёжн.{0,8}уголок|l-?bracket", t):
        dims = _parse_two_dims(t)
        arm_a = dims[0] if dims else _num(r"плеч\w*\D{0,10}(\d{2,3})", 60.0)
        arm_b = dims[1] if dims else arm_a
        thickness = _num(r"толщин\w*\D{0,10}(\d{1,2})", 5.0)
        width = _num(r"ширин\w*\D{0,10}(\d{2,3})", 40.0)
        hole = _num(r"(?:отверст|болт|винт|под\s*м)\D{0,8}(\d{1,2})", 6.5)
        cad_specs.append({
            "name": "angle_bracket",
            "generator": "mounting_bracket",
            "params": {
                "arm_a": arm_a, "arm_b": arm_b, "width": width,
                "thickness": thickness, "hole_d": hole,
                "fillet": min(6.0, thickness * 1.4), "gusset": True,
            },
        })
        project, label = "cad-angle-bracket", "усиленный уголок-кронштейн"
    elif re.search(r"фланец|flange|бобышк|втулк.{0,8}фланц|gland|сальник", t):
        bore = _num(r"(?:бор|отверст|вал|диам\w*\s*вн)\D{0,8}(\d{2,3})", 20.0)
        cad_specs.append({
            "name": "flanged_bushing",
            "generator": "flanged_bushing",
            "params": {"bore": bore, "flange_d": max(bore * 3, 50.0),
                       "hub_d": max(bore * 1.6, 30.0)},
        })
        project, label = "cad-flanged-bushing", "фланцевая втулка"
    else:
        # Default: filleted parametric box (container) with rounded edges.
        dims = _parse_two_dims(t)
        w = dims[0] if dims else _num(r"ширин\w*\D{0,10}(\d{2,3})", 80.0)
        d = dims[1] if dims else _num(r"глубин\w*\D{0,10}(\d{2,3})", 50.0)
        h = _num(r"высот\w*\D{0,10}(\d{2,3})", 35.0)
        wall = _num(r"стенк\w*\D{0,8}(\d(?:[.,]\d)?)", 2.4)
        cad_specs.append({
            "name": "filleted_box",
            "generator": "filleted_box",
            "params": {"width": w, "depth": d, "height": h,
                       "wall": wall, "fillet": 5.0},
        })
        project, label = "cad-filleted-box", "коробка со скруглениями"

    specs = _with_print_contract(
        {
            "project_name": project,
            "requirements": [
                f"{label}: настоящая B-rep CAD-геометрия (фаски, скругления, "
                "boolean), а не выдавленные примитивы.",
                "Выдать STL для печати и STEP для CAD-правки.",
            ],
            "assumptions": [
                "Геометрия строится OpenCASCADE-кернелом (CadQuery) в "
                "изолированном процессе.",
            ],
            "critical_dimensions": [
                {"name": "минимальная стенка", "value_mm": 1.2, "tolerance_mm": 0.2},
            ],
            "parts": [
                {
                    "id": s["name"],
                    "name": s["name"].replace("_", " "),
                    "template": "cad_kernel",
                    "purpose": label,
                    "orientation": "по рекомендации инженерного анализа",
                }
                for s in cad_specs
            ],
            "cad_specs": cad_specs,
            "material": "PETG",
        },
        strategy="cad-kernel-occt",
        project_kind="cad_functional_kit",
        min_wall_mm=1.2,
    )
    return specs


def zero_to_print_specs(text: str) -> Optional[Dict[str, Any]]:
    t = text or ""
    from bot.services.airplane_3mf import airplane_wants_mechanical_kit, airplane_wants_realistic_mesh

    if not airplane_wants_realistic_mesh(t) and (
        airplane_wants_mechanical_kit(t)
        or re.search(
            r"(boeing|боинг|самол[её]т).{0,160}(шасси|шосси|landing\s*gear|лопаст|кол[её]с|ось|крут|вращ|убира|складыва)",
            t,
            re.I,
        )
    ):
        return _mechanical_boeing_airliner_specs(t)
    if re.search(
        r"кронштейн|уголок|angle\s*bracket|\bbracket\b|полкодержат|"
        r"фланец|flange|сальник|gland\b",
        t, re.I,
    ):
        return _cad_functional_kit_specs(t)
    if re.search(
        r"гидроцилиндр|hydraulic\s*cylinder|hydraulic\s*ram|hydraulic\s*actuator|"
        r"шток.{0,10}поршн|гидро.{0,8}привод",
        t, re.I,
    ):
        return _hydraulic_cylinder_kit_specs(t)
    if re.search(
        r"таблетниц|pill[\s-]?box|органайзер|комод|drawer|cabinet|шкатулк|"
        r"шкафчик.{0,8}мелк|сортировк.{0,15}болт|ячейк.{0,10}набор",
        t, re.I,
    ):
        return _organizer_box_specs(t)
    if re.search(
        r"трафарет|stencil|шаблон.{0,15}(рисов|надпис)|name[\s-]?plate|табличк.{0,15}(плоск|тонк)",
        t, re.I,
    ):
        return _stencil_plate_specs(t)
    if re.search(r"starter.{0,20}plant|seed.{0,20}starter|plant.{0,20}grower|рассад|проращив", t, re.I):
        return _seed_starter_kit_specs(t)
    if re.search(r"key[\s_-]?holder|wall[\s_-]?fixing|wall[\s_-]?mount|настенн.{0,20}креп|креплен.{0,20}стен", t, re.I):
        return _wall_mount_system_specs(t)
    if re.search(r"ender.{0,20}tool|tool[\s_-]?holder|держател.{0,20}инструмент", t, re.I):
        return _printer_tool_holder_specs(t)
    if re.search(r"stackable.{0,20}crate|screw[\s_-]?box|modular.{0,20}storage|ящик.{0,20}винт|органайзер", t, re.I):
        return _modular_storage_system_specs(t)
    if re.search(r"pegstr|pegboard|перфорированн.{0,20}панел", t, re.I):
        return _pegboard_ecosystem_specs(t)
    if re.search(r"egg[\s_-]?roll.{0,20}basket|perforated.{0,20}basket|корзин", t, re.I):
        return _perforated_basket_specs(t)
    if re.search(r"charizard|pokemon|pok[eé]mon|winged.{0,20}creature|крылат.{0,20}(существ|дракон)", t, re.I):
        return _winged_creature_statue_specs(t)
    if re.search(r"deadpool|bust|бюст", t, re.I):
        return _character_bust_specs(t)
    if re.search(r"stitch|halloween.{0,20}stitch|split.{0,25}character|разборн.{0,30}персонаж", t, re.I):
        return _accessory_character_kit_specs(t)
    if re.search(r"baby\s+yoda|grogu|гро[гг]у|йода|paintable\s+miniature|miniature\s+pack", t, re.I):
        return _paintable_miniature_pack_specs(t)
    if re.search(r"collectible|коллекционн|character.{0,25}kit", t, re.I):
        return _split_collectible_character_specs(t)
    if re.search(r"lamp|ламп|светиль|абажур|\bled\b|ночник", t, re.I):
        return _lamp_project_specs(t)
    if re.search(r"mmu|многоцвет|multi[\s-]?color|olaf|ams.{0,30}(цвет|объект|персонаж)|персонаж.{0,30}(цвет|ams|mmu)", t, re.I):
        return _mmu_character_specs(t)
    if re.search(r"plant\s+pot|planter|кашпо|горш|вазон|дренаж|rocket.{0,20}plant|aztec.{0,20}temple", t, re.I):
        return _planter_project_specs(t)
    if re.search(r"oreo|box.{0,20}(decor|cookie)|декоративн.{0,20}короб|шкатул|контейнер", t, re.I):
        return _decorative_container_specs(t)
    if re.search(r"vase|ваза|vase\s+mode|low[\s-]?poly.{0,20}vase|тонкостенн", t, re.I):
        return _vase_shell_specs(t)
    if re.search(r"sla|resin|смол|calibration|калибров|amera", t, re.I):
        return _sla_calibration_specs(t)
    if re.search(r"easter\s+egg|пасхальн.{0,20}яйц|voronoi|variant\s+family|family\s+of\s+variants|семейств.{0,20}вариант", t, re.I):
        return _variant_family_specs(t)
    if re.search(r"jewellery|jewelry|украшен|дерев.{0,20}украшен", t, re.I):
        return _jewellery_tree_specs(t)
    if re.search(r"planetarium|планетар|gear|шестер|редуктор", t, re.I):
        return _mechanical_planetarium_specs(t)
    if re.search(r"dna|днк|helix|спирал.{0,20}(подстав|держател|карандаш)|карандашниц", t, re.I):
        return _dna_helix_holder_specs(t)
    if re.search(r"impossible\s+cube|невозможн.{0,20}куб|оптическ.{0,20}иллюз|illusion", t, re.I):
        return _impossible_cube_specs(t)
    if re.search(r"puzzle.{0,20}(board|chess)|пазл.{0,30}(доск|шахмат)|шахмат.{0,30}(пазл|доск|набор)", t, re.I):
        return _puzzle_chess_board_specs(t)
    if re.search(r"spiral.{0,20}chess|спиральн.{0,20}шахмат|no\s+supports|без\s+поддерж", t, re.I):
        return _spiral_chess_set_specs(t)
    if re.search(r"rugged\s+box|parametric\s+box|параметрическ.{0,20}короб|коробк.{0,24}(защёл|защел|snap|петл|hinge)", t, re.I):
        return _rugged_box_specs(t)
    if re.search(r"kit[\s-]?card|кит[\s-]?кард|карточк.{0,16}детал|destroyer|зв[её]здн", t, re.I):
        return _kit_card_specs(t)
    if re.search(
        r"extra\s*300|fokker|turboprop|rc\s*plane|планер|крылат|avia|авиамодел",
        t,
        re.I,
    ):
        return _rc_aircraft_kit_specs(t)
    if re.search(r"drone|квадрокоптер|fpv|hexacopter|мультикоптер|дрон", t, re.I):
        return _drone_fpv_kit_specs(t)
    if re.search(r"tank|танк|гусениц|tracked|брон", t, re.I):
        return _rc_tracked_vehicle_specs(t)
    if re.search(r"robot|робот|manipulator|scara|gripper|клешн|spider\s*robot", t, re.I):
        return _robot_mechanism_kit_specs(t)
    if re.search(
        r"castle|замок|eiffel|эйфел|manhattan|город|city|riesenrad|architecture|архитект",
        t,
        re.I,
    ):
        return _architecture_miniature_specs(t)
    if re.search(r"willys|jeep|джип|машин[ауы].{0,40}(kit|набор|сборк|детал|cad|с\s+0|с\s+нуля)", t, re.I):
        return _vehicle_kit_specs(t)
    if re.search(r"уровн.{0,30}(thingiverse|printables|скачан|интернет|makerworld|cults)|с\s+нуля.{0,80}(модель|набор|сборк)", t, re.I):
        from bot.services.reference_library import infer_project_kind_from_library

        lib_kind = infer_project_kind_from_library(t) or "reference_guided_kit"
        builder = _LIBRARY_KIND_BUILDERS.get(lib_kind, _reference_guided_kit_specs)
        return builder(t)
    # Библиотека референсов: если запрос похож на скачанный kit — маршрут по категории.
    from bot.services.reference_library import infer_project_kind_from_library, library_stats

    if library_stats().get("kit_count", 0) >= 10:
        lib_kind = infer_project_kind_from_library(t)
        if lib_kind and lib_kind not in ("mechanical_boeing_airliner",):
            builder = _LIBRARY_KIND_BUILDERS.get(lib_kind)
            if builder and re.search(
                r"самол|plane|drone|дрон|танк|tank|robot|робот|castle|замок|город|city|"
                r"gear|шестерн|kit|набор|сборк|механ|rc\b|fpv|архитект",
                t,
                re.I,
            ):
                return builder(t)
    return None


def _fallback_hybrid_parts() -> List[Dict[str, Any]]:
    from bot.services.hybrid_generator import hybrid_generator_parts

    return hybrid_generator_parts()


async def generate_project_specs(
    user_request: str,
    context: str,
    text_model: str,
    *,
    part_count: int = 8,
    storyboard_frames: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from bot.services import llm
    from bot.services.hybrid_generator import hybrid_generator_specs, is_hybrid_generator_storyboard
    from bot.services.storyboard import frames_to_project_specs

    from bot.services.reference_library import enrich_specs, llm_reference_context

    if is_hybrid_generator_storyboard(storyboard_frames, f"{user_request}\n{context}"):
        return hybrid_generator_specs(storyboard_frames)

    deterministic = zero_to_print_specs(f"{user_request}\n{context}")
    if deterministic:
        if deterministic.get("project_kind") == "mechanical_boeing_airliner":
            hard = validate_mechanical_boeing_specs(deterministic)
            if hard:
                raise ValueError(
                    "Mechanical Boeing v2 spec failed validation: " + "; ".join(hard)
                )
        return enrich_specs(deterministic, f"{user_request}\n{context}")

    if storyboard_frames and len(storyboard_frames) >= 2:
        base = frames_to_project_specs(storyboard_frames)
        part_count = len(base["parts"])
        # Уточняем размеры через LLM, но сохраняем названия кадров
        context_frames = "\n".join(
            f"Кадр {f.get('frame')}: {f.get('title')} — {f.get('description', '')}"
            for f in storyboard_frames[:20]
        )
        context = f"{context[:4000]}\n\nКадры раскадровки:\n{context_frames}"

    if storyboard_frames:
        printable_n = len([f for f in storyboard_frames if f.get("printable", True)]) or len(storyboard_frames)
        part_count = max(2, min(15, printable_n))
    else:
        part_count = max(3, min(12, part_count))

    frame_names_hint = ""
    if storyboard_frames:
        frame_names_hint = (
            "\nОБЯЗАТЕЛЬНО: ровно "
            f"{part_count} деталей, названия parts[].name ТОЧНО как в кадрах раскадровки ниже.\n"
        )

    ref_block = llm_reference_context(f"{user_request}\n{context}")
    ref_section = ""
    if ref_block:
        ref_section = (
            "\n\nЛОКАЛЬНАЯ БИБЛИОТЕКА РЕФЕРЕНСОВ (обязательно учти splits, id и роли деталей):\n"
            f"{ref_block}\n"
            "Используй похожие id/name/template; не выдумывай монолит если референс — multi-part kit.\n"
        )

    physics_section = ""
    try:
        from bot.services.mesh_engineering import physics_design_rules

        physics_section = "\n\n" + physics_design_rules() + "\n"
    except Exception:
        physics_section = ""

    prompt = (
        f"Запрос:\n{user_request[:2000]}\n\n"
        f"Контекст проекта:\n{context[:6000]}\n\n"
        f"{physics_section}"
        f"{ref_section}"
        f"{frame_names_hint}"
        f"Собери инженерный локальный проект для 3D-печати из {part_count} деталей.\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"project_name":"slug",'
        '"requirements":["функциональное требование"],'
        '"assumptions":["инженерное допущение"],'
        '"critical_dimensions":[{"name":"общая ширина","value_mm":200,"tolerance_mm":0.5}],'
        '"parts":[{"id":"body_lower","name":"Нижняя половина корпуса",'
        '"template":"hollow_box|box|plate|cylinder|bobbin|tube_clip|sphere|triangle_rect_circle|'
        'rugged_box_bottom|rugged_box_lid|snap_latch|kit_card_frame|kit_card_wedge|slot_stand|'
        'vehicle_body_tub|vehicle_chassis|seat_block|spur_gear|planet_arm|axle_peg_set|'
        'dna_helix_holder|dna_helix_half|impossible_cube|puzzle_tile_center|puzzle_tile_tab|'
        'puzzle_tile_slot|spiral_chess_piece|lamp_shade_shell|greek_meander_shade|lamp_base|'
        'led_fit_coupon|character_body|character_insert|button_set|branch_arm_set|'
        'rocket_planter_shell|temple_planter_shell|plant_pot_liner|drainage_ring|'
        'decorative_box_shell|box_liner|ring_fit_coupon|low_poly_vase_shell|'
        'sla_calibration_town|sla_supported_variant|sla_exposure_ladder|egg_low_poly|'
        'egg_wavy|egg_voronoi_safe|jewellery_tree_panel|jewellery_tree_base|'
        'bust_head_torso|display_base_keyed|nameplate_blank|hollow_support_coupon|'
        'collectible_full_preview|keyed_character_torso|keyed_character_head|'
        'character_ears_pair|character_hands_pair|pin_connector_set|pin_socket_coupon|'
        'cape_shell|sleeves_pair|prop_pumpkin|collectible_display_base|'
        'color_eye_set|nail_claw_set|paint_swatch_strip|seed_cell_tray|humidity_dome|'
        'soil_press|water_gap_base|wall_plate|object_mount_half|key_hook_bar|'
        'screw_clearance_coupon|load_test_bar|printer_tool_holder_rail|nozzle_slot_block|'
        'hex_key_rack|scraper_hook|rail_fit_coupon|stackable_crate_body|crate_mesh_side|'
        'storage_divider|screw_compartment_box|label_tab|stacking_lip_coupon|'
        'pegboard_base_plate|peg_hook_module|peg_box_module|peg_caliper_holder|'
        'peg_flashlight_clip|peg_spacing_coupon|perforated_basket_shell|basket_handle|'
        'rib_strength_coupon|winged_body_statue|wing_pair_split|tail_segment|'
        'creature_base|support_scar_coupon|airliner_fuselage_section|airliner_wing_half|'
        'airliner_vert_stab|airliner_horz_stab_half|airliner_engine_pod_single|'
        'airliner_fan_rotor_single|airliner_folding_gear_set|airliner_wheel_axle_set|'
        'airliner_fan_blade_coupon|airliner_gear_strut|airliner_wheel_revolute|'
        'airliner_wheel_fit_coupon|pin_socket_coupon|pin_connector_set",'
        '"params":{"width_mm":200,"depth_mm":120,"height_mm":60,"wall_mm":3,"radius_mm":10,"hole_mm":4},'
        '"material":"PETG|ASA|TPU|PLA","orientation":"...","purpose":"...",'
        '"assembly_step":"...","tolerance_mm":0.2,"description":"..."}]}\n'
        "Размеры в мм, реалистичные. Каждая деталь уникальна. "
        "Если это техническая модель/kit-card/коробка/машина, не используй neural single STL: "
        "выбери CAD-like стратегию, раздельные печатные solids, min wall >=0.8 мм, ориентацию и supports. "
        "Если данных мало — зафиксируй assumptions и сделай v0 с безопасными допущениями. Без отказов."
    )
    try:
        raw = await llm.chat_completion(
            [{"role": "user", "content": prompt}],
            text_model,
            system=(
                "Ты инженер-конструктор и специалист FDM-печати. Ответ — только JSON. "
                "Готовишь проект OpenSCAD, не STL-примитивы. "
            "Мысли как инженер: требования, допущения, размеры, допуски, сборка, проверка. "
            "Урок: Meshy/нейросеть даёт только шаблон; финал для техники — CAD-like solids."
            ),
            temperature=0.35,
        )
    except Exception as e:
        if storyboard_frames and len(storyboard_frames) >= 2:
            fallback = frames_to_project_specs(storyboard_frames)
        elif _should_use_hybrid_fallback(user_request) or _should_use_hybrid_fallback(context):
            fallback = {
                "project_name": "hybrid-generator-v0",
                "mode": "fallback-network",
                "parts": _fallback_hybrid_parts()[:part_count],
                "assumptions": [],
            }
        else:
            fallback = _fallback_single_part(user_request or context)
        fallback["assumptions"] = list(fallback.get("assumptions") or []) + [
            f"LLM/прокси недоступен ({type(e).__name__}: {str(e)[:120]}). "
            "Собран локальный fallback v0 без ожидания сети.",
        ]
        return fallback
    data = parse_project_specs(raw)
    if storyboard_frames and len(storyboard_frames) >= 2:
        sb = frames_to_project_specs(storyboard_frames)
        if not data or not isinstance(data.get("parts"), list) or not data["parts"]:
            return sb
        # Слить: названия из storyboard, параметры из LLM если есть
        merged: List[Dict[str, Any]] = []
        llm_parts = data["parts"]
        for idx, sb_part in enumerate(sb["parts"]):
            part = dict(sb_part)
            if idx < len(llm_parts) and isinstance(llm_parts[idx], dict):
                lp = llm_parts[idx]
                if isinstance(lp.get("params"), dict):
                    part["params"] = {**part.get("params", {}), **lp["params"]}
                for k in ("material", "orientation", "tolerance_mm"):
                    if lp.get(k):
                        part[k] = lp[k]
            merged.append(part)
        data = {**sb, **data, "parts": merged, "mode": "storyboard+llm"}
        return data

    if not data or not isinstance(data.get("parts"), list) or not data["parts"]:
        if storyboard_frames and len(storyboard_frames) >= 2:
            return frames_to_project_specs(storyboard_frames)
        if _should_use_hybrid_fallback(user_request) or _should_use_hybrid_fallback(context):
            return {
                "project_name": "hybrid-generator-v0",
                "mode": "fallback",
                "parts": _fallback_hybrid_parts()[:part_count],
                "assumptions": [
                    "Не удалось разобрать раскадровку — шаблон гибридного генератора.",
                    "Отправьте storyboard.html или укажите размеры в мм.",
                ],
            }
        single = _fallback_single_part(user_request or context)
        single["assumptions"] = list(single.get("assumptions") or []) + [
            "LLM не вернул JSON — собрана одна деталь по тексту запроса, не проект генератора.",
        ]
        return single
    data["parts"] = data["parts"][:part_count]
    if len(data["parts"]) < part_count and _should_use_hybrid_fallback(user_request):
        for extra in _fallback_hybrid_parts():
            if len(data["parts"]) >= part_count:
                break
            eid = extra["id"]
            if not any(sanitize_id(str(p.get("id") or p.get("name"))) == eid for p in data["parts"]):
                data["parts"].append(extra)
    return data


async def generate_single_part_specs(
    user_request: str,
    text_model: str,
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Одна деталь для печати — ручка, кронштейн и т.п."""
    from bot.services import llm

    profile_hint = ""
    if profile and (profile.get("printer") or profile.get("material")):
        profile_hint = f"\nПринтер/материал: {profile.get('printer') or '—'} / {profile.get('material') or 'PETG'}."

    prompt = (
        f"Запрос пользователя:\n{user_request[:2500]}\n"
        f"{profile_hint}\n\n"
        "Сделай ОДНУ деталь для FDM 3D-печати (не сборку, не генератор, не 8 частей).\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"project_name":"slug",'
        '"requirements":["..."],'
        '"assumptions":["..."],'
        '"critical_dimensions":[{"name":"...","value_mm":50,"tolerance_mm":0.3}],'
        '"parts":[{"id":"part_id","name":"Название детали",'
        '"template":"bottle_handle|plate|cylinder|tube_clip|hollow_box|bobbin",'
        '"params":{"width_mm":80,"depth_mm":40,"height_mm":12,"radius_mm":26,"neck_radius_mm":26,"wall_mm":3},'
        '"material":"PETG","orientation":"...","purpose":"...","tolerance_mm":0.2}]}\n'
        "Ровно одна деталь в parts. Размеры в мм, реалистичные для запроса."
    )
    raw = await llm.chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system=(
            "Ты инженер-конструктор FDM. Ответ — только JSON с одной деталью. "
            "Не предлагай гибридный генератор и не дроби на много частей."
        ),
        temperature=0.35,
    )
    data = parse_project_specs(raw)
    if not data or not isinstance(data.get("parts"), list) or not data["parts"]:
        return _fallback_single_part(user_request)
    data["parts"] = [data["parts"][0]]
    data["mode"] = data.get("mode") or "single"
    return data


async def export_single_part_stl(
    specs: Dict[str, Any],
) -> Tuple[Optional[bytes], str, str, Dict[str, Any]]:
    """STL одной детали + имя файла и подпись."""
    parts = [p for p in (specs.get("parts") or []) if isinstance(p, dict)]
    if not parts:
        specs = _fallback_single_part(str(specs.get("project_name") or "part"))
        parts = specs["parts"]
    part = parts[0]
    pid = sanitize_id(str(part.get("id") or part.get("name") or "part"))
    project = sanitize_id(str(specs.get("project_name") or pid), pid)
    scad_src = build_scad_source(part).encode("utf-8")
    title = str(part.get("name") or pid)
    caption = f"🖨 {title}\nПроект: {project}"
    if not openscad_available():
        return None, f"{pid}.scad", caption, part
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        stl_path = Path(td) / f"{pid}.stl"
        if await export_stl_from_scad(scad_src, stl_path):
            return stl_path.read_bytes(), f"{pid}.stl", caption, part
    return None, f"{pid}.scad", caption, part


def _part_params(part: Dict[str, Any]) -> Dict[str, Any]:
    p = part.get("params")
    return p if isinstance(p, dict) else part


def _dimension_value(part: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    p = _part_params(part)
    for key in keys:
        try:
            value = p.get(key)
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return default


def build_requirements_md(specs: Dict[str, Any], parts: List[Dict[str, Any]], profile: Dict[str, Any]) -> str:
    from bot.services.print_profile import format_profile

    lines = ["# Инженерное задание", "", "## Профиль печати", format_profile(profile), ""]
    requirements = specs.get("requirements") if isinstance(specs.get("requirements"), list) else []
    assumptions = specs.get("assumptions") if isinstance(specs.get("assumptions"), list) else []
    critical = specs.get("critical_dimensions") if isinstance(specs.get("critical_dimensions"), list) else []
    lines.append("## Требования")
    if requirements:
        lines.extend(f"- {r}" for r in requirements[:20])
    else:
        lines.append("- Выполнить печатаемый проект по запросу пользователя.")
    lines.extend(["", "## Допущения"])
    if assumptions:
        lines.extend(f"- {a}" for a in assumptions[:20])
    else:
        lines.append("- Размеры являются инженерной версией v0 и требуют проверки на реальном узле.")
    lines.extend(["", "## Критические размеры"])
    if critical:
        for item in critical[:20]:
            if isinstance(item, dict):
                name = item.get("name") or "размер"
                value = item.get("value_mm") or item.get("value") or "—"
                tol = item.get("tolerance_mm") or item.get("tolerance") or "—"
                lines.append(f"- {name}: {value} мм, допуск ±{tol} мм")
    else:
        lines.append("- Проверить посадочные размеры, зазоры, толщину стенок и ориентацию печати.")
    lines.extend(["", "## Детали"])
    for idx, part in enumerate(parts, start=1):
        p = _part_params(part)
        dims = []
        for key in ("width_mm", "depth_mm", "height_mm", "radius_mm", "wall_mm", "hole_mm"):
            if p.get(key) not in (None, ""):
                dims.append(f"{key}={p.get(key)} мм")
        tol = part.get("tolerance_mm") or p.get("tolerance_mm") or 0.2
        lines.append(f"{idx}. {part.get('name') or part.get('id')} — {', '.join(dims) or 'размеры в SCAD'}, допуск ±{tol} мм")
    return "\n".join(lines) + "\n"


def build_dimension_table_csv(parts: List[Dict[str, Any]]) -> str:
    lines = ["part_id,name,width_mm,depth_mm,height_mm,radius_mm,wall_mm,hole_mm,tolerance_mm"]
    for idx, part in enumerate(parts, start=1):
        pid = sanitize_id(str(part.get("id") or part.get("name") or f"part-{idx:02d}"))
        name = str(part.get("name") or pid).replace(",", ";")
        p = _part_params(part)
        vals = [p.get(k, "") for k in ("width_mm", "depth_mm", "height_mm", "radius_mm", "wall_mm", "hole_mm")]
        tol = part.get("tolerance_mm") or p.get("tolerance_mm") or 0.2
        lines.append(",".join([pid, name, *[str(v) for v in vals], str(tol)]))
    return "\n".join(lines) + "\n"


def build_quality_checklist(parts: List[Dict[str, Any]]) -> str:
    lines = [
        "КОНТРОЛЬ ПЕРЕД ПЕЧАТЬЮ",
        "======================",
        "1. Проверить масштаб импорта в слайсере: единицы — миллиметры.",
        "2. Проверить толщину стенок относительно сопла и материала.",
        "3. Проверить свесы, поддержку и ориентацию каждой детали.",
        "4. Проверить зазоры посадок: обычно 0.2–0.4 мм для FDM.",
        "5. Напечатать малый тест посадки, если есть сопрягаемые детали.",
        "6. Для скачанных/нейросетевых моделей: каждая деталь должна быть manifold/solid, без внутренних zero-thickness стенок.",
        "7. Не сшивать сборку в один mesh автоматически: kit-card, коробки, колёса, петли и защёлки обычно лучше печатать отдельными деталями.",
        "8. Supports подбирать по размеру: крупные держат корпус/крылья, мелкие только касаются хрупких деталей.",
        "",
        "Детали:",
    ]
    for idx, part in enumerate(parts, start=1):
        lines.append(f"- {idx}. {part.get('name') or part.get('id')}: {part.get('purpose') or part.get('description') or 'проверить геометрию'}")
    return "\n".join(lines) + "\n"


def build_svg_drawing(project: str, parts: List[Dict[str, Any]]) -> str:
    row_h = 78
    width = 900
    height = max(180, 90 + row_h * len(parts))
    rows = []
    y = 60
    for idx, part in enumerate(parts, start=1):
        p = _part_params(part)
        w = max(12.0, min(180.0, _dimension_value(part, "width_mm", default=_dimension_value(part, "radius_mm", default=20) * 2)))
        d = max(12.0, min(90.0, _dimension_value(part, "depth_mm", default=w)))
        h = max(6.0, min(70.0, _dimension_value(part, "height_mm", default=20)))
        name = str(part.get("name") or part.get("id") or f"part-{idx}")[:42]
        pid = sanitize_id(str(part.get("id") or name or idx))
        template = str(part.get("template") or part.get("shape") or "box")
        rows.append(f'<text x="24" y="{y}" font-size="14" font-family="Arial">{idx}. {name} ({pid})</text>')
        rows.append(f'<rect x="260" y="{y - 22}" width="{w}" height="{d}" fill="none" stroke="#111" stroke-width="2"/>')
        rows.append(f'<rect x="520" y="{y - 22}" width="{w}" height="{h}" fill="none" stroke="#555" stroke-width="2"/>')
        rows.append(f'<text x="260" y="{y + d + 12}" font-size="11" font-family="Arial">top: {w:.0f}×{d:.0f} мм</text>')
        rows.append(f'<text x="520" y="{y + h + 12}" font-size="11" font-family="Arial">side: {w:.0f}×{h:.0f} мм · {template}</text>')
        y += row_h
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="24" y="28" font-size="20" font-family="Arial" font-weight="bold">Инженерный чертёж: {project}</text>'
        '<text x="260" y="48" font-size="12" font-family="Arial">Вид сверху</text>'
        '<text x="520" y="48" font-size="12" font-family="Arial">Вид сбоку</text>'
        + "".join(rows)
        + '</svg>'
    )


async def _build_cad_project_zip(specs: Dict[str, Any]):
    """Build a kit ZIP from `cad_specs` using the out-of-process CAD kernel.

    Returns the same 6-tuple contract as build_project_zip, or None if the
    kernel is unavailable or the build failed (so the caller can fall back).
    """
    import asyncio
    import tempfile
    import zipfile
    from pathlib import Path

    try:
        from bot.services import cad_kernel
    except Exception:
        return None
    if not cad_kernel.available():
        return None

    cad_specs = specs.get("cad_specs") or []
    project = sanitize_id(str(specs.get("project_name") or "cad-kit"), "cad-kit")
    material = str(specs.get("material") or "petg").lower()
    zp = tempfile.mktemp(suffix=".zip")
    try:
        res = await asyncio.to_thread(
            cad_kernel.build_kit_zip_safe, zp, cad_specs, material, 150, 3
        )
    except Exception:
        return None
    if not res.get("ok") or not Path(zp).exists():
        return None

    data = Path(zp).read_bytes()
    try:
        Path(zp).unlink()
    except Exception:
        pass

    # Extract per-part STL bytes for the assembly/preview delivery contract.
    ordered_stl: List[Tuple[int, bytes, str, str]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        stl_names = sorted(n for n in zf.namelist()
                           if n.startswith("parts/") and n.endswith(".stl"))
        for i, n in enumerate(stl_names, start=1):
            base = Path(n).stem
            ordered_stl.append((i, zf.read(n), f"{base}.stl",
                                 f"CAD-деталь: {base}"))

    n_parts = len(cad_specs)
    cap = (
        f"📦 CAD-проект (OpenCASCADE-кернел): {n_parts} деталей\n"
        f"• parts/*.stl — для печати, step/*.step — для CAD-правки\n"
        f"• настоящая B-rep геометрия: фаски, скругления, boolean, counterbore\n"
        f"• engineering_report.txt — масса/ЦТ/устойчивость/нависания/ориентация\n"
        f"• стратегия: {specs.get('strategy') or 'cad-kernel-occt'}"
    )
    return (data, f"{project}-cad-pack.zip", cap, n_parts,
            len(ordered_stl) > 0, ordered_stl)


async def build_project_zip(
    specs: Dict[str, Any],
    profile: Dict[str, Any],
) -> Tuple[bytes, str, str, int, bool, List[Tuple[int, bytes, str, str]]]:
    """ZIP: scad/, stl?/, engineering docs, plan, BOM."""
    # CAD short-circuit: real B-rep kernel parts are built out-of-process.
    if specs.get("cad_specs"):
        cad_result = await _build_cad_project_zip(specs)
        if cad_result is not None:
            return cad_result
        # else: kernel unavailable/crashed → fall through to OpenSCAD path.

    project = sanitize_id(str(specs.get("project_name") or "print-project"), "print-project")
    parts: List[Dict[str, Any]] = [
        p for p in (specs.get("parts") or []) if isinstance(p, dict)
    ]
    if not parts:
        if _should_use_hybrid_fallback(str(specs.get("project_name") or "")):
            parts = _fallback_hybrid_parts()
        else:
            parts = _fallback_single_part(str(specs.get("project_name") or "part"))["parts"]

    buf = io.BytesIO()
    stl_count = 0
    stl_files_out: List[Tuple[int, bytes, str, str]] = []
    storyboard_frames = specs.get("storyboard_frames") if isinstance(specs.get("storyboard_frames"), list) else []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, part in enumerate(parts, start=1):
            frame_num = int(part.get("frame_number") or idx)
            pid = sanitize_id(str(part.get("id") or part.get("name") or f"part-{idx:02d}"))
            ordered_name = f"{frame_num:02d}-{pid}"
            scad_src = build_scad_source(part).encode("utf-8")
            zf.writestr(f"scad/{ordered_name}.scad", scad_src)
            part["stl_included"] = False
            if openscad_available():
                import tempfile
                from pathlib import Path

                with tempfile.TemporaryDirectory() as td:
                    stl_path = Path(td) / f"{ordered_name}.stl"
                    if await export_stl_from_scad(scad_src, stl_path):
                        stl_bytes = stl_path.read_bytes()
                        zf.writestr(f"stl/{ordered_name}.stl", stl_bytes)
                        part["stl_included"] = True
                        stl_count += 1
                        title = str(part.get("name") or pid)
                        desc = str(part.get("purpose") or part.get("description") or "")
                        stl_files_out.append((frame_num, stl_bytes, ordered_name, title, desc))

        if stl_files_out:
            from bot.services.assembly_preview import build_assembly_previews

            for path, blob in build_assembly_previews(specs, stl_files_out).items():
                zf.writestr(path, blob)

        zf.writestr("engineering/requirements.md", build_requirements_md(specs, parts, profile))
        zf.writestr("engineering/dimensions.csv", build_dimension_table_csv(parts))
        zf.writestr("engineering/quality_checklist.txt", build_quality_checklist(parts))
        if specs.get("project_kind") == "mechanical_boeing_airliner":
            zf.writestr("engineering/kinematics.json", build_kinematics_json(specs))
            zf.writestr("engineering/kinematics.md", build_kinematics_md(specs))
            zf.writestr("engineering/fit_first_print_order.txt", build_fit_first_print_order(parts))
        if isinstance(specs.get("print_prep_contract"), dict):
            zf.writestr(
                "engineering/print_prep_contract.json",
                json.dumps(specs["print_prep_contract"], ensure_ascii=False, indent=2),
            )
        if isinstance(specs.get("reference_blueprint"), dict):
            zf.writestr(
                "engineering/reference_blueprint.json",
                json.dumps(specs["reference_blueprint"], ensure_ascii=False, indent=2),
            )
        ref_lib = specs.get("reference_library")
        if isinstance(ref_lib, dict):
            zf.writestr(
                "engineering/reference_library.json",
                json.dumps(ref_lib, ensure_ascii=False, indent=2),
            )
        zf.writestr("drawings/overview.svg", build_svg_drawing(project, parts))
        if storyboard_frames:
            from bot.services.storyboard import build_print_order_txt

            zf.writestr("print_order.txt", build_print_order_txt(storyboard_frames, parts))
        zf.writestr("print_plan.txt", build_print_plan(parts, profile))
        zf.writestr("bom.csv", build_bom_csv(parts))
        zf.writestr("assembly.md", build_assembly_md(project, parts))
        readme = (
            f"Проект: {project}\n"
            f"Деталей: {len(parts)}\n"
            f"STL внутри: {stl_count} (OpenSCAD на сервере: {'да' if openscad_available() else 'нет'})\n\n"
            "1. Откройте scad/*.scad в OpenSCAD → F6 → Export STL\n"
            "2. Или используйте stl/*.stl если они есть\n"
            "3. Перед печатью проверьте engineering/requirements.md и engineering/quality_checklist.txt\n"
            "4. Чертёж-обзор: drawings/overview.svg\n"
            "5. Bambu Studio / OrcaSlicer → импорт → печать\n"
            "6. Сборка — assembly.md\n"
            "7. Превью сборки (если есть STL): preview/assembly_pose.stl (NACA-референс) "
            "+ preview/parts_layout_print_orientation.stl (раскладка деталей)\n"
        )
        zf.writestr("README.txt", readme)

    mode = str(specs.get("mode") or "")
    source_note = ""
    if mode.startswith("storyboard"):
        source_note = "\n📋 По вашей раскадровке (storyboard.html), порядок — print_order.txt"
    elif mode == "fallback":
        source_note = "\n⚠️ Шаблонный набор — файл раскадровки разобран не полностью. Пришлите HTML ещё раз."

    cap = (
        f"📦 Проект на печать: {len(parts)} деталей{source_note}\n"
        f"• scad/ — параметрические модели (01-, 02-… по кадрам)\n"
    )
    if specs.get("project_kind"):
        cap += f"• стратегия: {specs.get('strategy') or specs.get('project_kind')}\n"
    if specs.get("project_kind") == "mechanical_boeing_airliner":
        cap += (
            f"• кинематика v2: {len(specs.get('kinematics') or [])} узлов "
            "(engineering/kinematics.md)\n"
            "• fit-first: engineering/fit_first_print_order.txt\n"
            "• превью: assembly_pose.stl (NACA-самолёт) + parts_layout_print_orientation.stl\n"
        )
    if stl_count:
        cap += f"• stl/ — {stl_count} готовых файлов\n"
    else:
        cap += "• STL: экспортируйте из OpenSCAD (F6 → Export STL)\n"
    if storyboard_frames:
        cap += "• print_order.txt — что печатать по кадрам\n"
    cap += "• engineering/, drawings/overview.svg, print_plan.txt, assembly.md, bom.csv"

    ordered_stl: List[Tuple[int, bytes, str, str]] = [
        (n, b, f"{base}.stl", f"Кадр {n}: {title}\n{desc}".strip())
        for n, b, base, title, desc in sorted(stl_files_out, key=lambda x: x[0])
    ]
    return buf.getvalue(), f"{project}-print-pack.zip", cap, len(parts), stl_count > 0, ordered_stl
