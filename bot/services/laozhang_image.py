"""LaoZhang API — OpenAI-совместимые images/generations и images/edits."""

import base64
import logging
from typing import Tuple

import aiohttp

from bot.config import (
    LAOZHANG_API_KEY,
    LAOZHANG_BASE_URL,
    LAOZHANG_IMAGE_MODEL,
    LAOZHANG_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


class LaoZhangError(Exception):
    pass


def _headers_json() -> dict:
    return {
        "Authorization": f"Bearer {LAOZHANG_API_KEY}",
        "Content-Type": "application/json",
    }


def _parse_item(item: dict) -> Tuple[bytes, str]:
    if item.get("b64_json"):
        return base64.standard_b64decode(item["b64_json"]), "image/png"
    if item.get("url"):
        return item["url"], "url"
    raise LaoZhangError("В ответе нет b64_json и url")


async def _download(session: aiohttp.ClientSession, url: str) -> Tuple[bytes, str]:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as r:
        if r.status != 200:
            raise LaoZhangError(f"скачивание: HTTP {r.status}")
        raw = await r.read()
        ctype = r.headers.get("Content-Type", "image/png")
        return raw, ctype.split(";")[0].strip() or "image/png"


async def generate_image(prompt: str, *, size: str = "1024x1024") -> Tuple[bytes, str]:
    if not LAOZHANG_API_KEY:
        raise LaoZhangError("LAOZHANG_API_KEY не задан")

    url = f"{LAOZHANG_BASE_URL}/images/generations"
    payload = {
        "model": LAOZHANG_IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    timeout = aiohttp.ClientTimeout(total=LAOZHANG_TIMEOUT_SEC)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=_headers_json(), timeout=timeout
        ) as resp:
            data = await resp.json()
            if resp.status != 200 or data.get("error"):
                err = data.get("error", {})
                msg = err.get("message", str(data)) if isinstance(err, dict) else str(err)
                raise LaoZhangError(f"generations ({resp.status}): {msg}")
        item = (data.get("data") or [{}])[0]
        result = _parse_item(item)
        if result[1] == "url":
            return await _download(session, result[0])
        return result


async def edit_image(
    image_data: bytes,
    prompt: str,
    *,
    mime: str = "image/png",
    size: str = "1024x1024",
) -> Tuple[bytes, str]:
    if not LAOZHANG_API_KEY:
        raise LaoZhangError("LAOZHANG_API_KEY не задан")

    url = f"{LAOZHANG_BASE_URL}/images/edits"
    ext = "png" if "png" in mime else "jpeg"
    form = aiohttp.FormData()
    form.add_field("model", LAOZHANG_IMAGE_MODEL)
    form.add_field("prompt", prompt)
    form.add_field("n", "1")
    form.add_field("size", size)
    form.add_field(
        "image",
        image_data,
        filename=f"photo.{ext}",
        content_type=mime,
    )
    headers = {"Authorization": f"Bearer {LAOZHANG_API_KEY}"}
    timeout = aiohttp.ClientTimeout(total=LAOZHANG_TIMEOUT_SEC)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, headers=headers, timeout=timeout) as resp:
            data = await resp.json()
            if resp.status != 200 or data.get("error"):
                err = data.get("error", {})
                msg = err.get("message", str(data)) if isinstance(err, dict) else str(err)
                raise LaoZhangError(f"edits ({resp.status}): {msg}")
        item = (data.get("data") or [{}])[0]
        result = _parse_item(item)
        if result[1] == "url":
            return await _download(session, result[0])
        return result


async def list_image_models_report() -> str:
    """Список моделей LaoZhang и быстрая проверка доступности."""
    if not LAOZHANG_API_KEY:
        return "LAOZHANG_API_KEY не задан в .env"

    lines = ["<b>Модели LaoZhang (картинки)</b>\n"]
    url = f"{LAOZHANG_BASE_URL}/models"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={"Authorization": f"Bearer {LAOZHANG_API_KEY}"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            data = await resp.json()
    all_ids = [m.get("id", "") for m in data.get("data", [])]
    img_kw = ("image", "dall", "flux", "gpt-image", "sora", "imagen")
    img_models = [m for m in all_ids if any(k in m.lower() for k in img_kw)]

    probe_models = [
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-4o-image",
        "dall-e-3",
        "gemini-2.5-flash-image",
        "flux-kontext-pro",
    ]
    lines.append(f"В каталоге ~{len(img_models)} image-моделей.\n")
    lines.append("<b>Проверка (сейчас):</b>")
    for model in probe_models:
        if model not in all_ids and not any(model in x for x in all_ids):
            continue
        test_url = f"{LAOZHANG_BASE_URL}/images/generations"
        payload = {"model": model, "prompt": "test", "n": 1, "size": "512x512"}
        status = "?"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    test_url,
                    json=payload,
                    headers=_headers_json(),
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as r:
                    d = await r.json()
                    err = d.get("error") or {}
                    msg = err.get("message", "ok") if isinstance(err, dict) else "ok"
                    if r.status == 200 and not d.get("error"):
                        status = "✅ доступна"
                    elif "配额" in str(msg) or "quota" in str(msg).lower():
                        status = "⚠️ нет квоты / баланса"
                    elif "无可用渠道" in str(msg) or "not found" in str(msg).lower():
                        status = "❌ нет канала на тарифе"
                    else:
                        status = f"❌ {str(msg)[:60]}"
        except Exception as e:
            status = f"❌ {str(e)[:50]}"
        lines.append(f"• <code>{model}</code> — {status}")

    lines.append(
        "\n<i>«Бесплатно» = только если на аккаунте есть баланс/пробные кредиты. "
        "Пополнение: api.laozhang.ai</i>"
    )
    return "\n".join(lines)


async def check_api() -> str:
    if not LAOZHANG_API_KEY:
        return "ключ не задан"
    try:
        url = f"{LAOZHANG_BASE_URL}/models"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {LAOZHANG_API_KEY}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    return "неверный ключ"
                if resp.status != 200:
                    return f"HTTP {resp.status}"
        return f"OK · модель {LAOZHANG_IMAGE_MODEL}"
    except Exception as e:
        return str(e)[:80]
