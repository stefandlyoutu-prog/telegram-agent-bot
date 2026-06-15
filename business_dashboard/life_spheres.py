"""12 сфер жизни — матрица «сфера × бизнес-идеи»."""

from __future__ import annotations

from typing import Any, Dict, List

# slug идей из registry привязаны к сферам
LIFE_SPHERES: List[Dict[str, Any]] = [
    {
        "id": "health",
        "title": "Здоровье",
        "emoji": "🫀",
        "business_angle": "боты привычек, добавки affiliate, запись к врачу",
        "idea_slugs": ["oracle-platform"],
    },
    {
        "id": "career",
        "title": "Карьера",
        "emoji": "💼",
        "business_angle": "B2B-автоматизация, фриланс-боты, биржа лидов",
        "idea_slugs": ["biz-automation-matcher", "lead-exchange", "agent-deal-network", "tg-b2b-bots"],
    },
    {
        "id": "money",
        "title": "Деньги",
        "emoji": "💰",
        "business_angle": "рефералки, CPA, дашборд доходов",
        "idea_slugs": [
            "referral-hub", "yandex-browser-partner", "ozon-affiliate",
            "credit-card-cpa", "cpa-micro-tasks",
        ],
    },
    {
        "id": "family",
        "title": "Семья",
        "emoji": "👨‍👩‍👧",
        "business_angle": "детские боты, семейный бюджет, подборки Ozon",
        "idea_slugs": ["pdd-premium-bot", "greeting-video"],
    },
    {
        "id": "love",
        "title": "Любовь",
        "emoji": "❤️",
        "business_angle": "совместимость, пикап-модуль, поздравления",
        "idea_slugs": ["oracle-platform", "greeting-video"],
    },
    {
        "id": "friends",
        "title": "Друзья",
        "emoji": "🤝",
        "business_angle": "вирусный контент, мемы, реферал «приведи друга»",
        "idea_slugs": ["content-factory", "service-seo-funnel"],
    },
    {
        "id": "growth",
        "title": "Развитие",
        "emoji": "📚",
        "business_angle": "ПДД, курсы, подбор бизнеса под бюджет",
        "idea_slugs": ["pdd-premium-bot", "biz-plan-budget", "spending-intelligence"],
    },
    {
        "id": "fun",
        "title": "Отдых",
        "emoji": "🎮",
        "business_angle": "гадания, игры, музыка, rewarded-контент",
        "idea_slugs": ["oracle-platform", "music-track-promo", "watch-earn-platform"],
    },
    {
        "id": "home",
        "title": "Дом и дача",
        "emoji": "🏡",
        "business_angle": "хозблок, теплица, сметы, Ozon affiliate",
        "idea_slugs": [
            "shed-kit-sales", "shed-estimate-bot", "english-greenhouse",
            "dacha-astro-bot", "avito-free-scanner",
        ],
    },
    {
        "id": "spirit",
        "title": "Смысл",
        "emoji": "✨",
        "business_angle": "эзотерика, астрология, хиромантия — подписка",
        "idea_slugs": ["oracle-platform", "dacha-astro-bot"],
    },
    {
        "id": "creativity",
        "title": "Творчество",
        "emoji": "🎵",
        "business_angle": "продвижение треков, видео-конвейер, AI-картинки",
        "idea_slugs": ["music-track-promo", "content-factory", "greeting-video"],
    },
    {
        "id": "impact",
        "title": "Польза людям",
        "emoji": "🌍",
        "business_angle": "помощь бизнесу, чеки СМЗ, ответы на отзывы",
        "idea_slugs": [
            "biz-automation-matcher", "review-reply-bot",
            "selfemployed-receipt-bot", "osago-cpa",
        ],
    },
]


def spheres_with_ideas(all_ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_slug = {i["slug"]: i for i in all_ideas}
    out = []
    for sp in LIFE_SPHERES:
        linked = [by_slug[s] for s in sp["idea_slugs"] if s in by_slug]
        out.append({**sp, "ideas": linked, "ideas_count": len(linked)})
    return out
