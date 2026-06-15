"""Доступ: админ, премиум, безлимит."""

from __future__ import annotations


def is_admin_user(user_id: int) -> bool:
    if user_id <= 0:
        return False
    try:
        from business_dashboard.config import MONEY_ADMIN_IDS

        return bool(MONEY_ADMIN_IDS) and user_id in MONEY_ADMIN_IDS
    except Exception:
        return False


def has_full_access(user_id: int) -> bool:
    from oracle_bot import storage as db

    return db.is_premium(user_id) or is_admin_user(user_id)
