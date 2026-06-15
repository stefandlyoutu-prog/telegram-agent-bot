"""Карточки для объявлений: Unsplash-фон + шаблон Avito."""

import asyncio
import base64
import io
import logging
import re
from typing import Optional, Tuple

import aiohttp

from bot.config import (
    GEMINI_API_KEY,
    GROK_API_KEY,
    GROK_IMAGE_MODEL,
    IMAGE_EDIT_MODEL,
    IMAGE_GENERATION_MODEL,
    IMAGE_OUTPUT_ENABLED,
    IMAGE_PROVIDER_ORDER,
    LLM_API_KEY,
    LLM_BASE_URL,
)

logger = logging.getLogger(__name__)

_GEMINI_IMAGE_MODELS = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
)

PDF_INTENT_PATTERN = re.compile(
    r"pdf|пдф|\.pdf|seo|сео|текст.{0,12}(объявлен|авито|карточк)",
    re.IGNORECASE,
)

IMAGE_INTENT_PATTERN = re.compile(
    r"карточк|обложк|макет|авито|отредакт|обработ|"
    r"убери.{0,12}фон|добавь.{0,12}текст|готов.{0,12}(jpg|png|фото|картин)|"
    r"выдай.{0,12}(фото|картин|jpg|png)|nano|banana|визуал|без текста|"
    r"нарисуй|сгенерир.{0,12}картин|иллюстрац|концепт|референс",
    re.IGNORECASE,
)

TEXT_ONLY_REFUSAL = re.compile(
    r"не могу.{0,40}(физическ|отредактир|выдать|создать|сгенерировать|прикрепить).{0,30}"
    r"(jpg|png|фото|файл|изображ|stl|excel|xlsx|word|docx|pdf|документ)|"
    r"опишите|промпт для|canva|photoshop|figma|напишите одно слово",
    re.IGNORECASE,
)


class ImageOutputError(Exception):
    pass


def _provider_sequence() -> list[str]:
    order = (IMAGE_PROVIDER_ORDER or "auto").lower()
    providers = []
    if order == "grok":
        providers = ["grok", "gemini", "kupiapi"]
    elif order == "gemini":
        providers = ["gemini", "grok", "kupiapi"]
    else:
        providers = ["grok", "gemini", "kupiapi"]

    available = []
    for name in providers:
        if name == "grok" and GROK_API_KEY:
            available.append(name)
        elif name == "gemini" and GEMINI_API_KEY:
            available.append(name)
        elif name == "kupiapi" and LLM_API_KEY:
            available.append(name)
    return available


async def _download_url(url: str) -> Tuple[bytes, str]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=180)) as r:
            if r.status != 200:
                raise ImageOutputError(f"Не удалось скачать картинку: {r.status}")
            raw = await r.read()
            ctype = r.headers.get("Content-Type", "image/png")
            return raw, ctype.split(";")[0].strip() or "image/png"


def _grok_data_url(image_data: bytes, mime: str) -> str:
    b64 = base64.standard_b64encode(image_data).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def _grok_parse_response(data: dict) -> Tuple[bytes, str]:
    items = data.get("data") or []
    if not items:
        raise ImageOutputError("Grok не вернул изображение")
    item = items[0]
    mime = item.get("mime_type") or "image/png"
    if item.get("b64_json"):
        return base64.standard_b64decode(item["b64_json"]), mime
    if item.get("url"):
        raw, dl_mime = await _download_url(item["url"])
        return raw, dl_mime
    raise ImageOutputError("Grok: нет b64_json/url")


async def _grok_edit(image_data: bytes, mime: str, prompt: str) -> Tuple[bytes, str]:
    """Редактирование по исходному фото (xAI Imagine)."""
    url = "https://api.x.ai/v1/images/edits"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROK_IMAGE_MODEL,
        "prompt": prompt,
        "image": {"url": _grok_data_url(image_data, mime), "type": "image_url"},
        "aspect_ratio": "1:1",
        "response_format": "b64_json",
        "n": 1,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise ImageOutputError(f"Grok edit ({resp.status}): {data}")
    return await _grok_parse_response(data)


async def _grok_generate(prompt: str) -> Tuple[bytes, str]:
    url = "https://api.x.ai/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROK_IMAGE_MODEL,
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "response_format": "b64_json",
        "n": 1,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise ImageOutputError(f"Grok generate ({resp.status}): {data}")
    return await _grok_parse_response(data)


async def _gemini_generate(prompt: str) -> Tuple[bytes, str]:
    last_err: Optional[Exception] = None
    for model in _GEMINI_IMAGE_MODELS:
        try:
            return await _gemini_generate_with_model(model, prompt)
        except ImageOutputError as e:
            last_err = e
            if "404" not in str(e) and "not found" not in str(e).lower():
                raise
    if last_err:
        raise last_err
    raise ImageOutputError("Gemini image models недоступны")


async def _gemini_generate_with_model(model: str, prompt: str) -> Tuple[bytes, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise ImageOutputError(f"Gemini image API ({resp.status}): {data}")
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or {}
            if inline.get("data"):
                return base64.standard_b64decode(inline["data"]), inline.get("mimeType", "image/png")
    raise ImageOutputError("Gemini не вернул изображение")



def wants_pdf_output(text: Optional[str]) -> bool:
    if not text or not text.strip():
        return False
    return bool(PDF_INTENT_PATTERN.search(text))


def format_method_label(method: str) -> str:
    labels = {
        "laozhang/edit": "LaoZhang AI (редактирование фото)",
        "laozhang/generate": "LaoZhang AI (генерация)",
        "grok/edit": "Grok Imagine",
        "gemini/enhance": "Gemini",
        "free-t2i": "Free T2I",
        "meshy/text-to-image": "Meshy (nano-banana)",
        "unsplash/studio-bg": "Шаблон Avito + фон Unsplash",
        "studio/avito-card": "Шаблон Avito (ваше фото + текст)",
        "local/photo-only": "Локальная обработка",
        "local/card-fallback": "Локальный макет",
    }
    return labels.get(method, method)


def wants_image_output(caption: Optional[str]) -> bool:
    if not IMAGE_OUTPUT_ENABLED:
        return False
    if not caption or not caption.strip():
        return False
    from bot.services.file_output import resolve_output_file_format

    if resolve_output_file_format(caption):
        return False
    return bool(IMAGE_INTENT_PATTERN.search(caption))


def looks_like_text_only_refusal(text: str) -> bool:
    return bool(TEXT_ONLY_REFUSAL.search(text))


async def _api_images(
    endpoint: str,
    payload: dict,
) -> Tuple[bytes, str]:
    """POST /images/generations или /images/edits → bytes, mime."""
    url = f"{LLM_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                err = data.get("error", {})
                msg = err.get("message", str(data)) if isinstance(err, dict) else str(data)
                raise ImageOutputError(f"Images API ({resp.status}): {msg}")

    items = data.get("data") or []
    if not items:
        raise ImageOutputError("API не вернул изображение")

    item = items[0]
    if item.get("b64_json"):
        raw = base64.standard_b64decode(item["b64_json"])
        return raw, "image/png"

    if item.get("url"):
        async with aiohttp.ClientSession() as session:
            async with session.get(item["url"], timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status != 200:
                    raise ImageOutputError(f"Не удалось скачать картинку: {r.status}")
                raw = await r.read()
                ctype = r.headers.get("Content-Type", "image/png")
                return raw, ctype.split(";")[0].strip() or "image/png"

    raise ImageOutputError("Нет b64_json и url в ответе API")


async def try_api_generate(prompt: str, size: str = "1024x1024") -> Tuple[bytes, str]:
    payload = {
        "model": IMAGE_GENERATION_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",
    }
    return await _api_images("images/generations", payload)


async def try_api_edit(prompt: str, image_b64: str) -> Tuple[bytes, str]:
    payload = {
        "model": IMAGE_EDIT_MODEL,
        "prompt": prompt,
        "image": image_b64,
        "n": 1,
        "response_format": "b64_json",
    }
    return await _api_images("images/edits", payload)


def build_generation_prompt(user_request: str, vision_facts: str) -> str:
    return (
        f"{user_request}\n\n"
        f"Факты с исходного фото:\n{vision_facts[:1800]}\n\n"
        "Professional product photo for a Russian classifieds marketplace.\n"
        "Keep the EXACT same product, pose, color and details as in the input image.\n"
        "Clean white studio background, soft natural shadow, centered composition.\n"
        "No watermarks, no text overlays, no extra objects, no pose changes.\n"
        "High-end catalog photography, sharp focus."
    )


_GENERIC_TEXT = re.compile(
    r"товар для авито|качественное фото|без лишнего фона|метод:|vision:|ocr:",
    re.I,
)


def _strip_bottom_caption_band(img):
    """Убирает нижнюю белую полосу с текстом, если фото уже было карточкой."""
    from PIL import Image, ImageStat

    rgb = img.convert("RGB")
    w, h = rgb.size
    white_rows = 0
    cut_y = h
    for y in range(h - 1, int(h * 0.45), -1):
        row = rgb.crop((0, y, w, y + 1))
        mean = ImageStat.Stat(row).mean[:3]
        if mean[0] > 238 and mean[1] > 238 and mean[2] > 238:
            white_rows += 1
            if white_rows >= 24:
                cut_y = y
        else:
            white_rows = 0
    if cut_y < h - 30:
        return rgb.crop((0, 0, w, cut_y - 4))
    return rgb


def _inner_photo_bbox(rgb):
    """BBox самого фото (без белых полей вокруг)."""
    w, h = rgb.size
    px = rgb.load()

    def row_nonwhite(y: int) -> int:
        return sum(1 for x in range(w) if max(px[x, y]) < 242)

    def col_nonwhite(x: int) -> int:
        return sum(1 for y in range(h) if max(px[x, y]) < 242)

    top = 0
    while top < h and row_nonwhite(top) < w * 0.08:
        top += 1
    bottom = h - 1
    while bottom > top and row_nonwhite(bottom) < w * 0.08:
        bottom -= 1
    left = 0
    while left < w and col_nonwhite(left) < h * 0.08:
        left += 1
    right = w - 1
    while right > left and col_nonwhite(right) < h * 0.08:
        right -= 1
    if right - left < 20 or bottom - top < 20:
        return (0, 0, w, h)
    return (left, top, right + 1, bottom + 1)


def _content_bbox(rgb):
    """BBox не-белой области (фото внутри белой карточки)."""
    w, h = rgb.size
    px = rgb.load()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r < 238 or g < 238 or b < 238:
                found = True
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if not found:
        return (0, 0, w, h)
    return (min_x, min_y, max_x + 1, max_y + 1)


def _corner_bg_color(img) -> tuple[int, int, int]:
    from PIL import ImageStat

    rgb = img.convert("RGB")
    w, h = rgb.size
    x0, y0, x1, y1 = _content_bbox(rgb)
    cw, ch = x1 - x0, y1 - y0
    if cw < w * 0.5 or ch < h * 0.5:
        rgb = rgb.crop((x0, y0, x1, y1))
        w, h = rgb.size

    pad = max(6, min(w, h) // 18)
    patches = [
        rgb.crop((0, 0, pad, pad)),
        rgb.crop((w - pad, 0, w, pad)),
        rgb.crop((0, h - pad, pad, h)),
        rgb.crop((w - pad, h - pad, w, h)),
    ]
    corner_mean = ImageStat.Stat(patches[0]).mean[:3]
    if corner_mean[0] > 238 and corner_mean[1] > 238 and corner_mean[2] > 238:
        mid = max(4, min(w, h) // 28)
        patches = [
            rgb.crop((w // 2 - mid, 0, w // 2 + mid, pad)),
            rgb.crop((w // 2 - mid, h - pad, w // 2 + mid, h)),
            rgb.crop((0, h // 2 - mid, pad, h // 2 + mid)),
            rgb.crop((w - pad, h // 2 - mid, w, h // 2 + mid)),
        ]
    r = g = b = n = 0
    for patch in patches:
        mean = ImageStat.Stat(patch).mean[:3]
        r += mean[0]
        g += mean[1]
        b += mean[2]
        n += 1
    return int(r / n), int(g / n), int(b / n)


def _largest_component_bbox(mask) -> Optional[tuple[int, int, int, int]]:
    """BBox самой большой связной области маски (сам предмет)."""
    from collections import deque

    w, h = mask.size
    px = mask.load()
    seen: set[tuple[int, int]] = set()
    best: Optional[tuple[int, int, int, int, int]] = None

    for sx in range(w):
        for sy in range(h):
            if px[sx, sy] < 128 or (sx, sy) in seen:
                continue
            q: deque[tuple[int, int]] = deque([(sx, sy)])
            comp_seen = {(sx, sy)}
            min_x = max_x = sx
            min_y = max_y = sy
            while q:
                x, y = q.popleft()
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in comp_seen and px[nx, ny] > 128:
                        comp_seen.add((nx, ny))
                        q.append((nx, ny))
            seen.update(comp_seen)
            area = len(comp_seen)
            if best is None or area > best[4]:
                best = (min_x, min_y, max_x + 1, max_y + 1, area)

    if not best:
        return None
    return best[:4]


def _flood_background_mask(work, bg: tuple[int, int, int], tol: int = 38) -> list[int]:
    """Заливка фона от краёв кадра — убирает однотонный фон и водяные знаки."""
    from collections import deque

    w, h = work.size
    px = work.load()
    br, bgc, bb = bg

    def is_bg(x: int, y: int) -> bool:
        r, g, b = px[x, y]
        if r > 236 and g > 236 and b > 236:
            return True
        d = ((r - br) ** 2 + (g - bgc) ** 2 + (b - bb) ** 2) ** 0.5
        return d <= tol

    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        q.append((x, 0))
        q.append((x, h - 1))
    for y in range(1, h - 1):
        q.append((0, y))
        q.append((w - 1, y))

    while q:
        x, y = q.popleft()
        idx = y * w + x
        if visited[idx]:
            continue
        if not is_bg(x, y):
            continue
        visited[idx] = 1
        if x > 0:
            q.append((x - 1, y))
        if x < w - 1:
            q.append((x + 1, y))
        if y > 0:
            q.append((x, y - 1))
        if y < h - 1:
            q.append((x, y + 1))

    mask_px: list[int] = []
    for y in range(h):
        for x in range(w):
            mask_px.append(0 if visited[y * w + x] else 255)
    return mask_px


def _isolate_subject_rgba(img):
    """Вырезает предмет: заливка фона с краёв + лёгкое сглаживание маски."""
    from PIL import Image, ImageFilter

    rgb = _strip_bottom_caption_band(img)
    cx0, cy0, cx1, cy1 = _content_bbox(rgb)
    if (cx1 - cx0) < rgb.width * 0.98 or (cy1 - cy0) < rgb.height * 0.98:
        rgb = rgb.crop((cx0, cy0, cx1, cy1))
    ix0, iy0, ix1, iy1 = _inner_photo_bbox(rgb)
    if (ix1 - ix0) < rgb.width * 0.95 and (iy1 - iy0) < rgb.height * 0.95:
        rgb = rgb.crop((ix0, iy0, ix1, iy1))
    w, h = rgb.size
    work = rgb
    scale = 1.0
    max_side = 520
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        work = rgb.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

    bg = _corner_bg_color(work)
    lumas = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in work.getdata()]
    lumas_sorted = sorted(lumas)
    pct_idx = max(0, int(len(lumas_sorted) * 0.15) - 1)
    dark_thresh = max(38.0, lumas_sorted[pct_idx] + 8)
    mask_px = [255 if l <= dark_thresh else 0 for l in lumas]

    mask = Image.new("L", work.size)
    mask.putdata(mask_px)
    comp = _largest_component_bbox(mask)
    if not comp:
        return rgb.convert("RGBA")
    comp_mask = Image.new("L", work.size, 0)
    comp_crop = mask.crop(comp)
    comp_mask.paste(comp_crop, comp[:2])
    mask = comp_mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(2))

    x0, y0, x1, y1 = comp
    pad_px = 12
    x0 = max(0, int(x0 / scale) - pad_px)
    y0 = max(0, int(y0 / scale) - pad_px)
    x1 = min(w, int(x1 / scale) + pad_px)
    y1 = min(h, int(y1 / scale) + pad_px)
    cropped = rgb.crop((x0, y0, x1, y1))
    c_mask = mask.resize(cropped.size, Image.Resampling.BILINEAR)
    cropped.putalpha(c_mask.point(lambda p: min(255, int(p * 1.35))))
    return cropped


def _fit_subject(img, max_w: int, max_h: int):
    from PIL import Image

    img = img.convert("RGBA")
    ratio = min(max_w / img.width, max_h / img.height, 1.0)
    if ratio < 1.0:
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.Resampling.LANCZOS)
    return img


def _paste_shadow(canvas, subject, x: int, y: int):
    from PIL import Image, ImageFilter

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    s = subject.copy()
    s = s.resize((int(s.width * 1.02), int(s.height * 1.02)), Image.Resampling.LANCZOS)
    alpha = s.split()[-1]
    black = Image.new("RGBA", s.size, (0, 0, 0, 120))
    black.putalpha(alpha)
    shadow.paste(black, (x + 10, y + 14), black)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(shadow)
    canvas.paste(subject, (x, y), subject)


def _draw_card_text(draw, w: int, h: int, lines: list[str], y_start: int) -> None:
    from PIL import ImageFont

    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 46)
        sub_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = title_font

    y = y_start
    for i, line in enumerate(lines[:3]):
        if not line.strip():
            continue
        font = title_font if i == 0 else sub_font
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (w - tw) // 2
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 90), font=font)
        draw.text((x, y), line, fill=(30, 30, 35, 255), font=font)
        y += th + 14


def _extract_title_lines(user_request: str, vision_facts: str) -> list[str]:
    text = f"{user_request}\n{vision_facts}"
    lines = []

    if "ксеноморф" in text.lower() or "чужой" in text.lower() or "alien" in text.lower():
        lines = ["Фигурка ксеноморфа Alien", "3D-печать", "Коллекционная фигурка"]
    elif "авито" in user_request.lower() and len(lines) < 2:
        for raw in vision_facts.splitlines():
            t = raw.strip().lstrip("•-* ").strip()
            if not t or _GENERIC_TEXT.search(t):
                continue
            if 4 < len(t) < 55:
                lines.append(t)
            if len(lines) >= 2:
                break

    req = user_request.strip()
    if not lines and req and len(req) < 80 and "сделай" not in req.lower()[:6]:
        lines = [req]

    if not lines:
        for raw in vision_facts.splitlines():
            t = raw.strip().lstrip("•-* ").strip()
            if not t or _GENERIC_TEXT.search(t):
                continue
            if 4 < len(t) < 55:
                lines.append(t)
            if len(lines) >= 2:
                break

    if not lines:
        lines = ["Товар"]
    return lines[:3]


def render_local_avito_card(
    image_data: bytes,
    user_request: str,
    vision_facts: str,
    *,
    with_text: bool = True,
) -> Tuple[bytes, str]:
    from PIL import Image, ImageDraw

    src = Image.open(io.BytesIO(image_data))
    src = _strip_bottom_caption_band(src)
    subject = _isolate_subject_rgba(src)
    canvas = Image.new("RGBA", (1080, 1080), (252, 252, 254, 255))

    text_h = 200 if with_text else 0
    zone_h = 1080 - text_h - 80
    subject = _fit_subject(subject, 900, zone_h)
    x = (1080 - subject.width) // 2
    y = 60 + (zone_h - subject.height) // 2
    _paste_shadow(canvas, subject, x, y)

    if with_text:
        bar = Image.new("RGBA", (1080, text_h + 40), (255, 255, 255, 235))
        canvas.alpha_composite(bar, (0, 1080 - text_h - 20))
        draw = ImageDraw.Draw(canvas)
        lines = _extract_title_lines(user_request, vision_facts)
        _draw_card_text(draw, 1080, 1080, lines, 1080 - text_h)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=94)
    return out.getvalue(), "image/jpeg"


async def _gemini_enhance_photo(image_data: bytes, mime: str, prompt: str) -> Tuple[bytes, str]:
    last_err: Optional[Exception] = None
    for model in _GEMINI_IMAGE_MODELS:
        try:
            return await _gemini_enhance_with_model(model, image_data, mime, prompt)
        except ImageOutputError as e:
            last_err = e
            if "404" not in str(e) and "not found" not in str(e).lower():
                raise
    if last_err:
        raise last_err
    raise ImageOutputError("Gemini image models недоступны")


async def _gemini_enhance_with_model(
    model: str, image_data: bytes, mime: str, prompt: str
) -> Tuple[bytes, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    b64 = base64.standard_b64encode(image_data).decode("ascii")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise ImageOutputError(f"Gemini enhance ({resp.status}): {data}")
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or {}
            if inline.get("data"):
                return base64.standard_b64decode(inline["data"]), inline.get("mimeType", "image/png")
    raise ImageOutputError("Gemini не вернул изображение")


async def produce_image(
    image_data: bytes,
    user_request: str,
    vision_facts: str,
    *,
    with_text: bool = True,
    card_copy=None,
) -> Tuple[bytes, str, str]:
    from bot.services.avito_card import (
        CardCopy,
        _parse_card_copy_fallback,
        render_studio_card,
    )
    copy: CardCopy = card_copy or _parse_card_copy_fallback(user_request, vision_facts)

    from bot.config import (
        FREE_T2I_ENABLED,
        GEMINI_IMAGE_ENABLED,
        GROK_IMAGE_ENABLED,
        LAOZHANG_API_KEY,
        LAOZHANG_IMAGE_ENABLED,
        UNSPLASH_ACCESS_KEY,
        UNSPLASH_ENABLED,
    )
    from bot.services.vision import detect_mime

    prompt = build_generation_prompt(user_request, vision_facts)
    mime = detect_mime(image_data)
    attempts = []

    from bot.config import MESHY_API_KEY
    from bot.services.meshy_plan import is_avito_card_request

    if MESHY_API_KEY and not is_avito_card_request(user_request):

        async def _meshy_t2i():
            from bot.services.meshy_3d import meshy_text_to_image
            from bot.services.meshy_plan import plan_text_to_image

            plan = plan_text_to_image(user_request)
            data, out_mime, _ = await meshy_text_to_image(prompt, user_request=user_request, plan=plan)
            return data, out_mime

        attempts.append(("meshy/text-to-image", _meshy_t2i))

    if LAOZHANG_IMAGE_ENABLED and LAOZHANG_API_KEY:
        async def _lz_edit():
            from bot.services.laozhang_image import edit_image

            return await edit_image(image_data, prompt, mime=mime)

        async def _lz_generate():
            from bot.services.laozhang_image import generate_image

            return await generate_image(prompt)

        attempts.extend([
            ("laozhang/edit", _lz_edit),
            ("laozhang/generate", _lz_generate),
        ])
    if GROK_IMAGE_ENABLED and GROK_API_KEY and not GROK_API_KEY.startswith("gsk_"):
        attempts.append(
            ("grok/edit", lambda: _grok_edit(image_data, mime, prompt))
        )
    if GEMINI_IMAGE_ENABLED and GEMINI_API_KEY:
        attempts.append(
            ("gemini/enhance", lambda: _gemini_enhance_photo(image_data, mime, prompt))
        )
    if FREE_T2I_ENABLED:
        async def _free_t2i_attempt():
            from bot.services.free_t2i import generate_image as free_gen

            t2i_prompt = (
                f"{prompt}\n\n"
                "Single product photo for e-commerce listing, photorealistic, "
                "white studio background, no text, no watermark."
            )
            data, out_mime, _base = await free_gen(t2i_prompt)
            return data, out_mime

        attempts.append(("free-t2i", _free_t2i_attempt))

    if UNSPLASH_ENABLED and UNSPLASH_ACCESS_KEY:

        async def _unsplash_card():
            from bot.services.unsplash import make_unsplash_studio_card

            return await make_unsplash_studio_card(
                image_data, copy, user_request, vision_facts
            )

        attempts.append(("unsplash/studio-bg", _unsplash_card))

    for name, coro_factory in attempts:
        try:
            if name.startswith("laozhang/"):
                wait_sec = 280
            elif name.startswith("unsplash/"):
                wait_sec = 45
            else:
                wait_sec = 100
            data, out_mime = await asyncio.wait_for(coro_factory(), timeout=wait_sec)
            if data:
                return data, out_mime, name
        except Exception as e:
            logger.info("%s недоступен: %s", name, e)

    if with_text:
        method = "studio/avito-card"
        data, out_mime = render_studio_card(
            image_data, copy, method_label=format_method_label(method)
        )
        return data, out_mime, method

    data, out_mime = render_local_avito_card(
        image_data, user_request, vision_facts, with_text=False
    )
    return data, out_mime, "local/photo-only"
