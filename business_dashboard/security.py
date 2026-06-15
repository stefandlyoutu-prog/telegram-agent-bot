"""Опциональная защита API дашборда."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from business_dashboard.config import DASHBOARD_TOKEN


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not DASHBOARD_TOKEN:
            return await call_next(request)
        path = request.url.path
        if path.startswith("/api/") and path != "/api/config":
            token = request.headers.get("X-Dashboard-Token", "")
            if token != DASHBOARD_TOKEN:
                return JSONResponse({"detail": "Нужен заголовок X-Dashboard-Token"}, status_code=401)
        return await call_next(request)
