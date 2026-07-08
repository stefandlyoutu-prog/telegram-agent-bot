"""Отчёты по кампании продаж книг (ХВД/Ultra): прогноз перед стартом и итог за день.

- Прогноз считается по реальной аудитории (охват, прошлая конверсия) и честно
  даёт диапазон, а не красивую цифру.
- Итоговый отчёт вечером: сколько продано по каждому продукту, выручка, как
  сработала воронка отработки возражений, что учесть завтра.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oracle_bot import storage as db

logger = logging.getLogger(__name__)

_LAST_SENT_FILE = Path(__file__).resolve().parents[1] / "data" / "oracle_last_books_report.txt"


def _last_sent_date() -> str | None:
    try:
        if _LAST_SENT_FILE.exists():
            return _LAST_SENT_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def _mark_sent(today: str) -> None:
    try:
        _LAST_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_SENT_FILE.write_text(today, encoding="utf-8")
    except OSError:
        pass

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


def _web_stats_block(today: str) -> list[str]:
    """Посещения сайта и клики по кнопкам за день."""
    from datetime import timedelta

    week = (date.today() - timedelta(days=7)).isoformat()
    with db._connect() as conn:
        visits_today = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='web_visit' AND substr(created_at,1,10)=?",
            (today,),
        ).fetchone()[0]
        visits_week = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='web_visit' AND substr(created_at,1,10)>=?",
            (week,),
        ).fetchone()[0]
        actions_today = conn.execute(
            """
            SELECT payload, COUNT(*) AS c FROM events
            WHERE event_type='web_action' AND substr(created_at,1,10)=?
            GROUP BY payload ORDER BY c DESC LIMIT 8
            """,
            (today,),
        ).fetchall()
        by_path = conn.execute(
            """
            SELECT payload AS path, COUNT(*) AS c FROM events
            WHERE event_type='web_visit' AND substr(created_at,1,10)=?
            GROUP BY payload ORDER BY c DESC
            """,
            (today,),
        ).fetchall()
    lines = [
        "<b>🌐 Сайт moracul.ru (сегодня):</b>",
        f"• Просмотры страниц: <b>{int(visits_today)}</b> (за 7д: {int(visits_week)})",
    ]
    if by_path:
        lines.append(
            "• Страницы: "
            + " · ".join(f"{r['path']} {r['c']}" for r in by_path)
        )
    if actions_today:
        lines.append("• Переходы/клики:")
        for r in actions_today:
            lines.append(f"  — {r['payload']}: {r['c']}")
    else:
        lines.append("• Переходы в бота с сайта: пока нет кликов")
    lines.append("")
    return lines


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

    # Как отработала воронка возражений (реакции на первый вопрос).
    # Считаем и явные реакции (клики), и сам факт запуска лестницы за день.
    reasons = {"price": 0, "fit": 0, "later": 0, "bought": 0}
    for payload, cnt in obj_rows:
        # payload вида obj:price:exclusive_hvd
        parts = str(payload).split(":")
        if len(parts) >= 2 and parts[1] in reasons:
            reasons[parts[1]] += int(cnt)
    obj_reactions = sum(reasons.values())

    with db._connect() as conn:
        obj_pushes = conn.execute(
            """
            SELECT COUNT(*) FROM push_queue
            WHERE push_type LIKE 'obj_%' AND sent_at IS NOT NULL
              AND substr(sent_at, 1, 10) = ?
            """,
            (today,),
        ).fetchone()[0]

    lines.append("<b>Воронка возражений:</b>")
    if obj_reactions or obj_pushes:
        lines.append(
            f"• Отправлено дожимов: {int(obj_pushes)} · получено ответов: {obj_reactions}"
        )
        if obj_reactions:
            lines.append(
                f"• «дорого» {reasons['price']} · «не моё» {reasons['fit']} · "
                f"«подумаю» {reasons['later']} · «уже купил» {reasons['bought']}"
            )
    else:
        lines.append("• Не запускалась — сегодня не было рассылки оффера книг.")
    lines.append("")

    # Выводы — блок всегда содержательный, даже при полном нуле.
    lines.append("<b>Что учесть завтра:</b>")
    if int(ad_sent) == 0:
        lines.append(
            "— Сегодня рассылка оффера книг НЕ отправлялась (0 доставок), поэтому продаж и "
            "возражений закономерно нет. Реклама в каналах — это другой канал (новые подписчики), "
            "а книги продаются рассылкой по базе бота."
        )
        lines.append(
            "— Действие: запустить рассылку варианта «entry» (вход 99₽) по активной базе — "
            "это включит и воронку возражений автоматически."
        )
    elif total_cnt == 0:
        lines.append(
            "— Рассылка ушла, но покупок в день старта нет: воронка возражений добьёт "
            "−50%/даунсейлом в ближайшие 1–2 суток. Если и дальше 0 — снизить входной чек "
            "или начать с ХВД (599₽), Ultra предлагать апселлом."
        )
    else:
        lines.append(
            f"— Конверсия рассылки в оплату: {total_cnt / int(ad_sent) * 100:.1f}%. "
            "Повторить показ тем, кто открыл, но не купил; усилить крючки по дате рождения."
        )
    if reasons["price"] > reasons["fit"] and reasons["price"]:
        lines.append("— Главное возражение — цена. Акцент на «−50% лично тебе» и рассрочку смыслом.")
    elif reasons["fit"] > 0:
        lines.append("— Сомнения «моё ли это» — усилить персонализацию оффера (имя, дата, черты).")
    lines.extend(_web_stats_block(today))
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

    while True:
        try:
            now = datetime.now(_MSK)
            today = now.date().isoformat()
            if now.hour == hour_msk and _last_sent_date() != today:
                await send_sales_report(bot)
                _mark_sent(today)
                logger.info("books sales report sent %s", today)
        except Exception:
            logger.exception("books_report_worker")
        await asyncio.sleep(300)
