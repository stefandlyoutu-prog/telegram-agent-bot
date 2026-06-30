"""Акция «бесплатный день»: полный доступ + рассылка + отчёт в полночь МСК."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from oracle_bot import storage as db

logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))
FREE_DAY_KEY = "free_day_date"
BROADCAST_KEY_PREFIX = "free_day_broadcast_"
REPORT_SENT_PREFIX = "free_day_report_sent_"


def msk_today() -> str:
    return datetime.now(MSK).date().isoformat()


def msk_day_bounds(day: str) -> tuple[str, str]:
    d = date.fromisoformat(day)
    start = datetime(d.year, d.month, d.day, tzinfo=MSK)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).isoformat(),
        end.astimezone(timezone.utc).isoformat(),
    )


def get_free_day_date() -> str | None:
    return db.kv_get(FREE_DAY_KEY)


def is_free_day_active() -> bool:
    return get_free_day_date() == msk_today()


def activate_free_day_today() -> str:
    day = msk_today()
    db.kv_set(FREE_DAY_KEY, day)
    return day


def broadcast_message() -> str:
    return (
        "🎁 <b>Сегодня до конца дня — полный бесплатный доступ!</b>\n\n"
        "Все разделы без лимитов: таро, гороскоп, натальная карта и 25+ практик.\n\n"
        "Заходи и протестируй — жду тебя в боте 👇"
    )


def broadcast_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from oracle_bot.config import ORACLE_BOT_USERNAME

    username = ORACLE_BOT_USERNAME.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔮 Открыть бота",
                    url=f"https://t.me/{username}?start=free_day",
                )
            ]
        ]
    )


def _free_day_link(source: str = "") -> str:
    from oracle_bot.config import ORACLE_BOT_USERNAME

    username = ORACLE_BOT_USERNAME.lstrip("@")
    return f"https://t.me/{username}?start=free_day"


def channel_post(source: str = "") -> str:
    """Пост в канал: сегодня полный бесплатный доступ."""
    u = source.lstrip("@").lower()
    link = _free_day_link(u)
    cta = f'👉 <a href="{link}">Открыть @MOracul_bot бесплатно</a>'
    if u == "signsvishe":
        return (
            "✨ <b>Сегодня — полный доступ для всех</b>\n\n"
            "До конца дня в @MOracul_bot <b>без лимитов</b>: "
            "Таро, гороскоп, сонник, совместимость, натальная — "
            "всё открыто, тестируй сколько хочешь.\n\n"
            f"{cta}"
        )
    if u == "auragirlss":
        return (
            "💫 <b>Сегодня всё бесплатно в боте</b>\n\n"
            "Чакры, совместимость, сонник, Таро, ладонь — "
            "<b>до конца дня без ограничений</b> в @MOracul_bot. "
            "Заходи и проверь на себе.\n\n"
            f"{cta}"
        )
    return (
        "🎁 <b>Сегодня до конца дня — полный бесплатный доступ!</b>\n\n"
        "В @MOracul_bot открыты <b>все разделы без лимитов</b>: "
        "Таро, гороскоп на сегодня, совместимость, натальная карта и 25+ практик.\n\n"
        "Заходи и протестируй — акция только сегодня.\n\n"
        f"{cta}"
    )


async def post_to_admin_channels(bot) -> list[dict[str, Any]]:
    """Пост во все каналы из ORACLE_PROMO_CHANNELS, где бот может писать."""
    from oracle_bot.broadcast import post_to_channels
    from oracle_bot.config import ORACLE_PROMO_CHANNELS

    channels = [c.strip().lstrip("@") for c in ORACLE_PROMO_CHANNELS if c.strip()]
    if not channels:
        return []
    posts = [channel_post(ch) for ch in channels]
    results = await post_to_channels(bot, posts, channels)
    day = get_free_day_date() or msk_today()
    db.kv_set(
        f"free_day_channels_{day}",
        json.dumps(results, ensure_ascii=False),
    )
    db.log_event(None, "free_day_channels", json.dumps(results)[:500])
    logger.info("free day channel posts %s: %s", day, results)
    return results


def track_visit(user_id: int, start_args: str = "") -> None:
    if not is_free_day_active():
        return
    db.log_event(user_id, "free_day_open", (start_args or "")[:120])


def _broadcast_stats(day: str) -> dict[str, Any]:
    raw = db.kv_get(f"{BROADCAST_KEY_PREFIX}{day}")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def metrics_for_day(day: str) -> dict[str, Any]:
    start_utc, end_utc = msk_day_bounds(day)
    broadcast = _broadcast_stats(day)
    with db._connect() as conn:
        dau = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        opens = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'free_day_open' AND created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        opens_from_broadcast = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'free_day_open' AND created_at >= ? AND created_at < ?
            AND payload LIKE 'free_day%'
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        readings = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'reading' AND created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        readers = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'reading' AND created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        new_users = conn.execute(
            """
            SELECT COUNT(*) FROM users
            WHERE created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        returns = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE event_type = 'return_visit' AND created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        limit_hits = conn.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE event_type = 'limit_hit' AND created_at >= ? AND created_at < ?
            """,
            (start_utc, end_utc),
        ).fetchone()[0]
        top_modules = conn.execute(
            """
            SELECT substr(payload, 1, instr(payload || ':', ':') - 1) AS mod, COUNT(*) AS c
            FROM events
            WHERE event_type = 'reading' AND created_at >= ? AND created_at < ?
            GROUP BY mod ORDER BY c DESC LIMIT 5
            """,
            (start_utc, end_utc),
        ).fetchall()
    return {
        "day": day,
        "broadcast": broadcast,
        "dau": int(dau),
        "opens": int(opens),
        "opens_from_broadcast": int(opens_from_broadcast),
        "readings": int(readings),
        "readers": int(readers),
        "new_users": int(new_users),
        "returns": int(returns),
        "limit_hits": int(limit_hits),
        "top_modules": [{"module": r[0], "count": int(r[1])} for r in top_modules],
    }


def format_campaign_report(day: str) -> str:
    m = metrics_for_day(day)
    b = m.get("broadcast") or {}
    total = int(b.get("total") or 0)
    ok = int(b.get("ok") or 0)
    fail = int(b.get("fail") or 0)
    try:
        day_label = date.fromisoformat(day).strftime("%d.%m.%Y")
    except ValueError:
        day_label = day
    mod_lines = "\n".join(
        f"  • {r['module']}: {r['count']}" for r in (m.get("top_modules") or [])
    ) or "  • пока нет"
    open_rate = int(100 * m["opens"] / ok) if ok else 0
    read_rate = int(100 * m["readers"] / m["opens"]) if m["opens"] else 0
    return (
        f"🌙 <b>Оракул — отчёт «бесплатный день» за {day_label}</b>\n\n"
        f"📤 <b>Рассылка</b>\n"
        f"  Отправлено: <b>{ok}</b> из {total} (ошибок: {fail})\n\n"
        f"👥 <b>Активность</b>\n"
        f"  Зашли в бота (события): <b>{m['dau']}</b>\n"
        f"  Открыли по акции: <b>{m['opens']}</b> "
        f"(из рассылки: {m['opens_from_broadcast']}, {open_rate}% от доставленных)\n"
        f"  Вернувшиеся: {m['returns']}\n"
        f"  🆕 Новых: <b>{m['new_users']}</b>\n\n"
        f"🔮 <b>Чтения</b>\n"
        f"  Почитали (уник.): <b>{m['readers']}</b> ({read_rate}% от зашедших)\n"
        f"  Чтений всего: <b>{m['readings']}</b>\n"
        f"  Уперлись в лимит: {m['limit_hits']}\n"
        f"  <b>Топ разделов:</b>\n{mod_lines}\n\n"
        f"📈 /stats · /funnel"
    )


async def run_broadcast(bot) -> dict[str, Any]:
    from oracle_bot.broadcast import broadcast_text

    day = activate_free_day_today()
    result = await broadcast_text(
        bot,
        broadcast_message(),
        reply_markup=broadcast_keyboard(),
    )
    payload = {**result, "day": day, "at": datetime.now(timezone.utc).isoformat()}
    db.kv_set(f"{BROADCAST_KEY_PREFIX}{day}", json.dumps(payload, ensure_ascii=False))
    db.log_event(None, "free_day_broadcast", json.dumps(result)[:500])
    logger.info("free day broadcast %s: %s", day, result)
    return payload


async def send_campaign_report(bot, day: str) -> None:
    from oracle_bot.admin_notify import admin_ids, notify_admins

    if not admin_ids():
        logger.warning("free day report: ORACLE_ADMIN_IDS пуст")
        return
    text = format_campaign_report(day)
    await notify_admins(bot, text, skip_footer=True)
    logger.info("free day report sent for %s", day)


async def free_day_report_worker(bot, *, hour_msk: int = 0) -> None:
    """В полночь МСК — отчёт за вчерашний бесплатный день."""
    import asyncio

    while True:
        try:
            now = datetime.now(MSK)
            yesterday = (now.date() - timedelta(days=1)).isoformat()
            if now.hour == hour_msk and get_free_day_date() == yesterday:
                sent_key = f"{REPORT_SENT_PREFIX}{yesterday}"
                if db.kv_get(sent_key) != "1":
                    await send_campaign_report(bot, yesterday)
                    db.kv_set(sent_key, "1")
        except Exception:
            logger.exception("free_day_report_worker")
        await asyncio.sleep(300)
