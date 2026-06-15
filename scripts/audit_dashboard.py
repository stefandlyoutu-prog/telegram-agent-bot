#!/usr/bin/env python3
"""Полная проверка Центра доходов — запуск: python3 scripts/audit_dashboard.py"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8765"


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    FAILURES.append(msg)


FAILURES: list[str] = []


def http_get(path: str) -> tuple[int, dict | list]:
    try:
        with urllib.request.urlopen(BASE + path) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except urllib.error.URLError as e:
        fail(f"Сервер не запущен ({BASE}): {e}")
        return 0, {}


def http_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def audit_python() -> None:
    print("\n[Python / SQLite]")
    from business_dashboard.storage import init_db, get_dashboard, enrich_idea, get_done_asset_keys
    from business_dashboard.registry import SEED_IDEAS
    from business_dashboard.idea_scout import list_opportunities

    init_db()
    ok("init_db")

    slugs = [i["slug"] for i in SEED_IDEAS]
    if len(slugs) != len(set(slugs)):
        fail("Дубликаты slug в registry")
    else:
        ok(f"registry: {len(slugs)} уникальных slug")

    d = get_dashboard()
    ok(f"ideas: {len(d['all'])}, opps: {len(d['opportunities'])}, assets: {len(d['user_assets'])}")

    for o in list_opportunities():
        if any(ord(c) > 127 for c in o["slug"]):
            fail(f"Кириллица в slug: {o['slug']}")
            break
    else:
        ok("все slug opportunities — ASCII")

    done = get_done_asset_keys()
    enriched = enrich_idea(d["all"][0], done)
    if "effective_action" not in enriched:
        fail("enrich_idea без effective_action")
    else:
        ok("enrich_idea + активы")


def audit_api() -> None:
    print("\n[HTTP API]")
    endpoints = ["/api/dashboard", "/api/spheres", "/api/chart", "/api/scout", "/api/assets", "/api/today/plan"]
    for ep in endpoints:
        code, data = http_get(ep)
        if code != 200:
            fail(f"{ep} → {code}")
        else:
            ok(f"{ep}")

    code, dash = http_get("/api/dashboard")
    if code == 200:
        m = dash.get("metrics", {})
        if "target_today" not in m or "gap" not in m:
            fail("metrics неполные")
        else:
            ok("metrics: план/факт/разрыв")

    code, _ = http_json("POST", "/api/scout/scout-tarot-telegram/launch")
    if code not in (200, 404):
        fail(f"launch ASCII slug → {code}")
    else:
        ok("launch opportunity (ASCII URL)")

    code, _ = http_json("PATCH", "/api/scout/bad-slug", {"stage": "nope"})
    if code not in (400, 404):
        fail(f"невалидный stage → {code}")
    else:
        ok("валидация stage")


def audit_bot() -> None:
    print("\n[Telegram /money]")
    try:
        from bot.handlers.money import cmd_money  # noqa: F401
        ok("импорт money handler")
    except ImportError as e:
        if "aiogram" in str(e):
            print("  ⚠ aiogram не в system python — OK если бот в venv")
        else:
            fail(f"money handler: {e}")


def main() -> int:
    print("=== Аудит Центра доходов ===")
    audit_python()
    audit_api()
    audit_bot()
    print(f"\nИтого: {len(FAILURES)} ошибок")
    for f in FAILURES:
        print(f"  - {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
