import base64
import io
from typing import Optional, Tuple

from aiogram import Bot
from aiogram.types import PhotoSize

MAX_IMAGE_BYTES = 10 * 1024 * 1024

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class VisionError(Exception):
    pass


def detect_mime(data: bytes, fallback: str = "image/jpeg") -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return fallback


def image_dimensions(data: bytes) -> Tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Exception:
        return (0, 0)


def pick_largest_photo(photos: list[PhotoSize]) -> PhotoSize:
    return max(photos, key=lambda p: (p.width or 0) * (p.height or 0))


async def download_photo_bytes(bot: Bot, file_id: str) -> bytes:
    from bot.services.telegram_net import format_telegram_error, telegram_retry

    try:
        file = await telegram_retry(
            "get_file",
            lambda: bot.get_file(file_id),
        )
    except Exception as e:
        raise VisionError(format_telegram_error(e)) from e

    if file.file_size and file.file_size > MAX_IMAGE_BYTES:
        raise VisionError(f"Фото больше {MAX_IMAGE_BYTES // (1024*1024)} MB")
    buf = io.BytesIO()
    try:
        await telegram_retry(
            "download_file",
            lambda: bot.download_file(file.file_path, buf),
        )
    except Exception as e:
        raise VisionError(format_telegram_error(e)) from e
    data = buf.getvalue()
    if not data:
        raise VisionError("Файл изображения пустой")
    if len(data) > MAX_IMAGE_BYTES:
        raise VisionError(f"Фото больше {MAX_IMAGE_BYTES // (1024*1024)} MB")
    return data


def to_data_url(data: bytes, mime: Optional[str] = None) -> str:
    mime = mime or detect_mime(data)
    encoded = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def mime_from_filename(filename: str) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ".jpg"
    return IMAGE_MIME.get(ext, "image/jpeg")


def build_vision_prompt(caption: Optional[str]) -> str:
    from bot.services.file_output import wants_3d_model_from_photo
    from bot.services.image_output import wants_image_output

    if caption and caption.strip():
        cap = caption.strip()
        if wants_3d_model_from_photo(cap):
            return (
                f"{cap}\n\n"
                "Сделай 3D-модель (STL) для печати по этому фото: размеры в мм, "
                "отдельные детали если нужно, готово для загрузки в слайсер."
            )
        if wants_image_output(cap) or "авито" in cap.lower():
            return (
                f"{cap}\n\n"
                "Сделай готовую карточку/обложку для Авито по фото: чистый фон, "
                "предмет по центру, короткий читаемый текст на русском."
            )
        return cap
    return (
        "Опиши что на фото и дай полезный комментарий: "
        "предмет, состояние, текст на изображении."
    )
