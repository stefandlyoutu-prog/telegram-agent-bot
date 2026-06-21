"""Очередь постов в каналы прогрева + автопубликация."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from aiogram import Bot

from oracle_bot import storage as db
from oracle_bot.promo import build_week_plan

logger = logging.getLogger(__name__)


def seed_week_queue(
    *,
    start_day: date | None = None,
    days: int = 7,
    replace_pending: bool = True,
) -> dict:
    """Заполняет очередь на неделю: 5 постов/день × каналы."""
    start = start_day or date.today()
    if replace_pending:
        db.clear_pending_channel_posts_from(start.isoformat())
    plan = build_week_plan(start_day=start, days=days)
    ids: list[int] = []
    for row in plan:
        pid = db.enqueue_channel_post(
            row["channel"],
            row["scheduled_at"],
            row["kind"],
            row["body"],
            variant_id=row.get("variant_id", ""),
        )
        ids.append(pid)
    return {
        "start": start.isoformat(),
        "days": days,
        "enqueued": len(ids),
        "pending": db.count_channel_posts(status="pending"),
    }


async def publish_due_posts(bot: Bot, *, limit: int = 5) -> list[dict]:
    """Публикует посты, у которых наступило scheduled_at."""
    results: list[dict] = []
    for row in db.fetch_due_channel_posts(limit=limit):
        post_id = int(row["id"])
        channel = row["channel"]
        chat_id = f"@{channel}"
        try:
            msg = await bot.send_message(chat_id, row["body"], parse_mode="HTML")
            db.mark_channel_post_sent(post_id, msg.message_id)
            db.log_event(
                None,
                "channel_post",
                f"{channel}:{row['kind']}:{row.get('variant_id') or ''}",
            )
            results.append(
                {
                    "id": post_id,
                    "channel": channel,
                    "kind": row["kind"],
                    "variant_id": row.get("variant_id"),
                    "ok": True,
                    "message_id": msg.message_id,
                }
            )
            logger.info(
                "channel post #%s @%s %s/%s",
                post_id,
                channel,
                row["kind"],
                row.get("variant_id"),
            )
        except Exception as e:
            err = str(e)[:300]
            db.mark_channel_post_failed(post_id, err)
            results.append(
                {
                    "id": post_id,
                    "channel": channel,
                    "ok": False,
                    "error": err,
                }
            )
            logger.warning("channel post #%s @%s: %s", post_id, channel, err)
        await asyncio.sleep(1.2)
    return results


async def channel_post_worker(bot: Bot, interval_sec: int) -> None:
    while True:
        try:
            published = await publish_due_posts(bot)
            if published:
                logger.info("channel posts published: %d", len(published))
        except Exception:
            logger.exception("channel_post_worker")
        await asyncio.sleep(interval_sec)
