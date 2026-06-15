"""Meshy rigging + animation для человекоподобных персонажей."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import aiohttp

from bot.config import MESHY_API_KEY, MESHY_RIG_TIMEOUT_SEC
from bot.services.meshy_3d import (
    MESHY_BASE,
    MeshyDelivery,
    MeshyError,
    MeshyFile,
    _create_text_preview,
    _create_meshy_session,
    _download_url,
    _poll_task,
    _refine_preview,
    _remesh_stl_pipeline,
    _request_json,
)
from bot.services.meshy_plan import Meshy3DPlan, Meshy3DPipeline, texture_prompt_from_text

logger = logging.getLogger(__name__)

_ANIM_CATALOG_URL = "https://api.meshy.ai/web/public/animations/resources"
_catalog_cache: Optional[List[Dict[str, Any]]] = None

_ACTION_HINTS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"бег|run|беж", re.I), "running"),
    (re.compile(r"ходьб|walk|идт", re.I), "walking"),
    (re.compile(r"танц|dance", re.I), "dance"),
    (re.compile(r"атак|attack|удар", re.I), "attack"),
    (re.compile(r"idle|стоит|покой", re.I), "idle"),
)


async def _load_animation_catalog(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    try:
        async with session.get(
            _ANIM_CATALOG_URL,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                logger.warning("Animation catalog HTTP %s", resp.status)
                _catalog_cache = []
                return _catalog_cache
            data = await resp.json(content_type=None)
            if isinstance(data, list):
                _catalog_cache = data
            elif isinstance(data, dict):
                _catalog_cache = data.get("animations") or data.get("data") or []
            else:
                _catalog_cache = []
    except Exception as e:
        logger.warning("Animation catalog: %s", e)
        _catalog_cache = []
    return _catalog_cache


async def resolve_action_id(session: aiohttp.ClientSession, user_text: str) -> int:
    catalog = await _load_animation_catalog(session)
    hint = "walking"
    for pat, label in _ACTION_HINTS:
        if pat.search(user_text or ""):
            hint = label
            break

    best_id = 0
    best_score = -1
    for item in catalog:
        if not isinstance(item, dict):
            continue
        aid = item.get("action_id") or item.get("id")
        name = (item.get("name") or item.get("title") or "").lower()
        if aid is None:
            continue
        score = 0
        if hint in name:
            score += 10
        if "walk" in hint and "walk" in name:
            score += 8
        if "run" in hint and "run" in name:
            score += 8
        if score > best_score:
            best_score = score
            best_id = int(aid)

    if best_id:
        return best_id
    return 92


def _rig_result_blob(task: Dict[str, Any]) -> Dict[str, Any]:
    r = task.get("result")
    return r if isinstance(r, dict) else {}


async def _poll_rig(session: aiohttp.ClientSession, task_id: str) -> Dict[str, Any]:
    return await _poll_task(
        session, task_id, kind="rigging", timeout_sec=MESHY_RIG_TIMEOUT_SEC
    )


async def _poll_animation(session: aiohttp.ClientSession, task_id: str) -> Dict[str, Any]:
    return await _poll_task(
        session, task_id, kind="animations", timeout_sec=MESHY_RIG_TIMEOUT_SEC
    )


async def run_rig_animation_delivery(
    prompt: str,
    *,
    user_request: str = "",
) -> MeshyDelivery:
    """
    Text-to-3D (текстуры) → rigging → animation → GLB (+ STL для статики).
    Только человекоподобные персонажи.
    """
    if not MESHY_API_KEY:
        raise MeshyError("Meshy API key не задан")

    ctx = user_request or prompt
    from bot.services.stl_postprocess import target_height_mm_from_text

    height_m = max(target_height_mm_from_text(ctx) / 1000.0, 0.5)
    plan = Meshy3DPlan(
        pipeline=Meshy3DPipeline.PRINT_TEXTURED,
        label="Meshy персонаж: 3D → rig → анимация",
        use_refine=True,
        texture_prompt=texture_prompt_from_text(ctx, prompt),
        deliver_glb=True,
    )
    delivery = MeshyDelivery(plan_label=plan.label)

    async with _create_meshy_session() as session:
        preview_id = await _create_text_preview(session, prompt, plan)
        refine_id = await _refine_preview(session, preview_id, plan)

        rig_created = await _request_json(
            session,
            "POST",
            f"{MESHY_BASE}/rigging",
            json_body={
                "input_task_id": refine_id,
                "height_meters": min(height_m, 2.5),
            },
        )
        rig_id = rig_created.get("result") or rig_created.get("id")
        if not rig_id:
            raise MeshyError("Meshy rigging: нет task id")
        logger.info("Meshy rigging: %s", rig_id)
        rig_task = await _poll_rig(session, rig_id)
        rig_blob = _rig_result_blob(rig_task)

        anim_bytes: Optional[bytes] = None
        anim_name = "walk"

        basics = rig_blob.get("basic_animations") or {}
        if re.search(r"бег|run", ctx, re.I) and basics.get("running_glb_url"):
            anim_bytes = await _download_url(session, basics["running_glb_url"])
            anim_name = "run"
        elif basics.get("walking_glb_url"):
            anim_bytes = await _download_url(session, basics["walking_glb_url"])
            anim_name = "walk"

        action_id = await resolve_action_id(session, ctx)
        try:
            anim_created = await _request_json(
                session,
                "POST",
                f"{MESHY_BASE}/animations",
                json_body={"rig_task_id": rig_id, "action_id": action_id},
            )
            anim_task_id = anim_created.get("result") or anim_created.get("id")
            if anim_task_id:
                anim_task = await _poll_animation(session, anim_task_id)
                blob = _rig_result_blob(anim_task)
                url = blob.get("animation_glb_url")
                if url:
                    anim_bytes = await _download_url(session, url)
                    anim_name = f"action-{action_id}"
        except MeshyError as e:
            logger.warning("Custom animation skipped: %s", e)

        if not anim_bytes:
            glb_url = rig_blob.get("rigged_character_glb_url")
            if glb_url:
                anim_bytes = await _download_url(session, glb_url)
                anim_name = "rigged"
            else:
                raise MeshyError(
                    "Rigging готов, но GLB анимации не найден. "
                    "Попробуйте другого человекоподобного персонажа."
                )

        delivery.files.append(
            MeshyFile(data=anim_bytes, ext="glb", role="primary")
        )

        try:
            stl_data, stl_method = await _remesh_stl_pipeline(
                session,
                task_id=refine_id,
                ctx=ctx,
                resize_height_m=height_m,
                method_prefix="meshy/rig+anim",
            )
            delivery.files.append(
                MeshyFile(data=stl_data, ext="stl", role="print_static")
            )
            delivery.method = f"rig+anim ({anim_name}) · {stl_method}"
        except MeshyError as e:
            logger.warning("Static STL for rig skipped: %s", e)
            delivery.method = f"rig+anim ({anim_name})"

    return delivery
