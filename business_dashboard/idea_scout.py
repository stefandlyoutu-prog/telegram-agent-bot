"""Разведка идей: тренды → монетизация → решение → запуск."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from business_dashboard.storage import _connect, _now_iso, _row_to_dict

# Стартовые тренды (позже: Wordstat API, Google Trends, TG-чаты)
SEED_TRENDS: List[Dict[str, Any]] = [
    {
        "slug": "scout-compat-birth",
        "query": "совместимость по дате рождения",
        "source": "поиск",
        "volume": 85,
        "intent": "развлечение",
        "solution_type": "bot",
        "monetization": "подписка Stars 199 ₽",
        "expected_daily_rub": 400,
    },
    {
        "slug": "scout-shed-estimate",
        "query": "смета на хозблок / баню",
        "source": "авито",
        "volume": 72,
        "intent": "покупка",
        "solution_type": "bot",
        "monetization": "affiliate Ozon + PDF",
        "expected_daily_rub": 350,
    },
    {
        "slug": "scout-wb-reviews",
        "query": "ответы на отзывы wildberries",
        "source": "селлеры",
        "volume": 68,
        "intent": "боль бизнеса",
        "solution_type": "bot",
        "monetization": "490 ₽ / 100 ответов",
        "expected_daily_rub": 500,
    },
    {
        "slug": "scout-selfemployed-check",
        "query": "чек самозанятого онлайн",
        "source": "поиск",
        "volume": 60,
        "intent": "рутина",
        "solution_type": "bot",
        "monetization": "49 ₽ / чек",
        "expected_daily_rub": 250,
    },
    {
        "slug": "scout-pdd-exam",
        "query": "пдд экзамен онлайн бесплатно",
        "source": "поиск",
        "volume": 90,
        "intent": "обучение",
        "solution_type": "bot",
        "monetization": "Premium 199 ₽/мес",
        "expected_daily_rub": 300,
    },
    {
        "slug": "scout-osago-compare",
        "query": "осаго онлайн сравнить цены",
        "source": "поиск",
        "volume": 78,
        "intent": "страхование",
        "solution_type": "site",
        "monetization": "CPA 500–2000 ₽",
        "expected_daily_rub": 600,
    },
    {
        "slug": "scout-ozon-card-ai",
        "query": "карточка товара для ozon нейросеть",
        "source": "селлеры",
        "volume": 75,
        "intent": "боль бизнеса",
        "solution_type": "bot",
        "monetization": "59–299 ₽ / карточка",
        "expected_daily_rub": 450,
    },
    {
        "slug": "scout-tarot-telegram",
        "query": "гадание на картах таро телеграм",
        "source": "telegram",
        "volume": 88,
        "intent": "развлечение",
        "solution_type": "bot",
        "monetization": "Stars подписка",
        "expected_daily_rub": 500,
    },
]

SOLUTION_LABELS = {"bot": "Telegram-бот", "site": "Сайт / лендинг", "chat": "Онлайн-чат", "referral": "Рефералка/CPA"}


def _slugify_query(q: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    import hashlib
    digest = hashlib.sha256(q.encode("utf-8")).hexdigest()[:12]
    return f"scout-{digest}"


def _migrate_opportunity_slugs(conn) -> None:
    """Перенос старых кириллических slug на латиницу по query_text."""
    for t in SEED_TRENDS:
        slug = _slugify_query(t["query"], t.get("slug", ""))
        row = conn.execute(
            "SELECT slug FROM opportunities WHERE query_text = ?", (t["query"],)
        ).fetchone()
        if not row:
            continue
        old = row["slug"]
        if old == slug:
            continue
        linked = conn.execute(
            "SELECT slug FROM ideas WHERE slug = ?", (old,)
        ).fetchone()
        if linked:
            conn.execute("UPDATE ideas SET slug = ? WHERE slug = ?", (slug, old))
        conn.execute(
            "UPDATE opportunities SET slug = ?, linked_idea_slug = COALESCE(linked_idea_slug, ?) WHERE query_text = ?",
            (slug, slug if linked else None, t["query"]),
        )


def init_opportunities(conn=None) -> None:
    now = _now_iso()
    own = conn is None
    if own:
        conn = _connect()
    try:
        _migrate_opportunity_slugs(conn)
        for t in SEED_TRENDS:
            slug = _slugify_query(t["query"], t.get("slug", ""))
            exists = conn.execute("SELECT 1 FROM opportunities WHERE slug = ?", (slug,)).fetchone()
            if exists:
                continue
            score = int(t["volume"] * 0.6 + min(t.get("expected_daily_rub", 0) / 10, 40))
            proposal = (
                f"Запрос: «{t['query']}» ({t['source']}, спрос {t['volume']}/100).\n"
                f"Решение: {SOLUTION_LABELS.get(t['solution_type'], t['solution_type'])}.\n"
                f"Монетизация: {t['monetization']}.\n"
                f"Ожидание: ~{t.get('expected_daily_rub', 0):.0f} ₽/день при запуске."
            )
            conn.execute(
                """
                INSERT INTO opportunities (
                    slug, query_text, source, volume_score, monetization_score,
                    solution_type, proposal, pipeline_stage, expected_daily_rub,
                    linked_idea_slug, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, NULL, ?, ?)
                """,
                (
                    slug,
                    t["query"],
                    t["source"],
                    t["volume"],
                    score,
                    t["solution_type"],
                    proposal,
                    t.get("expected_daily_rub", 100),
                    now,
                    now,
                ),
            )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def list_opportunities(stage: Optional[str] = None) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if stage:
            rows = conn.execute(
                "SELECT * FROM opportunities WHERE pipeline_stage = ? ORDER BY monetization_score DESC",
                (stage,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM opportunities ORDER BY monetization_score DESC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_pipeline_summary() -> Dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT pipeline_stage, COUNT(*) AS c FROM opportunities GROUP BY pipeline_stage"
        ).fetchall()
    counts = {r["pipeline_stage"]: r["c"] for r in rows}
    return {
        "scout": counts.get("scout", 0),
        "scored": counts.get("scored", 0),
        "proposed": counts.get("proposed", 0),
        "needs_user": counts.get("needs_user", 0),
        "launching": counts.get("launching", 0),
        "launched": counts.get("launched", 0),
        "rejected": counts.get("rejected", 0),
        "total": sum(counts.values()),
    }


def scan_new_trends() -> int:
    """Seed + живые подсказки Google/Yandex."""
    from business_dashboard.config import TREND_SEED_QUERIES
    from business_dashboard.trend_fetcher import fetch_live_trends

    before = len(list_opportunities())
    init_opportunities()
    live = fetch_live_trends(list(TREND_SEED_QUERIES))
    now = _now_iso()
    with _connect() as conn:
        for t in live:
            exists = conn.execute(
                "SELECT 1 FROM opportunities WHERE query_text = ? OR slug = ?",
                (t["query"], t["slug"]),
            ).fetchone()
            if exists:
                continue
            score = int(t["volume"] * 0.5 + min(t.get("expected_daily_rub", 0) / 12, 35))
            proposal = (
                f"Запрос: «{t['query']}» (источник: {t['source']}).\n"
                f"Решение: {SOLUTION_LABELS.get(t['solution_type'], t['solution_type'])}.\n"
                f"Ожидание: ~{t.get('expected_daily_rub', 0):.0f} ₽/день."
            )
            conn.execute(
                """
                INSERT INTO opportunities (
                    slug, query_text, source, volume_score, monetization_score,
                    solution_type, proposal, pipeline_stage, expected_daily_rub,
                    linked_idea_slug, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'scout', ?, NULL, ?, ?)
                """,
                (
                    t["slug"],
                    t["query"],
                    t["source"],
                    t["volume"],
                    score,
                    t["solution_type"],
                    proposal,
                    t.get("expected_daily_rub", 100),
                    now,
                    now,
                ),
            )
    return len(list_opportunities()) - before


def update_opportunity_stage(slug: str, stage: str) -> Optional[Dict[str, Any]]:
    allowed = ("scout", "scored", "proposed", "needs_user", "launching", "launched", "rejected")
    if stage not in allowed:
        return None
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "UPDATE opportunities SET pipeline_stage = ?, updated_at = ? WHERE slug = ?",
            (stage, now, slug),
        )
        row = conn.execute("SELECT * FROM opportunities WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def launch_opportunity(opp_slug: str) -> Optional[Dict[str, Any]]:
    """Переводит тренд в реестр идей (needs_action) и связывает."""
    now = _now_iso()
    with _connect() as conn:
        opp = conn.execute("SELECT * FROM opportunities WHERE slug = ?", (opp_slug,)).fetchone()
        if not opp:
            return None
        idea_slug = opp_slug if len(opp_slug) <= 60 else opp_slug[:60]
        title = f"🔍 {opp['query_text']} ({SOLUTION_LABELS.get(opp['solution_type'], 'решение')})"
        exists = conn.execute("SELECT 1 FROM ideas WHERE slug = ?", (idea_slug,)).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO ideas (
                    slug, title, category, cluster, tier, channel, status,
                    action_required, potential_rub, automation_pct, expected_daily_rub,
                    revenue_today, revenue_month, note, last_event_at, created_at, updated_at
                ) VALUES (?, ?, 'разведка', 'data', 'strong', 'online', 'needs_action',
                    ?, ?, 90, ?, 0, 0, ?, NULL, ?, ?)
                """,
                (
                    idea_slug,
                    title,
                    f"Из тренда «{opp['query_text']}». {opp['proposal'][:200]}",
                    opp["proposal"].split("\n")[-1] if opp["proposal"] else "",
                    float(opp["expected_daily_rub"] or 100),
                    f"Авто из разведки. Источник: {opp['source']}",
                    now,
                    now,
                ),
            )
        conn.execute(
            """
            UPDATE opportunities SET pipeline_stage = 'needs_user', linked_idea_slug = ?, updated_at = ?
            WHERE slug = ?
            """,
            (idea_slug, now, opp_slug),
        )
        row = conn.execute("SELECT * FROM opportunities WHERE slug = ?", (opp_slug,)).fetchone()
    return _row_to_dict(row) if row else None
