"""Telegram-каналы: реестр, API, контент, воронки."""

from telegram_channels.client import ChannelBot
from telegram_channels.content import funnel_post, yandex_browser_post
from telegram_channels.storage import (
    add_tg_channel,
    get_tg_channel,
    init_tg_channels,
    list_tg_channels,
    sync_tg_channel,
    sync_all_tg_channels,
)

__all__ = [
    "ChannelBot",
    "add_tg_channel",
    "funnel_post",
    "get_tg_channel",
    "init_tg_channels",
    "list_tg_channels",
    "sync_all_tg_channels",
    "sync_tg_channel",
    "yandex_browser_post",
]
