from aiogram import Router

from bot.handlers import chat, commands, files, money, photos, voice


def setup_routers() -> Router:
    root = Router()
    root.include_router(commands.router)
    root.include_router(money.router)
    root.include_router(photos.router)
    root.include_router(files.router)
    root.include_router(voice.router)
    root.include_router(chat.router)
    return root
