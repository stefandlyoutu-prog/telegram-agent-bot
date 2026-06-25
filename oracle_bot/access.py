"""Доступ: админ, премиум, безлимит."""

from __future__ import annotations


def is_admin_user(user_id: int) -> bool:
    if user_id <= 0:
        return False
    from oracle_bot.config import ORACLE_ADMIN_IDS

    return bool(ORACLE_ADMIN_IDS) and user_id in ORACLE_ADMIN_IDS


def has_full_access(user_id: int) -> bool:
    from oracle_bot import storage as db
    from oracle_bot.free_day import is_free_day_active

    return (
        db.is_premium(user_id)
        or is_admin_user(user_id)
        or is_free_day_active()
    )
