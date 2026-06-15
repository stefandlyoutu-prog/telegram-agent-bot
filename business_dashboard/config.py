"""Настройки Центра доходов из окружения."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Только эти Telegram user id могут /money (пусто = все)
MONEY_ADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv("MONEY_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# Токен для API дашборда (пусто = без авторизации, только localhost)
DASHBOARD_TOKEN: str = os.getenv("MONEY_DASHBOARD_TOKEN", "").strip()

# Авто-отчёт в полночь (локальное время)
AUTO_CLOSE_DAY: bool = os.getenv("MONEY_AUTO_CLOSE_DAY", "1") not in {"0", "false", "False"}

# Подсказки для разведки трендов
TREND_SEED_QUERIES: tuple[str, ...] = tuple(
    q.strip()
    for q in os.getenv(
        "MONEY_TREND_QUERIES",
        "заработать в интернете,telegram бот подписка,осаго онлайн,"
        "самозанятый чек,карточка ozon,гадание таро бот,хозблок смета",
    ).split(",")
    if q.strip()
)
