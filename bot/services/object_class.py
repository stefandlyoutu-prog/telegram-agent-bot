"""Classify user requests into three 3D-generation families.

  ORGANIC       — soft shapes (banana, dog, dragon) → AI mesh (Meshy)
  HARD_SURFACE  — recognizable machines (airplane, car) → CAD / curated geometry
  FUNCTIONAL    — brackets, boxes, gears → parametric CAD (OpenSCAD / CadQuery)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Tuple

_HARD_SURFACE = re.compile(
    r"самол[её]т|airplane|airliner|aircraft|боинг|boeing|b747|\b747\b|"
    r"истребител|fighter|вертол[её]т|helicopter|"
    r"автомобил|машин[ауы]|car\b|vehicle|танк|tank\b|"
    r"корабл|ship\b|ракет|rocket|дрон|drone\b|поезд|train\b|"
    r"двигател|engine\b|турбин",
    re.I,
)

_ORGANIC = re.compile(
    r"банан|banana|яблок|apple|фрукт|fruit|"
    r"фигур|персонаж|чебурашк|angel|ангел|"
    r"животн|собак|dog|кошк|cat\b|кот\b|labrador|лабрадор|"
    r"дракон|dragon|монстр|monster|"
    r"человек|лиц[оа]|голова|бюст|statue|стату|"
    r"игрушк|кукл|cartoon|аниме|mascot|"
    r"органическ|скulpt|декоратив",
    re.I,
)

_FUNCTIONAL = re.compile(
    r"кронштейн|bracket|держател|holder|"
    r"короб|box|organizer|органайз|"
    r"шестерн|gear|планетар|"
    r"крюч|hook|защелк|clip|"
    r"адаптер|adapter|креплен|mount|"
    r"труб|pipe|фитинг|fitting|"
    r"клапан|valve|компрессор|compressor|"
    r"ручк[ауи]|handle|"
    r"кроншт|подставк|stand\b|"
    r"проект\s+на\s+печать|print\s+project|"
    r"openscad|параметрич",
    re.I,
)

_PRINT_INTENT = re.compile(
    r"3d[\s-]?(модел|модель|печат)|stl|3mf|"
    r"для\s+печат|bambu|бамбу|принтер|слайс|"
    r"сделай|создай|напечат|нужн[ао]?\s+3d|хочу|пришли",
    re.I,
)


class ObjectClass(str, Enum):
    ORGANIC = "organic"
    HARD_SURFACE = "hard_surface"
    FUNCTIONAL = "functional"
    NON_3D = "non_3d"


def has_print_intent(text: str) -> bool:
    return bool(_PRINT_INTENT.search(text or ""))


def classify_object(text: str) -> Tuple[ObjectClass, str]:
    """Return (class, short subject hint)."""
    t = text or ""

    from bot.services.airplane_3mf import airplane_requested
    from bot.services.print_project import is_existing_project_help_request, wants_print_project

    if is_existing_project_help_request(t):
        return ObjectClass.NON_3D, "consultation"

    if airplane_requested(t) or _HARD_SURFACE.search(t):
        return ObjectClass.HARD_SURFACE, "hard_surface"

    if _FUNCTIONAL.search(t) or wants_print_project(t):
        return ObjectClass.FUNCTIONAL, "functional"

    if _ORGANIC.search(t) or has_print_intent(t):
        return ObjectClass.ORGANIC, "organic"

    return ObjectClass.NON_3D, ""
