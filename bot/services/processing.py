"""Состояние обработки запросов по пользователям."""

from typing import Optional

_busy_users: dict[int, str] = {}


def set_busy(user_id: int, phase: str) -> None:
    _busy_users[user_id] = phase


def clear_busy(user_id: int) -> None:
    _busy_users.pop(user_id, None)


def set_phase(user_id: int, phase: str) -> None:
    _busy_users[user_id] = phase


def is_user_busy(user_id: int) -> bool:
    return user_id in _busy_users


def get_phase(user_id: int) -> Optional[str]:
    return _busy_users.get(user_id)
