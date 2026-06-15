from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.chat_logic import reply_with_llm

router = Router()


@router.message(F.text)
async def on_text(message: Message) -> None:
    if not message.text or message.text.startswith("/"):
        return
    await reply_with_llm(message, message.text)
