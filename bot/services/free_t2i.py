"""Бесплатный T2I API (mcpcore / subnp): POST /api/free/generate (SSE)."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from bot.config import (
    FREE_T2I_BASE_URL,
    FREE_T2I_ENABLED,
    FREE_T2I_FALLBACK_URL,
    FREE_T2I_MODEL,
    FREE_T2I_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


class FreeT2IError(Exception):
    pass


def _bases() -> List[str]:
    out: List[str] = []
    for url in (FREE_T2I_BASE_URL, FREE_T2I_FALLBACK_URL):
        u = (url or "").strip().rstrip("/")
        if u and u not in out:
            out.append(u)
    return out


async def fetch_models() -> Dict[str, Any]:
    """GET /api/free/models — список моделей или ошибка."""
    last_err: Optional[str] = None
    async with aiohttp.ClientSession() as session:
        for base in _bases():
            url = f"{base}/api/free/models"
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        last_err = f"{base}: HTTP {resp.status}"
                        continue
                    return json.loads(text)
            except Exception as e:
                last_err = f"{base}: {e}"
    return {"success": False, "error": last_err or "нет доступных URL"}


async def fetch_stats() -> Dict[str, Any]:
    last_err: Optional[str] = None
    async with aiohttp.ClientSession() as session:
        for base in _bases():
            url = f"{base}/api/free/stats"
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        last_err = f"{base}: HTTP {resp.status}"
                        continue
                    return json.loads(text)
            except Exception as e:
                last_err = f"{base}: {e}"
    return {"success": False, "error": last_err or "нет доступных URL"}


def _parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


async def _generate_on_base(
    session: aiohttp.ClientSession,
    base: str,
    prompt: str,
    model: str,
) -> str:
    url = f"{base}/api/free/generate"
    payload = {"prompt": prompt, "model": model}
    image_url: Optional[str] = None
    last_message = ""

    async with session.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=aiohttp.ClientTimeout(total=FREE_T2I_TIMEOUT_SEC),
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise FreeT2IError(f"HTTP {resp.status}: {body[:300]}")

        buffer = ""
        async for chunk in resp.content.iter_any():
            if not chunk:
                continue
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                data = _parse_sse_line(line)
                if not data:
                    continue
                status = data.get("status")
                if data.get("message"):
                    last_message = str(data["message"])
                if status == "processing":
                    logger.debug("free-t2i [%s]: %s", base, last_message)
                elif status == "complete":
                    image_url = data.get("imageUrl") or data.get("image_url")
                    if image_url:
                        return image_url
                elif status == "error":
                    msg = data.get("message") or data.get("error") or last_message
                    raise FreeT2IError(str(msg))

        if buffer.strip():
            for line in buffer.splitlines():
                data = _parse_sse_line(line)
                if data and data.get("status") == "complete":
                    image_url = data.get("imageUrl") or data.get("image_url")
                    if image_url:
                        return image_url

    raise FreeT2IError(last_message or "нет imageUrl в SSE-ответе")


async def generate_image(
    prompt: str,
    *,
    model: Optional[str] = None,
) -> Tuple[bytes, str, str]:
    """
    Генерация по текстовому промпту.
    Возвращает (bytes, mime, base_url).
    """
    if not FREE_T2I_ENABLED:
        raise FreeT2IError("FREE_T2I_ENABLED=0")

    model = model or FREE_T2I_MODEL
    last_err: Optional[Exception] = None

    async with aiohttp.ClientSession() as session:
        for base in _bases():
            try:
                image_url = await _generate_on_base(session, base, prompt, model)
                async with session.get(
                    image_url, timeout=aiohttp.ClientTimeout(total=120)
                ) as dl:
                    if dl.status != 200:
                        raise FreeT2IError(f"скачивание: HTTP {dl.status}")
                    raw = await dl.read()
                    ctype = dl.headers.get("Content-Type", "image/png")
                    mime = ctype.split(";")[0].strip() or "image/png"
                    return raw, mime, base
            except Exception as e:
                last_err = e
                logger.info("free-t2i %s: %s", base, e)

    if last_err:
        raise FreeT2IError(str(last_err))
    raise FreeT2IError("не настроен FREE_T2I_BASE_URL")


async def check_api() -> str:
    """Краткий статус для логов и /status."""
    models = await fetch_models()
    stats = await fetch_stats()
    bases = ", ".join(_bases()) or "(нет URL)"
    if models.get("success") and models.get("models"):
        names = [m.get("model", "?") for m in models["models"][:5]]
        return f"OK · {bases} · модели: {', '.join(names)}"
    err = models.get("error") or stats.get("message") or stats.get("error") or "недоступен"
    return f"ошибка · {bases} · {err}"
