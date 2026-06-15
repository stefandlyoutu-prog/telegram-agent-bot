"""Дневной цикл: план → работа → отчёт в полночь."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from business_dashboard.storage import (
    _connect,
    _now_iso,
    _row_to_dict,
    list_ideas,
    list_blockers,
)


def _today_str() -> str:
    return date.today().isoformat()


def get_today_plan() -> List[Dict[str, Any]]:
    d = _today_str()
    ideas = {i["slug"]: i for i in list_ideas()}
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.*, i.title, i.channel, i.status
            FROM daily_plan p
            JOIN ideas i ON i.slug = p.slug
            WHERE p.plan_date = ?
            ORDER BY p.sort_order, p.id
            """,
            (d,),
        ).fetchall()
    out = []
    for r in rows:
        item = _row_to_dict(r)
        idea = ideas.get(item["slug"], {})
        item["revenue_today"] = idea.get("revenue_today", 0)
        out.append(item)
    return out


def set_today_plan(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """items: [{slug, expected_rub?, promotion?}]"""
    d = _today_str()
    now = _now_iso()
    with _connect() as conn:
        conn.execute("DELETE FROM daily_plan WHERE plan_date = ?", (d,))
        for i, item in enumerate(items):
            conn.execute(
                """
                INSERT INTO daily_plan (plan_date, slug, expected_rub, promotion, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    d,
                    item["slug"],
                    float(item.get("expected_rub", 0)),
                    item.get("promotion", ""),
                    i,
                    now,
                ),
            )
    return get_today_plan()


def add_to_today_plan(slug: str, expected_rub: Optional[float] = None, promotion: str = "") -> bool:
    from business_dashboard.channels import expected_daily_for
    from business_dashboard.storage import add_blocker

    d = _today_str()
    now = _now_iso()
    with _connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM daily_plan WHERE plan_date = ? AND slug = ?", (d, slug)
        ).fetchone()
        if exists:
            return False
        row = conn.execute(
            "SELECT expected_daily_rub, action_required, title FROM ideas WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            return False
        exp = expected_rub if expected_rub is not None else (row["expected_daily_rub"] or expected_daily_for(slug))
        n = conn.execute("SELECT COUNT(*) FROM daily_plan WHERE plan_date = ?", (d,)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO daily_plan (plan_date, slug, expected_rub, promotion, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (d, slug, float(exp), promotion, n, now),
        )
        action = (row["action_required"] or "").strip()
        need_blocker = action and any(
            w in action.lower() for w in ("регистр", "botfather", "логин", "почт", "ип", "самозанят")
        )
    if need_blocker:
        with _connect() as conn:
            dup = conn.execute(
                "SELECT 1 FROM user_blockers WHERE slug = ? AND done = 0 AND description = ?",
                (slug, action),
            ).fetchone()
        if not dup:
            add_blocker(action, slug=slug, blocker_type="setup")
    return True


def get_money_metrics() -> Dict[str, Any]:
    from business_dashboard.storage import actual_revenue_today

    ideas = list_ideas()
    plan = get_today_plan()
    blockers = [b for b in list_blockers() if not b.get("done")]

    actual_today = actual_revenue_today()
    planned_expected = sum(float(p.get("expected_rub") or 0) for p in plan)

    online_launch = [
        i for i in ideas
        if i.get("channel") == "online" and i.get("status") == "needs_action"
    ]
    online_running = [i for i in ideas if i.get("channel") == "online" and i.get("status") == "running"]
    physical_pending = [i for i in ideas if i.get("channel") == "physical" and i.get("status") != "running"]

    potential_if_launch = sum(float(i.get("expected_daily_rub") or 0) for i in online_launch[:5])
    running_expected = sum(float(i.get("expected_daily_rub") or 0) for i in online_running)

    target_today = planned_expected if plan else running_expected
    gap = target_today - actual_today

    return {
        "date": _today_str(),
        "actual_today": actual_today,
        "planned_expected": planned_expected,
        "target_today": target_today,
        "gap": gap,
        "potential_if_launch_online": potential_if_launch,
        "online_launch_count": len(online_launch),
        "online_running_count": len(online_running),
        "physical_pending_count": len(physical_pending),
        "blockers_open": len(blockers),
        "plan_items": len(plan),
        "met_target": actual_today >= target_today if target_today > 0 else None,
    }


def _analyze_gap(
    expected: float,
    actual: float,
    plan: List[Dict[str, Any]],
    blockers: List[Dict[str, Any]],
    ideas: List[Dict[str, Any]],
) -> tuple[str, str, str]:
    """gap_reason, suggestions, next_actions"""
    gap = expected - actual
    if expected <= 0:
        return (
            "План на день не задан — добавь проекты в «План на сегодня».",
            "Выбери 2–3 онлайн-проекта и укажи ожидаемый доход.",
            "Открыть дашборд → План на сегодня.",
        )

    reasons: List[str] = []
    suggestions: List[str] = []
    actions: List[str] = []

    if actual == 0:
        reasons.append("Доход не зафиксирован — возможно, не нажали «+ доход» или проекты не запущены.")

    open_blockers = [b for b in blockers if not b.get("done")]
    if open_blockers:
        reasons.append(
            "Блокеры от вас: " + "; ".join(b["description"][:80] for b in open_blockers[:5])
        )
        actions.extend(f"Выполнить: {b['description']}" for b in open_blockers[:3])

    not_running = [p for p in plan if p.get("status") != "running"]
    if not_running:
        reasons.append(f"Из плана не в статусе «онлайн»: {len(not_running)} шт.")
        suggestions.append("Перевести запланированные проекты в «Запустить» после деплоя.")

    under = []
    for p in plan:
        slug = p["slug"]
        idea = next((i for i in ideas if i["slug"] == slug), None)
        if not idea:
            continue
        exp = float(p.get("expected_rub") or 0)
        got = float(idea.get("revenue_today") or 0)
        if exp > 0 and got < exp * 0.5:
            under.append((idea["title"], exp, got))

    if under:
        reasons.append("Недобор по проектам: " + ", ".join(f"«{t}» ({int(g)}/{int(e)} ₽)" for t, e, g in under[:3]))
        suggestions.append("Усилить продвижение там, где указано в плане (promotion).")
        for p in plan:
            if p.get("promotion"):
                suggestions.append(f"«{p.get('title', p['slug'])}»: {p['promotion']}")

    if gap > 0 and not reasons:
        reasons.append("План был амбициозным для первого дня — нормально на старте.")

    if gap <= 0 and actual > 0:
        reasons.append("Цель достигнута или перевыполнена.")
        suggestions.append("Закрепить работающие каналы, масштабировать завтра.")

    if not suggestions:
        suggestions = [
            "Добавить 1 рефералку с быстрым CPA (Яндекс Браузер).",
            "Запустить контент-конвейер для музыки или Оракула.",
            "Снизить план на завтра на 30% и нарастить постепенно.",
        ]

    if not actions:
        actions = ["Обновить план на завтра в дашборде.", "Проверить блокеры и закрыть регистрации."]

    return (
        " ".join(reasons) if reasons else f"Разрыв {int(gap)} ₽ без явных блокеров.",
        "\n".join(f"• {s}" for s in suggestions[:6]),
        "\n".join(f"• {a}" for a in actions[:5]),
    )


def close_day_report(note: str = "") -> Dict[str, Any]:
    """Отчёт за сегодня (вызывать вручную или в 00:00)."""
    d = _today_str()
    ideas = list_ideas()
    plan = get_today_plan()
    blockers = list_blockers()
    metrics = get_money_metrics()
    expected = metrics["target_today"]
    actual = metrics["actual_today"]

    gap_reason, suggestions, next_actions = _analyze_gap(expected, actual, plan, blockers, ideas)
    if note:
        gap_reason += f" Заметка: {note}"

    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_reports (
                report_date, expected_total, actual_total, gap_rub,
                gap_reason, suggestions, next_actions, plan_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE SET
                expected_total = excluded.expected_total,
                actual_total = excluded.actual_total,
                gap_rub = excluded.gap_rub,
                gap_reason = excluded.gap_reason,
                suggestions = excluded.suggestions,
                next_actions = excluded.next_actions,
                created_at = excluded.created_at
            """,
            (
                d,
                expected,
                actual,
                expected - actual,
                gap_reason,
                suggestions,
                next_actions,
                str(len(plan)),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO daily_history (hist_date, expected_total, actual_total)
            VALUES (?, ?, ?)
            ON CONFLICT(hist_date) DO UPDATE SET
                expected_total = excluded.expected_total,
                actual_total = excluded.actual_total
            """,
            (d, expected, actual),
        )

    return get_report(d)


def get_report(report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    d = report_date or _today_str()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM daily_reports WHERE report_date = ?", (d,)).fetchone()
    return _row_to_dict(row) if row else None


def list_reports(limit: int = 14) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_reports ORDER BY report_date DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_chart_history(days: int = 7) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT hist_date, expected_total, actual_total
            FROM daily_history
            ORDER BY hist_date DESC LIMIT ?
            """,
            (days,),
        ).fetchall()
    return list(reversed([_row_to_dict(r) for r in rows]))
