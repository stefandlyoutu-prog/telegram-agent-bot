"""Один раз сделал — используется во всех проектах."""

from __future__ import annotations

from typing import Any, Dict, List

# Ключи активов пользователя (без паролей — только флаги «готово»)
ASSET_CATALOG: List[Dict[str, Any]] = [
    {"key": "email", "label": "Рабочая почта", "hint": "Для регистраций на всех площадках"},
    {"key": "samozanyatost", "label": "Самозанятость (Мой налог)", "hint": "Вывод с партнёрок, Ozon, Stars"},
    {"key": "yandex_partner", "label": "Яндекс Партнёр / Дистрибуция", "hint": "Браузер, Директ, Еда"},
    {"key": "ozon_blogger", "label": "Ozon Blogger", "hint": "Affiliate подборки"},
    {"key": "botfather", "label": "Telegram BotFather (аккаунт)", "hint": "Все TG-боты"},
    {"key": "telegram_stars", "label": "Telegram Stars / оплата в боте", "hint": "Подписки Оракул, ПДД"},
    {"key": "vk_ads", "label": "VK Реклама / сообщество", "hint": "Продвижение треков, ботов"},
    {"key": "youtube_channel", "label": "YouTube-канал", "hint": "Shorts, музыка, воронки"},
    {"key": "tiktok_account", "label": "TikTok", "hint": "Контент-конвейер"},
    {"key": "leadgid_cpa", "label": "CPA-сеть (Leadgid / Admitad)", "hint": "ОСАГО, банки"},
    {"key": "yukassa", "label": "ЮKassa / приём платежей", "hint": "B2B боты, SaaS"},
]

# Какие активы нужны проекту (остальное — деплой/код, без вас)
IDEA_ASSET_REQUIRES: Dict[str, List[str]] = {
    "yandex-browser-partner": ["email", "samozanyatost", "yandex_partner"],
    "yandex-distribution": ["email", "samozanyatost", "yandex_partner"],
    "yandex-eda-courier": ["email", "yandex_partner"],
    "ozon-affiliate": ["email", "samozanyatost", "ozon_blogger"],
    "osago-cpa": ["email", "samozanyatost", "leadgid_cpa"],
    "credit-card-cpa": ["email", "samozanyatost", "leadgid_cpa"],
    "oracle-platform": ["botfather", "telegram_stars"],
    "dacha-astro-bot": ["botfather", "telegram_stars"],
    "pdd-premium-bot": ["botfather", "telegram_stars"],
    "music-track-promo": ["vk_ads", "youtube_channel", "tiktok_account"],
    "content-factory": ["youtube_channel", "tiktok_account"],
    "wb-card-bot": ["botfather", "samozanyatost", "yukassa"],
    "review-reply-bot": ["botfather", "samozanyatost", "yukassa"],
    "selfemployed-receipt-bot": ["botfather", "samozanyatost"],
    "shed-estimate-bot": ["botfather", "ozon_blogger"],
    "biz-automation-matcher": ["botfather", "yukassa"],
    "watch-earn-platform": ["botfather", "yukassa"],
    "referral-hub": ["email", "samozanyatost"],
}

# Триггеры в action_required → ключ актива
ACTION_ASSET_HINTS: Dict[str, str] = {
    "самозанят": "samozanyatost",
    "botfather": "botfather",
    "stars": "telegram_stars",
    "ozon blogger": "ozon_blogger",
    "distribution.yandex": "yandex_partner",
    "partner.browser": "yandex_partner",
    "leadgid": "leadgid_cpa",
    "admitad": "leadgid_cpa",
    "юkassa": "yukassa",
    "yukassa": "yukassa",
    "youtube": "youtube_channel",
    "tiktok": "tiktok_account",
    "polis812": "leadgid_cpa",
    "pampadu": "leadgid_cpa",
}


def assets_for_idea(slug: str) -> List[str]:
    return IDEA_ASSET_REQUIRES.get(slug, [])


def missing_assets(slug: str, done_keys: set[str]) -> List[Dict[str, Any]]:
    catalog = {a["key"]: a for a in ASSET_CATALOG}
    return [catalog[k] for k in assets_for_idea(slug) if k not in done_keys and k in catalog]


def effective_action_required(slug: str, raw: str, done_keys: set[str]) -> str:
    """Убирает из шага то, что уже закрыто активами."""
    missing = missing_assets(slug, done_keys)
    if not missing:
        base = raw or ""
        if base:
            return base + " · Аккаунты готовы — остался деплой/код"
        return "Аккаунты готовы — остался деплой/код (без вас)"
    labels = ", ".join(m["label"] for m in missing)
    return f"Нужно один раз: {labels}"
