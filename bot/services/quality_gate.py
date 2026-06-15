"""Unified pre-send quality gate for all 3D deliveries.

File is NOT sent to the user when the gate fails — no silent fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from bot.services.self_check import DeliveryResult, SelfCheckOutcome, _programmatic_check
from bot.services.task_plan import TaskKind, TaskPlan


@dataclass
class GateResult:
    ok: bool
    message: str = ""
    issues: List[str] = field(default_factory=list)


def run_quality_gate(plan: TaskPlan, delivery: DeliveryResult) -> GateResult:
    """Synchronous programmatic gate (fast, deterministic)."""
    if not delivery.success or not delivery.files:
        return GateResult(ok=False, message="Нет файла для проверки.", issues=["пустая выдача"])

    outcome: SelfCheckOutcome = _programmatic_check(plan, delivery)
    return GateResult(ok=outcome.ok, message=outcome.message or "", issues=list(outcome.issues or []))


def format_gate_failure(result: GateResult) -> str:
    issues = "\n".join(f"• {i}" for i in result.issues[:6])
    return (
        "⚠️ **Модель не прошла проверку качества** — файл **не отправлен**.\n"
        f"{result.message}\n"
        f"{issues}\n\n"
        "Повторите запрос. Fallback на другой генератор отключён: "
        "бот не подменит результат примитивами."
    )


async def gate_and_notify(message, plan: TaskPlan, delivery: DeliveryResult) -> bool:
    """Run gate; on failure notify user. Returns True if OK to send files."""
    from bot.config import SELF_CHECK_ENABLED

    if not SELF_CHECK_ENABLED:
        return True
    result = run_quality_gate(plan, delivery)
    if result.ok:
        if result.message:
            await message.answer(f"✅ {result.message}"[:1024])
        return True
    await message.answer(format_gate_failure(result)[:1024], parse_mode="Markdown")
    return False
