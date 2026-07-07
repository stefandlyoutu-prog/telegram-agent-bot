#!/usr/bin/env python3
"""Вечерняя сверка автопостинга upload-post: что реально опубликовалось.

Посты уходят по расписанию (9/12/15/18/21 МСК), а API отвечает 200 сразу —
реальный результат виден только в истории. Скрипт берёт историю за сутки,
считает успехи/ошибки и шлёт отчёт админу в Telegram.

Запуск вручную:  .venv/bin/python scripts/uploadpost_check.py
Планировщик:     launchd com.oracle.uploadpostcheck (22:30 ежедневно)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


def _notify(text: str) -> None:
    token = os.getenv("ORACLE_BOT_TOKEN", "").strip()
    admin = os.getenv("MONEY_ADMIN_IDS", "").split(",")[0].strip()
    if not token or not admin.isdigit():
        return
    body = json.dumps({"chat_id": int(admin), "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body, headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30)


def main() -> None:
    api_key = os.getenv("UPLOAD_POST_API_KEY", "").strip()
    if not api_key:
        print("UPLOAD_POST_API_KEY не задан")
        return
    req = urllib.request.Request(
        "https://api.upload-post.com/api/uploadposts/history",
        headers={"Authorization": f"Apikey {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        history = json.loads(r.read()).get("history", [])

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    ok_lines, fail_lines = [], []
    for rec in history:
        try:
            ts = datetime.fromisoformat(rec["upload_timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if ts < since:
            continue
        plat = rec.get("platform", "?")
        title = (rec.get("post_title") or "")[:45]
        if rec.get("success"):
            url = rec.get("post_url") or ""
            ok_lines.append(f"✔ {plat}: {title} {url}")
        else:
            err = (rec.get("error_message") or "")[:110]
            fail_lines.append(f"✖ {plat}: {title} — {err}")

    if not ok_lines and not fail_lines:
        print("за сутки публикаций не было")
        return

    banned = any("banned_from_posting" in line for line in fail_lines)
    text = (
        f"📊 <b>Автопостинг за сутки: {len(ok_lines)} ок, {len(fail_lines)} ошибок</b>\n\n"
        + "\n".join(ok_lines[:10])
        + ("\n" if ok_lines and fail_lines else "")
        + "\n".join(fail_lines[:10])
    )
    if banned:
        text += (
            "\n\n⚠️ TikTok временно забанил аккаунт на публикации (spam risk). "
            "Обычно проходит за 24-72 ч. Если не пройдёт — нужен другой TikTok-аккаунт."
        )
    _notify(text)
    print(f"ok={len(ok_lines)} fail={len(fail_lines)}")


if __name__ == "__main__":
    main()
