#!/usr/bin/env python3
"""Однократный вход в YouTube (Google OAuth) → печатает YOUTUBE_REFRESH_TOKEN.

Подготовка (один раз, у тебя в Google Cloud):
  1. console.cloud.google.com → создай проект
  2. APIs & Services → Enable → "YouTube Data API v3"
  3. OAuth consent screen → External → добавь себя в Test users
  4. Credentials → Create OAuth client ID → Desktop app
  5. Скопируй Client ID и Client secret

Запуск:
  YOUTUBE_CLIENT_ID=xxx YOUTUBE_CLIENT_SECRET=yyy \
      .venv/bin/python scripts/youtube_authorize.py

Откроется браузер, войдёшь в нужный Google-аккаунт (канал), разрешишь доступ.
Скрипт напечатает refresh_token — вставь его в .env как YOUTUBE_REFRESH_TOKEN.
"""

from __future__ import annotations

import http.server
import os
import sys
import urllib.parse
import webbrowser

import requests

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/"
_code: dict[str, str] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _code["code"] = (params.get("code") or [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>Готово! Можно закрыть вкладку и вернуться в терминал.</h2>".encode())

    def log_message(self, *a) -> None:  # тише
        pass


def main() -> None:
    cid = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("FAIL: задай YOUTUBE_CLIENT_ID и YOUTUBE_CLIENT_SECRET в окружении", file=sys.stderr)
        sys.exit(1)

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    print("Открываю браузер для входа в Google...")
    print(auth_url)
    webbrowser.open(auth_url)

    httpd = http.server.HTTPServer(("localhost", PORT), _Handler)
    httpd.handle_request()  # ждём один редирект с кодом
    code = _code.get("code")
    if not code:
        print("FAIL: код авторизации не получен", file=sys.stderr)
        sys.exit(1)

    tok = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cid,
            "client_secret": secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT,
        },
        timeout=30,
    ).json()
    rt = tok.get("refresh_token")
    if not rt:
        print(f"FAIL: refresh_token не получен: {tok}", file=sys.stderr)
        sys.exit(1)
    print("\n================  ВСТАВЬ В .env  ================")
    print(f"YOUTUBE_CLIENT_ID={cid}")
    print(f"YOUTUBE_CLIENT_SECRET={secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={rt}")
    print("================================================")


if __name__ == "__main__":
    main()
