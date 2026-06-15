"""FastAPI для Telegram Mini App Оракула."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from oracle_bot import storage as db
from oracle_bot.access import is_admin_user
from oracle_bot.config import ORACLE_BOT_USERNAME, ORACLE_FREE_PER_DAY, cloud_webapp_url
from oracle_bot.streak import get_streak, record_visit

STATIC = Path(__file__).resolve().parent / "static" / "miniapp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    from oracle_bot.cloud import cloud_enabled, start_cloud, stop_cloud

    if cloud_enabled():
        await start_cloud()
    try:
        yield
    finally:
        if cloud_enabled():
            await stop_cloud()


app = FastAPI(title="m-Oracul WebApp", version="1.0", lifespan=lifespan)

from oracle_bot.cloud import router_cloud  # noqa: E402

app.include_router(router_cloud)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/home")
def api_home(user_id: int = Query(...)):
    db.ensure_user(user_id)
    record_visit(user_id)
    p = db.get_profile(user_id)
    meta = db.get_user_meta(user_id)
    name = p.get("name") or meta.get("first_name") or "друг"
    card, hint = card_for_user(user_id)
    st = db.referral_stats(user_id)
    return {
        "greeting": f"Привет, {name}",
        "subtitle": "Выбери разбор — бесплатная часть уже с пользой",
        "streak": get_streak(user_id),
        "credits": st["credits"],
        "used_today": db.total_usage_today(user_id),
        "free_limit": ORACLE_FREE_PER_DAY,
        "premium": db.is_premium(user_id) or is_admin_user(user_id),
        "topic": meta.get("topic") or "",
        "card": {"title": card, "hint": hint},
        "bot": ORACLE_BOT_USERNAME,
    }


class TopicBody(BaseModel):
    user_id: int
    topic: str = ""


@app.post("/api/topic")
def api_topic(body: TopicBody):
    if body.topic and body.topic not in ("love", "money", "career"):
        raise HTTPException(400, "invalid topic")
    db.ensure_user(body.user_id)
    with db._connect() as conn:
        conn.execute(
            """
            INSERT INTO user_meta (user_id, topic, signup_at, last_active_at, push_opt_out)
            VALUES (?, ?, datetime('now'), datetime('now'), 0)
            ON CONFLICT(user_id) DO UPDATE SET topic = excluded.topic
            """,
            (body.user_id, body.topic or None),
        )
    from oracle_bot.pushes import schedule_topic_morning

    schedule_topic_morning(body.user_id)
    return {"ok": True, "topic": body.topic}


@app.get("/api/stats")
def api_stats(user_id: int = Query(...)):
    if user_id <= 0:
        raise HTTPException(400)
    from oracle_bot.analytics import format_stats_report

    return {"text": format_stats_report()}
