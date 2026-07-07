"""Модели сценария контент-продукта."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FunnelStage = Literal[
    "hook",
    "problem",
    "agitate",
    "solution",
    "proof",
    "offer",
    "urgency",
    "cta",
]

MediaPrefer = Literal["video", "photo", "any"]


@dataclass
class Scene:
    stage: FunnelStage
    caption_lines: list[str]
    highlight: str
    voice: str
    broll_search: str
    media_prefer: MediaPrefer = "video"
    cut_sec: float = 2.0

    @property
    def caption_on_screen(self) -> str:
        return "\n".join(self.caption_lines[:2])


@dataclass
class VideoScript:
    topic: str
    cta: str
    scenes: list[Scene] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
