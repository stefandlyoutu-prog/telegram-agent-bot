from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.chat_logic import reply_with_vision
from bot.services.processing import clear_busy, set_busy
from bot.services.vision import (
    VisionError,
    build_vision_prompt,
    download_photo_bytes,
    image_dimensions,
    pick_largest_photo,
)
from bot.status_ui import StatusIndicator

router = Router()


@router.message(F.photo)
async def on_photo(message: Message) -> None:
    user_id = message.from_user.id
    photo = pick_largest_photo(message.photo)
    indicator = StatusIndicator(message)
    set_busy(user_id, "смотрю фото")

    try:
        await indicator.viewing_image()
        data = await download_photo_bytes(message.bot, photo.file_id)
        w, h = image_dimensions(data)
    except VisionError as e:
        await indicator.error(str(e))
        clear_busy(user_id)
        return
    except Exception as e:
        await indicator.error(f"Не удалось загрузить фото: {e}")
        clear_busy(user_id)
        return

    prompt = build_vision_prompt(message.caption)
    await indicator.done()
    await reply_with_vision(
        message,
        data,
        prompt,
        image_bytes=len(data),
        width=w,
        height=h,
        telegram_file_id=photo.file_id,
    )
