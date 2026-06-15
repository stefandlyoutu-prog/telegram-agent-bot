"""Исполнение TaskPlan для текстовых сообщений."""

from __future__ import annotations

import re
from typing import Optional

from aiogram.types import Message

from bot.services import history
from bot.services.file_output import parse_file_count
from bot.services.processing import clear_busy, set_busy
from bot.services.self_check import DeliveryResult, DeliveredFile
from bot.services.task_plan import TaskKind, TaskPlan


async def execute_text_plan(
    message: Message,
    plan: TaskPlan,
    *,
    phase: str = "думаю",
    storyboard_frames: Optional[list] = None,
) -> DeliveryResult:
    """Маршрутизация по plan.kind — вызывает handlers из chat_logic."""
    from bot.handlers import chat_logic as cl

    user_id = message.from_user.id
    model = plan.model
    text = plan.user_text

    if plan.kind == TaskKind.PENDING_3D:
        ok = await cl._complete_pending_3d_from_text(message, text)
        return DeliveryResult(
            summary="Профиль принтера принят" if ok else "Не удалось продолжить 3D",
            success=ok,
        )

    if plan.kind == TaskKind.ARTICULATED_3MF:
        return await cl._reply_articulated_3mf(message, text, model)

    if plan.kind == TaskKind.AIRPLANE_3MF:
        return await cl._reply_airplane_3mf(
            message,
            text,
            model,
            plan=plan,
            high_detail=bool((plan.extra or {}).get("high_detail")),
            print_tuned=bool((plan.extra or {}).get("print_tuned")),
        )

    if plan.kind == TaskKind.UNSUPPORTED_ARTICULATED_3D:
        return await cl._reply_unsupported_articulated(message, plan)

    if plan.kind == TaskKind.MECHANICAL_PROJECT:
        return await cl._reply_mechanical_project(message, plan)

    if plan.kind == TaskKind.MESHY_TEXT_3D:
        return await cl._reply_stl_from_text_meshy(message, text, model)

    if plan.kind == TaskKind.MESHY_IMAGE:
        return await cl._reply_meshy_image(message, text, plan=plan)

    if plan.kind == TaskKind.OPENSCAD_SINGLE:
        return await cl._send_single_print_part(message, text, model)

    if plan.kind == TaskKind.PRINT_PROJECT:
        ctx = text
        if re.search(r"продолж|добавь деталь|пересобери|из проекта|/project", text, re.I):
            saved = await history.get_project_context(user_id)
            if saved:
                ctx = saved + "\n\n" + text
        return await cl._send_print_project(
            message, text, model, context=ctx, storyboard_frames=storyboard_frames
        )

    if plan.kind == TaskKind.SEO_PDF:
        set_busy(user_id, phase)
        try:
            await cl._send_seo_pdf(message, text, text, model)
            await history.add_message(user_id, "user", text)
            await history.add_message(user_id, "assistant", "Отправлен PDF (SEO для Авитo).")
            return DeliveryResult(summary="Отправлен SEO PDF", success=True)
        except Exception as e:
            return DeliveryResult(summary=str(e), success=False)
        finally:
            clear_busy(user_id)

    if plan.kind == TaskKind.FILE_OUTPUT and plan.file_fmt:
        set_busy(user_id, phase)
        try:
            dr = await cl._send_generated_file(
                message,
                text,
                model,
                plan.file_fmt,
                count=parse_file_count(text, 1),
            )
            await history.add_message(user_id, "user", text)
            await history.add_message(
                user_id, "assistant", f"Отправлен файл ({plan.file_fmt.upper()})."
            )
            return dr
        except Exception as e:
            return DeliveryResult(summary=str(e), success=False)
        finally:
            clear_busy(user_id)

    if plan.kind == TaskKind.CHAT:
        return await cl._reply_chat_with_model(message, text, model, phase=phase)

    return DeliveryResult(summary=f"Неизвестный тип задачи: {plan.kind}", success=False)
