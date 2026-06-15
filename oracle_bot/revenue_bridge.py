"""Мост Оракул → Центр доходов: каталог, матчинг, новые идеи."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Модули бота → slug идеи / внутренний продукт
MODULE_PRODUCTS: dict[str, list[str]] = {
    "horo_today": ["oracle-platform"],
    "horo_week": ["oracle-platform"],
    "natal": ["oracle-platform"],
    "past_life": ["oracle-platform"],
    "karma": ["oracle-platform"],
    "akashic": ["oracle-platform"],
    "tarot": ["oracle-platform"],
    "lenormand": ["oracle-platform"],
    "compat": ["oracle-platform"],
    "twin_flame": ["oracle-platform"],
    "dating": ["oracle-platform"],
    "palm": ["oracle-platform"],
    "dream": ["oracle-platform"],
    "shadow": ["oracle-platform"],
    "career": ["biz-plan-budget", "review-reply-bot", "wb-card-bot", "biz-automation-matcher"],
    "numerology": ["oracle-platform"],
    "biorhythm": ["oracle-platform"],
    "moon": ["oracle-platform"],
    "yesno": ["oracle-platform"],
    "family_karma": ["oracle-platform"],
}

PAIN_RULES: list[tuple[list[str], list[str]]] = [
    (["любов", "отношен", "расстал", "одинок", "парн", "измен", "бросил"], ["oracle-platform", "twin_flame"]),
    (["деньг", "долг", "кредит", "ипотек", "банкр", "бедн", "заработ"], ["credit-card-cpa", "biz-plan-budget", "ozon-affiliate"]),
    (["работ", "уволь", "карьер", "началь", "офис", "зарплат"], ["review-reply-bot", "wb-card-bot", "biz-automation-matcher"]),
    (["wb", "wildberries", "ozon", "маркетплейс", "селлер", "карточк"], ["wb-card-bot", "review-reply-bot", "ozon-affiliate"]),
    (["осаг", "страхов", "полис", "дтп"], ["osago-cpa"]),
    (["дач", "хозблок", "баня", "теплиц", "участ"], ["shed-kit-sales", "english-greenhouse", "shed-estimate-bot"]),
    (["пдд", "права", "гибдд", "экзамен"], ["pdd-premium-bot"]),
    (["самозанят", "чек", "налог", "ип ", "ооо"], ["selfemployed-receipt-bot", "yandex-distribution"]),
    (["реклам", "директ", "трафик", "клиент"], ["yandex-distribution", "service-seo-funnel"]),
    (["род", "семь", "мама", "отец", "родител"], ["family_karma", "oracle-platform"]),
    (["здоров", "болит", "врач", "диагн"], []),  # gap → новая идея
    (["юрист", "суд", "развод", "наслед"], []),
]

ORACLE_INTERNAL = [
    {
        "slug": "oracle-premium",
        "title": "⭐ Премиум Оракул 30 дней",
        "pitch": "Безлимит всех гаданий и полные чтения без 🔒",
        "action": "mod:premium",
        "status": "running",
    },
    {
        "slug": "oracle-deep",
        "title": "🔓 Продолжение чтения",
        "pitch": "Открыть скрытую часть последнего прогноза",
        "action": "deep:last",
        "status": "running",
    },
]


def _slugify(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"oracle-gap-{digest}"


def load_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(ORACLE_INTERNAL)
    try:
        from business_dashboard.storage import init_db, list_ideas

        init_db()
        for idea in list_ideas():
            items.append(
                {
                    "slug": idea["slug"],
                    "title": idea["title"],
                    "pitch": (idea.get("note") or idea.get("potential_rub") or "")[:120],
                    "action": f"idea:{idea['slug']}",
                    "status": idea.get("status", "needs_action"),
                    "category": idea.get("category", ""),
                }
            )
    except Exception as e:
        logger.warning("catalog load: %s", e)
    return items


def rule_match(text: str, module: str) -> list[dict[str, Any]]:
    catalog = {i["slug"]: i for i in load_catalog()}
    slugs: list[str] = list(MODULE_PRODUCTS.get(module, ["oracle-platform"]))
    blob = (text or "").lower()
    for keys, products in PAIN_RULES:
        if any(k in blob for k in keys):
            slugs.extend(products)
    # unique preserve order
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for s in slugs:
        if s in seen:
            continue
        seen.add(s)
        if s in catalog:
            out.append(catalog[s])
        elif s == "twin_flame":
            out.append(
                {
                    "slug": "twin_flame",
                    "title": "🔥 Родственная душа",
                    "pitch": "Разбор связи и следующий шаг",
                    "action": "mod:twin_flame",
                    "status": "running",
                }
            )
        elif s == "family_karma":
            out.append(
                {
                    "slug": "family_karma",
                    "title": "🧬 Родовая карма",
                    "pitch": "Повторы рода и освобождение",
                    "action": "mod:family_karma",
                    "status": "running",
                }
            )
    return out[:3]


def register_gap(
    *,
    user_id: int,
    pain_summary: str,
    proposal: str,
    module: str = "",
    automation: str = "manual",
) -> str:
    """Новая идея в opportunities + blocker если нужен человек."""
    slug = _slugify(pain_summary)
    from business_dashboard.storage import _connect, _now_iso, add_blocker, init_db

    now = _now_iso()
    stage = "proposed" if automation == "auto" else "needs_user"
    try:
        init_db()
        with _connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM opportunities WHERE slug = ?", (slug,)
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO opportunities (
                        slug, query_text, source, volume_score, monetization_score,
                        solution_type, proposal, pipeline_stage, expected_daily_rub,
                        linked_idea_slug, created_at, updated_at
                    ) VALUES (?, ?, 'oracle_bot', 70, 75, 'bot', ?, ?, 200, NULL, ?, ?)
                    """,
                    (
                        slug,
                        pain_summary[:200],
                        f"Запрос из @MOracul_bot (user {user_id}, модуль {module or '—'}).\n{proposal}",
                        stage,
                        now,
                        now,
                    ),
                )
        if automation != "auto":
            add_blocker(
                f"💡 Оракул: новая идея «{pain_summary[:80]}» — проверить в дашборде",
                slug=slug,
                blocker_type="oracle_idea",
            )
        return slug
    except Exception as e:
        logger.exception("register_gap: %s", e)
        return ""


async def notify_admins(bot, text: str) -> None:
    try:
        from business_dashboard.config import MONEY_ADMIN_IDS
        from oracle_bot.config import ORACLE_BOT_USERNAME

        ids = MONEY_ADMIN_IDS or set()
        if not ids:
            return
        footer = (
            f"\n\n📬 Это сообщение от бота <b>@{ORACLE_BOT_USERNAME}</b>.\n"
            f"📊 Идеи: открой <code>/money</code> в основном боте или "
            f"дашборд http://127.0.0.1:8765 → блок «Разведка»"
        )
        for aid in ids:
            try:
                await bot.send_message(aid, text + footer, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                logger.warning("admin notify %s: %s", aid, e)
    except Exception as e:
        logger.warning("notify_admins: %s", e)
