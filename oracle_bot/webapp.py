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
from oracle_bot.card_of_day import card_for_user
from oracle_bot.config import ORACLE_BOT_USERNAME, ORACLE_FREE_PER_DAY, cloud_webapp_url
from oracle_bot.miniapp_catalog import SECTION_LABELS, modules_for_api
from oracle_bot.paywall import paywall_mode
from oracle_bot.streak import get_streak, record_visit

STATIC = Path(__file__).resolve().parent / "static" / "miniapp"
SITE = Path(__file__).resolve().parent / "static" / "site"


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


@app.get("/landing")
def landing_page():
    return FileResponse(SITE / "landing.html")


@app.get("/admin")
def admin_crm():
    return FileResponse(SITE / "admin.html")


@app.get("/oferta")
def oferta_page():
    return FileResponse(SITE / "oferta.html")


@app.get("/robots.txt")
def robots_txt():
    from fastapi.responses import PlainTextResponse

    base = cloud_webapp_url() or "https://moracul.onrender.com"
    return PlainTextResponse(
        f"User-agent: *\nAllow: /landing\nAllow: /oferta\nSitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap_xml():
    from fastapi.responses import Response

    base = cloud_webapp_url() or "https://moracul.onrender.com"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/landing</loc><priority>1.0</priority></url>
  <url><loc>{base}/oferta</loc><priority>0.5</priority></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/catalog")
def api_catalog():
    return {
        "modules": modules_for_api(),
        "sections": SECTION_LABELS,
        "bot": ORACLE_BOT_USERNAME,
        "bot_link": f"https://t.me/{ORACLE_BOT_USERNAME}",
    }


def _guest_home() -> dict:
    return {
        "greeting": "Привет",
        "subtitle": "Нажми раздел — ответ придёт в чат с ботом",
        "streak": 0,
        "credits": 0,
        "used_today": 0,
        "free_limit": ORACLE_FREE_PER_DAY,
        "premium": False,
        "topic": "",
        "card": {"title": "—", "hint": "Карта дня откроется в чате"},
        "bot": ORACLE_BOT_USERNAME,
        "bot_link": f"https://t.me/{ORACLE_BOT_USERNAME}",
        "modules": modules_for_api(),
        "sections": SECTION_LABELS,
        "paywall_mode": paywall_mode(),
    }


@app.get("/api/home")
def api_home(user_id: int | None = Query(None)):
    if not user_id or user_id <= 0:
        return _guest_home()
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
        "bot_link": f"https://t.me/{ORACLE_BOT_USERNAME}",
        "modules": modules_for_api(),
        "sections": SECTION_LABELS,
        "paywall_mode": paywall_mode(),
    }


class TopicBody(BaseModel):
    user_id: int
    topic: str = ""


class ActionBody(BaseModel):
    init_data: str = ""
    action: str
    module: str = ""


@app.post("/api/action")
async def api_action(body: ActionBody):
    from oracle_bot.cloud import cloud_runtime
    from oracle_bot.webapp_actions import dispatch_webapp_action

    bot, dp = cloud_runtime()
    if not bot or not dp:
        raise HTTPException(503, "Бот не инициализирован")
    try:
        await dispatch_webapp_action(
            bot,
            dp,
            body.init_data,
            action=body.action.strip(),
            module=body.module.strip(),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, "Не удалось выполнить действие") from e
    return {"ok": True}


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
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.analytics import format_stats_report

    return {"text": format_stats_report()}


@app.get("/api/admin/funnel")
def api_admin_funnel(user_id: int = Query(...)):
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.analytics import funnel_snapshot

    return funnel_snapshot()


class AdminBroadcastBody(BaseModel):
    user_id: int
    text: str = ""


class AdminLaunchBody(BaseModel):
    user_id: int
    channels: list[str] = []
    broadcast: bool = True
    channel_posts: int = 1


@app.post("/api/admin/broadcast")
async def api_admin_broadcast(body: AdminBroadcastBody):
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    text = (body.text or "").strip()
    if len(text) < 2:
        raise HTTPException(400, "Пустой текст")
    from oracle_bot.cloud import _bot
    from oracle_bot.broadcast import broadcast_text

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")
    return await broadcast_text(_bot, text)


class AdminFreeDayBody(BaseModel):
    user_id: int


@app.post("/api/admin/free-day-start")
async def api_admin_free_day_start(body: AdminFreeDayBody):
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.cloud import _bot
    from oracle_bot.free_day import run_broadcast

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")
    return await run_broadcast(_bot)


@app.get("/api/admin/channel-queue")
def api_admin_channel_queue(user_id: int = Query(...)):
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    return db.channel_queue_summary()


class AdminSeedQueueBody(BaseModel):
    user_id: int
    days: int = 7


@app.post("/api/admin/seed-channel-queue")
def api_admin_seed_channel_queue(body: AdminSeedQueueBody):
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.channel_queue import seed_week_queue

    return seed_week_queue(days=max(1, min(body.days, 14)))


@app.post("/api/admin/launch-promo")
async def api_admin_launch_promo(body: AdminLaunchBody):
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.cloud import _bot
    from oracle_bot.broadcast import broadcast_text, post_to_channels
    from oracle_bot.promo import post_for_channel, post_launch_broadcast, pick_promo_variant

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")

    channels = [c.strip().lstrip("@") for c in body.channels if c.strip()]
    if not channels:
        from oracle_bot.config import ORACLE_PROMO_CHANNELS

        channels = list(ORACLE_PROMO_CHANNELS)

    posts = [post_for_channel(ch) for ch in channels]
    if body.channel_posts > 1:
        posts = []
        for i, ch in enumerate(channels):
            vid, text = pick_promo_variant(i, ch)
            posts.append(text)
    channel_result = await post_to_channels(_bot, posts, channels)
    broadcast_result = None
    if body.broadcast:
        broadcast_result = await broadcast_text(_bot, post_launch_broadcast())
    return {
        "channels": channel_result,
        "broadcast": broadcast_result,
        "posts_used": len(channel_result),
    }
