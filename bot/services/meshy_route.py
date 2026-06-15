"""Когда фото или текст должны идти в Meshy 3D."""

import re
from typing import Optional

from bot.config import MESHY_API_KEY

_AVITO_ONLY = re.compile(
    r"карточк.{0,12}авитo|авитo.{0,12}карточ|обложк.{0,12}авитo|"
    r"seo.{0,12}авитo|макет.{0,10}авитo",
    re.IGNORECASE,
)
_DESCRIBE_ONLY = re.compile(
    r"^(опиши|что на фото|расскажи|объясни|анализ)( только| фото)?\.?$",
    re.IGNORECASE,
)
_PRINT_3D_INTENT = re.compile(
    r"3d[\s-]?(модел|модель|печат)|stl|для\s+печат|bambu|бамбу|"
    r"слайсер|принтер|загрузить\s+в\s+принтер|"
    r"сделай|создай|напечат|нужн[ао]?\s+3d|хочу",
    re.IGNORECASE,
)
_ORGANIC_3D = re.compile(
    r"фигур|персонаж|чебурашк|ангел|angel|животн|человек|лиц[оа]|голова|"
    r"скulpt|statue|mask|маск|игрушк|кукл|mascot|"
    r"декоратив|органическ|сложн.{0,12}форм|статуэтк|бюст|"
    r"мульт|cartoon|аниме|robot|робот|монстр|maskot|нимб|крыл|"
    r"лабрадор|labrador|retriever|ретривер|собак|dog|кошк|cat|кот|"
    r"банан|banana",
    re.IGNORECASE,
)
_SIMPLE_STL = re.compile(
    r"\bупрощён|\bупрощен|\bчернов|\bтестов|\bтест\b|"
    r"\bпримитив|\bзаготов|\bпрост(?:ой|ая|ое)\s+(?:stl|модел)|"
    r"\bбез\s+точн|\bупрощ",
    re.IGNORECASE,
)

# Русский субъект → английский промпт Meshy
_SUBJECT_EN: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"лабрадор|labrador", re.I), "labrador retriever dog"),
    (re.compile(r"чебурашк", re.I), "cheburashka cartoon character"),
    (re.compile(r"ангел|angel", re.I), "angel figurine with wings"),
    (re.compile(r"собак|dog|retriever", re.I), "dog figurine"),
)


def meshy_available() -> bool:
    return bool(MESHY_API_KEY)


def should_meshy_from_photo(prompt_text: Optional[str]) -> bool:
    """
    Если Meshy настроен — любое фото = 3D-модель,
    кроме явного запроса карточки Авитo или «только опиши».
    """
    if not meshy_available():
        return False
    text = (prompt_text or "").strip()
    if _AVITO_ONLY.search(text):
        return False
    if _DESCRIBE_ONLY.match(text):
        return False
    if re.search(r"черт[её]ж|blueprint|cad|эскиз|технич.{0,16}рисун|схем[ауы]", text, re.I):
        return False
    return True


def should_meshy_from_text(prompt_text: Optional[str]) -> bool:
    """Текстовый запрос 3D-модели сложной формы — Meshy text-to-3D, не OpenSCAD-примитив."""
    if not meshy_available():
        return False
    text = (prompt_text or "").strip()
    if not text:
        return False

    from bot.services.print_project import is_openscad_suitable_part

    has_print = bool(_PRINT_3D_INTENT.search(text))
    has_organic = bool(_ORGANIC_3D.search(text))

    # Фигурки/персонажи — всегда Meshy (не ловить «примерно» / «просто файл» как «упрощённый STL»)
    if has_organic and has_print and not is_openscad_suitable_part(text):
        return True

    if _SIMPLE_STL.search(text):
        return False
    if not has_print:
        return False
    if is_openscad_suitable_part(text):
        return False
    if has_organic:
        return True
    if re.search(r"сделай|создай|нужн[аоы]?|нужен|хочу", text, re.I):
        return True
    return False


def _color_tags(text: str) -> str:
    from bot.services.bambu_hints import color_words_from_text, part_color_prompt_fragment

    parts: list[str] = []
    part_specific = part_color_prompt_fragment(text)
    if part_specific:
        parts.append(part_specific)
    for color in color_words_from_text(text):
        generic = f"{color} accents"
        if color == "black":
            generic = "black"
        if generic not in parts:
            parts.append(generic)
    return ", ".join(parts)


def _subject_en(text: str) -> Optional[str]:
    for pat, en in _SUBJECT_EN:
        if pat.search(text):
            subj = en
            if re.search(r"ч[ёе]рн|black", text, re.I) and "black" not in subj:
                subj = f"black {subj}"
            colors = _color_tags(text)
            colors = re.sub(r"^black,?\s*", "", colors)
            if colors:
                return f"{subj}, {colors}"
            return subj
    return None


def _append_reference_style(base: str, raw: str) -> str:
    try:
        from bot.services.reference_library import meshy_style_fragment

        frag = meshy_style_fragment(raw)
        if frag and frag.lower() not in base.lower():
            merged = f"{base.rstrip('.')}, {frag}"
            return merged[:500]
    except Exception:
        pass
    return base[:500]


def meshy_prompt_from_text(prompt_text: str) -> str:
    """Короткий промпт для Meshy из русского запроса."""
    raw = prompt_text.strip()

    if re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", raw, re.I):
        from bot.services.bambu_hints import color_words_from_text, extract_part_color_requests

        colors = _color_tags(raw)
        part_colors = extract_part_color_requests(raw)
        color_desc = f", {colors}" if colors else ""
        if "white" in color_words_from_text(raw):
            color_desc += ", overall white aircraft livery"
            if "engines" not in part_colors:
                color_desc += ", white engine nacelles (not black)"
            if "tail" not in part_colors:
                color_desc += ", white tail (not red)"
        forbidden = []
        if "engines" not in part_colors:
            forbidden.append("no black engines")
        if "tail" not in part_colors:
            forbidden.append("no red tail")
        if forbidden:
            color_desc += ", " + ", ".join(forbidden)
        return _append_reference_style(
            (
                "3D printable scale model, Boeing passenger airliner airplane"
                f"{color_desc}, high detail fuselage, wings, tail, engines, landing gear, "
                "single clean manifold model, FDM friendly, no text, no thin wires, "
                "optimized for Bambu Studio"
            ),
            raw,
        )

    known = _subject_en(raw)
    if known:
        return _append_reference_style(
            (
                f"3D printable figurine, {known}, sitting pose, "
                f"single solid piece, FDM friendly, thick features, no thin wires, "
                f"no base plate, printable without supports"
            ),
            raw,
        )

    t = raw
    t = re.sub(
        r"^(?:сделай|создай|нужн[ао]?|хочу)\s+(?:мне\s+)?",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"^(?:3d[\s-]?)?(?:модел[ьи]?|stl)\s*(?:для\s+(?:печати|принтер[ае]))?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"(?:для\s+(?:печати|принтер[ае]))?\s*(?:на\s+(?:принтер[еу]|bambu|бамбу)[^\.\n]*)",
        "",
        t,
        flags=re.I,
    )
    t = re.split(r"\?\s*Какой|\?\s*какой|\n\n", t, maxsplit=1)[0].strip(" .")
    t = re.sub(r"^3d[\s-]?модел[^\.\n]*[\.\n]\s*", "", t, flags=re.I)
    t = re.sub(r"^для\s+принтер[^\.\n]*[\.\n]\s*", "", t, flags=re.I)
    t = re.sub(r"^(?:bambu|бамбу|p2s)[^\.\n]*[\.\n]\s*", "", t, flags=re.I)
    t = re.sub(r"^(?:bambu|бамбу|p2s)\.\s*", "", t, flags=re.I)
    t = t.strip(" .")

    fig = re.search(
        r"(?:фигурк[аи]|статуэтк[аи]|персонаж)\s+([^\.\n,]{2,80})",
        raw,
        re.I,
    )
    if fig:
        subject = fig.group(1).strip()
        subject = re.split(r"\.\s*", subject)[0].strip()
        subject = re.sub(r"\s*[,]?\s*у\s+которого.*", "", subject, flags=re.I)
        colors = _color_tags(raw)
        extra = f", {colors}" if colors else ""
        return _append_reference_style(
            (
                f"3D printable figurine, {subject}{extra}, sitting pose, "
                f"single solid piece, FDM friendly, thick features"
            ),
            raw,
        )

    if len(t) < 8:
        return _append_reference_style(raw, raw)
    return _append_reference_style(
        f"3D printable model, {t}, single piece, FDM friendly",
        raw,
    )
