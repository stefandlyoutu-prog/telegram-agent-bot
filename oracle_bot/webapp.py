"""FastAPI для Telegram Mini App Оракула."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
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


def site_base_url() -> str:
    from oracle_bot.config import site_public_url

    return site_public_url()


def miniapp_url() -> str:
    """Telegram Mini App — отдельно от маркeting-сайта."""
    base = cloud_webapp_url()
    if not base:
        return ""
    if base.endswith("/app"):
        return base
    return f"{base}/app"


SITE_PAGES: dict[str, str] = {
    "": "index.html",
    "2-scenariya": "2-scenariya.html",
    "taro": "taro.html",
    "goroskop": "goroskop.html",
    "sovmestimost": "sovmestimost.html",
    "numerologiya": "numerologiya.html",
}


def _inject_metrika(html: str) -> str:
    import os

    cid = os.getenv("ORACLE_YANDEX_METRIKA_ID", "").strip()
    if not cid.isdigit():
        return html
    snippet = f"""
<!-- Yandex.Metrika counter -->
<script type="text/javascript">
   (function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
   m[i].l=1*new Date();
   for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }} }}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}}
   )(window, document,'script','https://mc.yandex.ru/metrika/tag.js', 'ym');
   ym({cid}, 'init', {{clickmap:true, trackLinks:true, accurateTrackBounce:true, webvisor:true}});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/{cid}" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
"""
    return html.replace("</head>", snippet + "\n</head>")


def _serve_site(slug: str, request: Request | None = None):
    from fastapi.responses import HTMLResponse, RedirectResponse

    fname = SITE_PAGES.get(slug)
    if not fname:
        raise HTTPException(404, "Страница не найдена")
    path = f"/{slug}" if slug else "/"
    if request is not None:
        _log_web_visit(path, request)
    html = (SITE / fname).read_text(encoding="utf-8")
    html = html.replace("{{BASE}}", site_base_url())
    html = _inject_metrika(html)
    return HTMLResponse(html)


@app.get("/")
def site_index(request: Request):
    return _serve_site("", request)


@app.get("/app")
def miniapp_index():
    return FileResponse(STATIC / "index.html")


@app.get("/landing")
def landing_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/", status_code=301)


def _log_web_visit(path: str, request: "Request | None" = None) -> None:
    """Серверный счётчик посещений сайта (внешних, вне Telegram).

    Ботов/пауков не считаем, чтобы цифры были честные.
    """
    try:
        ua = ""
        if request is not None:
            ua = (request.headers.get("user-agent") or "").lower()
        if any(b in ua for b in ("bot", "spider", "crawl", "preview", "monitor", "curl", "python-requests")):
            return
        db.log_event(0, "web_visit", path)
    except Exception:
        pass


@app.get("/2-scenariya")
def page_2_scenariya(request: Request):
    return _serve_site("2-scenariya", request)


@app.get("/taro")
def page_taro(request: Request):
    return _serve_site("taro", request)


@app.get("/goroskop")
def page_goroskop(request: Request):
    return _serve_site("goroskop", request)


@app.get("/sovmestimost")
def page_sovmestimost(request: Request):
    return _serve_site("sovmestimost", request)


@app.get("/numerologiya")
def page_numerologiya(request: Request):
    return _serve_site("numerologiya", request)


@app.get("/landing-legacy")
def landing_page_legacy(request: Request):
    """Старый лендинг (архив) — основной сайт на /."""
    _log_web_visit("/landing-legacy", request)
    import os

    html = (SITE / "landing.html").read_text(encoding="utf-8")
    html = html.replace("https://moracul.onrender.com/landing", site_base_url())
    html = html.replace("{{BASE}}", site_base_url())
    html = _inject_metrika(html)
    from fastapi.responses import HTMLResponse

    return HTMLResponse(html)


class TrackBody(BaseModel):
    path: str = "/landing"
    action: str = "click"


@app.post("/api/track")
def api_track(body: TrackBody, request: Request):
    """Клики на лендинге: переходы в бота, блог и т.д."""
    ua = (request.headers.get("user-agent") or "").lower()
    if any(b in ua for b in ("bot", "spider", "crawl", "curl")):
        return {"ok": True}
    path = (body.path or "/landing")[:80]
    action = (body.action or "click")[:120]
    db.log_event(0, "web_action", f"{path}:{action}")
    return {"ok": True}


@app.get("/admin")
def admin_crm():
    return FileResponse(SITE / "admin.html")


@app.get("/oferta")
def oferta_page():
    return FileResponse(SITE / "oferta.html")


@app.get("/blog")
def blog_index(request: Request):
    _log_web_visit("/blog", request)
    return FileResponse(SITE / "blog" / "index.html")


@app.get("/blog/{slug}")
def blog_article(slug: str, request: Request):
    # только [a-z0-9-] — защита от обхода пути
    safe = "".join(c for c in slug if c.isalnum() or c == "-")
    path = SITE / "blog" / f"{safe}.html"
    if not path.exists():
        raise HTTPException(404, "Статья не найдена")
    _log_web_visit(f"/blog/{safe}", request)
    return FileResponse(path)


@app.get("/robots.txt")
def robots_txt():
    from fastapi.responses import PlainTextResponse

    base = site_base_url()
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nAllow: /blog\nAllow: /oferta\n"
        "Disallow: /bestpaints\nDisallow: /bestpaints/\nDisallow: /admin\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap_xml():
    from fastapi.responses import Response

    base = site_base_url()
    pages = list(SITE_PAGES.keys())
    page_urls = "\n".join(
        f"  <url><loc>{base}/{p}</loc><priority>{'1.0' if p == '' else '0.9'}</priority></url>"
        for p in pages
        if p
    )
    home = f"  <url><loc>{base}/</loc><priority>1.0</priority></url>\n"
    blog_dir = SITE / "blog"
    blog_urls = ""
    if blog_dir.exists():
        slugs = sorted(p.stem for p in blog_dir.glob("*.html") if p.stem != "index")
        blog_urls = "\n".join(
            f"  <url><loc>{base}/blog/{s}</loc><priority>0.8</priority></url>" for s in slugs
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{home}{page_urls}
  <url><loc>{base}/blog</loc><priority>0.9</priority></url>
{blog_urls}
  <url><loc>{base}/oferta</loc><priority>0.5</priority></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


app.mount("/assets", StaticFiles(directory=SITE / "assets"), name="site_assets")


# ── BestPaints Survey (закрытый раздел) ─────────────────────────────
from fastapi.responses import RedirectResponse  # noqa: E402
from oracle_bot.bestpaints_gate import (  # noqa: E402
    bestpaints_dir,
    credentials_ok,
    is_authenticated,
    login_redirect_ok,
    logout_response,
)

BP_STATIC = bestpaints_dir()


def _bp_safe_file(rel: str) -> Path:
    base = BP_STATIC.resolve()
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(404, "Not found")
    if not target.is_file():
        raise HTTPException(404, "Not found")
    return target


@app.get("/bestpaints/login")
async def bestpaints_login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/bestpaints/", status_code=303)
    return FileResponse(BP_STATIC / "login.html")


@app.post("/bestpaints/login")
async def bestpaints_login_submit(request: Request):
    username = ""
    password = ""
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in ctype:
            data = await request.json()
            username = str(data.get("username") or "")
            password = str(data.get("password") or "")
        else:
            # Prefer Starlette form (needs python-multipart); fallback to raw body.
            try:
                form = await request.form()
                username = str(form.get("username") or "")
                password = str(form.get("password") or "")
            except Exception:
                from urllib.parse import parse_qs

                raw = (await request.body()).decode("utf-8", errors="ignore")
                parsed = parse_qs(raw, keep_blank_values=True)
                username = (parsed.get("username") or [""])[0]
                password = (parsed.get("password") or [""])[0]
    except Exception:
        return RedirectResponse("/bestpaints/login?e=1", status_code=303)
    if not credentials_ok(username, password):
        return RedirectResponse("/bestpaints/login?e=1", status_code=303)
    return login_redirect_ok()


@app.get("/bestpaints/logout")
async def bestpaints_logout():
    return logout_response()


@app.get("/bestpaints")
@app.get("/bestpaints/")
async def bestpaints_index(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/bestpaints/login", status_code=303)
    return FileResponse(BP_STATIC / "index.html")


# ── BestPaints CRM API ──────────────────────────────────────────────
from oracle_bot import bestpaints_crm as bp_crm  # noqa: E402

bp_crm.init_db()


def _bp_api_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(401, "login required")


@app.get("/bestpaints/api/meta")
async def bp_api_meta(request: Request):
    _bp_api_auth(request)
    return bp_crm.meta()


@app.get("/bestpaints/api/objects")
async def bp_api_objects(request: Request, status: str | None = None, include_deleted: int = 0):
    _bp_api_auth(request)
    return {"objects": bp_crm.list_objects(status=status, include_deleted=bool(include_deleted))}


@app.post("/bestpaints/api/objects")
async def bp_api_create_object(request: Request):
    _bp_api_auth(request)
    data = await request.json()
    obj = bp_crm.create_object(data if isinstance(data, dict) else {})
    return obj


@app.get("/bestpaints/api/objects/{oid}")
async def bp_api_get_object(oid: str, request: Request):
    _bp_api_auth(request)
    obj = bp_crm.get_object(oid)
    if not obj:
        raise HTTPException(404, "not found")
    return {"object": obj, "events": bp_crm.list_events(oid)}


@app.post("/bestpaints/api/objects/{oid}/action")
async def bp_api_action(oid: str, request: Request):
    _bp_api_auth(request)
    data = await request.json()
    action = str((data or {}).get("action") or "")
    try:
        obj = bp_crm.transition(oid, action, data if isinstance(data, dict) else {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"object": obj, "events": bp_crm.list_events(oid)}


@app.get("/bestpaints/api/schedule")
async def bp_api_schedule(request: Request, date: str | None = None):
    _bp_api_auth(request)
    day = date or bp_crm.today_str()
    return {"date": day, "items": bp_crm.list_schedule(day), "on_duty_surveyors": bp_crm.on_duty("surveyor", day), "on_duty_managers": bp_crm.on_duty("manager", day)}


@app.post("/bestpaints/api/schedule")
async def bp_api_schedule_set(request: Request):
    _bp_api_auth(request)
    data = await request.json()
    if (data or {}).get("toggle"):
        try:
            return bp_crm.toggle_schedule(
                str(data.get("role") or ""),
                str(data.get("person_id") or ""),
                str(data.get("work_date") or bp_crm.today_str()),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    if (data or {}).get("clear"):
        day = str(data.get("work_date") or bp_crm.today_str())
        n = bp_crm.clear_schedule(day, str(data["role"]) if data.get("role") else None)
        return {"ok": True, "cleared": n, "work_date": day}
    if (data or {}).get("fill_all"):
        day = str(data.get("work_date") or bp_crm.today_str())
        staff = bp_crm.load_staff()
        added = []
        for s in staff.get("surveyors") or []:
            bp_crm.set_schedule("surveyor", s["id"], day, "fill_all")
            added.append({"role": "surveyor", "person_id": s["id"], "name": s.get("name")})
        for m in staff.get("managers") or []:
            bp_crm.set_schedule("manager", m["id"], day, "fill_all")
            added.append({"role": "manager", "person_id": m["id"], "name": m.get("name")})
        return {"ok": True, "work_date": day, "added": added}
    try:
        return bp_crm.set_schedule(
            str(data.get("role") or ""),
            str(data.get("person_id") or ""),
            str(data.get("work_date") or bp_crm.today_str()),
            str(data.get("note") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/bestpaints/api/staff")
async def bp_api_staff_get(request: Request):
    _bp_api_auth(request)
    return bp_crm.load_staff()


@app.put("/bestpaints/api/staff")
async def bp_api_staff_put(request: Request):
    _bp_api_auth(request)
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(400, "json object required")
    return bp_crm.save_staff(data)


@app.post("/bestpaints/api/staff/person")
async def bp_api_staff_person(request: Request):
    _bp_api_auth(request)
    data = await request.json()
    try:
        return bp_crm.upsert_person(str((data or {}).get("role") or ""), data if isinstance(data, dict) else {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/bestpaints/api/staff/person/{role}/{person_id}")
async def bp_api_staff_delete(role: str, person_id: str, request: Request):
    _bp_api_auth(request)
    try:
        return bp_crm.delete_person(role, person_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/bestpaints/api/analytics")
async def bp_api_analytics(
    request: Request,
    period: str = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
):
    _bp_api_auth(request)
    try:
        return bp_crm.analytics(period=period, date_from=date_from, date_to=date_to)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/bestpaints/api/payroll")
async def bp_api_payroll(
    request: Request,
    period: str = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
):
    _bp_api_auth(request)
    try:
        return bp_crm.payroll(period=period, date_from=date_from, date_to=date_to)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/bestpaints/{file_path:path}")
async def bestpaints_files(file_path: str, request: Request):
    # Bust stale cached training PDF
    if file_path in (
        "docs/BestPaints_Obuchenie.pdf",
        "docs/BestPaints_Obuchenie.pdf/",
        "docs/BestPaints_Obuchenie_v3.pdf",
        "docs/BestPaints_Obuchenie_v3.pdf/",
        "docs/BestPaints_Obuchenie_v4.pdf",
        "docs/BestPaints_Obuchenie_v4.pdf/",
    ):
        return RedirectResponse("/bestpaints/docs/BestPaints_Obuchenie_v5.pdf?v=20260728a", status_code=302)
    if file_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    if file_path in ("login", "login.html"):
        return RedirectResponse("/bestpaints/login", status_code=303)
    if not is_authenticated(request):
        return RedirectResponse("/bestpaints/login", status_code=303)
    # default document
    if not file_path or file_path.endswith("/"):
        return FileResponse(BP_STATIC / "index.html")
    path = _bp_safe_file(file_path)
    headers = {}
    low = file_path.lower()
    if low.endswith(".pdf") or low.startswith("docs/") or low.endswith("sw.js"):
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    media = None
    if low.endswith(".pdf"):
        media = "application/pdf"
    return FileResponse(path, media_type=media, headers=headers)


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


@app.get("/api/admin/sources")
def api_admin_sources(user_id: int = Query(...), days: int = Query(30)):
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from datetime import date

    today = date.today().isoformat()
    with db._connect() as conn:
        today_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(signup_source, ''), '(без метки)') AS source,
                   COUNT(*) AS users
            FROM user_meta
            WHERE substr(COALESCE(signup_at, ''), 1, 10) = ?
            GROUP BY source ORDER BY users DESC
            """,
            (today,),
        ).fetchall()
    from datetime import timedelta

    week = (date.today() - timedelta(days=7)).isoformat()
    with db._connect() as conn:
        web_today = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='web_visit' AND substr(created_at,1,10)=?",
            (today,),
        ).fetchone()[0]
        web_week = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='web_visit' AND substr(created_at,1,10)>=?",
            (week,),
        ).fetchone()[0]
        web_by_path = conn.execute(
            """
            SELECT payload AS path, COUNT(*) AS c FROM events
            WHERE event_type='web_visit' AND substr(created_at,1,10)>=?
            GROUP BY payload ORDER BY c DESC LIMIT 10
            """,
            (week,),
        ).fetchall()
    return {
        "period": db.signups_by_source(days),
        "today": [dict(r) for r in today_rows],
        "web_visits": {
            "today": int(web_today),
            "week": int(web_week),
            "by_path_week": [dict(r) for r in web_by_path],
        },
    }


@app.post("/api/admin/backfill-sources")
def api_admin_backfill_sources(user_id: int = Query(...)):
    """Восстановить signup_source из событий return_visit с payload src_*.

    Нужен из-за бага: middleware создавал юзера раньше /start, из-за чего
    is_new всегда был False и метка src_ не сохранялась.
    """
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    fixed = []
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT user_id, payload, MIN(created_at) AS first_seen
            FROM events
            WHERE event_type = 'return_visit' AND payload LIKE 'src\\_%' ESCAPE '\\'
            GROUP BY user_id
            """
        ).fetchall()
        for r in rows:
            src = (r["payload"] or "")[4:].strip().lower()[:64]
            if not src:
                continue
            cur = conn.execute(
                """
                UPDATE user_meta SET signup_source = ?
                WHERE user_id = ? AND COALESCE(signup_source, '') = ''
                """,
                (src, r["user_id"]),
            )
            if cur.rowcount:
                fixed.append({"user_id": r["user_id"], "source": src})
    return {"fixed": len(fixed), "users": fixed}


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


@app.post("/api/admin/hot-recovery")
async def api_admin_hot_recovery(
    user_id: int = Query(...),
    limit: int = Query(30),
    intent_only: int = Query(0),
    flash_price: int | None = Query(None),
):
    """Дожим лидов. intent_only=1 — только payment_intent; flash_price=29 — спеццена."""
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.cloud import _bot
    from oracle_bot.hot_recovery import run_hot_recovery

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")
    fp = flash_price if flash_price and flash_price > 0 else None
    result = await run_hot_recovery(
        _bot,
        limit=min(limit, 50),
        intent_only=bool(intent_only),
        flash_price=fp,
        hours=168 if intent_only else 72,
    )
    try:
        from oracle_bot.admin_notify import notify_admins

        tag = f" flash={fp}₽" if fp else ""
        mode = " intent-only" if intent_only else ""
        summary = f"sent={result['sent']} skip={result['skip']} fail={result['fail']}{mode}{tag}"
        await notify_admins(
            _bot,
            f"⚡ Flash recovery: {summary}\n" + "\n".join(result.get("details", [])[:15]),
        )
    except Exception:
        pass
    return result


@app.get("/api/admin/pay-config")
def api_admin_pay_config(user_id: int = Query(...)):
    """Санити-проверка платёжного контура: режим, пароли, цены (без секретов)."""
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot import config as cfg

    return {
        "robokassa_test_mode": cfg.ROBOKASSA_TEST,
        "robokassa_login_set": bool(cfg.ROBOKASSA_LOGIN),
        "live_password1_set": bool(cfg.ROBOKASSA_PASSWORD1),
        "live_password2_set": bool(cfg.ROBOKASSA_PASSWORD2),
        "test_password1_set": bool(cfg.ROBOKASSA_TEST_PASSWORD1),
        "test_password2_set": bool(cfg.ROBOKASSA_TEST_PASSWORD2),
        "hash_algo": cfg.ROBOKASSA_HASH,
        "prices_rub": {
            "premium": cfg.ORACLE_PREMIUM_PRICE_RUB,
            "deep": cfg.ORACLE_DEEP_PRICE_RUB,
            "deep_first": cfg.ORACLE_DEEP_FIRST_PRICE_RUB,
            "hvd": cfg.ORACLE_EXCLUSIVE_HVD_PRICE_RUB,
            "ultra_plus": cfg.ORACLE_ULTRA_PLUS_PRICE_RUB,
            "pdf_hvd": cfg.ORACLE_PDF_HVD_PRICE_RUB,
        },
    }


@app.get("/api/admin/user-check")
async def api_admin_user_check(user_id: int = Query(...), target: int = Query(...)):
    """Диагностика конкретного пользователя: есть ли в базе рассылки, opt-out, покупки."""
    if user_id <= 0 or not is_admin_user(user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot import storage as db

    ids = set(db.all_user_ids())
    meta = db.get_user_meta(target)
    profile = db.get_profile(target)
    reachable = None
    error = ""
    from oracle_bot.cloud import _bot

    if _bot:
        try:
            chat = await _bot.get_chat(target)
            reachable = True
            profile["tg_name"] = (chat.first_name or "") + (
                f" @{chat.username}" if chat.username else ""
            )
        except Exception as e:  # noqa: BLE001
            reachable = False
            error = str(e)[:200]
    return {
        "target": target,
        "in_broadcast_list": target in ids,
        "push_opt_out": bool(meta.get("push_opt_out")),
        "bought_hvd": db.has_paid(target, "exclusive_hvd"),
        "bought_ultra": db.has_paid(target, "ultra_plus"),
        "profile": profile,
        "chat_reachable": reachable,
        "error": error,
    }


class AdminChannelPostBody(BaseModel):
    user_id: int
    text: str = ""
    channels: list[str] = []


@app.post("/api/admin/channel-post")
async def api_admin_channel_post(body: AdminChannelPostBody):
    """Произвольный пост в свои каналы (по умолчанию — все промо-каналы)."""
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    text = (body.text or "").strip()
    if len(text) < 2:
        raise HTTPException(400, "Пустой текст")
    import asyncio as _asyncio

    from oracle_bot.cloud import _bot

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")
    channels = [c.strip().lstrip("@") for c in body.channels if c.strip()]
    if not channels:
        from oracle_bot.config import ORACLE_PROMO_CHANNELS

        channels = list(ORACLE_PROMO_CHANNELS)
    results = []
    for u in channels:
        try:
            msg = await _bot.send_message(f"@{u}", text, parse_mode="HTML")
            results.append({"channel": u, "ok": True, "message_id": msg.message_id})
        except Exception as e:
            results.append({"channel": u, "ok": False, "error": str(e)[:200]})
        await _asyncio.sleep(1.0)
    return results


class AdminPromoBooksBody(BaseModel):
    user_id: int
    variant: str = "combo"


@app.post("/api/admin/promo-books")
async def api_admin_promo_books(body: AdminPromoBooksBody):
    """Прогноз админу + рассылка книг + запуск воронки возражений получателям."""
    if body.user_id <= 0 or not is_admin_user(body.user_id):
        raise HTTPException(403, "Нет доступа")
    from oracle_bot.cloud import _bot

    if not _bot:
        raise HTTPException(503, "Бот не инициализирован")
    variant = (body.variant or "entry").strip().lower()
    if variant not in ("combo", "hvd", "ultra", "entry"):
        variant = "entry"

    from oracle_bot.ads import push_books_ad_to_all
    from oracle_bot.campaign_report import send_forecast

    await send_forecast(_bot, variant)
    result = await push_books_ad_to_all(_bot, variant=variant)
    return {"variant": variant, "result": result}


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
