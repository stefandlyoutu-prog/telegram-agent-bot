"""Канал и ожидаемый дневной доход по slug."""

from __future__ import annotations

# online — только комп/разовые действия; physical — время в реальной жизни; meta — инфраструктура
IDEA_CHANNEL: dict[str, str] = {
    "shed-kit-sales": "physical",
    "english-greenhouse": "physical",
    "agent-deal-network": "physical",
    "life-spheres-matrix": "meta",
    "spending-intelligence": "meta",
}

# ₽/день при активном продвижении (реалистичная цель на старте)
IDEA_EXPECTED_DAILY_RUB: dict[str, float] = {
    "oracle-platform": 350,
    "dacha-astro-bot": 150,
    "pdd-premium-bot": 200,
    "music-track-promo": 100,
    "biz-automation-matcher": 500,
    "referral-hub": 0,
    "yandex-browser-partner": 200,
    "yandex-distribution": 300,
    "yandex-eda-courier": 0,
    "ozon-affiliate": 250,
    "osago-cpa": 400,
    "credit-card-cpa": 300,
    "cpa-micro-tasks": 150,
    "shed-estimate-bot": 200,
    "shed-kit-sales": 0,
    "english-greenhouse": 0,
    "content-factory": 150,
    "service-seo-funnel": 200,
    "watch-earn-platform": 100,
    "wb-card-bot": 300,
    "review-reply-bot": 250,
    "selfemployed-receipt-bot": 200,
    "tg-b2b-bots": 400,
    "greeting-video": 300,
    "lead-exchange": 500,
    "agent-deal-network": 0,
    "avito-free-scanner": 100,
    "biz-plan-budget": 200,
}


def channel_for(slug: str) -> str:
    return IDEA_CHANNEL.get(slug, "online")


def expected_daily_for(slug: str) -> float:
    return float(IDEA_EXPECTED_DAILY_RUB.get(slug, 100))
