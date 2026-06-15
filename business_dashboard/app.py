"""FastAPI-приложение дашборда."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from business_dashboard.config import DASHBOARD_TOKEN
from business_dashboard.daily import (
    add_to_today_plan,
    close_day_report,
    get_chart_history,
    get_report,
    get_today_plan,
    list_reports,
    set_today_plan,
)
from business_dashboard.idea_scout import (
    launch_opportunity,
    list_opportunities,
    scan_new_trends,
    update_opportunity_stage,
)
from business_dashboard.life_spheres import spheres_with_ideas
from business_dashboard.scheduler import run_background_loop
from business_dashboard.security import DashboardAuthMiddleware
from business_dashboard.storage import (
    add_blocker,
    add_revenue,
    complete_blocker,
    get_dashboard,
    init_db,
    list_ideas,
    list_user_assets,
    rollover_periods,
    set_user_asset,
    update_idea_fields,
    update_status,
)

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    rollover_periods()
    task = asyncio.create_task(run_background_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Центр доходов", version="0.3.0", lifespan=lifespan)
app.add_middleware(DashboardAuthMiddleware)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/config")
def api_config():
    return {"auth_required": bool(DASHBOARD_TOKEN), "version": "0.3.0"}


@app.get("/api/dashboard")
def api_dashboard(channel: Optional[str] = Query(None)):
    rollover_periods()
    return get_dashboard(channel)


@app.get("/api/spheres")
def api_spheres():
    return {"spheres": spheres_with_ideas(list_ideas())}


@app.get("/api/chart")
def api_chart(days: int = Query(7, ge=1, le=30)):
    return {"history": get_chart_history(days)}


@app.get("/api/reports")
def api_reports(limit: int = Query(14, ge=1, le=90)):
    return {"reports": list_reports(limit)}


@app.get("/api/reports/{report_date}")
def api_report(report_date: str):
    r = get_report(report_date)
    if not r:
        raise HTTPException(404, "Отчёт не найден")
    return r


class StatusBody(BaseModel):
    status: str = Field(..., pattern="^(needs_action|connected|running)$")


@app.patch("/api/ideas/{slug}/status")
def api_set_status(slug: str, body: StatusBody):
    row = update_status(slug, body.status)
    if not row:
        raise HTTPException(404, "Идея не найдена")
    return row


class IdeaPatchBody(BaseModel):
    expected_daily_rub: Optional[float] = None
    priority: Optional[int] = None
    note: Optional[str] = None
    action_required: Optional[str] = None


@app.patch("/api/ideas/{slug}")
def api_patch_idea(slug: str, body: IdeaPatchBody):
    row = update_idea_fields(slug, **body.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(404, "Идея не найдена")
    return row


class RevenueBody(BaseModel):
    amount: float = Field(..., gt=0)
    note: str = ""
    source: str = "manual"


@app.post("/api/ideas/{slug}/revenue")
def api_add_revenue(slug: str, body: RevenueBody):
    row = add_revenue(slug, body.amount, body.note, body.source)
    if not row:
        raise HTTPException(404, "Идея не найдена")
    return row


class PlanItem(BaseModel):
    slug: str
    expected_rub: float = 0
    promotion: str = ""


class PlanBody(BaseModel):
    items: List[PlanItem]


@app.get("/api/today/plan")
def api_today_plan():
    return {"plan": get_today_plan()}


@app.post("/api/today/plan")
def api_set_plan(body: PlanBody):
    items = [i.model_dump() for i in body.items]
    return {"plan": set_today_plan(items)}


@app.post("/api/today/plan/{slug}")
def api_add_plan_item(slug: str, expected_rub: Optional[float] = None, promotion: str = ""):
    ok = add_to_today_plan(slug, expected_rub, promotion)
    if not ok:
        raise HTTPException(409, "Уже в плане на сегодня")
    return {"plan": get_today_plan()}


class CloseDayBody(BaseModel):
    note: str = ""


@app.post("/api/today/close")
def api_close_day(body: CloseDayBody):
    return close_day_report(body.note)


class BlockerBody(BaseModel):
    description: str
    slug: str = ""
    blocker_type: str = "other"


@app.post("/api/blockers")
def api_add_blocker(body: BlockerBody):
    return add_blocker(body.description, body.slug, body.blocker_type)


@app.post("/api/blockers/{blocker_id}/done")
def api_blocker_done(blocker_id: int):
    row = complete_blocker(blocker_id)
    if not row:
        raise HTTPException(404, "Блокер не найден")
    return row


@app.get("/api/assets")
def api_assets():
    return {"assets": list_user_assets()}


class AssetBody(BaseModel):
    done: bool = True
    note: str = ""


@app.patch("/api/assets/{asset_key}")
def api_set_asset(asset_key: str, body: AssetBody):
    row = set_user_asset(asset_key, body.done, body.note)
    if not row:
        raise HTTPException(404, "Актив не найден")
    return row


@app.get("/api/scout")
def api_scout(stage: Optional[str] = Query(None)):
    return {"opportunities": list_opportunities(stage)}


@app.post("/api/scout/scan")
def api_scout_scan():
    added = scan_new_trends()
    return {"added": added, "opportunities": list_opportunities()}


class StageBody(BaseModel):
    stage: str


@app.patch("/api/scout/{slug}")
def api_scout_stage(slug: str, body: StageBody):
    row = update_opportunity_stage(slug, body.stage)
    if not row:
        raise HTTPException(400, "Неверный этап или slug")
    return row


@app.post("/api/scout/{slug}/launch")
def api_scout_launch(slug: str):
    row = launch_opportunity(slug)
    if not row:
        raise HTTPException(404, "Тренд не найден")
    return row


class TgChannelBody(BaseModel):
    username: str
    niche: str = ""
    funnel_url: str = "https://t.me/MOracul_bot"
    monetization: str = ""
    note: str = ""


class TgPostBody(BaseModel):
    text: str = ""
    pin: bool = False
    template: str = "funnel"


@app.get("/api/tg-channels")
def api_tg_channels():
    from telegram_channels.storage import list_tg_channels

    return {"channels": list_tg_channels()}


@app.post("/api/tg-channels")
def api_tg_channel_add(body: TgChannelBody):
    from telegram_channels.storage import add_tg_channel

    return add_tg_channel(
        body.username,
        niche=body.niche,
        funnel_url=body.funnel_url,
        monetization=body.monetization,
        note=body.note,
    )


@app.post("/api/tg-channels/sync")
def api_tg_channels_sync():
    from telegram_channels.storage import sync_all_tg_channels

    return {"channels": sync_all_tg_channels()}


@app.post("/api/tg-channels/{username}/sync")
def api_tg_channel_sync(username: str):
    from telegram_channels.storage import sync_tg_channel

    row = sync_tg_channel(username)
    if not row:
        raise HTTPException(404, "Канал не в реестре")
    return row


@app.post("/api/tg-channels/{username}/post")
def api_tg_channel_post(username: str, body: TgPostBody):
    from telegram_channels.client import ChannelBot, ChannelBotError
    from telegram_channels.content import funnel_post
    from telegram_channels.storage import get_tg_channel, mark_posted

    ch = get_tg_channel(username)
    if not ch:
        raise HTTPException(404, "Канал не найден")
    if not ch.get("can_post"):
        raise HTTPException(409, "Бот не может постить — добавь @MOracul_bot админом")
    text = body.text.strip()
    if not text:
        if body.template == "funnel":
            text = funnel_post()
        else:
            raise HTTPException(400, "Пустой текст поста")
    try:
        bot = ChannelBot()
        mid = bot.post(username, text, pin=body.pin)
        mark_posted(username)
        return {"ok": True, "message_id": mid}
    except ChannelBotError as e:
        raise HTTPException(502, str(e)) from e
