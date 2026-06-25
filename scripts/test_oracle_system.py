#!/usr/bin/env python3
"""Глобальная проверка m-Oracul: бот, сайт, storage, прод."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BASE = os.getenv("ORACLE_WEBAPP_URL", "https://moracul.onrender.com").rstrip("/")
FAILURES: list[str] = []
PASSED: list[str] = []


def ok(name: str, detail: str = "") -> None:
    PASSED.append(name)
    print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str) -> None:
    FAILURES.append(f"{name}: {detail}")
    print(f"  ❌ {name}: {detail}")


def _get(url: str, timeout: int = 60) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def test_storage_api() -> None:
    print("\n💾 Storage API")
    from oracle_bot import storage as db

    required = [
        "ensure_user",
        "get_referral_credits",
        "add_referral_credits",
        "register_referral",
        "can_use",
        "bump_usage",
        "log_event",
        "analytics_snapshot",
    ]
    for fn in required:
        if hasattr(db, fn):
            ok(f"storage.{fn}")
        else:
            fail(f"storage.{fn}", "отсутствует")


def test_streak_middleware() -> None:
    print("\n🔥 Streak + middleware path")
    from oracle_bot import storage as db
    from oracle_bot.streak import record_visit

    uid = 999_999_777
    db.init_db()
    with db._connect() as conn:
        conn.execute("DELETE FROM streaks WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))
    db.ensure_user(uid)
    try:
        # симулируем 3-й день подряд — раньше падало на add_referral_credits
        from datetime import date, timedelta

        today = date.today().isoformat()
        y1 = (date.today() - timedelta(days=1)).isoformat()
        y2 = (date.today() - timedelta(days=2)).isoformat()
        with db._connect() as conn:
            conn.execute("DELETE FROM streaks WHERE user_id = ?", (uid,))
            conn.execute(
                "INSERT INTO streaks (user_id, streak_count, last_day) VALUES (?, 2, ?)",
                (uid, y1),
            )
        # подмена «вчера» → сегодня даст count=3 и бонус
        with db._connect() as conn:
            conn.execute(
                "UPDATE streaks SET last_day = ? WHERE user_id = ?",
                (y1, uid),
            )
        r = record_visit(uid)
        if r["streak"] >= 3:
            ok("record_visit day-3", f"streak={r['streak']} bonus={r['bonus_granted']}")
        else:
            fail("record_visit", str(r))
        credits = db.get_referral_credits(uid)
        if r["bonus_granted"] and credits >= 1:
            ok("streak bonus credits", str(credits))
        elif r["bonus_granted"] == 0:
            ok("record_visit no crash")
    except Exception as e:
        fail("record_visit", str(e))
    finally:
        with db._connect() as conn:
            conn.execute("DELETE FROM streaks WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))


def test_landing_buttons() -> None:
    print("\n🌐 Лендинг — все кнопки")
    html_path = ROOT / "oracle_bot/static/site/landing.html"
    html = html_path.read_text(encoding="utf-8")
    links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*btn', html)
    if not links:
        links = re.findall(r'class="btn[^"]*"[^>]*href="([^"]+)"', html)
    # все <a class="btn
    for m in re.finditer(r'<a\s+class="btn[^"]*"[^>]*href="([^"]+)"', html):
        links.append(m.group(1))
    for m in re.finditer(r'<a\s+href="([^"]+)"[^>]*class="btn', html):
        links.append(m.group(1))
    links = list(dict.fromkeys(links))
    if len(links) >= 4:
        ok("landing btn count", str(len(links)))
    else:
        fail("landing buttons", f"найдено {len(links)}: {links}")
    for href in links:
        if href.startswith("https://t.me/") or href.startswith("/") or href.startswith("https://moracul"):
            ok(f"href {href[:50]}")
        else:
            fail("landing href", href)
    if "start=premium" in html or "Премиум" in html:
        if 'start=premium' in html:
            ok("premium CTA")
        else:
            fail("premium CTA", "нет кнопки премиум → бот")


def test_prod_http() -> None:
    print("\n☁️  Прод HTTP")
    routes = [
        ("/health", "webhook_sync"),
        ("/landing", "m-Oracul"),
        ("/oferta", "оферта"),
        ("/", "m-Oracul"),
        ("/robots.txt", "User-agent"),
        ("/sitemap.xml", "urlset"),
    ]
    for path, needle in routes:
        code, body = _get(f"{BASE}{path}")
        if code == 200 and needle.lower() in body.lower():
            ok(f"GET {path}", str(code))
        else:
            fail(f"GET {path}", f"code={code} needle={needle!r}")


def test_prod_webhook_ping() -> None:
    print("\n📡 Прод webhook /ping")
    admin = int((os.getenv("MONEY_ADMIN_IDS") or "0").split(",")[0])
    if admin <= 0:
        fail("webhook ping", "MONEY_ADMIN_IDS не задан")
        return
    uid = int(time.time())
    payload = {
        "update_id": uid,
        "message": {
            "message_id": uid,
            "date": uid,
            "chat": {"id": admin, "type": "private"},
            "from": {"id": admin, "is_bot": False, "first_name": "QA"},
            "text": "/ping",
            "entities": [{"offset": 0, "length": 5, "type": "bot_command"}],
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/webhook",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read().decode())
        elapsed = time.time() - t0
        if resp.get("ok") and elapsed >= 0.2:
            ok("webhook /ping", f"{elapsed:.2f}s")
        else:
            fail("webhook /ping", f"{resp} {elapsed:.2f}s")
    except Exception as e:
        fail("webhook /ping", str(e))


def test_unit_suite() -> None:
    print("\n🧪 scripts/test_oracle_all.py")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/test_oracle_all.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    tail = r.stdout[-800:] if r.stdout else r.stderr
    if r.returncode == 0:
        ok("test_oracle_all", "passed")
    else:
        fail("test_oracle_all", tail[-400:])


def test_handlers_commands() -> None:
    print("\n🤖 Команды бота")
    import inspect

    from oracle_bot import handlers as hmod

    src = inspect.getsource(hmod)
    cmds = ["start", "ping", "menu", "help", "ref", "stats", "premium", "stop_push"]
    for c in cmds:
        if f'Command("{c}")' in src or f"Command('{c}')" in src:
            ok(f"/{c}")
        else:
            fail(f"/{c}", "handler не найден в handlers.py")


async def test_async_ping_handler() -> None:
    print("\n⚡ Async handler /ping")
    from aiogram.types import Message, User, Chat
    from unittest.mock import AsyncMock, MagicMock

    from oracle_bot.handlers import cmd_ping

    user = User(id=123, is_bot=False, first_name="T")
    chat = Chat(id=123, type="private")
    msg = MagicMock(spec=Message)
    msg.from_user = user
    msg.chat = chat
    msg.answer = AsyncMock()
    try:
        await cmd_ping(msg)
        if msg.answer.called:
            ok("cmd_ping answer")
        else:
            fail("cmd_ping", "answer not called")
    except Exception as e:
        fail("cmd_ping", str(e))


def main() -> int:
    print("=" * 56)
    print("ГЛОБАЛЬНАЯ ПРОВЕРКА m-Oracul")
    print("=" * 56)
    test_storage_api()
    test_streak_middleware()
    test_handlers_commands()
    asyncio.run(test_async_ping_handler())
    test_landing_buttons()
    test_prod_http()
    test_prod_webhook_ping()
    test_unit_suite()

    print("\n" + "=" * 56)
    print(f"ПРОЙДЕНО: {len(PASSED)}")
    print(f"ПРОВАЛО: {len(FAILURES)}")
    if FAILURES:
        print("\nОшибки:")
        for f in FAILURES:
            print(f"  • {f}")
    print("=" * 56)
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
