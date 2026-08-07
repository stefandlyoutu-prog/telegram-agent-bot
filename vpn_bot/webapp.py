"""FastAPI-приложение VPN-бота для Render (webhook + health)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from vpn_bot import storage as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    from vpn_bot.cloud import start_cloud, stop_cloud

    await start_cloud()
    try:
        yield
    finally:
        await stop_cloud()


app = FastAPI(title="VPN Bot", version="1.0", lifespan=lifespan)

from vpn_bot.cloud import router_cloud  # noqa: E402

app.include_router(router_cloud)
