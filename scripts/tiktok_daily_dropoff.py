#!/usr/bin/env python3
"""Ежедневная поставка TikTok-роликов в ~/Downloads для ручной загрузки.

Владелец вечером заливает ролики на следующий день (у TikTok нет бесплатного API
для автопостинга без одобренного dev-приложения). Скрипт:

1. Берёт из плана 5 TikTok-роликов на завтра (добивает план, если их меньше).
2. Рендерит недостающие.
3. Складывает готовые mp4 в ~/Downloads/TikTok_<дата>/ + файл ОПИСАНИЯ.txt
   с текстом под каждый ролик (осталось скопировать и вставить).
4. Шлёт владельцу в Telegram уведомление со списком.

Запуск вручную:  .venv/bin/python scripts/tiktok_daily_dropoff.py
Планировщик:     launchd com.oracle.tiktokdropoff (17:00 ежедневно)
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import os  # noqa: E402

from video_bot.promo import oracle_promo as op  # noqa: E402

# 1–2 ролика в день: щадящий режим для TikTok (уходим от бана spam_risk).
PER_DAY = max(1, int(os.getenv("VIDEO_TIKTOK_PER_DAY", "2")))
DOWNLOADS = Path.home() / "Downloads"

_HASHTAGS = [
    "#таро #гороскоп #эзотерика #предсказания #знакизодиака",
    "#таро #любовь #расклад #гороскоп #эзотерика",
    "#гороскоп #знакизодиака #таро #судьба #предсказание",
    "#таро #раскладтаро #эзотерика #мистика #гадание",
    "#гороскопнасегодня #таро #знакизодиака #вселенная #эзотерика",
]


_BOT_LINK = "https://t.me/MOracul_bot?start=src_instagram"


def _caption(topic: str, idx: int) -> str:
    return (
        f"{topic} 🌙\n"
        f"2 сценария судьбы — бесплатно 👇\n"
        f"{_BOT_LINK}\n"
        f"{_HASHTAGS[idx % len(_HASHTAGS)]}"
    )


def _ensure_items(plan: list, day: date) -> list:
    """5 tiktok-элементов плана на дату (добавляет недостающие слоты)."""
    day_iso = day.isoformat()
    items = [i for i in plan if i.platform == "tiktok" and i.date == day_iso]
    have_slots = {i.slot for i in items}
    used_topics = {i.topic for i in items}
    topic_offset = abs(hash(day_iso)) % len(op.ORACLE_TOPICS)
    step = 0
    for slot in range(1, PER_DAY + 1):
        if slot in have_slots:
            continue
        topic = op.ORACLE_TOPICS[(topic_offset + slot + step) % len(op.ORACLE_TOPICS)]
        while topic in used_topics:
            step += 1
            topic = op.ORACLE_TOPICS[(topic_offset + slot + step) % len(op.ORACLE_TOPICS)]
        used_topics.add(topic)
        src = op.source_code("tiktok", day, slot)
        items.append(
            op.PromoItem(
                date=day_iso, platform="tiktok", slot=slot, topic=topic,
                source=src, link=op.deeplink(src),
            )
        )
        plan.append(items[-1])
    items.sort(key=lambda i: i.slot)
    return items[:PER_DAY]


def _notify(text: str) -> None:
    token = os.getenv("ORACLE_BOT_TOKEN", "").strip()
    admin = os.getenv("MONEY_ADMIN_IDS", "").split(",")[0].strip()
    if not token or not admin.isdigit():
        return
    try:
        body = json.dumps({"chat_id": int(admin), "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass


def main() -> None:
    target = date.today() + timedelta(days=1)
    if len(sys.argv) > 1:
        target = date.fromisoformat(sys.argv[1])

    plan = op.load_plan()
    if not plan:
        plan = op.build_month_plan(date.today(), {"tiktok": PER_DAY, "vk": 2, "telegram": 2}, days=30)
    items = _ensure_items(plan, target)
    op.save_plan(plan)

    out_render = ROOT / "data" / "video_bot" / "promo" / "out" / target.isoformat()
    drop_dir = DOWNLOADS / f"TikTok_{target.isoformat()}"
    if not os.getenv("UPLOAD_POST_API_KEY", "").strip():
        drop_dir.mkdir(parents=True, exist_ok=True)

    async def _render_all() -> None:
        for it in items:
            if it.status in {"rendered", "posted"} and it.file and Path(it.file).exists():
                continue
            try:
                path = await op.render_item(it, out_render)
                it.status = "rendered"
                it.file = str(path)
                print(f"OK  render {it.source}")
            except Exception as e:  # noqa: BLE001
                it.status = "failed"
                it.note = str(e)[:200]
                print(f"FAIL render {it.source}: {e}")
            op.save_plan(plan)

    asyncio.run(_render_all())

    # ── Автопостинг через upload-post.com (если настроен ключ) ──
    if os.getenv("UPLOAD_POST_API_KEY", "").strip():
        from video_bot.promo.distribute import post_uploadpost, uploadpost_platforms
        from video_bot.promo.tiktok_guard import tiktok_posting_disabled

        plats = uploadpost_platforms()
        if tiktok_posting_disabled() and "tiktok" in plats:
            plats = [p for p in plats if p != "tiktok"]
            print("TikTok отключён (spam_risk) — постим только:", plats)
        label = "+".join(p.upper() for p in plats)
        slots_h = [9, 12, 15, 18, 21]  # время выхода по Москве
        posted = failed = 0
        report: list[str] = []
        for idx, it in enumerate(items):
            if not it.file or not Path(it.file).exists():
                failed += 1
                report.append(f"✖ {it.topic[:40]} — рендер не удался")
                continue
            when = f"{target.isoformat()}T{slots_h[idx % len(slots_h)]:02d}:00:00"
            res = post_uploadpost(it, platforms=plats or None, scheduled_iso=when)
            if res.ok:
                posted += 1
                it.status = "posted"
                report.append(f"✔ {slots_h[idx % len(slots_h)]:02d}:00 — {it.topic[:40]}")
            else:
                failed += 1
                report.append(f"✖ {it.topic[:40]} — {res.error[:80]}")
            op.save_plan(plan)
        print(f"Автопостинг {label}: {posted} запланировано, {failed} ошибок")
        _notify(
            f"🤖 <b>{label} на {target.strftime('%d.%m')}: {posted}/{PER_DAY} роликов запланировано автоматически</b>\n"
            + "\n".join(report)
            + ("\n\n⚠️ Есть ошибки — файлы остались в папке рендера." if failed else "\nНичего загружать не нужно.")
        )
        return

    lines = [
        f"РОЛИКИ TIKTOK НА {target.strftime('%d.%m.%Y')} — {PER_DAY} шт",
        "Залей через tiktok.com/tiktokstudio/upload (можно «Запланировать» на завтра).",
        "Описание под каждым файлом — скопируй целиком.",
        "",
    ]
    ok_count = 0
    for idx, it in enumerate(items):
        if not it.file or not Path(it.file).exists():
            lines.append(f"[{idx + 1}] {it.topic} — РЕНДЕР НЕ УДАЛСЯ: {it.note}")
            lines.append("")
            continue
        dst = drop_dir / f"{idx + 1}_{Path(it.file).name}"
        shutil.copy2(it.file, dst)
        ok_count += 1
        lines.append(f"[{idx + 1}] Файл: {dst.name}")
        lines.append(f"Описание: {_caption(it.topic, idx)}")
        lines.append("")
    (drop_dir / "ОПИСАНИЯ.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"Готово: {ok_count}/{PER_DAY} роликов в {drop_dir}")
    _notify(
        f"🎬 <b>TikTok на {target.strftime('%d.%m')}: {ok_count} роликов готово</b>\n"
        f"Папка: <code>{drop_dir}</code>\n"
        "Описания в файле ОПИСАНИЯ.txt — скопируй под каждый ролик.\n"
        "Загрузка: tiktok.com/tiktokstudio/upload (кнопка «Запланировать» — и посты выйдут сами)."
    )


if __name__ == "__main__":
    main()
