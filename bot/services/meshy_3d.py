"""Meshy API: 3D, текстуры, remesh, картинки (https://docs.meshy.ai)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from bot.config import LLM_PROXY, MESHY_API_KEY, MESHY_TIMEOUT_SEC
from bot.services.meshy_plan import (
    Meshy3DPlan,
    Meshy3DPipeline,
    MeshyImagePlan,
    plan_photo_to_3d,
    plan_text_to_3d,
    plan_text_to_image,
)

logger = logging.getLogger(__name__)

MESHY_BASE = "https://api.meshy.ai/openapi/v1"
TEXT_TO_3D_BASE = "https://api.meshy.ai/openapi/v2/text-to-3d"


def _prompt_id(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:10]


@dataclass
class MeshyFile:
    data: bytes
    ext: str
    role: str = "primary"

    @property
    def filename_suffix(self) -> str:
        return self.ext


@dataclass
class MeshyDelivery:
    files: List[MeshyFile] = field(default_factory=list)
    method: str = ""
    plan_label: str = ""

    @property
    def primary(self) -> Optional[MeshyFile]:
        for f in self.files:
            if f.role == "primary":
                return f
        return self.files[0] if self.files else None


def score_meshy_delivery(delivery: MeshyDelivery, user_text: str = "") -> Dict[str, Any]:
    """Cheap local score used to decide whether one Meshy candidate is worth keeping."""
    primary = delivery.primary
    has_glb = any(f.ext == "glb" for f in delivery.files)
    score = 0
    reasons: List[str] = []
    stats: Dict[str, Any] = {
        "has_glb": has_glb,
        "score": 0,
        "reasons": reasons,
    }
    if has_glb:
        score += 25
        reasons.append("textured_glb")
    if not primary:
        stats["score"] = score
        return stats
    if len(primary.data) > 500_000:
        score += 20
        reasons.append("large_asset")
    elif len(primary.data) > 100_000:
        score += 10
        reasons.append("medium_asset")
    method = delivery.method or ""
    if _has_repair_warning(method):
        score -= 35
        reasons.append("repair_warning")
    try:
        if primary.ext == "stl":
            from bot.services.stl_postprocess import _dims, _parse_stl

            tris = _parse_stl(primary.data)
            faces = int(len(tris))
            _, _, size = _dims(tris)
            extents = [float(x) for x in size]
            stats.update({"faces": faces, "extents": extents})
            if faces >= 80_000:
                score += 25
                reasons.append("high_face_count")
            elif faces >= 25_000:
                score += 12
                reasons.append("ok_face_count")
            if re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", user_text or "", re.I):
                longest = max(extents)
                shortest = max(1e-6, min(extents))
                if longest / shortest >= 2.5:
                    score += 10
                    reasons.append("airliner_aspect")
    except Exception as e:
        stats["analysis_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    stats["score"] = score
    return stats


class MeshyError(Exception):
    pass


class MeshyNetworkError(MeshyError):
    pass


class MeshyInsufficientFundsError(MeshyError):
    """Meshy returned HTTP 402 — out of credits. Not a bug; needs top-up."""

    pass


def _create_meshy_session() -> aiohttp.ClientSession:
    """Use the same SOCKS/HTTP proxy path as LLM calls when configured."""
    if LLM_PROXY:
        from bot.services.http_client import session_kwargs

        return aiohttp.ClientSession(**session_kwargs(True))
    return aiohttp.ClientSession()


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {MESHY_API_KEY}",
        "Content-Type": "application/json",
    }


def _image_data_uri(image_bytes: bytes, mime: str) -> str:
    mime = mime if mime in ("image/jpeg", "image/png", "image/jpg") else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _stl_data_uri(stl_bytes: bytes) -> str:
    b64 = base64.b64encode(stl_bytes).decode("ascii")
    return f"data:application/octet-stream;base64,{b64}"


def _postprocess_stl(mesh: bytes, *, method: str, user_request: str) -> Tuple[bytes, str]:
    from bot.services.stl_postprocess import prepare_meshy_stl_for_bambu

    try:
        norm = prepare_meshy_stl_for_bambu(mesh, user_text=user_request)
        detail = (
            f"{method} · {norm.width_mm:.0f}×{norm.depth_mm:.0f}×{norm.height_mm:.0f} мм"
            f" ({norm.note})"
        )
        return norm.data, detail
    except Exception as e:
        logger.warning("STL postprocess failed: %s", e)
        return mesh, method


def _has_repair_warning(method: str) -> bool:
    text = method or ""
    return (
        "repair WARNING" in text
        or "non-manifold" in text
        or "repair skip" in text
        or "postprocess skip" in text
    )


def _repair_warning_count(method: str) -> Optional[int]:
    m = re.search(r"repair WARNING:\s*(\d+)\s+non-manifold", method or "", re.I)
    if not m:
        m = re.search(r"(\d+)\s+non-manifold", method or "", re.I)
    return int(m.group(1)) if m else None


def _repair_candidate_is_better(current_method: str, candidate_method: str) -> bool:
    """Prefer a strict retry if it removes or reduces Bambu non-manifold warnings."""
    if _has_repair_warning(current_method) and not _has_repair_warning(candidate_method):
        return True
    current = _repair_warning_count(current_method)
    candidate = _repair_warning_count(candidate_method)
    if current is None:
        return False
    if candidate is None:
        return not _has_repair_warning(candidate_method)
    return candidate < current


async def get_meshy_balance() -> Optional[int]:
    if not MESHY_API_KEY:
        return None
    try:
        async with _create_meshy_session() as session:
            data = await _request_json(session, "GET", f"{MESHY_BASE}/balance")
            bal = data.get("balance")
            return int(bal) if bal is not None else None
    except Exception as e:
        logger.warning("Meshy balance: %s", e)
        return None


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    json_body: Optional[dict] = None,
) -> Dict[str, Any]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            async with session.request(
                method,
                url,
                headers=_headers(),
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                text = await resp.text()
                if resp.status == 402 or "insufficient funds" in text.lower():
                    raise MeshyInsufficientFundsError(
                        "Meshy: закончились кредиты (HTTP 402 Insufficient funds)"
                    )
                if resp.status not in (200, 201, 202):
                    raise MeshyError(f"Meshy HTTP {resp.status}: {text[:300]}")
                try:
                    return await resp.json(content_type=None)
                except Exception as e:
                    raise MeshyError(f"Meshy JSON: {text[:200]}") from e
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            last_exc = e
            if attempt >= 3:
                break
            logger.warning("Meshy %s %s failed (%s), retry %s/3", method, url, e, attempt + 1)
            await asyncio.sleep(2 * attempt)
    raise MeshyNetworkError(str(last_exc) or type(last_exc).__name__)


def _download_url_blocking(url: str) -> bytes:
    """Blocking download via urllib — the reliable path on this environment.

    On Python 3.9 + LibreSSL, aiohttp intermittently times out fetching from
    assets.meshy.ai (empty TimeoutError), while urllib/curl succeed. We use
    this as the fallback (and de-facto primary) downloader.
    """
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        status = getattr(r, "status", 200)
        if status != 200:
            raise MeshyError(f"Download {status}")
        return r.read()


async def _download_url(session: aiohttp.ClientSession, url: str) -> bytes:
    # Primary path: urllib in a worker thread. On this environment (Python 3.9
    # + LibreSSL) aiohttp reliably TIMES OUT fetching from assets.meshy.ai
    # (empty TimeoutError) — which silently broke EVERY Meshy delivery and made
    # the bot fall back to procedural primitives. urllib/curl work in ~5 s, so
    # we use urllib first and only fall back to aiohttp if urllib itself fails.
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            return await asyncio.to_thread(_download_url_blocking, url)
        except Exception as e:  # noqa: BLE001 - any failure should retry/fall back
            last_exc = e
            if attempt >= 3:
                break
            logger.warning("Meshy urllib download failed (%s), retry %s/3",
                           e or type(e).__name__, attempt + 1)
            await asyncio.sleep(2 * attempt)

    # Fallback: aiohttp (in case urllib is blocked on some other environment).
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise MeshyError(f"Download {resp.status}")
            return await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        raise MeshyNetworkError(
            f"download failed (urllib: {last_exc or 'n/a'}; aiohttp: {e or 'n/a'})"
        )


async def _poll_task(
    session: aiohttp.ClientSession,
    task_id: str,
    *,
    kind: str = "image-to-3d",
    timeout_sec: Optional[int] = None,
) -> Dict[str, Any]:
    if kind == "text-to-3d":
        poll_url = f"{TEXT_TO_3D_BASE}/{task_id}"
    else:
        poll_url = f"{MESHY_BASE}/{kind}/{task_id}"
    deadline = timeout_sec or MESHY_TIMEOUT_SEC
    waited = 0
    while waited < deadline:
        data = await _request_json(session, "GET", poll_url)
        status = (data.get("status") or "").upper()
        if status == "SUCCEEDED":
            return data
        if status == "FAILED":
            err = data.get("task_error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise MeshyError(msg or "Meshy task failed")
        await asyncio.sleep(5)
        waited += 5
    raise MeshyError(f"Meshy timeout ({deadline}s)")


async def _remesh_for_print(
    session: aiohttp.ClientSession,
    *,
    input_task_id: Optional[str] = None,
    model_url: Optional[str] = None,
    resize_height_m: float = 0.11,
    target_formats: Optional[List[str]] = None,
    target_polycount: int = 30000,
) -> Dict[str, Any]:
    formats = target_formats or ["stl"]
    body: Dict[str, Any] = {
        "target_formats": formats,
        "topology": "triangle",
        "target_polycount": max(12000, min(300000, int(target_polycount or 30000))),
        "resize_height": resize_height_m,
        "origin_at": "bottom",
    }
    if input_task_id:
        body["input_task_id"] = input_task_id
    elif model_url:
        body["model_url"] = model_url
    else:
        raise MeshyError("remesh: нужен input_task_id или model_url")

    created = await _request_json(session, "POST", f"{MESHY_BASE}/remesh", json_body=body)
    remesh_id = created.get("result") or created.get("id")
    if not remesh_id:
        raise MeshyError(f"No remesh task id: {str(created)[:200]}")
    logger.info("Meshy remesh task: %s", remesh_id)
    return await _poll_task(session, remesh_id, kind="remesh")


async def _fetch_format(
    session: aiohttp.ClientSession,
    result: Dict[str, Any],
    fmt: str,
) -> bytes:
    urls = result.get("model_urls") or {}
    url = urls.get(fmt)
    if not url:
        raise MeshyError(f"Meshy: нет model_urls.{fmt}")
    return await _download_url(session, url)


async def _try_fetch_format(
    session: aiohttp.ClientSession,
    result: Dict[str, Any],
    fmt: str,
) -> Optional[bytes]:
    try:
        return await _fetch_format(session, result, fmt)
    except MeshyError as e:
        logger.warning("Meshy %s skipped: %s", fmt.upper(), e)
        return None


async def _fetch_stl_from_result(
    session: aiohttp.ClientSession,
    result: Dict[str, Any],
) -> bytes:
    urls = result.get("model_urls") or {}
    stl_url = urls.get("stl")
    if stl_url:
        return await _download_url(session, stl_url)
    glb_url = urls.get("glb")
    if glb_url:
        raise MeshyError("Есть только GLB — для Bambu нужен STL после remesh")
    raise MeshyError("Meshy: нет model_urls.stl")


async def _create_text_preview(
    session: aiohttp.ClientSession,
    prompt: str,
    plan: Meshy3DPlan,
) -> str:
    body: Dict[str, Any] = {
        "mode": "preview",
        "prompt": prompt[:600],
    }
    if plan.model_type == "lowpoly":
        body["model_type"] = "lowpoly"
    else:
        body.update(
            {
                "ai_model": "latest",
                "should_remesh": not plan.preserve_source_mesh,
                "target_polycount": plan.target_polycount,
                "target_formats": ["glb", "stl", "3mf"],
            }
        )
    created = await _request_json(session, "POST", TEXT_TO_3D_BASE, json_body=body)
    preview_id = created.get("result") or created.get("id")
    if not preview_id:
        raise MeshyError(f"No preview task id: {str(created)[:200]}")
    logger.info("Meshy text-to-3d preview: %s (%s)", preview_id, plan.pipeline.value)
    await _poll_task(session, preview_id, kind="text-to-3d")
    return preview_id


async def _refine_preview(
    session: aiohttp.ClientSession,
    preview_id: str,
    plan: Meshy3DPlan,
) -> str:
    body: Dict[str, Any] = {
        "mode": "refine",
        "preview_task_id": preview_id,
        "ai_model": "latest",
        "enable_pbr": True,
        "target_formats": ["glb", "stl", "3mf"],
    }
    if plan.hd_texture:
        body["hd_texture"] = True
        body["remove_lighting"] = True
    if plan.texture_prompt:
        body["texture_prompt"] = plan.texture_prompt[:600]
    created = await _request_json(session, "POST", TEXT_TO_3D_BASE, json_body=body)
    refine_id = created.get("result") or created.get("id")
    if not refine_id:
        raise MeshyError(f"No refine task id: {str(created)[:200]}")
    logger.info("Meshy text-to-3d refine: %s", refine_id)
    await _poll_task(session, refine_id, kind="text-to-3d")
    return refine_id


async def _remesh_stl_pipeline(
    session: aiohttp.ClientSession,
    *,
    task_id: str,
    ctx: str,
    resize_m: float,
    target_polycount: int,
    method_prefix: str,
) -> Tuple[bytes, str]:
    try:
        remeshed = await _remesh_for_print(
            session,
            input_task_id=task_id,
            resize_height_m=resize_m,
            target_polycount=target_polycount,
        )
        mesh = await _fetch_stl_from_result(session, remeshed)
        stl_data, method = _postprocess_stl(mesh, method=f"{method_prefix} (STL+remesh)", user_request=ctx)
        if _has_repair_warning(method):
            try:
                remeshed2 = await _remesh_for_print(
                    session,
                    model_url=_stl_data_uri(stl_data),
                    resize_height_m=resize_m,
                    target_polycount=target_polycount,
                )
                mesh2 = await _fetch_stl_from_result(session, remeshed2)
                stl_data2, method2 = _postprocess_stl(
                    mesh2,
                    method=f"{method_prefix} (STL+remesh strict)",
                    user_request=ctx,
                )
                if _repair_candidate_is_better(method, method2):
                    return stl_data2, f"{method2}; selected over first repair: {method}"
                method = f"{method}; strict retry not better: {method2}"
            except MeshyError as e:
                method = f"{method}; strict remesh failed: {e}"
        return stl_data, method
    except MeshyError as e:
        logger.warning("Meshy remesh failed, try model_url: %s", e)
        preview = await _poll_task(session, task_id, kind="text-to-3d")
        raw = await _fetch_stl_from_result(session, preview)
        from bot.services.stl_postprocess import prepare_meshy_stl_for_bambu, repair_stl_mesh

        scaled = prepare_meshy_stl_for_bambu(raw, user_text=ctx)
        remeshed2 = await _remesh_for_print(
            session,
            model_url=_stl_data_uri(scaled.data),
            resize_height_m=resize_m,
            target_polycount=target_polycount,
        )
        mesh = await _fetch_stl_from_result(session, remeshed2)
        repaired, repair_note = repair_stl_mesh(mesh)
        method = (
            f"{method_prefix} (STL+remesh URL) · "
            f"{scaled.width_mm:.0f}×{scaled.depth_mm:.0f}×{scaled.height_mm:.0f} мм "
            f"({scaled.note}; {repair_note})"
        )
        return repaired, method


async def run_text_to_3d_delivery(
    prompt: str,
    *,
    user_request: str = "",
    plan: Optional[Meshy3DPlan] = None,
) -> MeshyDelivery:
    if not MESHY_API_KEY:
        raise MeshyError("Meshy API key не задан")

    prompt = (prompt or "").strip()[:600]
    if not prompt:
        raise MeshyError("Пустой промпт для Meshy text-to-3D")

    ctx = user_request or prompt
    plan = plan or plan_text_to_3d(ctx, prompt)
    logger.info(
        "Meshy text-to-3d prompt_id=%s ctx_id=%s prompt=%r",
        _prompt_id(prompt),
        _prompt_id(ctx),
        prompt[:220],
    )

    if plan.pipeline == Meshy3DPipeline.RIG_ANIMATE:
        from bot.services.meshy_rig import run_rig_animation_delivery

        return await run_rig_animation_delivery(prompt, user_request=ctx)

    from bot.services.stl_postprocess import target_height_mm_from_text

    resize_m = target_height_mm_from_text(ctx) / 1000.0
    delivery = MeshyDelivery(plan_label=plan.label)
    prefix = f"meshy/{plan.pipeline.value}"

    async with _create_meshy_session() as session:
        preview_id = await _create_text_preview(session, prompt, plan)
        source_id = preview_id

        if plan.use_refine:
            source_id = await _refine_preview(session, preview_id, plan)
        if plan.deliver_glb:
            try:
                source = await _poll_task(session, source_id, kind="text-to-3d")
                glb = await _fetch_format(session, source, "glb")
                delivery.files.append(
                    MeshyFile(data=glb, ext="glb", role="preview_color")
                )
            except MeshyError as e:
                logger.warning("GLB from text-to-3d skipped: %s", e)

        stl_data, method = await _remesh_stl_pipeline(
            session,
            task_id=source_id,
            ctx=ctx,
            resize_m=resize_m,
            target_polycount=plan.target_polycount,
            method_prefix=prefix,
        )
        delivery.files.insert(
            0, MeshyFile(data=stl_data, ext="stl", role="primary")
        )
        delivery.method = method
    return delivery


async def run_image_to_3d_delivery(
    image_bytes: bytes,
    mime: str,
    prompt: str = "",
    *,
    plan: Optional[Meshy3DPlan] = None,
) -> MeshyDelivery:
    if not MESHY_API_KEY:
        raise MeshyError("Meshy API key не задан")

    from bot.services.stl_postprocess import target_height_mm_from_text
    from bot.services.vision import detect_mime

    ctx = prompt or ""
    plan = plan or plan_photo_to_3d(ctx)
    mime = mime or detect_mime(image_bytes)
    resize_m = target_height_mm_from_text(ctx) / 1000.0
    logger.info("Meshy image-to-3d prompt_id=%s prompt=%r", _prompt_id(ctx), ctx[:220])

    body: Dict[str, Any] = {
        "image_url": _image_data_uri(image_bytes, mime),
        "should_remesh": not plan.preserve_source_mesh,
        "ai_model": "latest",
        "target_formats": ["glb", "stl", "3mf"],
        "target_polycount": plan.target_polycount,
        "multi_view_thumbnails": True,
    }
    if plan.model_type == "lowpoly":
        body["model_type"] = "lowpoly"
        body.pop("should_texture", None)
    elif plan.should_texture_photo:
        body["should_texture"] = True
        body["enable_pbr"] = True
        if plan.hd_texture:
            body["hd_texture"] = True
            body["remove_lighting"] = True
        if plan.texture_prompt:
            body["texture_prompt"] = plan.texture_prompt[:600]
    else:
        body["should_texture"] = False

    delivery = MeshyDelivery(plan_label=plan.label)
    prefix = f"meshy/{plan.pipeline.value}"

    async with _create_meshy_session() as session:
        created = await _request_json(
            session, "POST", f"{MESHY_BASE}/image-to-3d", json_body=body
        )
        task_id = created.get("result") or created.get("id")
        if not task_id:
            raise MeshyError(f"No task id: {str(created)[:200]}")
        logger.info("Meshy image-to-3d: %s", task_id)
        result = await _poll_task(session, task_id, kind="image-to-3d")

        native_stl = await _try_fetch_format(session, result, "stl")
        native_3mf = await _try_fetch_format(session, result, "3mf")
        native_glb = await _try_fetch_format(session, result, "glb")
        if native_glb and plan.should_texture_photo:
            delivery.files.append(MeshyFile(data=native_glb, ext="glb", role="preview_color"))
        if native_3mf:
            delivery.files.append(MeshyFile(data=native_3mf, ext="3mf", role="native_3mf"))

        # Keep Meshy web exports, but make the primary print file a repaired/centered
        # derivative of the native STL. Native 3MF can open off-bed or non-manifold in Bambu.
        if native_stl and (plan.preserve_source_mesh or native_3mf or native_glb):
            delivery.files.append(MeshyFile(data=native_stl, ext="stl", role="native_stl"))
            repaired_stl, repaired_method = _postprocess_stl(
                native_stl,
                method=f"{prefix} (Meshy native STL → Bambu repair)",
                user_request=ctx,
            )
            if _has_repair_warning(repaired_method):
                try:
                    strict = await _remesh_for_print(
                        session,
                        model_url=_stl_data_uri(repaired_stl),
                        resize_height_m=resize_m,
                        target_polycount=plan.target_polycount,
                    )
                    strict_mesh = await _fetch_stl_from_result(session, strict)
                    strict_stl, strict_method = _postprocess_stl(
                        strict_mesh,
                        method=f"{prefix} (Meshy native STL → strict Bambu remesh)",
                        user_request=ctx,
                    )
                    if _repair_candidate_is_better(repaired_method, strict_method):
                        repaired_stl = strict_stl
                        repaired_method = (
                            f"{strict_method}; selected over native repair: {repaired_method}"
                        )
                    else:
                        repaired_method = (
                            f"{repaired_method}; strict native retry not better: {strict_method}"
                        )
                except MeshyError as e:
                    repaired_method = f"{repaired_method}; strict native remesh failed: {e}"
            delivery.files.insert(0, MeshyFile(data=repaired_stl, ext="stl", role="primary"))
            delivery.method = (
                f"{repaired_method}; preserved native exports: STL"
                f"{' + 3MF' if native_3mf else ''}{' + GLB' if native_glb else ''}"
            )
            return delivery

        try:
            remeshed = await _remesh_for_print(
                session,
                input_task_id=task_id,
                resize_height_m=resize_m,
                target_polycount=plan.target_polycount,
            )
            mesh = await _fetch_stl_from_result(session, remeshed)
            stl_data, method = _postprocess_stl(
                mesh, method=f"{prefix} (STL+remesh)", user_request=ctx
            )
            if _has_repair_warning(method):
                try:
                    remeshed2 = await _remesh_for_print(
                        session,
                        model_url=_stl_data_uri(stl_data),
                        resize_height_m=resize_m,
                        target_polycount=plan.target_polycount,
                    )
                    mesh2 = await _fetch_stl_from_result(session, remeshed2)
                    stl_data2, method2 = _postprocess_stl(
                        mesh2, method=f"{prefix} (STL+remesh strict)", user_request=ctx
                    )
                    if not _has_repair_warning(method2):
                        stl_data, method = stl_data2, method2
                    else:
                        method = f"{method}; strict retry: {method2}"
                except MeshyError as e:
                    method = f"{method}; strict remesh failed: {e}"
        except MeshyError as e:
            logger.warning("Meshy photo remesh fallback: %s", e)
            mesh = native_stl or await _fetch_stl_from_result(session, result)
            stl_data, method = _postprocess_stl(
                mesh, method=f"{prefix} (STL)", user_request=ctx
            )

        delivery.files.insert(0, MeshyFile(data=stl_data, ext="stl", role="primary"))
        delivery.method = method
    return delivery


def apply_reference_split_to_delivery(delivery: MeshyDelivery, slug: str) -> int:
    """Split primary STL by reference blueprint; append ZIP + per-part STLs."""
    primary = delivery.primary
    if not primary or primary.ext != "stl":
        return 0
    from bot.services.meshy_reference_split import split_meshy_delivery

    parts, zip_bytes, _profile = split_meshy_delivery(primary.data, slug)
    if not parts:
        return 0
    if zip_bytes:
        delivery.files.append(
            MeshyFile(data=zip_bytes, ext="zip", role="reference_split_kit")
        )
    for p in parts[:24]:
        delivery.files.append(
            MeshyFile(
                data=p.stl_bytes,
                ext="stl",
                role=f"reference_part_{p.part_id}",
            )
        )
    delivery.method = (
        f"{delivery.method}; level3_reference_split={len(parts)} parts from {slug}"
    )
    return len(parts)


async def run_meshy_with_reference_level3(
    prompt: str,
    *,
    user_request: str = "",
    plan: Optional[Meshy3DPlan] = None,
) -> MeshyDelivery:
    """Level 3: mood-board image-to-3D when useful, then blueprint-based STL split."""
    from bot.services.airplane_3mf import airplane_wants_realistic_mesh
    from bot.services.meshy_level3 import build_meshy_level3_plan

    ctx = user_request or prompt
    plan = plan or plan_text_to_3d(ctx, prompt)

    # Realistic airliners: skip mood-board image-to-3D (slow, often times out) and
    # reference split (AMS multi-object shards). Direct text-to-3D is faster and
    # produces one printable sculpted STL.
    if airplane_wants_realistic_mesh(ctx):
        from bot.services.meshy_plan import plan_airliner_text_to_3d

        air_plan = plan_airliner_text_to_3d(ctx, prompt, fast=True)
        delivery = await run_text_to_3d_delivery(
            prompt, user_request=ctx, plan=air_plan
        )
        delivery.method = f"{delivery.method}; airliner_direct_text_to_3d"
        return delivery

    l3 = build_meshy_level3_plan(ctx)
    full_prompt = (prompt + l3.prompt_suffix)[:600]

    if l3.use_image_to_3d and l3.mood_board_png:
        logger.info(
            "Meshy level3: image-to-3D via mood board slug=%s parts=%s",
            l3.slug,
            l3.blueprint_part_count,
        )
        delivery = await run_image_to_3d_delivery(
            l3.mood_board_png,
            "image/png",
            full_prompt,
            plan=plan,
        )
        delivery.method = f"{delivery.method}; level3_mood_board={l3.slug}"
    else:
        delivery = await run_text_to_3d_delivery(
            full_prompt, user_request=ctx, plan=plan
        )
        if l3.enabled and l3.slug:
            delivery.method = f"{delivery.method}; level3_prompt_ref={l3.slug}"

    if l3.apply_split and l3.slug:
        n = apply_reference_split_to_delivery(delivery, l3.slug)
        if n:
            delivery.plan_label = f"{delivery.plan_label or plan.label} + ref-split×{n}"

    return delivery


async def meshy_text_to_image(
    prompt: str,
    *,
    user_request: str = "",
    plan: Optional[MeshyImagePlan] = None,
) -> Tuple[bytes, str, str]:
    """Картинка по тексту (nano-banana / pro). Возвращает bytes, mime, method."""
    if not MESHY_API_KEY:
        raise MeshyError("Meshy API key не задан")

    plan = plan or plan_text_to_image(user_request or prompt)
    prompt_for_api = (prompt or user_request or "")[:800]
    logger.info(
        "Meshy text-to-image prompt_id=%s user_id=%s prompt=%r",
        _prompt_id(prompt_for_api),
        _prompt_id(user_request or prompt_for_api),
        prompt_for_api[:220],
    )
    body: Dict[str, Any] = {
        "ai_model": plan.ai_model,
        "prompt": prompt_for_api,
    }
    if plan.generate_multi_view:
        body["generate_multi_view"] = True
    else:
        body["aspect_ratio"] = plan.aspect_ratio

    async with _create_meshy_session() as session:
        created = await _request_json(
            session, "POST", f"{MESHY_BASE}/text-to-image", json_body=body
        )
        task_id = created.get("result") or created.get("id")
        if not task_id:
            raise MeshyError(f"No text-to-image id: {str(created)[:200]}")
        logger.info("Meshy text-to-image: %s (%s)", task_id, plan.ai_model)
        result = await _poll_task(session, task_id, kind="text-to-image")
        urls = result.get("image_urls") or []
        if not urls:
            raise MeshyError("Meshy text-to-image: нет image_urls")
        raw = await _download_url(session, urls[0])
        method = f"meshy/text-to-image ({plan.ai_model}, task {str(task_id)[-8:]})"
        return raw, "image/png", method


async def image_to_stl_mesh(
    image_bytes: bytes,
    mime: str,
    prompt: str = "",
) -> Optional[Tuple[bytes, str]]:
    delivery = await run_image_to_3d_delivery(
        image_bytes, mime, prompt, plan=plan_photo_to_3d(prompt)
    )
    primary = delivery.primary
    if not primary:
        return None
    return primary.data, delivery.method


async def text_to_stl_mesh(
    prompt: str,
    *,
    user_request: str = "",
) -> Optional[Tuple[bytes, str]]:
    delivery = await run_text_to_3d_delivery(
        prompt,
        user_request=user_request,
        plan=plan_text_to_3d(user_request or prompt, prompt),
    )
    primary = delivery.primary
    if not primary:
        return None
    return primary.data, delivery.method
