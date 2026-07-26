#!/usr/bin/env python3
"""Один ролик в день: «Люди, рождённые сегодня N-го числа».

Один и тот же ролик выходит на YouTube Shorts, VK, TikTok и Instagram.
Повторный запуск безопасен: успешные площадки запоминаются в state.json.

Пример без публикации:
  .venv/bin/python scripts/birthday_daily_series.py --day 21 --render-only

Ежедневный запуск:
  .venv/bin/python scripts/birthday_daily_series.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from video_bot.content_product.assembler import build_product_video  # noqa: E402
from video_bot.promo import oracle_promo as op  # noqa: E402
from video_bot.promo.birthday_series import build_script, bot_link, topic_for_day  # noqa: E402
from video_bot.promo.distribute import post_uploadpost, post_vk, post_youtube  # noqa: E402

OUT = ROOT / "data" / "video_bot" / "promo" / "birthday_series"
STATE = OUT / "state.json"


def _read_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def render(day: int, *, force: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"born_{day:02d}.mp4"
    work = OUT / f"_tmp_born_{day:02d}"
    if out.exists() and out.stat().st_size > 100_000 and not force:
        return out
    # LLM-polировка иногда превращала CTA в служебную фразу
    # «ДИНАМИЧНАЯ МУЗЫКА». Для этой точной серии текст уже готов.
    os.environ["VIDEO_TTS_POLISH"] = "0"
    # Голос «диктора»: ash + инструкции радиоведущего; темп чуть живее
    os.environ["VIDEO_TTS_VOICE"] = os.environ.get("VIDEO_TTS_VOICE_BIRTHDAY", "ash")
    os.environ["VIDEO_TTS_INSTRUCTIONS"] = (
        "Speak Russian exactly like a skilled national TV news and documentary narrator "
        "(clear Moscow standard): warm baritone, crisp consonants, confident pacing, "
        "engaging but not theatrical. Deliver short facts like a top TikTok host — "
        "punchy, readable, zero mystical whisper."
    )
    os.environ.setdefault("VIDEO_TTS_SPEED", "1.22")
    os.environ.setdefault("VIDEO_TTS_EDGE_RATE", "+22%")
    return await build_product_video(
        build_script(day),
        out,
        work_dir=work,
        min_duration_sec=24.0,
        topic_key="horoscope",
    )


def _item(day: int, platform: str, video: Path, *, when: date) -> op.PromoItem:
    source = f"{platform[:2]}_birth{day}_{when:%m%d}"
    return op.PromoItem(
        date=when.isoformat(),
        platform=platform,
        slot=0,
        topic=topic_for_day(day),
        source=source,
        link=bot_link(day, platform),
        status="rendered",
        file=str(video),
        note=f"[birth-day:{day}] [series:daily]",
    )


def _day_ok(row: dict | None) -> bool:
    plats = (row or {}).get("platforms") or {}
    return any((plats.get(p) or {}).get("ok") for p in ("vk", "tiktok"))


def publish(day: int, video: Path, *, when: date | None = None) -> dict:
    """Публикация. when — календарная дата выпуска (для догона пропущенных дней)."""
    when = when or date.today()
    state = _read_state()
    key = when.isoformat()
    row = state.setdefault(key, {"day": day, "video": str(video), "platforms": {}})
    row["day"] = day
    row["video"] = str(video)
    results: dict[str, dict] = {}

    if row["platforms"].get("youtube", {}).get("ok") is not True:
        res = post_youtube(_item(day, "youtube", video, when=when))
        row["platforms"]["youtube"] = {"ok": res.ok, "status": res.status, "url": res.url, "error": res.error}
        results["youtube"] = row["platforms"]["youtube"]
        _save_state(state)

    if row["platforms"].get("vk", {}).get("ok") is not True:
        res = post_vk(_item(day, "vk", video, when=when))
        row["platforms"]["vk"] = {"ok": res.ok, "status": res.status, "url": res.url, "error": res.error}
        results["vk"] = row["platforms"]["vk"]
        _save_state(state)

    # Instagram @moracul_taro отключён Meta (19.07.2026) — не постим, пока не будет нового аккаунта.
    skip_ig = os.getenv("BIRTHDAY_SKIP_INSTAGRAM", "1").strip().lower() not in ("0", "false", "no")
    upload_platforms = ["tiktok"]
    if not skip_ig:
        upload_platforms.append("instagram")

    for platform in upload_platforms:
        if row["platforms"].get(platform, {}).get("ok") is True:
            continue
        res = post_uploadpost(
            _item(day, platform, video, when=when),
            platforms=[platform],
        )
        row["platforms"][platform] = {
            "ok": res.ok,
            "status": res.status,
            "url": res.url,
            "error": res.error,
        }
        results[platform] = row["platforms"][platform]
        _save_state(state)

    if skip_ig and "instagram" not in row["platforms"]:
        row["platforms"]["instagram"] = {
            "ok": False,
            "status": "skipped",
            "url": "",
            "error": "аккаунт отключён Meta; ждём новый IG",
        }
        _save_state(state)

    return results


def catch_up(*, lookback: int = 7, force_render: bool = False, render_only: bool = False) -> int:
    """Догоняет пропуски за lookback дней (включая сегодня). Возвращает число неудач."""
    today = date.today()
    start_raw = os.getenv("BIRTHDAY_SERIES_START", "2026-07-20").strip()
    try:
        series_start = date.fromisoformat(start_raw) if start_raw else date(2026, 7, 20)
    except ValueError:
        series_start = date(2026, 7, 20)
    state = _read_state()
    failures = 0
    for delta in range(lookback, -1, -1):
        when = today - timedelta(days=delta)
        if when < series_start:
            continue
        key = when.isoformat()
        if _day_ok(state.get(key)):
            print(f"SKIP {key} already ok", flush=True)
            continue
        day = when.day
        print(f"CATCH-UP {key} day={day}", flush=True)
        try:
            video = asyncio.run(render(day, force=force_render))
            print(f"RENDERED {video} ({video.stat().st_size} bytes)", flush=True)
            if render_only:
                continue
            results = publish(day, video, when=when)
            print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
            state = _read_state()
            if not _day_ok(state.get(key)):
                failures += 1
                print(f"FAIL {key}: VK/TikTok не вышли", flush=True)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {key}: {e}", flush=True)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=int, help="число 1–31; по умолчанию сегодняшнее")
    parser.add_argument("--date", type=str, help="YYYY-MM-DD дата выпуска (для догона одного дня)")
    parser.add_argument("--catch-up", action="store_true", help="догонить пропуски за --lookback дней")
    parser.add_argument("--lookback", type=int, default=7, help="дней назад для --catch-up (вкл. сегодня)")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--force-render", action="store_true")
    args = parser.parse_args()

    # Edge TTS по умолчанию — OpenAI квота часто 429
    os.environ.setdefault("VIDEO_TTS_ENGINE", "edge")
    os.environ.setdefault("VIDEO_TTS_POLISH", "0")

    if args.catch_up:
        bad = catch_up(
            lookback=max(0, args.lookback),
            force_render=args.force_render,
            render_only=args.render_only,
        )
        raise SystemExit(1 if bad else 0)

    when = date.today()
    if args.date:
        when = date.fromisoformat(args.date)
    day = args.day or when.day
    if not 1 <= day <= 31:
        raise SystemExit("--day должен быть от 1 до 31")

    video = asyncio.run(render(day, force=args.force_render))
    print(f"RENDERED {video} ({video.stat().st_size} bytes)")
    if args.render_only:
        return
    results = publish(day, video, when=when)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    # Успех дня: хотя бы VK или TikTok вышли. YouTube/IG не роняют весь cron.
    critical = [results[k] for k in ("vk", "tiktok") if k in results]
    if critical and not any(r.get("ok") for r in critical):
        raise SystemExit(1)
    state = _read_state().get(when.isoformat(), {})
    plats = state.get("platforms") or {}
    if not any((plats.get(k) or {}).get("ok") for k in ("vk", "tiktok")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
