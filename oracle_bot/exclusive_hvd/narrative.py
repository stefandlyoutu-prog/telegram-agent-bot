"""ХВД как живая персональная книга: данные расчёта → тёплый личный текст."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

from oracle_bot.book_writer import SectionSpec, write_sections
from oracle_bot.exclusive_hvd.calculator import HVDProfile
from oracle_bot.exclusive_hvd.interpreter import CHAKRA_MEANING
from oracle_bot.exclusive_hvd.report import build_report_parts  # шаблонный фолбэк

try:
    from oracle_bot.exclusive_hvd.knowledge import (
        chakras_course_text,
        contour_course_text,
        intro_course_text,
        period_digit_course_text,
        reactivity_course_text,
        task_course_text,
        typology_course_text,
        yinyang_course_text,
    )
except Exception:  # noqa: BLE001
    def _empty(*a, **k):  # type: ignore
        return ""

    chakras_course_text = contour_course_text = intro_course_text = _empty  # type: ignore
    period_digit_course_text = reactivity_course_text = task_course_text = _empty  # type: ignore
    typology_course_text = yinyang_course_text = _empty  # type: ignore

logger = logging.getLogger(__name__)

_TG_LIMIT = 3900


def _course(text: str, limit: int = 1100) -> str:
    """Очищает и обрезает материал курса для подачи в LLM как опору."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(".", 1)[0] + "."
    return f"\n\nМатериал курса (перескажи смысл своими словами, не цитируй дословно):\n{text}"


@dataclass
class Section:
    title: str
    body: str


def _lvl(pct: int) -> str:
    if pct >= 75:
        return "очень сильно выражена — это твоя природная мощь и одновременно то, что легко перегружается"
    if pct >= 60:
        return "хорошо развита, на неё можно опираться"
    if pct >= 40:
        return "в рабочем балансе"
    if pct >= 25:
        return "приглушена, включается не сразу"
    return "почти спит — её стоит бережно пробуждать"


def _ch(profile: HVDProfile):
    return {
        "Муладхара": profile.physical.chakras[0].percent,
        "Свадхистана": profile.physical.chakras[1].percent,
        "Манипура": profile.emotional.chakras[0].percent,
        "Анахата": profile.emotional.chakras[1].percent,
        "Вишудха": profile.intellectual.chakras[0].percent,
        "Аджна": profile.intellectual.chakras[1].percent,
    }


def _chakra_facts(profile: HVDProfile, names: tuple[str, ...]) -> str:
    ch = _ch(profile)
    out = []
    for n in names:
        out.append(f"- {n} ({CHAKRA_MEANING.get(n, '')}): {_lvl(ch[n])}")
    return "\n".join(out)


def _clean_lvl(pct: int) -> str:
    """Короткая чистая формулировка уровня (без оговорок) — для фолбэков."""
    if pct >= 75:
        return "очень сильно выражена"
    if pct >= 60:
        return "хорошо развита"
    if pct >= 40:
        return "в балансе"
    if pct >= 25:
        return "приглушена"
    return "почти спит"


def _clean_fallbacks(profile: HVDProfile, leadership: str) -> dict[str, str]:
    """Чистые человеческие фолбэки по главам (без сырых транскриптов курса).

    Используются, только если LLM полностью недоступен.
    """
    nm = profile.name
    ch = _ch(profile)

    def lv(name: str) -> str:
        return _clean_lvl(ch.get(name, 0))

    periods = " ".join(
        f"В возрасте {p.age_range} на первый план выходит тема «{p.theme}»: {p.description}"
        for p in profile.life_periods
    )
    return {
        "С чего начинается эта книга": (
            f"{nm}, эта книга — про тебя. ХВД (хронально-векторная диагностика) — это не "
            "гадание, а карта личности, собранная по дате рождения. Она показывает твой "
            "темперамент, характер и мышление, энергию внутренних центров, баланс инь и ян, "
            "путь по возрастам и задачи души. Читай не спеша: в каждой главе ты будешь "
            "узнавать свои черты и точнее понимать, почему ты именно такой."
        ),
        "Твоя кармическая типология": (
            f"Твоя кармическая типология — основа характера, заложенная датой рождения. "
            f"Её суть для тебя: {profile.typology_hint} Это твой главный жизненный сюжет: "
            "здесь и сила, на которую можно опираться, и ловушка, через которую важно "
            "вырасти. Узнавая свой тип, ты перестаёшь бороться с собой и начинаешь "
            "действовать из своей природы."
        ),
        "Твоё тело и темперамент": (
            f"Твой темперамент — {profile.physical.label}. Это про природную энергию, "
            "выносливость и чувственность, про то, как тело откликается на нагрузку и "
            f"какой ритм жизни тебе подходит. Опора и устойчивость («могу») у тебя "
            f"{_clean_lvl(profile.can_pct)}. Энергия тела (Муладхара) {lv('Муладхара')}, "
            f"чувственность и удовольствие (Свадхистана) {lv('Свадхистана')}. Заботясь о "
            "теле и ритме, ты возвращаешь себе силу."
        ),
        "Твой характер и сердце": (
            f"Твой характер — {profile.emotional.label}. Это про волю и самооценку, "
            "отношение к деньгам и власти, про способность любить и принимать. "
            f"Воля и самоутверждение (Манипура) {lv('Манипура')}, сердечность и любовь "
            f"(Анахата) {lv('Анахата')}. {profile.egoism_note} Твоя позиция в отношениях — "
            f"{leadership}. Тень здесь — не враг, а зона роста."
        ),
        "Как ты думаешь": (
            f"Твоё мышление — {profile.intellectual.label}. Это про то, как ты "
            "воспринимаешь мир, говоришь и принимаешь решения. Речь и самовыражение "
            f"(Вишудха) {lv('Вишудха')}, интуиция и видение (Аджна) {lv('Аджна')}. "
            "Когда ты доверяешь и логике, и внутреннему чутью, решения становятся точными."
        ),
        "Карта твоей энергии: семь центров": (
            "Энергетические центры — это про то, где у тебя силы в избытке, а где их "
            "стоит бережно пробуждать. Вот твоя карта: "
            + "; ".join(f"{n} — {lv(n)}" for n in ch)
            + ". Там, где энергии много, — твоя природная мощь (и риск перегруза); там, "
            "где мало, — зона роста и заботы о себе."
        ),
        "Чего ты хочешь и что можешь": (
            f"В тебе сочетаются инь (восприятие, накопление) и ян (действие, отдача): "
            f"{'больше энергии действия' if profile.yang_pct>=profile.yin_pct else 'больше энергии восприятия'}. "
            f"Разрыв между «хочу» и «могу» у тебя "
            f"{'заметный — желания крупнее текущего ресурса, важно наполнять себя энергией' if profile.want>20 else 'небольшой — желания и возможности идут рядом'}. "
            f"Твоя позиция — {leadership}. Когда ты бережно наполняешь себя, желания "
            "доходят до результата."
        ),
        "Твой путь по возрастам": (
            "Жизнь раскрывается по периодам, и у каждого своя тема и урок. " + periods
            + " Это единая линия твоей судьбы — важно прожить каждый этап, не пропуская."
        ),
        "Задачи твоей души: прошлое, настоящее, род": (
            f"У твоей души есть несколько задач. Из прошлого опыта: {profile.task_past_hint} "
            f"Главный урок этой жизни: {profile.task_present_hint} По линии рода: "
            f"{profile.task_lineage_hint} От родителей: {profile.task_parents_hint} "
            "Вместе они складываются в твоё предназначение — направление, в котором "
            "жизнь раскрывает тебя полнее всего."
        ),
        "Как жить в своём плюсе": (
            "Жить в своём плюсе — значит наполнять энергией то, что приглушено, и не "
            "перегорать там, где силы через край. Твоя карта центров: "
            + "; ".join(f"{n} — {lv(n)}" for n in ch)
            + ". Маленькие ежедневные опоры — режим, забота о теле, честность с собой — "
            "возвращают тебя к ресурсу надёжнее любых рывков."
        ),
        "Напутствие лично тебе": (
            f"{nm}, эта книга — про тебя настоящего. В ней собрано то, что обычно "
            "прячется за повседневностью: твоя природа, твоя сила и твои задачи. У тебя "
            "есть всё, чтобы прожить свою жизнь глубоко и честно. Возвращайся к этим "
            "страницам, когда нужно вспомнить, кто ты и куда идёшь."
        ),
    }


def _specs(profile: HVDProfile) -> list[SectionSpec]:
    ya, my = profile.reactivity_ya, profile.reactivity_my
    leadership = (
        "ярко выраженное «Я», лидер, который вовлекает других в свои задачи"
        if ya >= 80
        else "сбалансированное «Я и Мы» — умеет и вести, и быть в команде"
        if ya >= 55
        else "мягкое «Я», человек команды, которому важно «мы»"
    )
    fbk = _clean_fallbacks(profile, leadership)

    periods_facts = "\n".join(
        f"- {p.age_range}: тема «{p.theme}» — {p.description}" for p in profile.life_periods
    )
    periods_course = "".join(
        _course(period_digit_course_text(d), 500)
        for d in dict.fromkeys(p.digit for p in profile.life_periods)
    )

    specs = [
        SectionSpec(
            title="С чего начинается эта книга",
            brief=(
                "Вступление к книге. Объясни простыми, тёплыми словами, что такое ХВД "
                "(хронально-векторная диагностика): это не гадание, а карта личности, "
                "собранная по дате рождения — темперамент, характер, мышление, энергия, "
                "задачи. Объясни, как читать эту книгу и почему она именно про него. "
                "Создай ощущение, что человек открывает книгу про самого себя."
            ),
            facts=(
                f"Это личная книга для: {profile.name}.\n"
                "Метод ХВД раскрывает: кармическую типологию, три контура "
                "(тело/характер/мышление), энергию семи центров, баланс инь/ян, "
                "путь по возрастам и задачи души." + _course(intro_course_text(), 900)
            ),
            words="220–300",
            fallback="",
        ),
        SectionSpec(
            title="Твоя кармическая типология",
            brief=(
                "Сначала объясни, ЧТО такое кармическая типология в методе ХВД, ЗАЧЕМ "
                "она и КАК определяется (по сумме цифр даты рождения, сводится к одному "
                "числу-архетипу). Потом — подробно и лично: что эта типология значит "
                "именно для него, его главный жизненный урок, сила и ловушка типа."
            ),
            facts=(
                f"Его кармическая типология — число {profile.typology}.\n"
                f"Суть типологии: {profile.typology_hint}"
                + _course(typology_course_text(profile.typology), 1200)
            ),
            words="260–340",
            fallback="",
        ),
        SectionSpec(
            title="Твоё тело и темперамент",
            brief=(
                "Объясни, что такое физический контур и темперамент в ХВД и за что "
                "отвечают центры Муладхара (опора, тело, безопасность) и Свадхистана "
                "(эмоции, удовольствие, чувственность). Потом — лично про него: его "
                "природная энергия, выносливость, чувственность, реакция на стресс, "
                "какой ритм жизни ему подходит."
            ),
            facts=(
                f"Тип темперамента: {profile.physical.label}\n"
                + _chakra_facts(profile, ("Муладхара", "Свадхистана"))
                + f"\nВнутренняя устойчивость («могу»): {_lvl(profile.can_pct)}"
                + _course(contour_course_text(profile.physical.label), 700)
            ),
            words="260–340",
            fallback="",
        ),
        SectionSpec(
            title="Твой характер и сердце",
            brief=(
                "Объясни, что такое эмоциональный контур и за что отвечают Манипура "
                "(воля, самооценка, деньги, власть) и Анахата (любовь, принятие, "
                "сострадание). Потом — лично: его воля и самооценка, отношение к деньгам "
                "и власти, способность любить и принимать, как ведёт себя в близких "
                "отношениях и в конфликте. Теневую сторону подавай бережно."
            ),
            facts=(
                f"Тип характера: {profile.emotional.label}\n"
                + _chakra_facts(profile, ("Манипура", "Анахата"))
                + f"\nЭгоизм/альтруизм: {profile.reactivity}. {profile.egoism_note}\n"
                f"Позиция: {leadership}"
                + _course(contour_course_text(profile.emotional.label), 700)
            ),
            words="260–340",
            fallback="",
        ),
        SectionSpec(
            title="Как ты думаешь",
            brief=(
                "Объясни, что такое интеллектуальный контур и за что отвечают Вишудха "
                "(речь, самовыражение, правда) и Аджна (интуиция, видение, анализ). "
                "Потом — лично: его стиль мышления, речь, как принимает решения, баланс "
                "логики и интуиции, где сила ума, где ловушки."
            ),
            facts=(
                f"Тип мышления: {profile.intellectual.label}\n"
                + _chakra_facts(profile, ("Вишудха", "Аджна"))
                + f"\n{profile.sahasrara_hint}\n"
                f"Вербальный интеллект {_lvl(int(profile.verbal_intellect))}; "
                f"невербальный {_lvl(int(profile.nonverbal_intellect))}."
                + _course(contour_course_text(profile.intellectual.label), 600)
            ),
            words="240–320",
            fallback="",
        ),
        SectionSpec(
            title="Карта твоей энергии: семь центров",
            brief=(
                "Объясни простыми словами, что такое чакры (энергоцентры) в методе ХВД и "
                "почему важен их баланс: где-то энергии много (сила и риск перегруза), "
                "где-то мало (зона роста). Пройди по всем центрам человека: что у него "
                "сильно, что приглушено, и что это значит в реальной жизни."
            ),
            facts=(
                "Энергия его центров:\n"
                + "\n".join(f"- {n} ({CHAKRA_MEANING.get(n,'')}): {_lvl(p)}" for n, p in _ch(profile).items())
                + _course(chakras_course_text(), 900)
            ),
            words="280–360",
            fallback="",
        ),
        SectionSpec(
            title="Чего ты хочешь и что можешь",
            brief=(
                "Объясни баланс инь/ян в ХВД (инь — восприятие, накопление; ян — "
                "действие, отдача) и что такое разрыв между «хочу» и «могу», а также "
                "позиция «Я/Мы». Потом — лично: как ему наполнять энергию, чтобы желания "
                "доходили до результата. Про чувственность — тактично, по-взрослому."
            ),
            facts=(
                f"Инь (восприятие): {'преобладает' if profile.yin_pct>profile.yang_pct else 'в меру'}; "
                f"Ян (действие): {'преобладает' if profile.yang_pct>=profile.yin_pct else 'в меру'}.\n"
                f"Разрыв «хочу/могу»: {'заметный — желания крупнее текущего ресурса' if profile.want>20 else 'небольшой — желания и возможности близки'}.\n"
                f"Опора на действие («могу»): {_lvl(profile.can_pct)}.\n"
                f"Позиция «Я/Мы»: {leadership}."
                + _course(yinyang_course_text(), 700)
            ),
            words="240–320",
            fallback="",
        ),
        SectionSpec(
            title="Твой путь по возрастам",
            brief=(
                "Объясни, что в ХВД жизнь раскрывается по периодам-возрастам, и у каждого "
                "своя тема и урок. Потом проведи человека по его периодам как по главам "
                "истории: что важно прожить в каждом и не пропустить. Свяжи в единую "
                "линию судьбы — прошлое, настоящее, будущее."
            ),
            facts=periods_facts + periods_course,
            words="300–380",
            fallback="",
        ),
        SectionSpec(
            title="Задачи твоей души: прошлое, настоящее, род",
            brief=(
                "Объясни понятие задач души в ХВД: задача из прошлого (что уже наработано "
                "и что осталось доделать), задача настоящего (главный урок этой жизни), "
                "родовая задача и задача от родителей. По каждой — что это значит и как "
                "проявляется у него. Сведи в понятное предназначение: куда ведёт эта жизнь."
            ),
            facts=(
                f"Задача из прошлого: {profile.task_past_hint}\n"
                f"Задача настоящего: {profile.task_present_hint}\n"
                f"Родовая задача: {profile.task_lineage_hint}\n"
                f"Задача от родителей: {profile.task_parents_hint}"
                + _course(task_course_text(profile.task_present), 700)
            ),
            words="280–360",
            fallback="",
        ),
        SectionSpec(
            title="Как жить в своём плюсе",
            brief=(
                "Практичная тёплая глава. По данным об энергии центров дай конкретные, "
                "выполнимые опоры на каждый день: что развивать там, где энергии мало, и "
                "как не перегорать там, где её через край. Привычки, ритм, забота о себе."
            ),
            facts=(
                "Энергия по центрам (что развивать, что разгружать):\n"
                + "\n".join(f"- {n}: {_lvl(p)}" for n, p in _ch(profile).items())
                + _course(chakras_course_text(), 600)
            ),
            words="280–360",
            fallback="",
        ),
        SectionSpec(
            title="Напутствие лично тебе",
            brief=(
                "Тёплое личное обращение-послесловие к человеку: собери воедино, какой он "
                "уникальный, в чём его сила и предназначение, и поддержи на пути. "
                "Вдохновляюще, искренне, как письмо близкого человека. 1–2 абзаца."
            ),
            facts=(
                f"Типология: {profile.typology_hint}. Темперамент: {profile.physical.label}. "
                f"Характер: {profile.emotional.label}. Главный урок жизни: {profile.task_present_hint}."
            ),
            words="160–220",
            fallback=(
                f"{profile.name}, эта книга — про тебя настоящего. В ней собрано то, что "
                "обычно прячется за повседневностью: твоя природа, твоя сила и твои "
                "задачи. Ты человек, у которого есть всё, чтобы прожить свою жизнь "
                "глубоко и честно. Возвращайся к этим страницам, когда нужно вспомнить, "
                "кто ты и куда идёшь. Пусть знание о себе станет твоей опорой и теплом."
            ),
        ),
    ]
    for s in specs:
        clean = fbk.get(s.title)
        if clean:
            s.fallback = clean
    return specs


def _passport(profile: HVDProfile) -> str:
    ch = _ch(profile)
    bars = " · ".join(f"{n} {p}%" for n, p in ch.items())
    return (
        "<b>📋 Твой паспорт ХВД</b> (для тех, кто любит точные данные)\n\n"
        f"Кармическая типология: <b>{profile.typology}</b>\n"
        f"Темперамент: {profile.physical.label}\n"
        f"Характер: {profile.emotional.label}\n"
        f"Мышление: {profile.intellectual.label}\n"
        f"Энергия центров: {bars}\n"
        f"Инь {profile.yin_pct}% · Ян {profile.yang_pct}% · "
        f"Я/Мы {profile.reactivity_ya}%/{profile.reactivity_my}%\n\n"
        "<i>ХВД по методике Жажкова–Солодкова. Продукт отдельный от Премиум. "
        "Не заменяет медицинскую консультацию.</i>"
    )


_TITLE_EMOJI = {
    "С чего начинается эта книга": "📖",
    "Твоя кармическая типология": "🔑",
    "Твоё тело и темперамент": "⚡",
    "Твой характер и сердце": "💗",
    "Как ты думаешь": "🧠",
    "Карта твоей энергии: семь центров": "🌈",
    "Чего ты хочешь и что можешь": "⚖️",
    "Твой путь по возрастам": "📅",
    "Задачи твоей души: прошлое, настоящее, род": "🎯",
    "Как жить в своём плюсе": "🌿",
    "Напутствие лично тебе": "💌",
}


def _to_html(body: str) -> str:
    out = []
    for ln in body.splitlines():
        s = ln.rstrip()
        if s.startswith("## "):
            out.append(f"<b>{html.escape(s[3:].strip())}</b>")
        else:
            out.append(html.escape(s))
    return "\n".join(out)


def _clean_fallback(text: str) -> str:
    """Шаблонный фолбэк — это HTML с эмодзи. Чистим для книги/PDF."""
    from oracle_bot.book_writer import _clean

    text = re.sub(r"<br\s*/?>", "\n", text or "")
    text = re.sub(r"</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return _clean(text).strip()


async def build_hvd_book(profile: HVDProfile) -> list[Section]:
    specs = _specs(profile)
    bodies = await write_sections(profile.name, specs, concurrency=2)
    sections: list[Section] = []
    for spec, body in zip(specs, bodies):
        body = (body or "").strip()
        if not body:
            body = _clean_fallback(spec.fallback)
        if not body:
            continue
        sections.append(Section(title=spec.title, body=body))
    return sections


def render_tg_parts(profile: HVDProfile, sections: list[Section]) -> list[str]:
    """Telegram-части из готовых разделов книги (+ паспорт). Фолбэк — шаблон."""
    if not sections:
        return build_report_parts(profile)

    bd = profile.birth.strftime("%d.%m.%Y")
    parts: list[str] = [
        f"📖 <b>ХВД — твоя личная книга</b>\n"
        f"👤 {html.escape(profile.name)} · {bd}\n\n"
        f"<i>Это написано лично про тебя — читай не спеша.</i>"
    ]
    for sec in sections:
        emoji = _TITLE_EMOJI.get(sec.title, "•")
        header = f"{emoji} <b>{html.escape(sec.title)}</b>\n\n"
        body_html = _to_html(sec.body)
        chunk = header + body_html
        if len(chunk) <= _TG_LIMIT:
            parts.append(chunk)
        else:
            start = 0
            first = True
            while start < len(body_html):
                piece = body_html[start : start + _TG_LIMIT - len(header)]
                parts.append((header if first else "") + piece)
                first = False
                start += _TG_LIMIT - len(header)
    parts.append(_passport(profile))
    return parts


async def build_report_parts_async(profile: HVDProfile) -> list[str]:
    """Совместимость: сгенерировать книгу и отрендерить Telegram-части."""
    try:
        sections = await build_hvd_book(profile)
    except Exception as e:  # noqa: BLE001
        logger.warning("hvd book failed, fallback to template: %s", e)
        sections = []
    return render_tg_parts(profile, sections)


def _passport_plain(profile: HVDProfile) -> str:
    ch = _ch(profile)
    return (
        "Эта страница — для тех, кто любит точные данные метода.\n\n"
        f"Кармическая типология: {profile.typology}.\n"
        f"Темперамент: {profile.physical.label}.\n"
        f"Характер: {profile.emotional.label}.\n"
        f"Мышление: {profile.intellectual.label}.\n"
        "Энергия центров: " + ", ".join(f"{n} {p}%" for n, p in ch.items()) + ".\n"
        f"Инь {profile.yin_pct}% · Ян {profile.yang_pct}% · "
        f"Я/Мы {profile.reactivity_ya}%/{profile.reactivity_my}%.\n\n"
        "ХВД по методике Жажкова–Солодкова. Продукт отдельный от Премиум. "
        "Не заменяет медицинскую консультацию."
    )


def book_for_pdf(profile: HVDProfile, sections: list[Section]) -> str:
    """Богатая книга для PDF: кодированные главы (обложка + главы + паспорт)."""
    from oracle_bot.book_pdf import encode_book

    chapters: list[tuple[str, str]] = [(s.title, s.body) for s in sections]
    chapters.append(("Паспорт ХВД", _passport_plain(profile)))
    return encode_book(
        title="ХВД",
        subtitle="Личная книга-разбор по дате рождения",
        author_line=f"{profile.name} · {profile.birth.strftime('%d.%m.%Y')}",
        chapters=chapters,
    )


def book_plain_text(profile: HVDProfile, sections: list[Section]) -> str:
    """Чистый текст книги для follow-up-контекста (без маркеров кодировки)."""
    out = [f"ХВД — личная книга. {profile.name} · {profile.birth.strftime('%d.%m.%Y')}"]
    for sec in sections:
        out.append(f"{sec.title}\n{sec.body}")
    out.append("Паспорт ХВД\n" + _passport_plain(profile))
    return "\n\n".join(out)
