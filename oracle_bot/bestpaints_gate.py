"""Закрытый доступ к BestPaints Survey на moracul.ru/bestpaints."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "bp_survey_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней

# Дефолты для первого деплоя; на Render лучше переопределить env.
DEFAULT_USER = "bestpaints"
DEFAULT_PASSWORD = "ZamerBp2026!"


def bestpaints_dir() -> Path:
    return Path(__file__).resolve().parent / "static" / "bestpaints"


def _user() -> str:
    return (os.getenv("BESTPAINTS_USER") or DEFAULT_USER).strip()


def _password() -> str:
    return (os.getenv("BESTPAINTS_PASSWORD") or DEFAULT_PASSWORD).strip()


def _secret() -> bytes:
    raw = (
        os.getenv("BESTPAINTS_SESSION_SECRET")
        or os.getenv("ORACLE_BOT_TOKEN")
        or "bp-survey-dev-secret"
    ).strip()
    return raw.encode("utf-8")


def make_session_token(username: str, *, now: int | None = None) -> str:
    ts = int(now if now is not None else time.time())
    payload = f"{username}:{ts}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: str | None) -> bool:
    if not token or token.count(":") < 2:
        return False
    username, ts_s, sig = token.rsplit(":", 2)
    if username != _user():
        return False
    try:
        ts = int(ts_s)
    except ValueError:
        return False
    if abs(time.time() - ts) > COOKIE_MAX_AGE:
        return False
    payload = f"{username}:{ts_s}"
    expect = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.compare_digest(expect, sig)


def credentials_ok(username: str, password: str) -> bool:
    u_ok = secrets.compare_digest(username.strip(), _user())
    p_ok = secrets.compare_digest(password, _password())
    return u_ok and p_ok


def is_authenticated(request: Request) -> bool:
    return verify_session_token(request.cookies.get(COOKIE_NAME))


def require_bestpaints_auth(request: Request) -> None:
    if is_authenticated(request):
        return
    raise HTTPException(
        status_code=303,
        detail="login",
        headers={"Location": "/bestpaints/login"},
    )


def login_redirect_ok() -> RedirectResponse:
    resp = RedirectResponse("/bestpaints/", status_code=303)
    token = make_session_token(_user())
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=os.getenv("ORACLE_CLOUD", "").strip() in ("1", "true", "yes"),
        samesite="lax",
        path="/bestpaints",
    )
    return resp


def logout_response() -> RedirectResponse:
    resp = RedirectResponse("/bestpaints/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/bestpaints")
    return resp
