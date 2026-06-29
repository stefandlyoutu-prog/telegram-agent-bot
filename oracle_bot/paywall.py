"""Режим paywall: Stars или рефералка (A/B эксперимент)."""

from __future__ import annotations

from datetime import date, datetime

from oracle_bot.config import (
    ORACLE_PAYWALL_EXPERIMENT_UNTIL,
    ORACLE_PAYWALL_MODE,
    ORACLE_STARS_ENABLED,
)


def paywall_mode() -> str:
    """stars — Telegram Stars; referral — только приглашение друзей."""
    until = (ORACLE_PAYWALL_EXPERIMENT_UNTIL or "").strip()
    if until:
        try:
            end = date.fromisoformat(until[:10])
            if date.today() <= end:
                return "referral"
        except ValueError:
            pass
    mode = (ORACLE_PAYWALL_MODE or "stars").strip().lower()
    return mode if mode in {"stars", "referral"} else "stars"


def stars_enabled() -> bool:
    # Глобальный выключатель: по умолчанию оплата только в рублях (Робокасса)
    return ORACLE_STARS_ENABLED and paywall_mode() == "stars"


def referral_primary() -> bool:
    return paywall_mode() == "referral"


def experiment_label() -> str:
    if not referral_primary():
        return ""
    until = (ORACLE_PAYWALL_EXPERIMENT_UNTIL or "").strip()[:10]
    return f"🧪 Эксперимент до {until}: вместо Stars — пригласи друга.\n\n" if until else ""
