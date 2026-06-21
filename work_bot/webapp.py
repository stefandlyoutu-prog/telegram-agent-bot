"""FastAPI для @WorkOnline bot на Render."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from work_bot.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from work_bot.cloud import cloud_enabled, start_cloud, stop_cloud

    if cloud_enabled():
        await start_cloud()
    try:
        yield
    finally:
        if cloud_enabled():
            await stop_cloud()


app = FastAPI(title="Work Online Bot", version="1.0", lifespan=lifespan)

from work_bot.cloud import router_cloud  # noqa: E402

app.include_router(router_cloud)


@app.get("/health")
def health():
    return {"ok": True, "bot": "work-online"}
