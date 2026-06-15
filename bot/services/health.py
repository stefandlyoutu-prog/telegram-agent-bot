import time
from typing import Optional

import aiohttp

from bot.config import LLM_API_KEY, LLM_BASE_URL, LLM_CONNECT_TIMEOUT_SEC, LLM_PROXY

_last_check: dict = {"at": 0.0, "llm_ok": False, "llm_detail": "не проверялось"}
CACHE_SEC = 45


async def check_llm_api() -> tuple[bool, str]:
    global _last_check
    now = time.time()
    if now - _last_check["at"] < CACHE_SEC:
        return _last_check["llm_ok"], _last_check["llm_detail"]

    if not LLM_API_KEY:
        _last_check = {"at": now, "llm_ok": False, "llm_detail": "ключ не задан"}
        return False, "ключ не задан"

    url = f"{LLM_BASE_URL}/models"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    from bot.services.http_client import (
        format_client_error,
        llm_connection_modes,
        proxy_for_request,
        session_kwargs,
    )

    last_err: Optional[str] = None
    ok = False
    detail = "не проверялось"

    for use_proxy in llm_connection_modes():
        try:
            timeout = aiohttp.ClientTimeout(
                total=20,
                connect=LLM_CONNECT_TIMEOUT_SEC,
                sock_connect=LLM_CONNECT_TIMEOUT_SEC,
            )
            async with aiohttp.ClientSession(**session_kwargs(use_proxy)) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    proxy=proxy_for_request(use_proxy),
                ) as resp:
                    if resp.status == 200:
                        detail = "API отвечает" + (" (прокси)" if use_proxy else "")
                        ok = True
                        break
                    if resp.status == 401:
                        detail = "неверный ключ"
                        ok = False
                        break
                    if resp.status == 402:
                        detail = "нужно пополнить баланс"
                        ok = False
                        break
                    detail = f"код {resp.status}"
                    ok = False
                    break
        except Exception as e:
            last_err = format_client_error(e)
            continue

    if not ok and last_err and detail == "не проверялось":
        if "kupiapi" in last_err.lower() or "connect" in last_err.lower():
            detail = f"нет связи ({last_err})"
        else:
            detail = last_err

    _last_check = {"at": now, "llm_ok": ok, "llm_detail": detail}
    return ok, detail


async def build_status_report(bot, user_id: int, model_label: str) -> str:
    from bot.services.processing import is_user_busy

    llm_ok, llm_detail = await check_llm_api()
    tg_ok = True
    try:
        await bot.get_me()
    except Exception as e:
        tg_ok = False
        tg_detail = str(e)[:80]
    else:
        tg_detail = "подключён"

    from bot.config import GEMINI_API_KEY, LLM_GEMINI_FALLBACK

    from bot.services.llm import kupi_circuit_open

    gemini_fb_line = ""
    gemini_ok = False
    if LLM_GEMINI_FALLBACK and GEMINI_API_KEY:
        try:
            from bot.services.gemini_llm import check_gemini_api

            gemini_ok, g_detail = await check_gemini_api()
            gemini_fb_line = (
                f"\n{'🟢' if gemini_ok else '🟡'} Gemini (запасной LLM) — {g_detail}"
            )
        except Exception as e:
            gemini_fb_line = f"\n🟡 Gemini (запасной LLM) — {str(e)[:80]}"

    bot_line = (
        "🟢 <b>Работает</b>"
        if tg_ok and (llm_ok or gemini_ok)
        else "🔴 <b>Не работает</b>"
    )
    tg_line = f"{'🟢' if tg_ok else '🔴'} Telegram — {tg_detail}"
    llm_line = f"{'🟢' if llm_ok else '🔴'} KupiAPI — {llm_detail}{gemini_fb_line}"
    if kupi_circuit_open():
        llm_line += "\n🟡 KupiAPI временно отключён — используется Gemini"

    t2i_line = "⚪️ Free T2I — выключен"
    from bot.config import FREE_T2I_ENABLED, SELF_CHECK_ENABLED, TASK_ROUTER_ANNOUNCE

    if FREE_T2I_ENABLED:
        try:
            from bot.services.free_t2i import check_api

            t2i_detail = await check_api()
            t2i_ok = t2i_detail.startswith("OK")
            t2i_line = f"{'🟢' if t2i_ok else '🟡'} Free T2I — {t2i_detail}"
        except Exception as e:
            t2i_line = f"🔴 Free T2I — {str(e)[:80]}"

    from bot.config import (
        LAOZHANG_API_KEY,
        LAOZHANG_IMAGE_ENABLED,
        MESHY_API_KEY,
        UNSPLASH_ACCESS_KEY,
        UNSPLASH_ENABLED,
    )

    unsplash_line = "⚪️ Unsplash — выключен"
    if UNSPLASH_ENABLED and UNSPLASH_ACCESS_KEY:
        try:
            from bot.services.unsplash import check_api as unsplash_check

            unsplash_detail = await unsplash_check()
            unsplash_ok = unsplash_detail.startswith("OK")
            unsplash_line = f"{'🟢' if unsplash_ok else '🟡'} Unsplash — {unsplash_detail}"
        except Exception as e:
            unsplash_line = f"🔴 Unsplash — {str(e)[:80]}"

    lz_line = "⚪️ LaoZhang — выключен"
    if LAOZHANG_IMAGE_ENABLED and LAOZHANG_API_KEY:
        try:
            from bot.services.laozhang_image import check_api as lz_check

            lz_detail = await lz_check()
            lz_ok = lz_detail.startswith("OK")
            lz_line = f"{'🟢' if lz_ok else '🟡'} LaoZhang — {lz_detail}"
        except Exception as e:
            lz_line = f"🔴 LaoZhang — {str(e)[:80]}"

    meshy_line = f"{'🟢' if MESHY_API_KEY else '⚪️'} Meshy — {'ключ задан' if MESHY_API_KEY else 'ключ не задан'}"
    if MESHY_API_KEY:
        try:
            from bot.services.meshy_3d import get_meshy_balance

            bal = await get_meshy_balance()
            feats = "3D·текстуры·remesh·nano-banana·low-poly"
            if bal is not None:
                meshy_line = f"🟢 Meshy ({feats}) — {bal} кред."
            else:
                meshy_line = f"🟡 Meshy ({feats}) — баланс недоступен"
        except Exception as e:
            meshy_line = f"🟡 Meshy — {str(e)[:60]}"
    try:
        from bot.services.openscad import openscad_available

        openscad_line = f"{'🟢' if openscad_available() else '🟡'} OpenSCAD — {'найден' if openscad_available() else 'не найден'}"
    except Exception as e:
        openscad_line = f"🔴 OpenSCAD — {str(e)[:80]}"

    gcp_line = "⚪️ Google Cloud — выключен"
    from bot.config import GCP_PROJECT_ID, GCP_SPEECH_ENABLED

    if GCP_SPEECH_ENABLED and GCP_PROJECT_ID:
        try:
            from bot.services.google_cloud import check_gcp_speech

            gcp_ok, gcp_detail = await check_gcp_speech()
            gcp_line = f"{'🟢' if gcp_ok else '🟡'} Google Cloud — {gcp_detail}"
        except Exception as e:
            gcp_line = f"🔴 Google Cloud — {str(e)[:80]}"
    elif GCP_PROJECT_ID:
        gcp_line = "⚪️ Google Cloud — GCP_SPEECH_ENABLED=0"

    model_line = f"📎 Модель: <b>{model_label}</b>"

    if is_user_busy(user_id):
        work_line = "🟡 <b>Сейчас обрабатываю ваш запрос</b>"
    else:
        work_line = "⚪️ Свободен — жду сообщение или файл"

    return (
        f"{bot_line}\n\n"
        f"{tg_line}\n"
        f"{llm_line}\n"
        f"{t2i_line}\n"
        f"{unsplash_line}\n"
        f"{lz_line}\n"
        f"{meshy_line}\n"
        f"{openscad_line}\n"
        f"{gcp_line}\n"
        f"{'🟢' if TASK_ROUTER_ANNOUNCE else '⚪️'} Маршрутизация задач — "
        f"{'вкл' if TASK_ROUTER_ANNOUNCE else 'выкл'}\n"
        f"⚡ Автопилот — не спрашивает принтер (DEFAULT_AUTO_PROCEED)\n"
        f"{'🟢' if SELF_CHECK_ENABLED else '⚪️'} Самопроверка — "
        f"{'вкл (SELF_CHECK_ENABLED=0 чтобы выключить)' if SELF_CHECK_ENABLED else 'выкл'}\n"
        f"{model_line}\n\n"
        f"{work_line}"
    )
