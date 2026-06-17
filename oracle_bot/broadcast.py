"""Рассылка и промо-запуск @MOracul_bot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from oracle_bot import storage as db

logger = logging.getLogger(__name__)


async def broadcast_text(bot, text: str) -> dict[str, Any]:
    ids = db.all_user_ids()
    ok = fail = 0
    for user_id in ids:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            try:
                await bot.send_message(user_id, text, parse_mode="HTML")
                ok += 1
            except Exception:
                fail += 1
        except TelegramForbiddenError:
            fail += 1
        except Exception as e:
            logger.warning("broadcast %s: %s", user_id, e)
            fail += 1
        await asyncio.sleep(0.05)
    return {"total": len(ids), "ok": ok, "fail": fail}


async def post_to_channels(bot, posts: list[str], channels: list[str]) -> list[dict[str, Any]]:
    from oracle_bot.promo import post_for_channel

    results: list[dict[str, Any]] = []
    for username in channels:
        u = username.strip().lstrip("@")
        if not u:
            continue
        chat_id = f"@{u}"
        texts = posts if len(posts) > 1 else [post_for_channel(u)]
        for text in texts:
            try:
                msg = await bot.send_message(chat_id, text, parse_mode="HTML")
                results.append({"channel": u, "ok": True, "message_id": msg.message_id})
            except Exception as e:
                results.append({"channel": u, "ok": False, "error": str(e)[:200]})
            await asyncio.sleep(1.0)
    return results
