"""Маркетинговая карточка Авито: шаблон + фото пользователя (без кривого вырезания)."""

import io
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class CardCopy:
    title: str
    subtitle: str
    bullets: List[str]
    badge: str = ""


def _parse_card_copy_fallback(user_request: str, vision_facts: str) -> CardCopy:
    text = f"{user_request}\n{vision_facts}".lower()
    title = "Товар"
    subtitle = ""
    bullets: List[str] = []

    if "ксеноморф" in text or "alien" in text or "чужой" in text:
        title = "Фигурка ксеноморфа Alien"
        subtitle = "3D-печать · коллекционная"
        bullets = ["Детальная проработка", "Идеально в подарок", "Редкая поза «йога»"]
    else:
        for line in vision_facts.splitlines():
            t = line.strip().lstrip("•-* ").strip()
            if not t or len(t) < 5 or "метод:" in t.lower() or "размер:" in t.lower():
                continue
            if not title or title == "Товар":
                title = t[:50]
            elif not subtitle:
                subtitle = t[:60]
            elif len(bullets) < 3:
                bullets.append(t[:45])
            if len(bullets) >= 3:
                break

    req = user_request.strip()
    if "класн" in req.lower() or "авито" in req.lower():
        if not bullets:
            bullets = ["Состояние как на фото", "Быстрая отправка", "Пишите в чат — отвечу"]
        if not subtitle:
            subtitle = "Для заказа — напишите в сообщения"

    return CardCopy(
        title=title[:52],
        subtitle=subtitle[:72],
        bullets=bullets[:3],
        badge="В наличии" if "заказ" in req.lower() else "",
    )


def render_studio_card(
    image_data: bytes,
    copy: CardCopy,
    *,
    method_label: str = "",
) -> Tuple[bytes, str]:
    """Карточка: оригинальное фото в рамке + продающий текст (без AI-вырезания)."""
    from PIL import Image, ImageDraw, ImageFont

    src = Image.open(io.BytesIO(image_data)).convert("RGB")
    w, h = 1080, 1350
    canvas = Image.new("RGB", (w, h), (248, 249, 252))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, w, 14), fill=(255, 92, 53))
    if copy.badge:
        draw.rounded_rectangle((w - 220, 36, w - 36, 88), radius=20, fill=(255, 92, 53))
        try:
            bf = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26
            )
        except OSError:
            bf = ImageFont.load_default()
        bb = draw.textbbox((0, 0), copy.badge, font=bf)
        tw = bb[2] - bb[0]
        draw.text((w - 128 - tw // 2, 48), copy.badge, fill=(255, 255, 255), font=bf)

    pad = 48
    photo_top = 100
    photo_bottom = 920
    photo_w = w - pad * 2
    photo_h = photo_bottom - photo_top
    frame = Image.new("RGB", (photo_w, photo_h), (255, 255, 255))
    frame_draw = ImageDraw.Draw(frame)
    frame_draw.rounded_rectangle(
        (0, 0, photo_w - 1, photo_h - 1), radius=28, outline=(220, 224, 230), width=3
    )

    ratio = min(photo_w / src.width, photo_h / src.height)
    nw, nh = int(src.width * ratio), int(src.height * ratio)
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    px = (photo_w - nw) // 2
    py = (photo_h - nh) // 2
    frame.paste(resized, (px, py))
    canvas.paste(frame, (pad, photo_top))

    text_top = 960
    draw.rectangle((0, text_top, w, h), fill=(255, 255, 255))
    draw.line((pad, text_top, w - pad, text_top), fill=(230, 233, 238), width=2)

    try:
        title_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 52
        )
        sub_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 32
        )
        bullet_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 28
        )
    except OSError:
        title_font = sub_font = bullet_font = ImageFont.load_default()

    y = text_top + 36
    draw.text((pad, y), copy.title, fill=(20, 22, 28), font=title_font)
    y += 62
    if copy.subtitle:
        draw.text((pad, y), copy.subtitle, fill=(90, 96, 110), font=sub_font)
        y += 44
    for bullet in copy.bullets:
        draw.text((pad, y), f"• {bullet}", fill=(50, 55, 65), font=bullet_font)
        y += 38

    if method_label:
        try:
            small = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial.ttf", 20
            )
        except OSError:
            small = bullet_font
        draw.text(
            (pad, h - 36),
            f"Сделано: {method_label}",
            fill=(140, 145, 155),
            font=small,
        )

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=92)
    return out.getvalue(), "image/jpeg"


def render_studio_card_with_background(
    image_data: bytes,
    copy: CardCopy,
    background_data: bytes,
    *,
    method_label: str = "",
) -> Tuple[bytes, str]:
    """Карточка Avito: стоковый фон Unsplash в зоне фото + товар пользователя сверху."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

    src = Image.open(io.BytesIO(image_data)).convert("RGB")
    bg = Image.open(io.BytesIO(background_data)).convert("RGB")
    w, h = 1080, 1350
    canvas = Image.new("RGB", (w, h), (248, 249, 252))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, w, 14), fill=(255, 92, 53))
    if copy.badge:
        draw.rounded_rectangle((w - 220, 36, w - 36, 88), radius=20, fill=(255, 92, 53))
        try:
            bf = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26
            )
        except OSError:
            bf = ImageFont.load_default()
        bb = draw.textbbox((0, 0), copy.badge, font=bf)
        tw = bb[2] - bb[0]
        draw.text((w - 128 - tw // 2, 48), copy.badge, fill=(255, 255, 255), font=bf)

    pad = 48
    photo_top = 100
    photo_bottom = 920
    photo_w = w - pad * 2
    photo_h = photo_bottom - photo_top

    bg_ratio = max(photo_w / bg.width, photo_h / bg.height)
    bg_resized = bg.resize(
        (int(bg.width * bg_ratio), int(bg.height * bg_ratio)),
        Image.Resampling.LANCZOS,
    )
    bx = (bg_resized.width - photo_w) // 2
    by = (bg_resized.height - photo_h) // 2
    bg_crop = bg_resized.crop((bx, by, bx + photo_w, by + photo_h))
    bg_crop = ImageEnhance.Brightness(bg_crop).enhance(0.92)
    bg_crop = bg_crop.filter(ImageFilter.GaussianBlur(1))

    frame = Image.new("RGB", (photo_w, photo_h), (255, 255, 255))
    frame.paste(bg_crop, (0, 0))
    frame_draw = ImageDraw.Draw(frame)
    frame_draw.rounded_rectangle(
        (0, 0, photo_w - 1, photo_h - 1), radius=28, outline=(220, 224, 230), width=3
    )

    product_ratio = min(photo_w * 0.88 / src.width, photo_h * 0.82 / src.height)
    nw, nh = int(src.width * product_ratio), int(src.height * product_ratio)
    product = src.resize((nw, nh), Image.Resampling.LANCZOS)
    px = (photo_w - nw) // 2
    py = (photo_h - nh) // 2

    shadow = Image.new("RGBA", (nw + 24, nh + 24), (0, 0, 0, 0))
    sh = Image.new("RGBA", (nw, nh), (0, 0, 0, 90))
    shadow.paste(sh, (12, 14))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    frame_rgba = frame.convert("RGBA")
    frame_rgba.paste(shadow, (px - 6, py - 4), shadow)
    frame_rgba.paste(product, (px, py))
    canvas.paste(frame_rgba.convert("RGB"), (pad, photo_top))

    text_top = 960
    draw.rectangle((0, text_top, w, h), fill=(255, 255, 255))
    draw.line((pad, text_top, w - pad, text_top), fill=(230, 233, 238), width=2)

    try:
        title_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 52
        )
        sub_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 32
        )
        bullet_font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 28
        )
    except OSError:
        title_font = sub_font = bullet_font = ImageFont.load_default()

    y = text_top + 36
    draw.text((pad, y), copy.title, fill=(20, 22, 28), font=title_font)
    y += 62
    if copy.subtitle:
        draw.text((pad, y), copy.subtitle, fill=(90, 96, 110), font=sub_font)
        y += 44
    for bullet in copy.bullets:
        draw.text((pad, y), f"• {bullet}", fill=(50, 55, 65), font=bullet_font)
        y += 38

    if method_label:
        try:
            small = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial.ttf", 20
            )
        except OSError:
            small = bullet_font
        draw.text((pad, h - 36), f"Сделано: {method_label}", fill=(140, 145, 155), font=small)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=92)
    return out.getvalue(), "image/jpeg"
