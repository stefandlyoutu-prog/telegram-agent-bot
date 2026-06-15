"""Telegram-команды /money — управление Центром доходов с телефона."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


from business_dashboard.config import MONEY_ADMIN_IDS


def _ensure_db() -> None:
    from business_dashboard.storage import init_db, rollover_day_if_needed

    init_db()
    rollover_day_if_needed()


def _money_allowed(user_id) -> bool:
    if not MONEY_ADMIN_IDS:
        return True
    if user_id is None:
        return False
    return user_id in MONEY_ADMIN_IDS


@router.message(Command("money"))
async def cmd_money(message: Message) -> None:
    if not _money_allowed(message.from_user.id if message.from_user else None):
        await message.answer("Нет доступа к /money")
        return
    _ensure_db()
    from business_dashboard.daily import close_day_report, get_money_metrics, get_today_plan
    from business_dashboard.storage import list_blockers, list_ideas, list_user_assets

    args = (message.text or "").split(maxsplit=1)
    sub = args[1].strip().lower() if len(args) > 1 else ""

    if sub.startswith("+"):
        # /money +500 oracle-platform
        parts = sub[1:].split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: /money +500 slug-идеи")
            return
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            await message.answer("Сумма должна быть числом")
            return
        if amount <= 0:
            await message.answer("Сумма должна быть больше 0")
            return
        slug = parts[1].strip()
        from business_dashboard.storage import add_revenue

        row = add_revenue(slug, amount, note="telegram", source="telegram")
        if not row:
            await message.answer(f"Идея «{slug}» не найдена")
            return
        await message.answer(f"✅ +{amount:.0f} ₽ → {row['title']}")
        return

    if sub.startswith("plan "):
        slug = sub[5:].strip()
        from business_dashboard.daily import add_to_today_plan

        if add_to_today_plan(slug):
            await message.answer(f"📋 В план на сегодня: {slug}")
        else:
            await message.answer("Уже в плане или slug не найден")
        return

    if sub == "report":
        report = close_day_report(note="из Telegram")
        text = (
            f"📊 <b>Отчёт {report['report_date']}</b>\n\n"
            f"План: {report['expected_total']:.0f} ₽\n"
            f"Факт: {report['actual_total']:.0f} ₽\n"
            f"Разрыв: {report['gap_rub']:.0f} ₽\n\n"
            f"<b>Почему:</b>\n{report['gap_reason']}\n\n"
            f"<b>Изменить:</b>\n{report['suggestions']}"
        )
        await message.answer(text[:4000], parse_mode="HTML")
        return

    if sub == "online":
        ideas = [i for i in list_ideas() if i.get("channel") == "online" and i["status"] == "needs_action"]
        lines = [f"🌐 <b>Онлайн — запустить первыми</b>\n"]
        for i in sorted(ideas, key=lambda x: -(x.get("expected_daily_rub") or 0))[:8]:
            lines.append(f"• {i['title'][:50]} — ~{i.get('expected_daily_rub', 0):.0f} ₽/день")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    if sub == "assets":
        assets = list_user_assets()
        lines = ["🔑 <b>Сделал один раз:</b>"]
        for a in assets:
            mark = "✅" if a.get("done") else "⬜"
            lines.append(f"{mark} {a['label']}")
        lines.append("\nОтметь в дашборде — подтянется во все проекты.")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    if sub == "scout":
        from business_dashboard.idea_scout import list_opportunities

        opps = list_opportunities()[:6]
        lines = ["🔍 <b>Тренды → решения:</b>"]
        for o in opps:
            if o["pipeline_stage"] in ("launched", "rejected"):
                continue
            lines.append(f"• {o['query_text'][:40]} — {o.get('expected_daily_rub', 0):.0f} ₽/д")
        await message.answer("\n".join(lines) or "Пусто", parse_mode="HTML")
        return

    m = get_money_metrics()
    plan = get_today_plan()
    blockers = list_blockers(open_only=True)[:5]

    lines = [
        "💰 <b>Центр доходов</b>",
        f"План: {m['target_today']:.0f} ₽ · Факт: {m['actual_today']:.0f} ₽ · Разрыв: {m['gap']:.0f} ₽",
        f"Потенциал онлайн: {m['potential_if_launch_online']:.0f} ₽",
        "",
    ]
    if plan:
        lines.append("<b>План на сегодня:</b>")
        for p in plan:
            lines.append(f"  • {p.get('title', p['slug'])} — {p.get('expected_rub', 0):.0f} ₽")
    else:
        lines.append("План пуст — /money plan slug-идеи")

    if blockers:
        lines.append("\n<b>Нужно от вас:</b>")
        for b in blockers:
            lines.append(f"  ⚠️ {b['description'][:100]}")

    lines.append("\n/money online · /money plan slug · /money +500 slug · /money report")
    lines.append("/money assets · /money scout")
    await message.answer("\n".join(lines), parse_mode="HTML")
