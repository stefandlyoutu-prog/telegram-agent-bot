"""Ultra Plus как настоящая книга-история, а не список вопросов.

Берём расчёт Матрицы Судьбы + опорные тексты корпуса и переписываем их
в тёплую, цельную, личную книгу через LLM. Фолбэк — корпусный ассемблер.
"""

from __future__ import annotations

import logging

from oracle_bot.book_writer import SectionSpec, write_sections
from oracle_bot.ultra_plus.assembler import (
    BookSection,
    SOURCE_NOTE,
    _hvd_enrichment,
    _load_corpus,
    _numbered_blocks,
    _talent_block,
    _text,
    build_book_sections,
)
from oracle_bot.ultra_plus.calculator import MatrixProfile, section_numbers

logger = logging.getLogger(__name__)


def _cap(text: str, limit: int = 1600) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _ref_personality(corpus: dict, nums: dict) -> str:
    pa, pb = nums["personal"]
    chunks = []
    for label, key in (("в плюсе", "personal_positive"), ("в минусе", "personal_negative")):
        for n in (pa, pb):
            t = _text(corpus, key, n)
            if t:
                chunks.append(f"[{label}] {t}")
    comm = _text(corpus, "communication", nums["communication"])
    if comm:
        chunks.append(f"[в общении] {comm}")
    return _cap("\n".join(chunks), 1800)


def _ref(corpus: dict, section: str, nums_key: str, nums: dict) -> str:
    val = nums[nums_key]
    seq = val if isinstance(val, (list, tuple)) else (val,)
    return _cap(_numbered_blocks(corpus, section, tuple(seq)))


def _specs(profile: MatrixProfile) -> list[SectionSpec]:
    corpus = _load_corpus()
    nums = section_numbers(profile)

    talents = "\n\n".join(
        t for t in (
            _talent_block(corpus, tuple(nums["talents_god"]), "talents_god"),
            _talent_block(corpus, tuple(nums["talents_mother"]), "talents_mother"),
            _talent_block(corpus, tuple(nums["talents_father"]), "talents_father"),
        ) if t
    )
    purpose = "\n\n".join(
        t for t in (
            _ref(corpus, "purpose_20_40", "purpose_20_40", nums),
            _ref(corpus, "purpose_40_60", "purpose_40_60", nums),
            _ref(corpus, "purpose_general", "purpose_general", nums),
        ) if t
    )
    money = "\n\n".join(
        t for t in (
            _ref(corpus, "money_direction", "money_direction", nums),
            _ref(corpus, "money_success", "money_success", nums),
        ) if t
    )
    rod = "\n\n".join(
        t for t in (
            _ref(corpus, "parents", "parents", nums),
            _ref(corpus, "lineage_male", "lineage_male", nums),
            _ref(corpus, "lineage_female", "lineage_female", nums),
            _ref(corpus, "parent_wounds", "parent_wounds", nums),
        ) if t
    )
    soul = "\n\n".join(
        t for t in (
            _ref(corpus, "past_life", "past_life", nums),
            _ref(corpus, "children", "children", nums),
        ) if t
    )
    finale = "\n\n".join(
        t for t in (
            _ref(corpus, "life_guide", "life_guide", nums),
            _ref(corpus, "year_forecast", "year_forecast", nums),
        ) if t
    )

    specs = [
        SectionSpec(
            title="Кто ты",
            brief="Вступление-портрет: суть характера, как раскрывается в плюсе и что "
            "включается в минусе, как ведёт себя в общении. Тёплое узнавание себя.",
            facts=_ref_personality(corpus, nums) or "Опиши цельный характер человека.",
            words="260–340",
        ),
        SectionSpec(
            title="Твои таланты и дары рода",
            brief="Сильные дары: врождённые таланты и то, что пришло по линии матери и "
            "отца. Как их узнать в себе и где применять. Свяжи в одну историю наследия.",
            facts=_cap(talents, 2000) or "Опиши таланты и сильные стороны человека.",
            words="260–340",
        ),
        SectionSpec(
            title="Твоё предназначение",
            brief="Путь и смысл жизни по возрастам (что важно до 40, после 40) и общее "
            "предназначение. Куда ведёт эта жизнь именно его.",
            facts=purpose or "Опиши предназначение и жизненный путь.",
            words="260–340",
        ),
        SectionSpec(
            title="Деньги и реализация",
            brief="В каком деле приходит изобилие, как этому человеку выстраивать "
            "достаток без надлома. Конкретно и вдохновляюще, без обещаний богатства.",
            facts=money or "Опиши денежный потенциал и сферу реализации.",
        ),
        SectionSpec(
            title="Любовь и отношения",
            brief="Как любит и как хочет быть любимым, что ищет в паре, где его сила и "
            "где уязвимость в близости. Бережно и по-взрослому.",
            facts=_ref(corpus, "relationships", "relationships", nums)
            or "Опиши отношения и любовь человека.",
        ),
        SectionSpec(
            title="Род и родители",
            brief="Что человек несёт из своей семьи: дары и задачи по мужской и женской "
            "линии, исцеление обид на родителей. С теплом и прощением.",
            facts=rod or "Опиши родовые программы и отношения с родителями.",
        ),
        SectionSpec(
            title="Душа: прошлое и продолжение",
            brief="Опыт души из прошлого и то, что она продолжает сейчас; тема детей и "
            "продолжения себя. Мягко, как разговор о глубинном.",
            facts=soul or "Опиши кармический опыт и тему детей.",
        ),
        SectionSpec(
            title="Здоровье и энергия",
            brief="Где у этого человека утекает энергия и как её беречь; тёплые, "
            "выполнимые опоры на каждый день. Без медицинских диагнозов.",
            facts=_ref(corpus, "health_recommend", "health_recommend", nums)
            or "Дай мягкие рекомендации по энергии и заботе о себе.",
        ),
        SectionSpec(
            title="Напутствие и год впереди",
            brief="Главные жизненные опоры и вдохновляющий взгляд на ближайший год. "
            "Заверши книгу тёплым личным обращением к нему.",
            facts=finale or "Дай напутствие и поддерживающий взгляд на год.",
            words="240–320",
        ),
    ]
    enrich = _hvd_enrichment(profile)
    if enrich:
        specs.append(
            SectionSpec(
                title="Дополнение: твой энергетический портрет",
                brief="Короткое дополнение к портрету по диагностике темперамента и "
                "энергии — связно и по-человечески, без терминов.",
                facts=_cap(enrich, 1400),
                words="180–240",
            )
        )
    return specs


async def build_book_sections_async(profile: MatrixProfile) -> list[BookSection]:
    """Книга-история через LLM. Если LLM недоступен — корпусный фолбэк."""
    bd = profile.birth.strftime("%d.%m.%Y")
    specs = _specs(profile)
    try:
        bodies = await write_sections(profile.name, specs, concurrency=2)
    except Exception as e:  # noqa: BLE001
        logger.warning("ultra book gen %s: %s", profile.name, e)
        bodies = []

    narrative = [b for b in bodies if (b or "").strip()]
    if len(narrative) < max(3, len(specs) // 2):
        logger.warning("ultra book too sparse → corpus fallback")
        return build_book_sections(profile)

    sections: list[BookSection] = [
        BookSection(
            title=f"{profile.name}",
            body=f"Книга о тебе · Ultra Plus\n{bd}\n\n" + SOURCE_NOTE,
        )
    ]
    for spec, body in zip(specs, bodies):
        body = (body or "").strip()
        if not body:
            continue
        sections.append(BookSection(title=spec.title, body=body))
    return sections
