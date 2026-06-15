"""Ожидание продолжения 3D-задач между сообщениями пользователя."""

from dataclasses import dataclass
from typing import Dict, Optional

_pending: Dict[int, "Pending3DJob"] = {}
_pending_concept: Dict[int, "PendingConcept3DJob"] = {}
_pending_engineering: Dict[int, "PendingEngineeringIntake"] = {}


@dataclass
class Pending3DJob:
    file_id: str
    prompt: str
    count: int
    facts: str
    width: int
    height: int


@dataclass
class PendingConcept3DJob:
    image_bytes: bytes
    mime: str
    prompt: str
    original_text: str
    subject: str = ""


@dataclass
class PendingEngineeringIntake:
    prompt: str


@dataclass
class PendingV3Figure8Preview:
    """PDF-превью v3 отправлено — «присылай 3MF» без контекста восьмёрки не перехватываем."""

    spec_version: str = "v3"


_pending_v3_figure8: Dict[int, PendingV3Figure8Preview] = {}


def set_pending(user_id: int, job: Pending3DJob) -> None:
    _pending[user_id] = job


def get_pending(user_id: int) -> Optional[Pending3DJob]:
    return _pending.get(user_id)


def pop_pending(user_id: int) -> Optional[Pending3DJob]:
    return _pending.pop(user_id, None)


def has_pending(user_id: int) -> bool:
    return user_id in _pending


def clear_pending(user_id: int) -> None:
    _pending.pop(user_id, None)


def set_pending_concept(user_id: int, job: PendingConcept3DJob) -> None:
    _pending_concept[user_id] = job


def get_pending_concept(user_id: int) -> Optional[PendingConcept3DJob]:
    return _pending_concept.get(user_id)


def pop_pending_concept(user_id: int) -> Optional[PendingConcept3DJob]:
    return _pending_concept.pop(user_id, None)


def clear_pending_concept(user_id: int) -> None:
    _pending_concept.pop(user_id, None)


def set_pending_engineering(user_id: int, job: PendingEngineeringIntake) -> None:
    _pending_engineering[user_id] = job


def get_pending_engineering(user_id: int) -> Optional[PendingEngineeringIntake]:
    return _pending_engineering.get(user_id)


def pop_pending_engineering(user_id: int) -> Optional[PendingEngineeringIntake]:
    return _pending_engineering.pop(user_id, None)


def clear_pending_engineering(user_id: int) -> None:
    _pending_engineering.pop(user_id, None)


def set_pending_v3_figure8(user_id: int, job: PendingV3Figure8Preview | None = None) -> None:
    _pending_v3_figure8[user_id] = job or PendingV3Figure8Preview()


def get_pending_v3_figure8(user_id: int) -> Optional[PendingV3Figure8Preview]:
    return _pending_v3_figure8.get(user_id)


def has_pending_v3_figure8(user_id: int) -> bool:
    return user_id in _pending_v3_figure8


def clear_pending_v3_figure8(user_id: int) -> None:
    _pending_v3_figure8.pop(user_id, None)
