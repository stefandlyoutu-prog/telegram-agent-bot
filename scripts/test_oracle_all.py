#!/usr/bin/env python3
"""Smoke-тест всех функций @MOracul_bot (LLM + storage + парсинг)."""

from __future__ import annotations

import asyncio
import random
import re
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle_bot import storage as db
from oracle_bot.config import ORACLE_FREE_PER_DAY, ORACLE_PREMIUM_STARS
from oracle_bot.groq_client import groq_configured
from oracle_bot.handlers import _DATE_RE
from oracle_bot.llm_helpers import oracle_chat, oracle_palm_reading
from oracle_bot.prompts import COMPAT_USER, DATING_USER, MAJOR_ARCANA, TAROT_USER

TEST_UID = 999_999_001


def _ok(name: str, detail: str = "") -> None:
    extra = f" — {detail}" if detail else ""
    print(f"  ✅ {name}{extra}")


def _fail(name: str, err: str) -> None:
    print(f"  ❌ {name}: {err}")


def test_config() -> bool:
    print("\n⚙️  Конфиг")
    ok = True
    if groq_configured():
        _ok("Groq API key (gsk_…)")
    else:
        _fail("Groq", "GROK_API_KEY не настроен")
        ok = False
    if ORACLE_PREMIUM_STARS > 0:
        _ok("Stars premium", f"{ORACLE_PREMIUM_STARS} XTR")
    else:
        _fail("Stars", "ORACLE_PREMIUM_STARS=0")
        ok = False
    _ok("Free limit", f"{ORACLE_FREE_PER_DAY}/день/модуль")
    return ok


def test_date_parse() -> bool:
    print("\n📅 Парсинг дат (совместимость)")
    cases = [
        ("15.03.1990 и 22.07.1992", ["15.03.1990", "22.07.1992"]),
        ("01/05/85, 12.12.2000", ["01/05/85", "12.12.2000"]),
        ("одна дата 15.03.1990", ["15.03.1990"]),
    ]
    ok = True
    for text, expected in cases:
        found = _DATE_RE.findall(text)
        if found == expected:
            _ok(repr(text), str(found))
        else:
            _fail(repr(text), f"ожидалось {expected}, получено {found}")
            ok = False
    return ok


def test_storage() -> bool:
    print("\n💾 Storage (лимиты / премиум)")
    db.init_db()
    ok = True
    # сброс usage для тестового юзера
    with db._connect() as conn:
        conn.execute("DELETE FROM usage WHERE user_id = ?", (TEST_UID,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (TEST_UID,))

    if db.can_use(TEST_UID, "tarot", ORACLE_FREE_PER_DAY):
        _ok("can_use (free)")
    else:
        _fail("can_use", "должен быть True для нового юзера")
        ok = False

    db.bump_usage(TEST_UID, "tarot")
    if db.usage_count(TEST_UID, "tarot") == 1:
        _ok("bump_usage")
    else:
        _fail("bump_usage", "count != 1")
        ok = False

    for _ in range(ORACLE_FREE_PER_DAY - 1):
        db.bump_usage(TEST_UID, "tarot")
    if not db.can_use(TEST_UID, "tarot", ORACLE_FREE_PER_DAY):
        _ok(f"лимит после {ORACLE_FREE_PER_DAY} запросов")
    else:
        _fail("лимит", f"can_use True при лимите={ORACLE_FREE_PER_DAY}")
        ok = False

    db.grant_premium(TEST_UID, days=30)
    if db.is_premium(TEST_UID):
        _ok("grant_premium / is_premium")
    else:
        _fail("premium", "не активировался")
        ok = False

    if db.can_use(TEST_UID, "tarot", ORACLE_FREE_PER_DAY):
        _ok("premium снимает лимит")
    else:
        _fail("premium bypass", "can_use False при премиуме")
        ok = False

    with db._connect() as conn:
        conn.execute("DELETE FROM usage WHERE user_id = ?", (TEST_UID,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (TEST_UID,))
    return ok


async def test_tarot() -> bool:
    print("\n🔮 Расклад (tarot)")
    cards = random.sample(MAJOR_ARCANA, 3)
    prompt = TAROT_USER.format(cards=", ".join(cards), question="что меня ждёт в любви?")
    try:
        text = await oracle_chat(prompt, temperature=0.85)
        if len(text) > 80:
            _ok("oracle_chat", f"{len(text)} симв., карты: {', '.join(cards)}")
            return True
        _fail("tarot", f"слишком короткий ответ: {text!r}")
        return False
    except Exception as e:
        _fail("tarot", str(e))
        return False


async def test_compat() -> bool:
    print("\n💕 Совместимость (compat)")
    prompt = COMPAT_USER.format(d1="15.03.1990", d2="22.07.1992")
    try:
        text = await oracle_chat(prompt, temperature=0.8)
        if len(text) > 80:
            _ok("oracle_chat", f"{len(text)} симв.")
            return True
        _fail("compat", f"короткий ответ: {text!r}")
        return False
    except Exception as e:
        _fail("compat", str(e))
        return False


async def test_dating() -> bool:
    print("\n💬 Отношения (dating)")
    prompt = DATING_USER.format(
        text="Познакомился в Tinder, переписка затихла. Хочу возобновить контакт."
    )
    try:
        text = await oracle_chat(prompt, temperature=0.8)
        if len(text) > 80:
            _ok("oracle_chat", f"{len(text)} симv.")
            return True
        _fail("dating", f"короткий ответ: {text!r}")
        return False
    except Exception as e:
        _fail("dating", str(e))
        return False


async def test_palm() -> bool:
    print("\n🖐 Ладонь (palm + vision)")
    try:
        from PIL import Image
    except ImportError:
        _fail("palm", "Pillow не установлен")
        return False

    img = Image.new("RGB", (400, 400), color=(210, 170, 140))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = buf.getvalue()

    try:
        text = await oracle_palm_reading(data, comment="тест")
        if len(text) > 80:
            _ok("oracle_palm_reading", f"{len(text)} симв.")
            return True
        _fail("palm", f"короткий ответ: {text!r}")
        return False
    except Exception as e:
        _fail("palm", str(e))
        return False


async def test_followup() -> bool:
    print("\n💬 Уточняющие вопросы (dialogue)")
    from oracle_bot.dialogue import answer_followup, build_reading_context, has_context

    uid = TEST_UID
    db.init_db()
    ctx = build_reading_context("Тестовое чтение: карта Солнце.", None, uid)
    db.save_session(uid, module="tarot", last_context=ctx)
    if not has_context(uid):
        _fail("has_context", "контекст не сохранился")
        return False
    _ok("save_session / has_context")

    class _FakeUser:
        id = uid

    class _FakeMessage:
        from_user = _FakeUser()

        async def answer(self, text: str):
            return _FakeWait()

    class _FakeWait:
        text = ""

        async def edit_text(self, text: str):
            _FakeWait.text = text

    msg = _FakeMessage()
    try:
        ok = await answer_followup(msg, "Что значит Солнце для меня?")
        if ok and len(_FakeWait.text) > 30:
            _ok("answer_followup", f"{len(_FakeWait.text)} симв.")
            return True
        _fail("followup", "answer_followup вернул False")
        return False
    except Exception as e:
        _fail("followup", str(e))
        return False


def test_revenue_bridge() -> bool:
    print("\n💰 Revenue bridge (каталог + gap)")
    from oracle_bot.revenue_bridge import load_catalog, register_gap, rule_match

    ok = True
    cat = load_catalog()
    if len(cat) >= 2:
        _ok("load_catalog", f"{len(cat)} продуктов")
    else:
        _fail("catalog", f"мало продуктов: {len(cat)}")
        ok = False

    matches = rule_match("хочу больше денег и карьеру", "career")
    if matches:
        _ok("rule_match", matches[0].get("title", "?")[:40])
    else:
        _fail("rule_match", "нет совпадений")
        ok = False

    slug = register_gap(
        user_id=TEST_UID,
        pain_summary="тест: юрист по наследству",
        proposal="бот-консультант по наследству",
        module="career",
        automation="manual",
    )
    if slug:
        _ok("register_gap", slug)
    else:
        _fail("register_gap", "пустой slug")
        ok = False
    return ok


def test_dialogue_storage() -> bool:
    print("\n🗂 Dialogue storage")
    db.init_db()
    uid = TEST_UID
    db.append_dialogue(uid, "user", "вопрос")
    db.append_dialogue(uid, "assistant", "ответ")
    with db._connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM dialogues WHERE user_id = ?", (uid,)
        ).fetchone()[0]
    if n >= 2:
        _ok("append_dialogue", f"{n} записей")
        return True
    _fail("dialogue", f"ожидалось >=2, got {n}")
    return False


def test_referral() -> bool:
    print("\n🎁 Реферальная программа")
    from oracle_bot.config import ORACLE_REFERRAL_BONUS, ORACLE_REFERRAL_WELCOME

    db.init_db()
    referrer = 999_999_010
    friend = 999_999_011
    ok = True
    with db._connect() as conn:
        conn.execute("DELETE FROM referrals WHERE referred_id IN (?, ?)", (referrer, friend))
        conn.execute("DELETE FROM users WHERE user_id IN (?, ?)", (referrer, friend))
        conn.execute("DELETE FROM usage WHERE user_id IN (?, ?)", (referrer, friend))

    db.ensure_user(referrer)
    db.ensure_user(friend)
    if db.register_referral(referrer, friend):
        _ok("register_referral")
    else:
        _fail("register_referral", "не зарегистрировался")
        ok = False

    if db.get_referral_credits(referrer) == ORACLE_REFERRAL_BONUS:
        _ok("бонус рефереру", str(ORACLE_REFERRAL_BONUS))
    else:
        _fail("referrer credits", str(db.get_referral_credits(referrer)))
        ok = False

    if db.get_referral_credits(friend) == ORACLE_REFERRAL_WELCOME:
        _ok("welcome другу", str(ORACLE_REFERRAL_WELCOME))
    else:
        _fail("friend welcome", str(db.get_referral_credits(friend)))
        ok = False

    for _ in range(ORACLE_FREE_PER_DAY):
        db.bump_usage(friend, "tarot")
    if db.can_use(friend, "tarot", ORACLE_FREE_PER_DAY):
        _ok("бонус снимает лимит")
    else:
        _fail("bonus bypass", "can_use False при наличии welcome-кредита")
        ok = False

    before = db.get_referral_credits(friend)
    db.bump_usage(friend, "tarot")
    after = db.get_referral_credits(friend)
    if after == before - 1:
        _ok("списание бонуса")
    else:
        _fail("consume", f"{before} -> {after}")
        ok = False

    with db._connect() as conn:
        conn.execute("DELETE FROM referrals WHERE referred_id IN (?, ?)", (referrer, friend))
        conn.execute("DELETE FROM users WHERE user_id IN (?, ?)", (referrer, friend))
        conn.execute("DELETE FROM usage WHERE user_id IN (?, ?)", (referrer, friend))
    return ok


def test_analytics() -> bool:
    print("\n📊 Analytics")
    db.init_db()
    uid = 999_999_020
    db.ensure_user(uid)
    db.log_event(uid, "reading", "tarot")
    db.record_payment(uid, "premium_30d", 99, "test")
    db.schedule_push(uid, "welcome_day1", delay_hours=999, context="{}")
    snap = db.analytics_snapshot()
    ok = True
    if snap["total_users"] >= 1:
        _ok("snapshot users", str(snap["total_users"]))
    else:
        _fail("snapshot", "no users")
        ok = False
    if snap["payments_count"] >= 1:
        _ok("payments tracked")
    else:
        _fail("payments", str(snap))
        ok = False
    with db._connect() as conn:
        conn.execute("DELETE FROM payments WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM events WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM push_queue WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM user_meta WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))

    from oracle_bot.analytics import format_funnel_report, funnel_snapshot

    f = funnel_snapshot()
    if "stages" in f and len(f["stages"]) >= 5:
        _ok("funnel_snapshot", str(len(f["stages"])))
    else:
        _fail("funnel_snapshot", str(f.keys()))
        ok = False
    txt = format_funnel_report()
    if "воронка" in txt.lower() or "CRM" in txt:
        _ok("format_funnel_report")
    else:
        _fail("format_funnel_report", txt[:60])
        ok = False
    return ok


def test_product_pages() -> bool:
    print("\n🌐 Продукт: лендинг / оферта / CRM")
    from oracle_bot.config import ORACLE_REFERRAL_UNLIMITED_AT, oferta_url

    ok = True
    ou = oferta_url()
    if "/oferta" in ou:
        _ok("oferta_url", ou)
    else:
        _fail("oferta_url", ou)
        ok = False
    if ORACLE_REFERRAL_UNLIMITED_AT == 10:
        _ok("referral unlimited at", "10")
    else:
        _fail("ORACLE_REFERRAL_UNLIMITED_AT", str(ORACLE_REFERRAL_UNLIMITED_AT))
        ok = False
    site = ROOT / "oracle_bot" / "static" / "site"
    for name in ("landing.html", "oferta.html", "admin.html"):
        p = site / name
        if p.is_file() and p.stat().st_size > 200:
            _ok(name)
        else:
            _fail(name, "missing or empty")
            ok = False
    return ok


async def test_telegram_bot_alive() -> bool:
    print("\n🤖 Telegram API (бот жив?)")
    from aiogram import Bot
    from bot.services.telegram_net import create_telegram_session
    from oracle_bot.config import ORACLE_BOT_TOKEN

    if not ORACLE_BOT_TOKEN:
        _fail("bot", "ORACLE_BOT_TOKEN пуст")
        return False
    bot = Bot(token=ORACLE_BOT_TOKEN, session=create_telegram_session())
    try:
        me = await bot.get_me()
        _ok("getMe", f"@{me.username} ({me.first_name})")
        return True
    except Exception as e:
        _fail("getMe", str(e))
        return False
    finally:
        await bot.session.close()


def test_access() -> bool:
    print("\n👑 Admin / full access")
    from oracle_bot.access import has_full_access, is_admin_user
    from business_dashboard.config import MONEY_ADMIN_IDS

    ok = True
    admin_id = next(iter(MONEY_ADMIN_IDS), 5845195049)
    if is_admin_user(admin_id):
        _ok("is_admin_user", str(admin_id))
    else:
        _fail("is_admin_user", f"MONEY_ADMIN_IDS={MONEY_ADMIN_IDS}")
        ok = False
    if has_full_access(admin_id):
        _ok("has_full_access admin")
    else:
        _fail("has_full_access admin", "admin should bypass limits")
        ok = False
    if db.can_use(admin_id, "tarot", 0):
        _ok("can_use admin unlimited")
    else:
        _fail("can_use admin", "expected True")
        ok = False
    return ok


def test_formatting() -> bool:
    print("\n📝 Formatting")
    from oracle_bot.formatting import format_reading_body

    wall = "Первое предложение. Второе предложение. Третье предложение. Четвёртое. Пятое. Шестое."
    out = format_reading_body(wall)
    if "\n\n" in out:
        _ok("paragraph breaks")
        return True
    _fail("paragraph breaks", out[:80])
    return False


def test_all_modules() -> bool:
    print("\n📋 All modules registered")
    from oracle_bot.handlers import _WAIT

    if len(_WAIT) >= 25:
        _ok("handler modules", str(len(_WAIT)))
        return True
    _fail("handler modules", f"only {len(_WAIT)}")
    return False


def test_broadcast_list() -> bool:
    print("\n📤 Broadcast users list")
    db.init_db()
    db.ensure_user(TEST_UID)
    ids = db.all_user_ids()
    if TEST_UID in ids:
        _ok("all_user_ids", f"{len(ids)} users")
        return True
    _fail("all_user_ids", "test user missing")
    return False


def test_import_webapp() -> bool:
    print("\n🚀 Import webapp (как на Render)")
    import asyncio

    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        from oracle_bot.webapp import app  # noqa: F401
        from oracle_bot.prompts import PSYCHOLOGY_USER  # noqa: F401

        _ok("oracle_bot.webapp + PSYCHOLOGY_USER")
        return True
    except Exception as e:
        _fail("import webapp", str(e))
        return False


async def main() -> int:
    print("=" * 50)
    print("Тест всех функций @MOracul_bot")
    print("=" * 50)

    results: list[tuple[str, bool]] = []
    results.append(("import_webapp", test_import_webapp()))
    results.append(("access", test_access()))
    results.append(("formatting", test_formatting()))
    results.append(("broadcast", test_broadcast_list()))
    results.append(("modules", test_all_modules()))
    results.append(("config", test_config()))
    results.append(("dates", test_date_parse()))
    results.append(("storage", test_storage()))
    results.append(("referral", test_referral()))
    results.append(("analytics", test_analytics()))
    results.append(("product_pages", test_product_pages()))
    results.append(("dialogue_storage", test_dialogue_storage()))
    results.append(("revenue", test_revenue_bridge()))
    results.append(("telegram", await test_telegram_bot_alive()))
    results.append(("tarot", await test_tarot()))
    results.append(("compat", await test_compat()))
    results.append(("dating", await test_dating()))
    results.append(("palm", await test_palm()))
    results.append(("followup", await test_followup()))

    print("\n" + "=" * 50)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\nИтого: {passed}/{total}")
    print("=" * 50)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
