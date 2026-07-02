"""Отчёты по кампании продаж книг (ХВД/Ultra): прогноз перед стартом и итог за день.

- Прогноз считается по реальной аудитории (охват, прошлая конверсия) и честно
  даёт диапазон, а не красивую цифру.
- Итоговый отчёт вечером: сколько продано по каждому продукту, выручка, как
  сработала воронка отработки возражений, что учесть завтра.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from oracle_bot import storage as db

logger = logging.getLogger(__name__)

_BOOK_KINDS = ("exclusive_hvd", "ultra_plus", "premium_30d")
_KIND_LABEL = {
    "exclusive_hvd": "🔮 ХВД",
    "ultra_plus": "📖 Книга о тебе (Ultra)",
    "premium_30d": "⭐ Премиум 30д",
    "pdf_hvd": "📄 ХВД в PDF",
    "pdf_reading": "📄 Разбор в PDF",
    "deep_unlock": "🔓 Продолжение",
}
_MSK = timezone(timedelta(hours=3))


def _today_msk() -> str:
    return datetime.now(_MSK).date().isoformat()


def _reachable_audience() -> int:
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM user_meta WHERE push_opt_out = 0 OR push_opt_out IS NULL"
        ).fetchone()
    return int(row[0] or 0)


def _historical_conversion() -> tuple[int, int, float]:
    """(всего плативших, всего пользователей, конверсия %) — по всей истории."""
    with db._connect() as conn:
        payers = conn.execute("SELECT COUNT(DISTINCT user_id) FROM payments").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    payers = int(payers or 0)
    users = int(users or 0)
    conv = (payers / users * 100.0) if users else 0.0
    return payers, users, conv


def forecast_report(variant: str = "combo") -> str:
    """Прогноз продаж на день перед запуском рассылки. Честный диапазон + обоснование."""
    audience = _reachable_audience()
    payers, users, conv = _historical_conversion()

    # Открываемость рассылки: по факту push_open/push_sent высок, но охват вялый (низкий DAU).
    # Берём осторожную вилку открытий за день.
    open_lo, open_hi = int(audience * 0.30), int(audience * 0.55)
    # Клик по продукту из открывших: премиум-цена → узкая вершина.
    click_lo, click_hi = int(open_hi * 0.10), int(open_hi * 0.25)
    # Покупка в день старта (импульс + первый шаг воронки). Первый в истории показ
    # платных книг холодной аудитории — конверсия низкая и честная.
    buy_lo, buy_hi = 0, max(1, int(click_hi * 0.30))
    # Воронка возражений добивает −50%/даунсейлом в течение ~2 суток (эффект позже).
    funnel_extra_lo, funnel_extra_hi = 0, max(1, buy_hi)

    from oracle_bot.config import (
        ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
        ORACLE_PREMIUM_PRICE_RUB,
        ORACLE_ULTRA_PLUS_PRICE_RUB,
    )

    # Средний чек: смесь ХВД (599) и редкой Ultra (1499), часть уйдёт в даунсейл/премиум.
    avg_check = int((ORACLE_EXCLUSIVE_HVD_PRICE_RUB + ORACLE_PREMIUM_PRICE_RUB) / 2)
    rev_lo = buy_lo * avg_check
    rev_hi = buy_hi * ORACLE_ULTRA_PLUS_PRICE_RUB

    return (
        "📈 <b>ПРОГНОЗ ПРОДАЖ НА ДЕНЬ</b> (кампания книг ХВД/Ultra)\n"
        f"Дата: {_today_msk()} · вариант рассылки: <b>{variant}</b>\n\n"
        "<b>Аудитория и на чём основан расчёт:</b>\n"
        f"• Достижимая база (не отписаны): <b>{audience}</b> чел.\n"
        f"• Историческая конверсия в оплату: <b>{conv:.1f}%</b> ({payers} плативших из {users}).\n"
        f"• Платные книги (599–1499₽) этой базе раньше <b>не продавали</b> — это первый показ, "
        "поэтому прогноз осторожный.\n\n"
        "<b>Воронка на сегодня (диапазон):</b>\n"
        f"• Откроют рассылку: ~{open_lo}–{open_hi}\n"
        f"• Кликнут по продукту: ~{click_lo}–{click_hi}\n"
        f"• Купят в день старта: <b>{buy_lo}–{buy_hi}</b>\n"
        f"• Добьёт воронка возражений (−50%/даунсейл, +1–2 суток): ещё <b>{funnel_extra_lo}–{funnel_extra_hi}</b>\n\n"
        f"💰 <b>Выручка в день старта: ~{rev_lo}–{rev_hi}₽</b>\n\n"
        "<b>Почему так, а не «десятки продаж»:</b>\n"
        "— база маленькая (десятки, не тысячи) и «холодная» к платным продуктам;\n"
        "— средний онлайн низкий (DAU единицы), часть увидит рассылку только завтра;\n"
        "— чек высокий для аудитории бесплатного таро — решение не импульсивное.\n\n"
        "<b>Что усилит результат:</b> персональные крючки по дате рождения, "
        "воронка возражений с −50%, и повтор показа тем, кто открыл, но не купил. "
        "Вечером пришлю факт и разбор."
    )


def sales_report() -> str:
    """Итог за день: продажи по продуктам, выручка, работа воронки, выводы."""
    today = _today_msk()
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT kind, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS rub
            FROM payments
            WHERE substr(created_at, 1, 10) = ? AND currency = 'RUB'
            GROUP BY kind
            """,
            (today,),
        ).fetchall()
        ad_sent = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'books_ad_sent' AND substr(created_at,1,10)=?",
            (today,),
        ).fetchone()[0]
        obj_rows = conn.execute(
            """
            SELECT payload, COUNT(*) FROM events
            WHERE event_type = 'click' AND payload LIKE 'obj:%' AND substr(created_at,1,10)=?
            GROUP BY payload
            """,
            (today,),
        ).fetchall()

    sales = {r["kind"]: (int(r["cnt"]), int(r["rub"])) for r in rows}
    total_cnt = sum(c for c, _ in sales.values())
    total_rub = sum(r for _, r in sales.values())

    lines = [
        "🧾 <b>ИТОГ ДНЯ: продажи книг ХВД/Ultra</b>",
        f"Дата: {today}\n",
        f"📤 Рассылка доставлена: <b>{int(ad_sent)}</b> чел.",
        f"🛒 Продаж всего: <b>{total_cnt}</b> · выручка <b>{total_rub}₽</b>\n",
    ]
    if sales:
        lines.append("<b>По продуктам:</b>")
        for kind, (cnt, rub) in sorted(sales.items(), key=lambda x: -x[1][1]):
            lines.append(f"• {_KIND_LABEL.get(kind, kind)}: {cnt} шт · {rub}₽")
        lines.append("")
    else:
        lines.append("Оплат сегодня не было.\n")

    # Как отработала воронка возражений (реакции на первый вопрос)
    reasons = {"price": 0, "fit": 0, "later": 0, "bought": 0}
    for payload, cnt in obj_rows:
        # payload вида obj:price:exclusive_hvd
        parts = str(payload).split(":")
        if len(parts) >= 2 and parts[1] in reasons:
            reasons[parts[1]] += int(cnt)
    if any(reasons.values()):
        lines.append("<b>Воронка возражений (реакции):</b>")
        lines.append(
            f"• «дорого» {reasons['price']} · «не моё» {reasons['fit']} · "
            f"«подумаю» {reasons['later']} · «уже купил» {reasons['bought']}"
        )
        lines.append("")

    # Выводы
    lines.append("<b>Что учесть завтра:</b>")
    if total_cnt == 0 and int(ad_sent) > 0:
        lines.append(
            "— В день старта покупок нет: воронка возражений добьёт −50%/даунсейлом "
            "в ближайшие 1–2 суток. Если и дальше 0 — снизить входной чек или начать "
            "с ХВД (599₽), а Ultra предлагать как апселл."
        )
    elif total_rub and int(ad_sent):
        lines.append(
            f"— Конверсия рассылки в оплату: {total_cnt / int(ad_sent) * 100:.1f}%. "
            "Повторить показ тем, кто открыл, но не купил; усилить крючки по дате рождения."
        )
    if reasons["price"] > reasons["fit"]:
        lines.append("— Основное возражение — цена. Двигать акцент на рассрочку смыслом: «−50% лично тебе».")
    elif reasons["fit"] > 0:
        lines.append("— Есть сомнения «моё ли это» — усилить персонализацию оффера (имя, дата, черты).")
    return "\n".join(lines)


async def send_forecast(bot, variant: str = "combo") -> None:
    from oracle_bot.admin_notify import notify_admins

    await notify_admins(bot, forecast_report(variant), skip_footer=True)


async def send_sales_report(bot) -> None:
    from oracle_bot.admin_notify import notify_admins

    await notify_admins(bot, sales_report(), skip_footer=True)


async def books_report_worker(bot, *, hour_msk: int = 22) -> None:
    """Раз в сутки в ~hour_msk МСК — итог продаж книг за день (устойчиво к рестартам)."""
    import asyncio

    last_sent: str | None = None
    while True:
        try:
            now = datetime.now(_MSK)
            today = now.date().isoformat()
            if now.hour == hour_msk and last_sent != today:
                await send_sales_report(bot)
                last_sent = today
                logger.info("books sales report sent %s", today)
        except Exception:
            logger.exception("books_report_worker")
        await asyncio.sleep(300)
