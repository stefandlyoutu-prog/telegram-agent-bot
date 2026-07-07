"""Правило конвейера: фото и видео не повторяются в одном ролике."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MediaRegistry:
    """Глобальный учёт кадров на весь ролик (все сцены)."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def is_used(self, key: str) -> bool:
        return key in self._used

    def claim(self, key: str) -> bool:
        """Зарезервировать кадр. False — уже был в ролике."""
        if key in self._used:
            return False
        self._used.add(key)
        return True

    def must_claim(self, key: str) -> None:
        if not self.claim(key):
            raise RuntimeError(f"Повтор медиа в ролике запрещён: {key!r}")

    def release(self, key: str) -> None:
        """Снять резерв (если файл не скачался)."""
        self._used.discard(key)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._used)

    def __len__(self) -> int:
        return len(self._used)
