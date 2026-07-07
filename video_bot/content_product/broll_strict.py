"""Жёсткий шаблон B-roll: только медиа по теме, без оффтопа."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicTemplate:
    """Промпт-шаблон темы: разрешённые запросы + фильтры."""

    key: str
    pexels_queries: list[str]
    required_in_url: tuple[str, ...] = ()
    forbidden_in_url: tuple[str, ...] = (
        "mall",
        "shopping",
        "store",
        "fashion",
        "runway",
        "crowd",
        "concert",
        "stadium",
        "beach",
        "wedding",
        "gym",
        "fitness",
    )
    forbidden_in_query: tuple[str, ...] = (
        "person",
        "people",
        "woman",
        "man",
        "portrait",
        "happy",
        "smile",
        "factory production",  # часто не то
        "designer measuring",
        "booking online",
        "smartphone booking",
    )


TOPIC_TEMPLATES: dict[str, TopicTemplate] = {
    "stretch_ceiling": TopicTemplate(
        key="stretch_ceiling",
        pexels_queries=[
            "ceiling spotlights living room interior",
            "modern ceiling lights apartment",
            "recessed ceiling lights interior",
            "white ceiling interior design",
            "kitchen ceiling spotlights modern",
            "bathroom ceiling lights modern",
            "led ceiling lights room",
            "interior ceiling lamp modern",
            "apartment ceiling renovation interior",
            "living room ceiling light fixture",
        ],
        required_in_url=(),
        forbidden_in_url=(
            "mall",
            "shopping",
            "store",
            "street",
            "city",
            "traffic",
            "office worker",
            "meeting",
            "hospital",
            "school",
            "restaurant",
            "cafe",
            "car",
            "road",
            "forest",
            "beach",
        ),
        forbidden_in_query=(
            "renovation completion happy",
            "factory",
            "designer measuring",
            "unfinished room",
            "old ceiling cracks",
            "smartphone",
            "booking",
        ),
    ),
    "chernobyl": TopicTemplate(
        key="chernobyl",
        pexels_queries=[],  # только Wikimedia
        forbidden_in_url=("stock", "business", "office"),
    ),
}


def queries_for_scene(topic_key: str, scene_query: str, scene_id: int, cut_idx: int) -> list[str]:
    tpl = TOPIC_TEMPLATES.get(topic_key)
    if not tpl or not tpl.pexels_queries:
        return [scene_query]
    base = tpl.pexels_queries
    i = (scene_id * 3 + cut_idx) % len(base)
    # 3 разных запроса из пула темы
    return [base[i], base[(i + 1) % len(base)], base[(i + 2) % len(base)]]


def query_allowed(topic_key: str, query: str) -> bool:
    tpl = TOPIC_TEMPLATES.get(topic_key)
    if not tpl:
        return True
    q = query.lower()
    return not any(b in q for b in tpl.forbidden_in_query)


def video_meta_allowed(topic_key: str, video: dict) -> bool:
    tpl = TOPIC_TEMPLATES.get(topic_key)
    if not tpl:
        return True
    url_l = (video.get("url") or "").lower()
    if tpl.forbidden_in_url and any(x in url_l for x in tpl.forbidden_in_url):
        return False
    if tpl.required_in_url and not any(x in url_l for x in tpl.required_in_url):
        # мягко: не блокируем, если required пуст
        pass
    return True
