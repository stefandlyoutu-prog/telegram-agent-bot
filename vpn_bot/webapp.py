"""FastAPI-приложение VPN-бота (standalone Render, если moracul не используется)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from vpn_bot.cloud import init_vpn_bot, router_vpn, stop_vpn_bot, vpn_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_vpn_bot()
    try:
        yield
    finally:
        await stop_vpn_bot()


app = FastAPI(title="VPN Bot", version="1.0", lifespan=lifespan)
app.include_router(router_vpn)


@app.get("/health")
async def health():
    bot_user = None
    bot, _ = vpn_runtime()
    if bot:
        try:
            me = await bot.get_me()
            bot_user = me.username
        except Exception:
            bot_user = "error"
    return {"ok": True, "bot_ready": bot is not None, "bot": bot_user}
