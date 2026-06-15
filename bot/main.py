import asyncio
import os
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError
from aiohttp import ClientConnectorError

try:
    from aiohttp_socks import ProxyConnectionError
except ImportError:
    ProxyConnectionError = type(None)  # type: ignore[misc,assignment]

from bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_PROXY
from bot.handlers import setup_routers
from bot.services.history import init_db
from bot.services.telegram_net import create_telegram_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

POLLING_RETRY_SEC = 30
_LOCK_FILE = None


def _acquire_single_instance_lock() -> None:
    """Do not allow two polling loops for the same Telegram bot token."""
    global _LOCK_FILE
    try:
        import fcntl

        root = os.path.dirname(os.path.dirname(__file__))
        _LOCK_FILE = open(os.path.join(root, ".bot.lock"), "w")
        fcntl.flock(_LOCK_FILE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FILE.write(str(os.getpid()))
        _LOCK_FILE.flush()
    except BlockingIOError:
        logger.error("Другая копия бота уже запущена — выхожу, чтобы не ломать Telegram polling.")
        sys.exit(2)
    except Exception as e:
        logger.warning("Не удалось поставить single-instance lock: %s", e)


async def _startup_checks() -> None:
    from bot.config import (
        FREE_T2I_ENABLED,
        GEMINI_IMAGE_ENABLED,
        GROK_IMAGE_ENABLED,
        LAOZHANG_API_KEY,
        LAOZHANG_IMAGE_ENABLED,
        LLM_API_KEY,
        UNSPLASH_ACCESS_KEY,
        UNSPLASH_ENABLED,
    )
    from bot.services.health import check_llm_api

    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY пуст — ответы не будут работать")

    llm_ok, llm_detail = await check_llm_api()
    from bot.config import GEMINI_API_KEY, LLM_GEMINI_FALLBACK, LLM_PRIMARY
    from bot.services.gemini_llm import check_gemini_api
    from bot.services.llm import kupi_circuit_open

    gemini_ok, gemini_detail = False, "выключен"
    if LLM_GEMINI_FALLBACK and GEMINI_API_KEY:
        gemini_ok, gemini_detail = await check_gemini_api()

    if llm_ok:
        logger.info("Бот запущен · KupiAPI: OK")
    else:
        logger.warning("Бот запущен · KupiAPI: %s", llm_detail)

    if gemini_ok:
        logger.info(
            "Запасной LLM · Gemini: OK (%s) · режим %s",
            gemini_detail,
            LLM_PRIMARY,
        )
    elif LLM_GEMINI_FALLBACK and GEMINI_API_KEY:
        logger.warning("Запасной LLM · Gemini: %s", gemini_detail)

    if kupi_circuit_open():
        logger.info("KupiAPI circuit open — следующие запросы пойдут в Gemini")

    if FREE_T2I_ENABLED:
        try:
            from bot.services.free_t2i import check_api

            logger.info("Free T2I: %s", await check_api())
        except Exception as e:
            logger.warning("Free T2I: %s", e)

    if LAOZHANG_IMAGE_ENABLED and LAOZHANG_API_KEY:
        try:
            from bot.services.laozhang_image import check_api as lz_check

            logger.info("LaoZhang: %s", await lz_check())
        except Exception as e:
            logger.warning("LaoZhang: %s", e)

    if GROK_IMAGE_ENABLED or GEMINI_IMAGE_ENABLED:
        logger.info(
            "AI-картинки: grok=%s gemini=%s",
            "on" if GROK_IMAGE_ENABLED else "off",
            "on" if GEMINI_IMAGE_ENABLED else "off",
        )

    if UNSPLASH_ENABLED and UNSPLASH_ACCESS_KEY:
        try:
            from bot.services.unsplash import check_api as unsplash_check

            detail = await asyncio.wait_for(unsplash_check(), timeout=15)
            logger.info("Unsplash: %s", detail)
        except Exception as e:
            logger.warning("Unsplash: %s", e)

    from bot.config import GCP_PROJECT_ID, GCP_SPEECH_ENABLED

    if GCP_PROJECT_ID:
        try:
            from bot.services.google_cloud import check_gcp_speech, check_gcp_tts

            if GCP_SPEECH_ENABLED:
                from bot.services.google_cloud import ensure_gcp_apis_enabled

                await asyncio.get_event_loop().run_in_executor(
                    None, ensure_gcp_apis_enabled
                )
                ok, detail = await check_gcp_speech()
                logger.info("Google Cloud Speech: %s — %s", "OK" if ok else "FAIL", detail)
            ok_tts, detail_tts = await check_gcp_tts()
            logger.info("Google Cloud TTS: %s — %s", "OK" if ok_tts else "FAIL", detail_tts)
        except Exception as e:
            logger.warning("Google Cloud: %s", e)

    try:
        from bot.services.model_catalog import refresh_from_api

        ids = await refresh_from_api()
        if ids:
            logger.info("KupiAPI models: %d доступно", len(ids))
    except Exception as e:
        logger.warning("Models list: %s", e)


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Задайте TELEGRAM_BOT_TOKEN в файле .env")
        sys.exit(1)

    _acquire_single_instance_lock()
    await init_db()

    session = create_telegram_session()
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(setup_routers())

    await _startup_checks()

    if TELEGRAM_PROXY:
        logger.info("Telegram proxy: %s", TELEGRAM_PROXY)
    else:
        logger.warning(
            "TELEGRAM_PROXY не задан — если бот не подключается, "
            "добавьте в .env: TELEGRAM_PROXY=socks5://127.0.0.1:1080"
        )

    while True:
        try:
            logger.info("Подключение к Telegram…")
            await dp.start_polling(bot)
            break
        except (
            TelegramConflictError,
            TelegramNetworkError,
            OSError,
            asyncio.TimeoutError,
            ClientConnectorError,
            ProxyConnectionError,
        ) as e:
            logger.error(
                "Telegram недоступен: %s — повтор через %s с",
                e,
                POLLING_RETRY_SEC,
            )
            await asyncio.sleep(POLLING_RETRY_SEC)


if __name__ == "__main__":
    asyncio.run(main())
