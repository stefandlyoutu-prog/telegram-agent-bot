"""Контент-продукт: воронка продаж → скрипт → B-roll видео → озвучка → сборка."""

from video_bot.content_product.assembler import build_product_video
from video_bot.content_product.script_engine import generate_script

__all__ = ["build_product_video", "generate_script"]
