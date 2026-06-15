import asyncio
import logging
import re
from typing import Awaitable, Optional, Tuple, TypeVar

from aiogram.types import BufferedInputFile, Message

from bot.config import AVAILABLE_MODELS, DEFAULT_MODEL
from bot.services import history, llm
from bot.services.file_output import (
    detect_file_format,
    infer_format_from_refusal,
    looks_like_file_refusal,
    parse_file_count,
    produce_file_items,
    resolve_output_file_format,
    should_refuse_placeholder_stl,
    wants_3d_model_from_photo,
    wants_file_output,
)
from bot.services.print_profile import (
    format_profile,
    format_questionnaire,
    merge_profiles,
    missing_fields,
    parse_print_profile,
)
from bot.services.pending_3d import (
    PendingEngineeringIntake,
    Pending3DJob,
    get_pending,
    get_pending_concept,
    get_pending_engineering,
    pop_pending,
    pop_pending_concept,
    pop_pending_engineering,
    set_pending,
    set_pending_engineering,
)
from bot.services.print_project import (
    build_project_zip,
    export_single_part_stl,
    generate_project_specs,
    generate_single_part_specs,
    is_single_part_print_request,
    wants_print_project,
)
from bot.services.image_output import (
    format_method_label,
    produce_image,
    wants_image_output,
    wants_pdf_output,
)
from bot.services.processing import clear_busy, set_busy
from bot.status_ui import StatusIndicator
from bot.services.self_check import DeliveredFile, DeliveryResult
from bot.utils import split_message


T = TypeVar("T")
logger = logging.getLogger(__name__)


async def _wait_with_progress(
    indicator: StatusIndicator,
    awaitable: Awaitable[T],
    *,
    detail: str,
    timeout: int,
    eta_seconds: int,
) -> T:
    """Keep Telegram status alive while an external API job is running."""
    indicator.start_progress(detail, eta_seconds=eta_seconds)
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    finally:
        indicator.stop_progress()


def _skip_meshy_component_ams_split(user_text: str, delivery) -> bool:
    """Never let connected-component AMS split replace Meshy geometry.

    Meshy often returns one sculpted mesh; naive connected-component splitting can
    create zero-volume shards in Bambu. The printable Meshy-derived STL/native
    export is the primary result for every subject, not just Boeing.
    """
    return True


def _meshy_requires_object_level_result(user_text: str, *, is_anim: bool = False) -> bool:
    """Return True when a single Meshy mesh cannot honestly satisfy the request."""
    if is_anim:
        return False
    from bot.services.bambu_hints import extract_part_color_requests
    from bot.services.articulated_3mf import articulation_requested

    t = user_text or ""
    if extract_part_color_requests(t):
        return True
    if articulation_requested(t):
        return True
    return bool(
        re.search(
            r"отдельн.{0,24}(детал|объект|част)|раздельн.{0,24}(детал|объект|цвет)|"
            r"multi[\s-]?object|несколько\s+детал|object[\s-]?level|"
            r"ams.{0,40}(детал|объект|разн|цвет)|амс.{0,40}(детал|объект|разн|цвет)",
            t,
            re.I,
        )
    )


async def _send_meshy_3d_files(
    message: Message,
    delivery,
    *,
    base_caption: str,
    primary_fname: str,
    user_id: int,
    history_user: str,
    history_assistant: str,
    include_preview_glb: bool = False,
    user_text_for_support: str = "",
    support_profile: Optional[dict] = None,
    require_object_level_colors: bool = False,
) -> DeliveryResult:
    """STL / GLB анимация / цветной GLB — по ролям файлов."""
    files_out: list[DeliveredFile] = []
    primary = delivery.primary
    if not primary:
        return DeliveryResult(summary="Meshy empty", success=False)

    split_zip = next((f for f in delivery.files if f.role == "reference_split_kit"), None)
    split_parts = [f for f in delivery.files if f.role.startswith("reference_part_")]

    static = next((f for f in delivery.files if f.role == "print_static"), None)
    base = primary_fname.rsplit(".", 1)[0]
    from bot.services.bambu_hints import extract_part_color_requests

    part_color_requests = extract_part_color_requests(user_text_for_support or history_user)
    color_limitation_warning = bool(part_color_requests)
    color_warning_sent = False
    native_3mf_sent = False

    async def send_visual_glb_preview(reason: str) -> bool:
        sent = False
        for extra in delivery.files:
            if extra.role != "preview_color":
                continue
            glb_name = f"{base}-best-meshy-visual.glb"
            await message.answer_document(
                BufferedInputFile(extra.data, filename=glb_name),
                caption=(
                    "Лучший Meshy visual asset: textured GLB/PBR для просмотра качества геометрии и цветов. "
                    f"Для Bambu/печати отдельно проверяю 3MF/STL. Причина: {reason}"
                )[:1024],
            )
            files_out.append(
                DeliveredFile(filename=glb_name, size_bytes=len(extra.data), kind="glb")
            )
            sent = True
        return sent

    async def send_native_3mf_asset(reason: str) -> bool:
        nonlocal native_3mf_sent
        if native_3mf_sent:
            return False
        sent = False
        for extra in delivery.files:
            if extra.role != "native_3mf":
                continue
            fname = f"{base}-meshy-native.3mf"
            await message.answer_document(
                BufferedInputFile(extra.data, filename=fname),
                caption=(
                    "Meshy-native 3MF как на сайте Meshy: этот файл не ремешится и не упрощается ботом. "
                    f"Причина выдачи: {reason}"
                )[:1024],
            )
            files_out.append(
                DeliveredFile(
                    filename=fname,
                    size_bytes=len(extra.data),
                    kind="3mf",
                    meta={"source": "meshy_native"},
                )
            )
            sent = True
        native_3mf_sent = native_3mf_sent or sent
        return sent

    async def send_color_limitation_warning() -> None:
        nonlocal color_warning_sent
        if color_warning_sent or not color_limitation_warning:
            return
        requested = ", ".join(f"{part}={color}" for part, color in part_color_requests.items())
        await message.answer(
            "⚠️ Цвета деталей: я понял запрос "
            f"({requested}), но Meshy обычно возвращает один цельный mesh. "
            "Если файл откроется как один объект, Bambu/AMS не сможет автоматически назначить разные цвета "
            "отдельным деталям. Основным результатом всё равно остаётся Meshy-derived файл; "
            "ручную раскраску можно сделать в Bambu Studio через Paint/Color Painting.",
            parse_mode=None,
        )
        color_warning_sent = True

    def repair_note_is_ok(note: str) -> bool:
        return "repair OK" in (note or "")

    def repair_note_count(note: str) -> Optional[int]:
        m = re.search(r"(\d+)\s+non-manifold", note or "", re.I)
        return int(m.group(1)) if m else None

    def repair_note_better(current: str, candidate: str) -> bool:
        if repair_note_is_ok(candidate) and not repair_note_is_ok(current):
            return True
        cur = repair_note_count(current)
        cand = repair_note_count(candidate)
        return cur is not None and cand is not None and cand < cur

    async def final_repair_stl_before_send(data: bytes) -> tuple[bytes, str, bool]:
        """Last gate before Telegram: Bambu must not receive the known-bad STL bytes."""
        try:
            from bot.services.stl_postprocess import (
                manifold_repair_stl_mesh,
                prepare_meshy_stl_for_bambu,
            )

            repaired, note = await asyncio.to_thread(
                manifold_repair_stl_mesh, data, timeout=300
            )
            if not repair_note_is_ok(note):
                try:
                    prepared = await asyncio.to_thread(
                        prepare_meshy_stl_for_bambu,
                        data,
                        user_text=user_text_for_support or history_user,
                    )
                    candidate_note = prepared.note
                    if repair_note_better(note, candidate_note):
                        repaired = prepared.data
                        note = f"{candidate_note}; selected over final manifold repair: {note}"
                    else:
                        note = f"{note}; final prepare retry not better: {candidate_note}"
                except Exception as e:
                    note = f"{note}; final prepare retry failed: {type(e).__name__}: {str(e)[:100]}"
            ok = repair_note_is_ok(note)
            logger.info(
                "Meshy final STL repair %s for %s: %s",
                "OK" if ok else "WARNING",
                primary_fname,
                note[:400],
            )
            return repaired, note, ok
        except Exception as e:
            note = f"final repair skip: {type(e).__name__}: {str(e)[:100]}"
            logger.warning("Meshy final STL repair failed for %s: %s", primary_fname, note)
            return data, note, False

    final_repair_note = ""
    final_repair_ok = True

    if primary.ext == "glb":
        await send_color_limitation_warning()
        anim_name = f"{base}-animated.glb"
        await message.answer_document(
            BufferedInputFile(primary.data, filename=anim_name),
            caption=base_caption[:1024],
        )
        files_out.append(
            DeliveredFile(
                filename=anim_name,
                size_bytes=len(primary.data),
                kind="glb",
            )
        )
        if static:
            stl_name = f"{base}-static.stl"
            await message.answer_document(
                BufferedInputFile(static.data, filename=stl_name),
                caption="🧊 Статичный STL для печати (анимация — в GLB выше).",
            )
            files_out.append(
                DeliveredFile(
                    filename=stl_name,
                    size_bytes=len(static.data),
                    kind="stl",
                )
            )
    else:
        if primary.ext == "stl" and user_text_for_support:
            if part_color_requests and not _skip_meshy_component_ams_split(
                user_text_for_support, delivery
            ):
                try:
                    from bot.services.support_3mf import wrap_stl_as_component_3mf

                    data_components, fname_components, component_meta = wrap_stl_as_component_3mf(
                        primary.data,
                        stl_filename=primary_fname,
                        user_text=user_text_for_support,
                        profile=support_profile or {},
                    )
                    if component_meta.get("object_level_colors"):
                        cap_components = (
                            base_caption
                            + "\n\n📎 Дополнительный AMS 3MF из компонентов STL (не основной Meshy-файл). "
                            "Если Bambu ругается на zero volume / too small — откройте основной "
                            f"{primary_fname} или meshy-native.3mf."
                        )
                        await message.answer_document(
                            BufferedInputFile(data_components, filename=fname_components),
                            caption=cap_components[:1024],
                        )
                        files_out.append(
                            DeliveredFile(
                                filename=fname_components,
                                size_bytes=len(data_components),
                                kind="3mf",
                                meta={"source": "meshy_components_optional", **component_meta},
                            )
                        )
                except Exception:
                    await send_color_limitation_warning()
            elif part_color_requests:
                await send_color_limitation_warning()
                if native_3mf_sent or any(
                    getattr(f, "role", "") == "native_3mf" for f in delivery.files
                ):
                    await message.answer(
                        "ℹ️ Для Meshy не делаю components-ams split: он часто даёт zero-volume осколки в Bambu. "
                        f"Основной файл для печати — {primary_fname} (Meshy-derived, уже в мм и на столе). "
                        "Meshy-native 3MF — только как эталон качества с сайта Meshy.",
                        parse_mode=None,
                    )
            from bot.services.bambu_hints import needs_auto_support_project

            meshy_primary_only = _skip_meshy_component_ams_split(user_text_for_support, delivery)
            if needs_auto_support_project(user_text_for_support) and not meshy_primary_only:
                try:
                    from bot.services.support_3mf import wrap_stl_as_support_3mf

                    data_3mf, fname_3mf = wrap_stl_as_support_3mf(
                        primary.data,
                        stl_filename=primary_fname,
                        user_text=user_text_for_support,
                        profile=support_profile or {},
                    )
                    cap_3mf = base_caption + "\n\n📎 Дополнительный 3MF с Tree(auto) supports."
                    if meshy_primary_only:
                        cap_3mf += (
                            f" Основной файл для печати — {primary_fname} (Meshy-derived STL), не этот 3MF."
                        )
                    else:
                        cap_3mf += " Голый STL для такой фигуры не считаю финальным print-ready файлом."
                    await message.answer_document(
                        BufferedInputFile(data_3mf, filename=fname_3mf),
                        caption=cap_3mf[:1024],
                    )
                    files_out.append(
                        DeliveredFile(
                            filename=fname_3mf,
                            size_bytes=len(data_3mf),
                            kind="3mf",
                            meta={
                                "source": "meshy_stl_support_optional"
                                if meshy_primary_only
                                else "meshy_stl",
                                "supports": "tree(auto)",
                            },
                        )
                    )
                    if not meshy_primary_only:
                        from bot.services.bambu_hints import bambu_print_steps

                        await message.answer(
                            bambu_print_steps(user_text_for_support, file_kind="3mf"),
                            parse_mode=None,
                        )
                        if include_preview_glb:
                            await send_visual_glb_preview(
                                "3MF support wrapper is print-oriented; GLB keeps Meshy visual quality."
                            )
                        await history.add_message(user_id, "user", history_user[:500])
                        await history.add_message(user_id, "assistant", history_assistant)
                        return DeliveryResult(
                            summary=history_assistant,
                            files=files_out,
                            meta={
                                "meshy_method": delivery.method,
                                "meshy_plan": delivery.plan_label,
                                "support_3mf": True,
                                "native_3mf": native_3mf_sent,
                                "part_color_requests": part_color_requests,
                                "color_limitation_warning": color_limitation_warning,
                            },
                            success=True,
                        )
                except Exception as e:
                    if not meshy_primary_only:
                        await message.answer(
                            "⚠️ Не удалось автоматически обернуть STL в 3MF с поддержками "
                            f"({e}). Отправляю STL, но для печати включите Tree(auto).",
                            parse_mode=None,
                        )
        await send_color_limitation_warning()
        primary_data = primary.data
        final_repair_note = ""
        final_repair_ok = primary.ext != "stl"
        if primary.ext == "stl":
            await message.answer(
                "🛠 Финально проверяю STL перед отправкой в Bambu Studio: manifold repair + post-check.",
                parse_mode=None,
            )
            primary_data, final_repair_note, final_repair_ok = await final_repair_stl_before_send(
                primary.data
            )
        repair_prefix = ""
        if final_repair_note:
            status = "✅ Финальная Bambu-проверка STL: repair OK." if final_repair_ok else "⚠️ Финальная Bambu-проверка STL: repair не стал идеальным."
            repair_prefix = f"{status}\n{final_repair_note[:420]}\n\n"
        stl_caption = repair_prefix + base_caption
        if (
            final_repair_ok
            and part_color_requests
            and _skip_meshy_component_ams_split(user_text_for_support, delivery)
        ):
            stl_caption += (
                "\n\n✅ Основной print-ready файл: этот STL (Meshy-derived, мм, на столе). "
                "Не открывайте components-ams — для Meshy он часто ломается в Bambu."
            )
        elif primary.ext == "stl" and not final_repair_ok:
            stl_caption += (
                "\n\n⚠️ Этот Meshy STL отправлен как лучший доступный Meshy-результат, "
                "но не называю его готовым print-ready: Bambu может показать repair warning."
            )
        await message.answer_document(
            BufferedInputFile(primary_data, filename=primary_fname),
            caption=stl_caption[:1024],
        )
        if re.search(r"boeing|боинг|самол[её]т|airliner|airplane", user_text_for_support or history_user, re.I):
            try:
                from bot.services.mesh_cache import save_mesh_asset

                save_mesh_asset(
                    user_id,
                    "boeing_airliner_last_meshy",
                    data=primary_data,
                    filename=primary_fname,
                    meta={
                        "source": "meshy_final_send",
                        "method": delivery.method,
                        "final_repair": final_repair_note,
                        "final_repair_ok": final_repair_ok,
                    },
                )
            except Exception as e:
                logger.warning("Could not cache Meshy Boeing asset: %s", e)
        files_out.append(
            DeliveredFile(
                filename=primary_fname,
                size_bytes=len(primary_data),
                kind=_file_kind(primary_fname, meshy=True),
                meta={"final_repair": final_repair_note} if final_repair_note else {},
            )
        )
        if primary.ext == "stl" and user_text_for_support:
            await send_native_3mf_asset(
                "оригинальный Meshy export для сравнения; основной STL отправлен выше после финальной проверки."
            )
        if split_zip:
            zip_name = f"{base}-reference-split-kit.zip"
            await message.answer_document(
                BufferedInputFile(split_zip.data, filename=zip_name),
                caption=(
                    "📦 Level 3: разрез Meshy-скульпта по blueprint из вашей библиотеки "
                    f"({len(split_parts)} STL внутри + manifest). Цельный sculpt — "
                    f"`00_whole_meshy_sculpt.stl`."
                )[:1024],
            )
            files_out.append(
                DeliveredFile(
                    filename=zip_name,
                    size_bytes=len(split_zip.data),
                    kind="zip",
                    meta={"source": "reference_split_kit"},
                )
            )

    if include_preview_glb:
        for extra in delivery.files:
            if extra.role != "preview_color":
                continue
            glb_name = f"{base}-colors.glb"
            await message.answer_document(
                BufferedInputFile(extra.data, filename=glb_name),
                caption="🎨 GLB с текстурами — просмотр цветов (печать — STL).",
            )
            files_out.append(
                DeliveredFile(
                    filename=glb_name,
                    size_bytes=len(extra.data),
                    kind="glb",
                )
            )

    await history.add_message(user_id, "user", history_user[:500])
    await history.add_message(user_id, "assistant", history_assistant)
    return DeliveryResult(
        summary=history_assistant,
        files=files_out,
        meta={
            "meshy_method": delivery.method,
            "meshy_plan": delivery.plan_label,
            "native_3mf": native_3mf_sent,
            "meshy_derived_print_ready": True,
            "final_repair": final_repair_note,
            "final_repair_ok": final_repair_ok,
            "repair_warning_accepted": (
                _meshy_delivery_has_repair_warning(delivery) or (primary.ext == "stl" and not final_repair_ok)
            ),
            "part_color_requests": part_color_requests,
            "color_limitation_warning": color_limitation_warning,
        },
        success=True,
    )


def _file_kind(name: str, *, meshy: bool = False) -> str:
    low = (name or "").lower()
    if meshy:
        return "meshy"
    if low.endswith(".stl"):
        return "stl"
    if low.endswith(".glb"):
        return "glb"
    if low.endswith(".scad"):
        return "scad"
    if low.endswith(".zip"):
        return "zip"
    if low.endswith(".pdf"):
        return "pdf"
    return "file"


def _local_card_facts(
    image_data: bytes,
    prompt_text: str,
    width: int,
    height: int,
) -> str:
    size_kb = len(image_data) // 1024
    return (
        f"Метод: локально (без KupiAPI).\n"
        f"Размер: {width}×{height} px, {size_kb} KB.\n"
        f"Запрос пользователя: {prompt_text.strip()}"
    )


async def _send_v3_figure8_print_pack(message: Message) -> DeliveryResult:
    """v3: ZIP с OpenSCAD/STL/3MF + PDF после одобрения пользователя."""
    from bot.services.hybrid_v3_figure8_corpus import build_v3_print_pack, default_figure8_spec
    from bot.services.openscad import openscad_available

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    set_busy(user_id, "v3 корпус 3MF")
    try:
        saved = await history.get_print_profile(user_id)
        profile = merge_profiles(saved, parse_print_profile(""))
        spec = default_figure8_spec()
        await message.answer(
            f"🖨 v3 — комплект P2S: «8» {spec.footprint_x_mm:.0f}×{spec.footprint_y_mm:.0f} мм, "
            f"подставка отдельно, {spec.screw_count}× M3.",
            parse_mode=None,
        )
        await indicator.show("🟡", "Обрабатываю", "STL → 3MF (3 детали)…")
        data, filename, n_parts, has_3mf = await build_v3_print_pack(profile)
        await indicator.done()
        if has_3mf:
            extra = "\n✅ 3MF в 3mf/ — импорт в Bambu Studio → Печать."
        elif openscad_available():
            extra = "\n⚠️ STL есть, 3MF не все — проверьте stl/ и scad/."
        else:
            extra = "\nℹ️ Установите OpenSCAD — в архиве PDF + SCAD."
        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption=(
                f"📦 Корпус «восьмёрки» v3 — {n_parts} детали\n"
                f"01 подставка · 02 нижняя · 03 верхняя{extra}"
            )[:1024],
        )
        await history.add_message(user_id, "assistant", "Отправлен ZIP v3: 3MF/STL корпус восьмёрки.")
        from bot.services.pending_3d import clear_pending_v3_figure8

        clear_pending_v3_figure8(user_id)
        return DeliveryResult(
            summary="ZIP v3 корпус восьмёрки",
            success=has_3mf,
            files=[DeliveredFile(filename=filename, size_bytes=len(data), kind="zip")],
        )
    except Exception as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)


async def _send_v3_figure8_preview(message: Message) -> DeliveryResult:
    """v3: PDF-превью + сразу ZIP с 3MF/STL."""
    from bot.services.hybrid_v3_figure8_corpus import (
        build_v3_corpus_pdf,
        build_v3_intro_message,
        build_v3_print_pack,
        default_figure8_spec,
    )
    from bot.services.openscad import openscad_available

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    set_busy(user_id, "v3 корпус PDF+3MF")
    try:
        spec = default_figure8_spec()
        saved = await history.get_print_profile(user_id)
        profile = merge_profiles(saved, parse_print_profile(""))
        await message.answer(build_v3_intro_message(spec), parse_mode=None)
        await indicator.show("🟡", "Обрабатываю", "Чертежи PDF → STL → 3MF…")
        pdf_bytes = build_v3_corpus_pdf(spec)
        data, filename, n_parts, has_3mf = await build_v3_print_pack(profile)
        await indicator.done()
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename="figure8-corpus-v3-preview.pdf"),
            caption=(
                "📄 PDF: подставка / нижняя / верхняя / разрез / сборка.\n"
                "Сквозной канал «8» без горловины — проверьте центр и ложа подставки."
            )[:1024],
        )
        if has_3mf:
            extra = "\n✅ 3MF в 3mf/ — импорт в Bambu Studio."
        elif openscad_available():
            extra = "\n⚠️ STL есть, часть 3MF не собралась."
        else:
            extra = "\nℹ️ STL + PDF в архиве."
        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption=(
                f"📦 v3 — {n_parts} детали: подставка · нижняя · верхняя{extra}"
            )[:1024],
        )
        from bot.services.pending_3d import clear_pending_v3_figure8

        clear_pending_v3_figure8(user_id)
        await history.add_message(user_id, "assistant", "Отправлены PDF и ZIP v3 (восьмёрка).")
        return DeliveryResult(
            summary="PDF+ZIP v3 корпус восьмёрки",
            success=has_3mf,
            files=[
                DeliveredFile(filename="figure8-corpus-v3-preview.pdf", size_bytes=len(pdf_bytes), kind="pdf"),
                DeliveredFile(filename=filename, size_bytes=len(data), kind="zip"),
            ],
        )
    except Exception as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)


async def _send_print_project(
    message: Message,
    user_request: str,
    text_model: str,
    *,
    context: str = "",
    storyboard_frames: Optional[list] = None,
) -> DeliveryResult:
    """Локальный ZIP: OpenSCAD + план печати + сборка (+ STL если openscad CLI)."""
    from bot.services.openscad import openscad_available

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    saved = await history.get_print_profile(user_id)
    profile = merge_profiles(saved, parse_print_profile(user_request))
    from bot.services.print_project import preview_project_build
    from bot.services.hybrid_generator import (
        build_hybrid_generator_print_pack,
        hybrid_generator_parts,
        hybrid_generator_v2_parts,
        is_hybrid_generator_storyboard,
    )
    from bot.services.hybrid_consultation import (
        build_consultation_messages,
        build_hybrid_presentation_pdf,
    )

    hybrid_project = bool(
        is_hybrid_generator_storyboard(storyboard_frames, f"{user_request}\n{context}")
    )

    preview_n, preview_label, _preview_specs = preview_project_build(
        user_request, context or user_request
    )
    if hybrid_project:
        v1_n = len(hybrid_generator_parts())
        v2_n = len(hybrid_generator_v2_parts())
        part_count = v1_n + v2_n
        status_detail = f"Собираю v1 ({v1_n}) + v2 ({v2_n}) 3MF, PDF и планы…"
    elif storyboard_frames:
        printable_n = len([f for f in storyboard_frames if f.get("printable", True)]) or len(
            storyboard_frames
        )
        part_count = max(printable_n, preview_n or 0)
        status_detail = f"Собираю проект ({part_count} дет.) по вашей раскадровке…"
    elif preview_n:
        part_count = preview_n
        if preview_label.startswith("mechanical Boeing"):
            status_detail = (
                f"Собираю {preview_label}: {part_count} деталей "
                f"(сначала 3 fit-coupons, затем корпус и узлы)…"
            )
        else:
            status_detail = f"Собираю {preview_label}: {part_count} деталей…"
    else:
        part_count = parse_file_count(user_request, 8)
        status_detail = f"Собираю проект (~{part_count} дет.)…"

    set_busy(user_id, "проект на печать")
    try:
        if hybrid_project:
            for part in build_consultation_messages(storyboard_frames):
                await message.answer(part, parse_mode=None)

        await indicator.show(
            "🟡",
            "Обрабатываю",
            status_detail,
        )
        specs = await generate_project_specs(
            user_request,
            context or user_request,
            text_model,
            part_count=part_count,
            storyboard_frames=storyboard_frames,
        )
        reject_reason = specs_is_unprintable_fallback(specs, user_request)
        if reject_reason:
            await indicator.done()
            await message.answer(f"⚠️ {reject_reason}", parse_mode=None)
            return DeliveryResult(summary=reject_reason, success=False, meta={"fallback_blocked": True})

        if profile.get("printer") or profile.get("material"):
            await history.set_print_profile(user_id, profile)

        ordered_stl: list = []
        pdf_bytes: Optional[bytes] = None
        if hybrid_project and specs.get("mode") == "hybrid-storyboard":
            data, filename, n_parts, has_stl = await build_hybrid_generator_print_pack(
                profile, frames=storyboard_frames
            )
            pdf_bytes = build_hybrid_presentation_pdf(storyboard_frames)
            caption = (
                f"📦 Гибридный генератор: v1 + v2 ({n_parts} деталей)\n"
                f"• v1-storyboard/3mf/ — раскадровка «восьмёрка»\n"
                f"• v2-improved/3mf/ — U-петля (рекомендуется)\n"
                f"• pdf/ и guides/ — презентация и пошаговые планы"
            )
        else:
            data, filename, caption, n_parts, has_stl, ordered_stl = await build_project_zip(
                specs, profile
            )
        await indicator.done()
        if hybrid_project and has_stl:
            extra = (
                "\n✅ 3MF в v1-storyboard/ и v2-improved/ — Bambu Studio → Печать."
                "\n📄 PDF-презентация — отдельным файлом ниже."
            )
        elif has_stl:
            extra = "\n✅ STL внутри архива — сразу в Bambu Studio."
        elif openscad_available():
            extra = "\n✅ OpenSCAD работает — STL должны быть в папке stl/."
        else:
            extra = "\nℹ️ Откройте scad/*.scad → F6 → Export STL."
        ref_lib = specs.get("reference_library") or {}
        if ref_lib.get("primary_slug"):
            extra += (
                f"\n📚 Референс: {ref_lib.get('primary_slug')} "
                f"({ref_lib.get('primary_stl_count', '?')} STL в библиотеке)."
            )
        if specs.get("project_kind") == "mechanical_boeing_airliner":
            extra += (
                f"\n📋 Всего {n_parts} деталей: 01–03 fit-coupons, затем шасси/лопасти/корпус. "
                "Порядок — engineering/fit_first_print_order.txt."
            )
        elif specs.get("project_kind") == "hybrid_electromagnetic_generator":
            extra += (
                f"\n📋 {n_parts} печатных деталей. tube_clip ×6, coil_bobbin ×2 — "
                "количество копий в Bambu Studio."
            )
        elif specs.get("project_kind") in {
            "rc_aircraft_kit",
            "drone_fpv_kit",
            "vehicle_kit",
            "robot_mechanism_kit",
            "architecture_miniature",
            "reference_guided_kit",
        }:
            extra += f"\n📋 {n_parts} деталей — CAD-kit по локальной библиотеке референсов."

        preview_pose: Optional[bytes] = None
        if has_stl and specs.get("project_kind") == "mechanical_boeing_airliner":
            import zipfile
            from io import BytesIO

            try:
                with zipfile.ZipFile(BytesIO(data), "r") as zf:
                    preview_pose = zf.read("preview/assembly_pose.stl")
            except KeyError:
                preview_pose = None

        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption=(caption + extra)[:1024],
        )

        if hybrid_project and pdf_bytes:
            await message.answer_document(
                BufferedInputFile(pdf_bytes, filename="hybrid-generator-presentation.pdf"),
                caption=(
                    "📄 PDF-презентация: оценка v1, улучшение v2, "
                    "пошаговые планы печати и сборки."
                )[:1024],
            )

        if preview_pose and len(preview_pose) > 500:
            await message.answer_document(
                BufferedInputFile(preview_pose, filename="assembly_pose_preview.stl"),
                caption=(
                    "👁 NACA-референс собранного самолёта (как должен выглядеть после сборки). "
                    "Реальные печатные детали лежат в ZIP по отдельности — это эталон пропорций. "
                    f"Раскладка деталей для печати — preview/parts_layout_print_orientation.stl в ZIP."
                )[:1024],
            )

        if ordered_stl and specs.get("mode") not in (
            "fallback_single",
            "fallback",
            "fallback-network",
            "hybrid-storyboard",
        ):
            await message.answer(
                f"📎 Отправляю {len(ordered_stl)} STL по порядку кадров (1 → {len(ordered_stl)})…"
            )
            failed_idx: list[int] = []
            for idx, (frame_num, stl_bytes, stl_name, cap_stl) in enumerate(ordered_stl, start=1):
                # Retry up to 3 times to survive transient Telegram errors / rate limits.
                # Without this, one network glitch silently swallows the rest of the kit
                # ("не все прислал" bug).
                sent = False
                last_err: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        await message.answer_document(
                            BufferedInputFile(stl_bytes, filename=stl_name),
                            caption=f"📎 {idx}/{len(ordered_stl)} · {cap_stl}"[:1024],
                        )
                        sent = True
                        break
                    except Exception as e:
                        last_err = e
                        # Backoff: 1s, 2s, 4s
                        await asyncio.sleep(2 ** attempt)
                if not sent:
                    failed_idx.append(idx)
                    logger.warning("STL send failed idx=%s name=%s err=%s", idx, stl_name, last_err)
                # Small pacing to avoid hitting Telegram's flood limit on big kits
                await asyncio.sleep(0.2)
            if failed_idx:
                await message.answer(
                    f"⚠️ Не отправил {len(failed_idx)} STL (#{', #'.join(map(str, failed_idx))}). "
                    "Все детали есть внутри ZIP в папке stl/ — откройте архив."
                )
        await history.save_project_context(
            user_id,
            str(specs.get("project_name") or "print-project"),
            (context or user_request)[:8000],
        )
        await history.add_message(user_id, "user", user_request[:500])
        await history.add_message(
            user_id,
            "assistant",
            f"Отправлен проект на печать ({n_parts} дет., ZIP).",
        )
        files = [
            DeliveredFile(
                filename=filename,
                size_bytes=len(data),
                kind="zip",
            )
        ]
        for _, stl_bytes, stl_name, _ in ordered_stl or []:
            files.append(
                DeliveredFile(
                    filename=f"{stl_name}.stl",
                    size_bytes=len(stl_bytes),
                    kind="stl",
                )
            )
        parts_list = specs.get("parts") or []
        return DeliveryResult(
            summary=f"Отправлен проект на печать ({n_parts} дет., ZIP).",
            files=files,
            success=True,
            meta={
                "parts_count": n_parts,
                "has_stl": has_stl,
                "project_kind": specs.get("project_kind"),
                "strategy": specs.get("strategy"),
                "min_wall_mm": specs.get("min_wall_mm"),
                "print_prep_contract": specs.get("print_prep_contract"),
                "zero_to_print": bool(specs.get("print_prep_contract")),
                "assembly_version": specs.get("assembly_version"),
                "kinematics_joints": len(specs.get("kinematics") or []),
                "fit_coupon_ids": specs.get("fit_first_coupon_ids") or [],
                "part_templates": [p.get("template") for p in parts_list if isinstance(p, dict)],
                "part_ids": [p.get("id") for p in parts_list if isinstance(p, dict)],
            },
        )
    except llm.LLMError as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    except Exception as e:
        await indicator.error(f"Не удалось собрать проект: {e}")
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)


async def _send_single_print_part(
    message: Message,
    user_request: str,
    text_model: str,
) -> DeliveryResult:
    """Одна деталь (ручка, кронштейн…) — STL, не ZIP генератора."""
    from bot.services.openscad import build_scad_source, openscad_available

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    saved = await history.get_print_profile(user_id)
    profile = merge_profiles(saved, parse_print_profile(user_request))

    set_busy(user_id, "3d модель")
    try:
        await indicator.show("🟡", "Обрабатываю", "Готовлю одну деталь для печати…")
        specs = await generate_single_part_specs(
            user_request, text_model, profile=profile
        )
        if profile.get("printer") or profile.get("material"):
            await history.set_print_profile(user_id, profile)

        stl_bytes, filename, caption, part = await export_single_part_stl(specs)
        await indicator.done()
        payload = stl_bytes
        fkind = "stl"
        if stl_bytes:
            await message.answer_document(
                BufferedInputFile(stl_bytes, filename=filename),
                caption=(caption + "\n✅ STL готов — загрузите в Bambu Studio.")[:1024],
            )
        else:
            payload = build_scad_source(part).encode("utf-8")
            fkind = "scad"
            await message.answer_document(
                BufferedInputFile(payload, filename=filename),
                caption=(
                    caption
                    + "\nℹ️ OpenSCAD не найден — отправлен .scad, экспортируйте STL вручную."
                )[:1024],
            )

        assumptions = specs.get("assumptions") if isinstance(specs.get("assumptions"), list) else []
        if assumptions:
            await message.answer("📐 Допущения:\n" + "\n".join(f"• {a}" for a in assumptions[:5]))

        part_name = str(part.get("name") or filename)
        await history.add_message(user_id, "user", user_request[:500])
        await history.add_message(
            user_id,
            "assistant",
            f"Отправлена одна деталь для печати: {part_name}.",
        )
        return DeliveryResult(
            summary=f"Отправлена одна деталь: {part_name}",
            files=[
                DeliveredFile(
                    filename=filename,
                    size_bytes=len(payload or b""),
                    kind=fkind,
                    meta={"template": part.get("template")},
                )
            ],
            success=True,
            meta={"template": str(part.get("template") or "")},
        )
    except llm.LLMError as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    except Exception as e:
        await indicator.error(f"Не удалось сделать деталь: {e}")
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)


async def _send_generated_file(
    message: Message,
    user_request: str,
    text_model: str,
    fmt: str,
    *,
    context: str = "",
    count: Optional[int] = None,
    print_profile: Optional[dict] = None,
    photo_measurements: Optional[str] = None,
    from_photo: bool = False,
) -> DeliveryResult:
    indicator = StatusIndicator(message)
    from bot.services.file_output import FORMAT_LABELS, produce_file

    n = count if count is not None else parse_file_count(user_request, 1)
    label = FORMAT_LABELS.get(fmt, fmt.upper())

    if fmt == "stl" and should_refuse_placeholder_stl(user_request, from_photo=from_photo):
        from bot.services.capabilities import agent_learn_hint
        from bot.services.meshy_route import should_meshy_from_text, meshy_available

        if should_meshy_from_text(user_request) or (
            meshy_available() and re.search(r"фигур|ангел|персонаж|чебурашк", user_request, re.I)
        ):
            from bot.services.bambu_hints import wants_articulated_figurine
            from bot.services.openscad import openscad_available

            if wants_articulated_figurine(user_request) and openscad_available():
                return await _reply_articulated_3mf(message, user_request, text_model)
            return await _reply_stl_from_text_meshy(message, user_request, text_model)

        if is_single_part_print_request(user_request):
            return await _send_single_print_part(message, user_request, text_model)

        if wants_print_project(user_request):
            return await _send_print_project(
                message, user_request, text_model, context=context or user_request
            )

        await message.answer(
            "Я не умею сделать точную STL-модель примитивами (прямоугольники).\n\n"
            "Вместо этого напишите:\n"
            "• «сделай проект на печать» — получите ZIP с OpenSCAD, планом и сборкой\n"
            "• или «сделай упрощённый STL» — если нужен только черновик"
            + agent_learn_hint("точные STL"),
            parse_mode=None,
        )
        return DeliveryResult(summary="Отказ от STL-примитивов", success=False)

    try:
        sent_files: list[DeliveredFile] = []
        if n > 1 or fmt == "stl":
            await indicator.show(
                "🟡", "Обрабатываю", f"Готовлю {n} файлов {label}…"
            )
            items = await produce_file_items(
                fmt,
                user_request,
                context or user_request,
                text_model,
                count=n,
                print_profile=print_profile,
                photo_measurements=photo_measurements,
                from_photo=from_photo,
            )
            await indicator.done()
            for idx, (data, filename, caption) in enumerate(items, start=1):
                cap = caption
                if len(items) > 1:
                    cap = f"{caption}\n📎 Файл {idx}/{len(items)}: {filename}"
                await message.answer_document(
                    BufferedInputFile(data, filename=filename),
                    caption=cap[:1024],
                )
                sent_files.append(
                    DeliveredFile(
                        filename=filename,
                        size_bytes=len(data),
                        kind=_file_kind(filename),
                    )
                )
            if len(items) > 1:
                await message.answer(
                    f"✅ Отправлено файлов: {len(items)} ({label})."
                )
            return DeliveryResult(
                summary=f"Отправлено файлов: {len(items)} ({label})",
                files=sent_files,
                success=True,
            )

        await indicator.show("🟡", "Обрабатываю", f"Готовлю файл {label}…")
        data, filename, caption = await produce_file(
            fmt, user_request, context or user_request, text_model
        )
        await indicator.done()
        await message.answer_document(
            BufferedInputFile(data, filename=filename),
            caption=caption,
        )
        return DeliveryResult(
            summary=f"Отправлен файл {label}",
            files=[
                DeliveredFile(
                    filename=filename,
                    size_bytes=len(data),
                    kind=_file_kind(filename),
                )
            ],
            success=True,
        )
    except llm.LLMError as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    except Exception as e:
        await indicator.error(f"Не удалось создать файл: {e}")
        return DeliveryResult(summary=str(e), success=False)


async def _send_seo_pdf(
    message: Message,
    user_request: str,
    context: str,
    text_model: str,
    *,
    card_method: str = "",
) -> None:
    indicator = StatusIndicator(message)
    await indicator.show("🟡", "Обрабатываю", "Готовлю SEO-текст в PDF…")
    try:
        seo_text = await llm.generate_seo_listing_text(
            user_request, context, text_model, card_method=card_method
        )
        from bot.services.seo_pdf import build_seo_pdf, parse_sections_from_markdown

        sections = parse_sections_from_markdown(seo_text)
        title = sections[0][0] if sections else "SEO для Авито"
        note = f"Карточка: {format_method_label(card_method)}" if card_method else ""
        pdf_bytes = build_seo_pdf(title, sections, method_note=note)
        await indicator.done()
        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename="avito-seo.pdf"),
            caption="📄 SEO-текст для Авито (PDF)",
        )
    except llm.LLMError as e:
        await indicator.error(str(e))
    except Exception as e:
        await indicator.error(f"Не удалось сделать PDF: {e}")


async def _complete_pending_3d_from_text(message: Message, user_text: str) -> bool:
    """Ответ с настройками принтера после запроса STL с фото."""
    user_id = message.from_user.id
    job = get_pending(user_id)
    if not job:
        return False

    saved = await history.get_print_profile(user_id)
    profile = merge_profiles(saved, parse_print_profile(user_text))
    still = missing_fields(profile)
    if still:
        await message.answer(
            format_questionnaire()
            + "\n\n⚠️ Не хватает: "
            + (", ".join(still))
        )
        return True

    pop_pending(user_id)
    await history.set_print_profile(user_id, profile)

    indicator = StatusIndicator(message)
    set_busy(user_id, "готовлю STL")
    try:
        await indicator.show("🟡", "Обрабатываю", "Загружаю фото и строю 3D…")
        from bot.services.vision import download_photo_bytes

        image_data = await download_photo_bytes(message.bot, job.file_id)
        await _reply_stl_from_photo(
            message,
            image_data,
            job.prompt,
            job.width,
            job.height,
            await history.get_model(user_id, DEFAULT_MODEL),
            telegram_file_id=job.file_id,
            profile=profile,
            prefetched_facts=job.facts,
            skip_profile_check=True,
        )
    except Exception as e:
        await indicator.error(f"Не удалось продолжить 3D: {e}")
    finally:
        clear_busy(user_id)
    return True


async def _reply_stl_from_photo(
    message: Message,
    image_data: bytes,
    prompt_text: str,
    width: int,
    height: int,
    text_model: str,
    *,
    telegram_file_id: str = "",
    profile: Optional[dict] = None,
    prefetched_facts: str = "",
    skip_profile_check: bool = False,
) -> None:
    from bot.config import MESHY_API_KEY, MESHY_TIMEOUT_SEC
    from bot.services.capabilities import agent_learn_hint, stl_quality_disclaimer
    from bot.services.file_output import parse_json_block, should_refuse_placeholder_stl
    from bot.services.vision import detect_mime

    user_id = message.from_user.id
    indicator = StatusIndicator(message)

    saved = await history.get_print_profile(user_id)
    prof = merge_profiles(saved, profile or parse_print_profile(prompt_text))

    facts = prefetched_facts or _local_card_facts(image_data, prompt_text, width, height)
    if not prefetched_facts:
        try:
            facts, _ = await asyncio.wait_for(
                llm.describe_image_facts(image_data, width, height),
                timeout=18,
            )
        except (asyncio.TimeoutError, llm.LLMError, Exception):
            pass

    from bot.services.print_profile import ensure_profile
    from bot.services.user_prefs import should_skip_questionnaire

    prof = ensure_profile(prof, prompt_text)
    skip_q = await should_skip_questionnaire(user_id)

    if (
        not skip_profile_check
        and missing_fields(prof)
        and not MESHY_API_KEY
        and not skip_q
    ):
        if telegram_file_id:
            set_pending(
                user_id,
                Pending3DJob(
                    file_id=telegram_file_id,
                    prompt=prompt_text,
                    count=parse_file_count(prompt_text, 1),
                    facts=facts,
                    width=width,
                    height=height,
                ),
            )
        await indicator.done()
        await message.answer(format_questionnaire())
        return

    await history.set_print_profile(user_id, prof)

    from bot.services.engineering_intake import engineering_drawing_requested

    if engineering_drawing_requested(prompt_text):
        await indicator.show("🟡", "Обрабатываю", "Читаю чертёж/эскиз как инженерный ввод, не отправляю его в Meshy…")
        try:
            measurements = await llm.measure_object_from_photo(
                image_data, width, height, prompt_text, prof
            )
        except (asyncio.TimeoutError, llm.LLMError, Exception) as e:
            measurements = f'{{"confidence":"low","assumptions":["Не удалось надёжно прочитать размеры: {str(e)[:120]}"]}}'
        context = (
            f"Источник: фото/скан чертежа или эскиза.\n"
            f"Vision/OCR факты:\n{facts}\n\n"
            f"Извлечённые инженерные размеры/допущения:\n{measurements}\n\n"
            "Требование: не делать художественный Meshy STL. Собрать параметрический инженерный проект "
            "по размерам с явными assumptions и допусками."
        )
        if wants_print_project(prompt_text) or re.search(r"проект|сборк|несколько|деталировк|3mf|zip", prompt_text, re.I):
            await _send_print_project(message, prompt_text, text_model, context=context)
        else:
            await _send_generated_file(
                message,
                prompt_text,
                text_model,
                "stl",
                context=context,
                print_profile=prof,
                photo_measurements=measurements,
                from_photo=True,
            )
        await history.add_message(user_id, "user", f"[Чертёж {width}x{height}] {prompt_text[:400]}")
        await history.add_message(user_id, "assistant", "Чертёж обработан через инженерный пайплайн, без Meshy image-to-3D.")
        return

    if not MESHY_API_KEY and should_refuse_placeholder_stl(prompt_text, from_photo=True):
        from bot.services.capabilities import agent_learn_hint

        await indicator.done()
        await message.answer(
            "Я этого не умею: сделать точную 3D/STL-модель из фото без image-to-3D или 3D-скана.\n\n"
            "Раньше я присылал упрощённые примитивы — это и выглядело как фигня. "
            "Теперь я не буду выдавать их за готовую модель.\n\n"
            "Чтобы получить файл, который можно реально загрузить в Bambu Studio, нужно подключить "
            "image-to-3D API (например Meshy/Tripo) или дать CAD-размеры/чертёж.\n\n"
            "Если нужен только грубый черновик — напишите: «сделай упрощённый STL по фото»."
            + agent_learn_hint("3D-модель из фото"),
            parse_mode=None,
        )
        await history.add_message(user_id, "user", f"[Фото STL] {prompt_text[:300]}")
        await history.add_message(user_id, "assistant", "Отказ от фейкового STL: нужен image-to-3D/CAD.")
        return

    if MESHY_API_KEY:
        from bot.services.meshy_3d import MeshyError, run_image_to_3d_delivery
        from bot.services.meshy_plan import plan_photo_to_3d

        plan = plan_photo_to_3d(prompt_text)
        await indicator.show(
            "🟡",
            "Обрабатываю",
            f"Meshy: {plan.status_hint()} (~{min(MESHY_TIMEOUT_SEC // 60, 5)} мин)…",
        )
        try:
            delivery = await _wait_with_progress(
                indicator,
                run_image_to_3d_delivery(
                    image_data,
                    detect_mime(image_data),
                    prompt_text,
                    plan=plan,
                ),
                timeout=MESHY_TIMEOUT_SEC + 60,
                eta_seconds=min(MESHY_TIMEOUT_SEC, 300),
                detail=(
                    "Meshy image-to-3D: генерирую модель, скачиваю native export, "
                    "масштабирую и чиню STL"
                ),
            )
        except asyncio.TimeoutError:
            await indicator.error(
                "Meshy/API не успел вернуть 3D-файл за отведённое время. Файл не получен; "
                "попробуйте ещё раз или фото меньшего размера."
            )
            return
        except MeshyError as e:
            await indicator.error(f"Meshy: {e}")
            return
        except Exception as e:
            await indicator.error(f"Meshy: {e}")
            return

        if delivery.primary:
            from bot.services.bambu_hints import meshy_export_filename

            await indicator.done()
            fname = meshy_export_filename(prompt_text, ext="stl")
            from bot.services.bambu_hints import support_decision_hint

            cap = stl_quality_disclaimer(
                from_photo=True, meshy=True, meshy_hint=plan.status_hint()
            )
            cap += (
                f"\n🖨 {format_profile(prof)}\n· {delivery.method}\n\n"
                "Загрузите STL в Bambu Studio → проверьте масштаб → печать."
                f"\n{support_decision_hint(prompt_text, file_kind='stl')}"
            )
            dr = await _send_meshy_3d_files(
                message,
                delivery,
                base_caption=cap,
                primary_fname=fname,
                user_id=user_id,
                history_user=f"[Фото 3D Meshy] {prompt_text[:300]}",
                history_assistant=f"3D Meshy ({delivery.method}).",
                include_preview_glb=plan.deliver_glb,
                user_text_for_support=prompt_text,
                support_profile=prof,
                require_object_level_colors=_meshy_requires_object_level_result(prompt_text),
            )
            if (
                not dr.success
                and dr.meta.get("quality_gate_failed")
                and not dr.files
                and not dr.meta.get("native_3mf")
            ):
                await _reply_printable_fallback_after_meshy_failure(
                    message,
                    prompt_text,
                    text_model,
                    reason=str(dr.meta.get("quality_gate_reason") or dr.summary),
                )
            return

        await indicator.done()
        await message.answer(
            "Meshy принял задачу, но не вернул файл модели. Попробуйте другое фото "
            "(крупнее, на однотонном фоне, как «Файл» без сжатия)."
        )
        return

    if should_refuse_placeholder_stl(prompt_text, from_photo=True):
        await indicator.done()
        await message.answer(
            "Meshy не настроен или не ответил. Точную модель с фото без него сделать нельзя."
            + agent_learn_hint("3D с фото"),
            parse_mode=None,
        )
        return

    await indicator.show("🟡", "Обрабатываю", "Замеряю предмет на фото…")
    try:
        measurements = await llm.measure_object_from_photo(
            image_data, width, height, prompt_text, prof
        )
    except llm.LLMError as e:
        await indicator.error(str(e))
        return

    count = parse_file_count(prompt_text, 1)
    meas = parse_json_block(measurements)
    if isinstance(meas, dict) and isinstance(meas.get("parts"), list):
        count = max(count, min(10, len(meas["parts"])))

    await _send_generated_file(
        message,
        prompt_text,
        text_model,
        "stl",
        context=facts,
        count=count,
        print_profile=prof,
        photo_measurements=measurements,
        from_photo=True,
    )
    await history.add_message(
        user_id, "user", f"[Фото {width}x{height}] {prompt_text[:400]}"
    )
    await history.add_message(
        user_id,
        "assistant",
        f"STL с фото ({count} дет.), принтер: {format_profile(prof)}.",
    )


async def _reply_portrait_figurine_from_photo(
    message: Message,
    image_data: bytes,
    prompt_text: str,
    width: int,
    height: int,
    text_model: str,
    *,
    telegram_file_id: str = "",
) -> None:
    from bot.config import MESHY_API_KEY, MESHY_TIMEOUT_SEC
    from bot.services.bambu_hints import bambu_slicer_hint, merge_bambu_profile
    from bot.services.capabilities import stl_quality_disclaimer
    from bot.services.meshy_3d import (
        MeshyError,
        meshy_text_to_image,
        run_image_to_3d_delivery,
    )
    from bot.services.meshy_plan import plan_photo_to_3d, plan_text_to_image
    from bot.services.portrait_figurine import (
        concept_prompt_from_facts,
        image_to_3d_prompt,
        parse_portrait_plan,
    )

    user_id = message.from_user.id
    indicator = StatusIndicator(message)

    if not MESHY_API_KEY:
        await indicator.done()
        await message.answer(
            "Для режима «портретная фигурка» нужен Meshy API: сначала concept image, затем 3D."
        )
        return

    prof = merge_bambu_profile(await history.get_print_profile(user_id), prompt_text)
    await history.set_print_profile(user_id, prof)
    portrait_plan = parse_portrait_plan(prompt_text)

    facts = _local_card_facts(image_data, prompt_text, width, height)
    try:
        facts, _ = await asyncio.wait_for(
            llm.describe_image_facts(image_data, width, height),
            timeout=18,
        )
    except (asyncio.TimeoutError, llm.LLMError, Exception):
        pass

    concept_prompt = concept_prompt_from_facts(facts, prompt_text)
    concept_plan = plan_text_to_image(f"pro hd {prompt_text}")
    await indicator.show(
        "🟡",
        "Шаг 1/2",
        f"Делаю 2D concept: {portrait_plan.style}, {portrait_plan.posture}…",
    )
    try:
        concept_bytes, concept_mime, concept_method = await _wait_with_progress(
            indicator,
            meshy_text_to_image(
                concept_prompt,
                user_request=f"portrait figurine concept {prompt_text}",
                plan=concept_plan,
            ),
            timeout=min(MESHY_TIMEOUT_SEC, 240),
            eta_seconds=min(MESHY_TIMEOUT_SEC, 180),
            detail="Meshy text-to-image: рисую свежий concept перед 3D",
        )
    except asyncio.TimeoutError:
        await indicator.error("Concept image не успел за отведённое время.")
        return
    except MeshyError as e:
        await indicator.error(f"Meshy concept: {e}")
        return
    except Exception as e:
        await indicator.error(f"Concept: {e}")
        return

    await message.answer_photo(
        BufferedInputFile(concept_bytes, filename="portrait-figurine-concept.png"),
        caption=(
            "🖼 2D concept для портретной фигурки.\n"
            f"Стиль: {portrait_plan.style}; поза: {portrait_plan.posture}.\n"
            f"Метод: {format_method_label(concept_method)}\n\n"
            "Дальше строю 3D по этому concept."
        )[:1024],
    )

    mesh_prompt = image_to_3d_prompt(prompt_text)
    photo_plan = plan_photo_to_3d(mesh_prompt + " textures colors")
    await indicator.show(
        "🟡",
        "Шаг 2/2",
        f"Строю 3D по concept: {photo_plan.status_hint()} (~{min(MESHY_TIMEOUT_SEC // 60, 5)} мин)…",
    )
    try:
        delivery = await _wait_with_progress(
            indicator,
            run_image_to_3d_delivery(
                concept_bytes,
                concept_mime,
                mesh_prompt,
                plan=photo_plan,
            ),
            timeout=MESHY_TIMEOUT_SEC + 120,
            eta_seconds=min(MESHY_TIMEOUT_SEC, 300),
            detail="Meshy image-to-3D: строю 3D по согласованному concept",
        )
    except asyncio.TimeoutError:
        await indicator.error("Meshy/API не успел вернуть 3D-файл за отведённое время.")
        return
    except MeshyError as e:
        await indicator.error(f"Meshy 3D: {e}")
        return
    except Exception as e:
        await indicator.error(f"Meshy 3D: {e}")
        return

    if not delivery.primary:
        await indicator.error("Meshy не вернул 3D-файл.")
        return

    await indicator.done()
    cap = stl_quality_disclaimer(
        from_photo=True,
        meshy=True,
        meshy_hint=f"portrait concept → {photo_plan.status_hint()}",
    )
    cap += (
        f"\n🧍 Режим: портретная фигурка ({portrait_plan.style}, {portrait_plan.posture})."
        f"\n🖨 {format_profile(prof)}"
        f"\n· Concept: {format_method_label(concept_method)}"
        f"\n· 3D: {delivery.method}"
        f"\n\n{bambu_slicer_hint(prof)}"
        "\n\nЧестно: это printU-like pipeline, но не их закрытый API. "
        "Проверьте сходство лица/цвета по concept preview и масштаб/вес в Bambu Studio."
    )
    dr = await _send_meshy_3d_files(
        message,
        delivery,
        base_caption=cap,
        primary_fname="portrait-figurine.stl",
        user_id=user_id,
        history_user=f"[Фото portrait figurine {width}x{height}] {prompt_text[:300]}",
        history_assistant=(
            f"Portrait figurine: concept ({concept_method}) → 3D ({delivery.method})."
        ),
        include_preview_glb=photo_plan.deliver_glb,
        user_text_for_support=prompt_text,
        support_profile=prof,
        require_object_level_colors=_meshy_requires_object_level_result(prompt_text),
    )
    if (
        not dr.success
        and dr.meta.get("quality_gate_failed")
        and not dr.files
        and not dr.meta.get("native_3mf")
    ):
        await _reply_printable_fallback_after_meshy_failure(
            message,
            prompt_text,
            text_model,
            reason=str(dr.meta.get("quality_gate_reason") or dr.summary),
        )


def _plastic_budget_hint(text: str) -> str:
    from bot.services.bambu_hints import plastic_weight_hint

    return plastic_weight_hint(text)


def _color_print_hint(text: str, profile: Optional[dict] = None) -> str:
    from bot.services.bambu_hints import color_ams_hint

    return color_ams_hint(text, profile or {})


def _needs_reference_before_meshy(text: str) -> bool:
    t = text or ""
    if re.search(r"без\s+референс|без\s+согласован|сразу\s+генер|делай\s+3d\s+сразу", t, re.I):
        return False
    # Aircraft have a strong canonical Boeing prompt (wings/tail/engines are
    # fixed) — no user reference image is needed; go straight to 3D.
    if re.search(r"самол[её]т|боинг|boeing|airliner|airplane|aircraft", t, re.I):
        return False
    has_print_intent = bool(re.search(r"3d|3д|stl|3mf|bambu|бамбу|печа|принтер|проект", t, re.I))
    has_subject = bool(
        re.search(
            r"ангел|angel|самол[её]т|боинг|airliner|собак|лабрадор|кот|чебурашк|"
            r"дракон|фигур|персонаж|робот|монстр|машин|ракета|дрон|животн",
            t,
            re.I,
        )
    )
    has_specs = bool(
        re.search(
            r"цвет|бел|ч[её]рн|красн|зел[её]н|син|ams|амс|длин|высот|размах|"
            r"\d+\s*(?:см|мм|гр|грамм)|филамент|материал|p2s",
            t,
            re.I,
        )
    )
    if has_print_intent and has_subject and has_specs:
        return False
    if re.search(r"как\s+на\s+(?:картинк|фото)|точн.{0,12}коп", t, re.I):
        return True
    return bool(
        re.search(
            r"максимальн.{0,12}детал|похож|точн.{0,12}коп|реалист|"
            r"сложн.{0,12}модел|как\s+на\s+картинк|как\s+на\s+фото",
            t,
            re.I,
        )
    )


def _is_print_instruction_request(text: str) -> bool:
    """A follow-up like 'дай инструкцию как запустить печать' is not concept approval."""
    t = (text or "").strip().lower()
    if not t or _looks_like_new_project_request(t):
        return False
    return bool(
        re.search(
            r"инструкц|как\s+(?:запуст|начать|отправ|печат|напечат)|"
            r"куда\s+наж|что\s+наж|как\s+и\s+куда|"
            r"запустит[ьи]\s+на\s+печать|нажать\s+на\s+печать|print\s+plate|slice\s+plate",
            t,
            re.I,
        )
    )


def _concept_approval_intent(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return ""
    if _is_print_instruction_request(t):
        return ""
    if _looks_like_new_project_request(t):
        return ""
    if re.search(r"отмен|стоп|не\s+надо|забудь|закрой|удали", t):
        return "cancel"
    if re.search(
        r"мало|больше|детал|подробн|улучш|лучше|передел|измени|добавь|"
        r"лишн|объект|не\s+по\s+настоящ|не\s+реалист|не\s+похож|"
        r"максимальн.{0,20}похож|выглядит|"
        r"не\s+супер|почти|не\s+хватает|слабовато",
        t,
    ):
        return "refine"
    if re.search(
        r"(?<![а-яёa-z])не\s+(?:норм|то|нрав)|(?<![а-яёa-z])нет(?![а-яёa-z])|"
        r"(?<![а-яёa-z])плохо(?![а-яёa-z])|(?<![а-яёa-z])друг(?:ой|ую|ая|ое)",
        t,
    ):
        return "reject"
    if re.search(
        r"^(?:норм|ок|да|устраивает|подходит)[\s,.!]*(?:делай|дела[ий]\s*(?:3d|3д)|можно)?|"
        r"нравит|запускай|запусти|можно\s+запуск|в\s+работу|"
        r"дела[ий]\s*(?:3d|3д|модель)|по\s+этой\s+картинк",
        t,
    ):
        return "approve"
    return ""


def _looks_like_3d_asset_command(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _looks_like_new_project_request(t):
        return False
    return bool(
        re.search(
            r"усиль|пилон|шасси|шосси|стойк|двигател|окн|панел|сохрани\s+meshy|"
            r"не\s+делай\s+procedural|не\s+процедур|почини|repair|bambu|бамбу|"
            r"центр|масштаб|support|поддержк|тест\s*2",
            t,
            re.I,
        )
        and re.search(r"stl|3mf|meshy|файл|модель|самол|boeing|боинг|шасси|шосси|пилон|двигател", t, re.I)
    )


def _engineering_intake_intent(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    tl = t.lower()
    if re.search(r"отмен|стоп|не\s+надо|забудь|неверн|не\s+верно|не\s+так", tl, re.I):
        return "cancel"
    if len(t) > 200 and _looks_like_new_project_request(t):
        return ""
    approve_short = re.search(
        r"(?:^|[\s,.;:!?«»\"'])"
        r"(?:да|верно|правильно|ок|согласен|согласна|запускай|подтверждаю|всё\s+верно|все\s+верно)"
        r"(?:[\s,.;:!?»\"']|$)",
        tl,
        re.I,
    )
    if approve_short:
        return "approve"
    if len(t) <= 80 and re.search(r"запускай|поехали|вперёд|делай|собирай", tl, re.I):
        return "approve"
    return ""


def _is_ambiguous_short_3d_command(text: str) -> bool:
    """A bare "make 3D" command is not enough to choose an object safely."""
    t = (text or "").strip().lower()
    if not t or len(t) > 70:
        return False
    has_3d = bool(re.search(r"(?:^|[\s,.;:!?])(?:3d|3д)(?:$|[\s,.;:!?])|stl|3mf|модел", t, re.I))
    has_action = bool(re.search(r"сделай|делай|создай|запусти|начинай|хочу|нужн", t, re.I))
    if not (has_3d and has_action):
        return False
    if re.search(r"по\s+этой\s+картинк|по\s+концепт|по\s+фото|референс", t, re.I):
        return False
    # If an actual subject or engineering target is present, let the normal router handle it.
    subject = re.search(
        r"самол[её]т|боинг|airliner|airplane|собак|кот|лабрадор|чебурашк|ангел|"
        r"фигур|персонаж|машин|ракета|дрон|ручк|держател|кронштейн|клип|"
        r"игрушк|маск|бюст|статуэтк|животн|робот|монстр|дракон",
        t,
        re.I,
    )
    return subject is None


def _looks_like_new_project_request(text: str) -> bool:
    """Do not treat a full new 3D/Bambu request as feedback for an old concept."""
    t = (text or "").strip().lower()
    if len(t) < 90:
        return False
    has_new_request = bool(
        re.search(
            r"мне\s+нуж|сделай|создай|пришли\s+проект|хочу\s+3d|нужен\s+3d|"
            r"3d\s+проект|3д\s+проект|3d\s+модел|3д\s+модел",
            t,
            re.I,
        )
    )
    has_3d_context = bool(
        re.search(r"bambu|бамбу|bambustudio|bambu\s*studio|3d|3д|stl|3mf|печати?", t, re.I)
    )
    has_spec = bool(
        re.search(r"длин|высот|размах|филамент|ams|амс|цвет|двигател|хвост|сопло", t, re.I)
    )
    return has_new_request and has_3d_context and has_spec


def _meshy_delivery_has_repair_warning(delivery) -> bool:
    method = str(getattr(delivery, "method", "") or "")
    return bool(re.search(r"repair WARNING|non-manifold", method, re.I))


def _needs_best_meshy_candidate(text: str) -> bool:
    return bool(
        re.search(
            r"максимальн.{0,16}детал|самый\s+лучш|шикарн|очень\s+красив|реалист|high[\s-]?detail|"
            r"boeing|боинг|airliner|самол[её]т",
            text or "",
            re.I,
        )
    )


async def _try_better_text_meshy_candidate(
    current_delivery,
    user_text: str,
    *,
    indicator: Optional[StatusIndicator] = None,
):
    """If image-to-3D is weak, try Meshy text-to-3D as a second candidate."""
    from bot.config import MESHY_TIMEOUT_SEC
    from bot.services.meshy_3d import (
        MeshyError,
        run_meshy_with_reference_level3,
        score_meshy_delivery,
    )
    from bot.services.meshy_plan import plan_text_to_3d
    from bot.services.meshy_route import meshy_prompt_from_text

    current_score = score_meshy_delivery(current_delivery, user_text)
    if not _needs_best_meshy_candidate(user_text) or int(current_score.get("score") or 0) >= 70:
        return current_delivery, current_score, None

    prompt = (
        meshy_prompt_from_text(user_text)
        + ", premium Meshy 6 quality, detailed geometry, accurate proportions, clean product-quality 3D asset"
    )[:600]
    plan = plan_text_to_3d(user_text + " максимальная детализация glb", prompt)
    try:
        candidate_task = run_meshy_with_reference_level3(
            prompt, user_request=user_text, plan=plan
        )
        if indicator:
            candidate = await _wait_with_progress(
                indicator,
                candidate_task,
                timeout=MESHY_TIMEOUT_SEC + 180,
                eta_seconds=min(MESHY_TIMEOUT_SEC + 120, 420),
                detail="Meshy best-of-2: пробую второй high-detail кандидат",
            )
        else:
            candidate = await asyncio.wait_for(candidate_task, timeout=MESHY_TIMEOUT_SEC + 180)
    except (asyncio.TimeoutError, MeshyError, Exception) as e:
        return current_delivery, current_score, {"error": f"{type(e).__name__}: {str(e)[:160]}"}

    candidate_score = score_meshy_delivery(candidate, user_text)
    if int(candidate_score.get("score") or 0) > int(current_score.get("score") or 0):
        return candidate, candidate_score, current_score
    return current_delivery, current_score, candidate_score


async def _retry_airliner_meshy_delivery(
    message: Message,
    user_text: str,
    text_model: str,
    *,
    fast: bool = False,
) -> DeliveryResult:
    """Second-chance Meshy for airliners: direct text-to-3D, extended timeout."""
    from bot.config import MESHY_TIMEOUT_SEC
    from bot.services.meshy_3d import MeshyError, MeshyNetworkError, run_text_to_3d_delivery
    from bot.services.meshy_plan import plan_airliner_text_to_3d
    from bot.services.meshy_route import meshy_prompt_from_text

    prompt = meshy_prompt_from_text(user_text)
    plan = plan_airliner_text_to_3d(user_text, prompt, fast=fast)
    indicator = StatusIndicator(message)
    timeout = max(MESHY_TIMEOUT_SEC + 300, 720)
    set_busy(message.from_user.id, "meshy 3d retry")
    try:
        delivery = await _wait_with_progress(
            indicator,
            run_text_to_3d_delivery(prompt, user_request=user_text, plan=plan),
            timeout=timeout,
            eta_seconds=min(timeout, 540),
            detail="Meshy retry: Boeing text-to-3D (без mood board)",
        )
    except (asyncio.TimeoutError, MeshyError, MeshyNetworkError, Exception):
        return DeliveryResult(summary="Airliner Meshy retry failed", success=False)
    finally:
        clear_busy(message.from_user.id)

    if not delivery.primary:
        return DeliveryResult(summary="Airliner Meshy retry: no primary file", success=False)

    # Re-enter normal Meshy STL delivery path with the recovered delivery.
    return await _deliver_meshy_text_stl(
        message, user_text, text_model, delivery, prompt, plan
    )


async def _deliver_meshy_text_stl(
    message: Message,
    user_text: str,
    text_model: str,
    delivery,
    prompt: str,
    plan,
) -> DeliveryResult:
    """Send primary Meshy STL from an already-completed delivery."""
    from bot.services.bambu_hints import (
        bambu_slicer_hint,
        merge_bambu_profile,
        meshy_export_filename,
        nozzle_material_warnings,
    )
    from bot.services.capabilities import stl_quality_disclaimer
    from bot.services.meshy_plan import wants_glb_output

    user_id = message.from_user.id
    prof = merge_bambu_profile(await history.get_print_profile(user_id), user_text)
    primary = delivery.primary
    is_anim = primary and primary.ext == "glb"
    fname = (
        meshy_export_filename(user_text, ext="glb").replace("-meshy.glb", "-animated.glb")
        if is_anim
        else meshy_export_filename(user_text, ext="stl")
    )
    from bot.services.bambu_hints import support_decision_hint

    if is_anim:
        cap = f"🎬 Анимированный персонаж (Meshy rig+anim).\n· {delivery.method}\n· {plan.status_hint()}"
    else:
        cap = stl_quality_disclaimer(
            from_photo=False,
            meshy=True,
            text_to_3d=True,
            meshy_hint=plan.status_hint(),
        )
    cap += f"\n🖨 {format_profile(prof)}\n· {delivery.method}\n· Промпт: {prompt[:120]}"
    cap += f"\n\n{bambu_slicer_hint(prof)}"
    if not is_anim and _meshy_delivery_has_repair_warning(delivery):
        cap += (
            "\n\n⚠️ Repair не смог гарантировать идеальную manifold-сетку — "
            "проверьте модель в Bambu перед печатью."
        )
    cap += f"\n{support_decision_hint(user_text, file_kind='stl')}"
    warn = nozzle_material_warnings(prof, user_text)
    if warn:
        cap += f"\n\n{warn}"
    await message.answer_document(
        BufferedInputFile(primary.data, filename=fname),
        caption=cap[:1024],
    )
    await history.add_message(user_id, "user", user_text[:500])
    await history.add_message(user_id, "assistant", f"Meshy STL ({delivery.method}).")
    return DeliveryResult(
        summary=f"Meshy STL ({delivery.method})",
        files=[DeliveredFile(filename=fname, size_bytes=len(primary.data), kind="stl")],
        success=True,
        meta={"meshy_method": delivery.method},
    )


async def _reply_printable_fallback_after_meshy_failure(
    message: Message,
    user_text: str,
    user_model: str,
    *,
    reason: str,
):
    """Meshy failed — notify user honestly. No generator substitution."""
    from bot.services.self_check import DeliveryResult
    from bot.services.task_plan import TaskKind, TaskPlan

    if "insufficient funds" in (reason or "").lower() or "402" in (reason or ""):
        dr = await _reply_meshy_out_of_credits(message, user_text)
        return TaskPlan(
            kind=TaskKind.MESHY_TEXT_3D,
            label="Meshy out of credits",
            model=user_model,
            model_reason=reason,
            capability="meshy",
            user_text=user_text,
            file_fmt="stl",
        ), dr

    await message.answer(
        "⚠️ **Meshy не удался** — файл **не отправлен**.\n"
        f"Причина: {(reason or 'unknown')[:400]}\n\n"
        "Fallback на другой генератор **отключён**: бот не подменит результат "
        "примитивами или процедурной геометрией. Повторите запрос или уточните параметры.",
        parse_mode="Markdown",
    )
    dr = DeliveryResult(
        summary=f"Meshy failed (no fallback): {reason}",
        success=False,
        meta={"meshy_failed": True, "no_fallback": True, "reason": reason},
    )
    return TaskPlan(
        kind=TaskKind.MESHY_TEXT_3D,
        label="Meshy failed (no fallback)",
        model=user_model,
        model_reason=reason,
        capability="meshy",
        user_text=user_text,
        file_fmt="stl",
    ), dr


async def _complete_pending_concept_from_text(message: Message, user_text: str, user_model: str):
    user_id = message.from_user.id
    intent = _concept_approval_intent(user_text)
    job = get_pending_concept(user_id)
    if not job:
        stored = await history.get_pending_concept(user_id)
        if stored:
            from bot.services.pending_3d import PendingConcept3DJob

            job = PendingConcept3DJob(
                image_bytes=stored["image_bytes"],
                mime=stored["mime"],
                prompt=stored["prompt"],
                original_text=stored["original_text"],
                subject=stored["subject"],
            )
    if job and _looks_like_new_project_request(user_text):
        pop_pending_concept(user_id)
        await history.clear_pending_concept(user_id)
        return None
    if not job:
        if intent in ("approve", "refine", "reject", "cancel"):
            await message.answer(
                "Не вижу активного концепта для запуска 3D. "
                "Скорее всего бот был перезапущен или старый концепт очищен. "
                "Отправьте запрос заново — я сначала покажу свежий концепт, затем по подтверждению запущу 3D.",
                parse_mode=None,
            )
            await history.add_message(user_id, "user", user_text[:500])
            await history.add_message(user_id, "assistant", "Нет активного pending concept для подтверждения.")
            return "handled"
        return None

    if intent == "refine":
        from bot.config import MESHY_TIMEOUT_SEC
        from bot.services.image_output import format_method_label
        from bot.services.meshy_3d import MeshyError, meshy_text_to_image
        from bot.services.meshy_plan import plan_text_to_image
        from bot.services.pending_3d import PendingConcept3DJob, set_pending_concept
        from uuid import uuid4

        variation_id = uuid4().hex[:8]
        refined_prompt = (
            f"{job.prompt}\n\n"
            "Improve this concept before 3D generation: add more visible print-friendly detail, "
            "clearer aircraft panels, engines, doors, landing gear, wing shape, and a more recognizable Boeing airliner silhouette. "
            f"User feedback: {user_text}\n"
            f"Fresh refined concept variation id: {variation_id}. Do not reuse the previous image."
        )[:1200]
        indicator = StatusIndicator(message)
        set_busy(message.from_user.id, "refine concept")
        try:
            await indicator.show("🟡", "Рисую", "Переделываю концепт: больше детализации, 3D пока не запускаю…")
            image_plan = plan_text_to_image(refined_prompt)
            data, mime, method = await _wait_with_progress(
                indicator,
                meshy_text_to_image(refined_prompt, user_request=job.original_text, plan=image_plan),
                timeout=min(MESHY_TIMEOUT_SEC, 180),
                eta_seconds=min(MESHY_TIMEOUT_SEC, 160),
                detail="Meshy text-to-image: переделываю concept, не запускаю 3D",
            )
        except asyncio.TimeoutError:
            await indicator.error("Meshy не успел переделать концепт.")
            return "handled"
        except MeshyError as e:
            await indicator.error(f"Meshy: {e}")
            return "handled"
        except Exception as e:
            await indicator.error(str(e))
            return "handled"
        finally:
            clear_busy(message.from_user.id)

        ext = "png" if "png" in mime else "jpg"
        await indicator.done()
        import hashlib

        image_id = hashlib.sha1(data).hexdigest()[:8]
        await message.answer_photo(
            BufferedInputFile(data, filename=f"boeing-concept-refined-{image_id}.{ext}"),
            caption=(
                f"🖼 {format_method_label(method)}\n\n"
                "Я НЕ запускаю 3D, потому что это была правка концепта, а не подтверждение. "
                "Если теперь устраивает — напишите «норм, делай 3D по этой картинке»."
            )[:1024],
        )
        set_pending_concept(
            user_id,
            PendingConcept3DJob(
                image_bytes=data,
                mime=mime,
                prompt=refined_prompt,
                original_text=job.original_text,
                subject=job.subject,
            ),
        )
        await history.save_pending_concept(
            user_id,
            image_bytes=data,
            mime=mime,
            prompt=refined_prompt,
            original_text=job.original_text,
            subject=job.subject,
        )
        return "handled"
    if intent == "reject":
        await message.answer(
            "Ок, 3D не запускаю. Задачу не закрываю: напишите, что именно изменить "
            "(ракурс, лишние объекты, окна, крылья, хвост, реалистичность), и я переделаю концепт.",
            parse_mode=None,
        )
        return "handled"
    if intent == "cancel":
        pop_pending_concept(user_id)
        await history.clear_pending_concept(user_id)
        await message.answer(
            "Ок, остановил этот концепт и не запускаю 3D.",
            parse_mode=None,
        )
        return "handled"
    if intent != "approve":
        return None

    from bot.config import MESHY_TIMEOUT_SEC
    from bot.services.bambu_hints import (
        bambu_slicer_hint,
        extract_part_color_requests,
        merge_bambu_profile,
        meshy_export_filename,
        support_decision_hint,
    )
    from bot.services.capabilities import stl_quality_disclaimer
    from bot.services.meshy_3d import MeshyError, run_image_to_3d_delivery
    from bot.services.meshy_plan import plan_photo_to_3d
    from bot.services.task_plan import TaskKind, TaskPlan

    indicator = StatusIndicator(message)
    original = job.original_text
    prof = merge_bambu_profile(await history.get_print_profile(user_id), original)
    plan_3d = plan_photo_to_3d(original)

    async def _fallback_and_clear(reason: str):
        result = await _reply_printable_fallback_after_meshy_failure(
            message,
            original,
            user_model,
            reason=reason,
        )
        fallback_plan, fallback_delivery = result
        if fallback_delivery.success:
            pop_pending_concept(user_id)
            await history.clear_pending_concept(user_id)
        return result

    set_busy(user_id, "concept to 3d")
    try:
        await indicator.show(
            "🟡",
            "Обрабатываю",
            "Концепт подтверждён — делаю Meshy image-to-3D и STL для Bambu…",
        )
        delivery = await _wait_with_progress(
            indicator,
            run_image_to_3d_delivery(job.image_bytes, job.mime, original, plan=plan_3d),
            timeout=MESHY_TIMEOUT_SEC + 120,
            eta_seconds=min(MESHY_TIMEOUT_SEC, 300),
            detail="Meshy image-to-3D: делаю модель по утверждённому concept",
        )
    except asyncio.TimeoutError:
        await indicator.show(
            "🟡",
            "Переключаюсь",
            "Meshy/API не вернул файл вовремя — fallback допустим только потому, что primary-файла нет…",
        )
        return await _fallback_and_clear("Meshy image-to-3D timeout after approved concept.")
    except MeshyError as e:
        await indicator.show(
            "🟡",
            "Переключаюсь",
            f"Meshy вернул ошибку до получения файла ({e}) — пробую запасной путь…",
        )
        return await _fallback_and_clear(f"Meshy image-to-3D failed after approved concept: {e}")
    except Exception as e:
        await indicator.show(
            "🟡",
            "Переключаюсь",
            f"Meshy сорвался до получения файла ({e}) — пробую запасной путь…",
        )
        return await _fallback_and_clear(f"Meshy image-to-3D crashed after approved concept: {e}")
    finally:
        clear_busy(user_id)

    if not delivery.primary:
        await indicator.show(
            "🟡",
            "Переключаюсь",
            "Meshy не вернул primary-файл — только в этом случае разрешён fallback…",
        )
        return await _fallback_and_clear("Meshy image-to-3D returned no primary model file.")

    if _needs_best_meshy_candidate(original):
        await indicator.show(
            "🟡",
            "Сравниваю",
            "Проверяю Meshy-кандидат и при необходимости пробую второй high-detail text-to-3D вариант…",
        )
        delivery, chosen_score, other_score = await _try_better_text_meshy_candidate(
            delivery, original, indicator=indicator
        )
        if other_score is not None:
            score_txt = f"chosen={chosen_score.get('score')}, other={other_score.get('score')}"
            delivery.method = f"{delivery.method} · best-of-2 Meshy ({score_txt})"

    task_plan = TaskPlan(
        kind=TaskKind.MESHY_PHOTO_3D,
        label="3D по подтверждённому концепту",
        model=user_model,
        model_reason="Meshy image-to-3D по утверждённой картинке.",
        capability="meshy",
        user_text=original,
        file_fmt="stl",
    )

    await indicator.done()
    cap = stl_quality_disclaimer(from_photo=True, meshy=True, meshy_hint=plan_3d.status_hint())
    cap += (
        f"\n🖨 {format_profile(prof)}\n· {delivery.method}\n\n"
        "Это Meshy-derived файл по утверждённой концепт-картинке. Бот не заменяет красивую Meshy-геометрию процедурным fallback."
        f"\n\n{bambu_slicer_hint(prof)}"
        f"\n{support_decision_hint(original, file_kind='stl')}"
    )
    if _meshy_delivery_has_repair_warning(delivery):
        cap += (
            "\n\n⚠️ Repair не смог гарантировать идеальную manifold-сетку, поэтому Bambu может показать предупреждение. "
            "Но это всё равно отредактированный Meshy-файл из исходной красивой геометрии, не процедурная подмена."
        )
    dr = await _send_meshy_3d_files(
        message,
        delivery,
        base_caption=cap,
        primary_fname=meshy_export_filename(original, ext="stl"),
        user_id=user_id,
        history_user=f"[Concept approved -> 3D] {original[:300]}",
        history_assistant=f"3D from approved concept ({delivery.method}).",
        include_preview_glb=plan_3d.deliver_glb,
        user_text_for_support=original,
        support_profile=prof,
        require_object_level_colors=_meshy_requires_object_level_result(original),
    )
    from bot.services.airplane_3mf import airplane_requested

    if (
        not dr.success
        and dr.meta.get("quality_gate_failed")
        and not dr.files
        and not dr.meta.get("native_3mf")
    ):
        await message.answer(
            "🛑 Meshy не смог собрать AMS multi-object проект и не осталось пригодных Meshy-файлов.",
            parse_mode=None,
        )
        return await _fallback_and_clear(str(dr.meta.get("quality_gate_reason") or dr.summary))

    if dr.success and extract_part_color_requests(original) and not dr.meta.get("object_level_colors"):
        if airplane_requested(original) or dr.meta.get("native_3mf"):
            await message.answer(
                "ℹ️ Meshy дал детальную геометрию одним mesh: автоматические AMS-цвета по деталям недоступны. "
                "Процедурный fallback не отправляю — используйте Meshy-native / repaired STL выше. "
                "В Bambu можно вручную назначить цвет всей модели или разрезать в Paint.",
                parse_mode=None,
            )
    if dr.success:
        pop_pending_concept(user_id)
        await history.clear_pending_concept(user_id)
    return task_plan, dr


async def _complete_pending_engineering_from_text(message: Message, user_text: str, user_model: str):
    job = get_pending_engineering(message.from_user.id)
    if not job:
        return None
    if _looks_like_new_project_request(user_text):
        pop_pending_engineering(message.from_user.id)
        return None
    intent = _engineering_intake_intent(user_text)
    if intent == "cancel":
        from bot.services.engineering_intake import (
            looks_like_engineering_correction,
            merge_engineering_correction,
            render_engineering_intake,
        )

        if looks_like_engineering_correction(user_text):
            updated = merge_engineering_correction(job.prompt, user_text)
            set_pending_engineering(message.from_user.id, PendingEngineeringIntake(prompt=updated))
            profile = merge_profiles(await history.get_print_profile(message.from_user.id), parse_print_profile(updated))
            await message.answer(render_engineering_intake(updated, profile), parse_mode=None)
            await history.add_message(message.from_user.id, "user", user_text[:500])
            await history.add_message(message.from_user.id, "assistant", "Обновил инженерное понимание и снова жду подтверждение.")
            return "handled"
        pop_pending_engineering(message.from_user.id)
        await message.answer("Ок, остановил инженерный запуск. Напишите уточнённый запрос заново.", parse_mode=None)
        return "handled"
    if intent != "approve":
        from bot.services.engineering_intake import (
            looks_like_engineering_correction,
            merge_engineering_correction,
            render_engineering_intake,
        )

        if looks_like_engineering_correction(user_text):
            updated = merge_engineering_correction(job.prompt, user_text)
            set_pending_engineering(message.from_user.id, PendingEngineeringIntake(prompt=updated))
            profile = merge_profiles(await history.get_print_profile(message.from_user.id), parse_print_profile(updated))
            await message.answer(render_engineering_intake(updated, profile), parse_mode=None)
            await history.add_message(message.from_user.id, "user", user_text[:500])
            await history.add_message(message.from_user.id, "assistant", "Обновил инженерное понимание и снова жду подтверждение.")
            return "handled"
        await message.answer(
            "Я жду подтверждение инженерных параметров. Ответьте «да, верно, запускай» "
            "или уточните, что изменить.",
            parse_mode=None,
        )
        return "handled"

    original = job.prompt
    pop_pending_engineering(message.from_user.id)
    await history.add_message(message.from_user.id, "user", user_text[:500])
    from bot.services.self_check import report_self_check
    from bot.services.task_plan import TaskKind, TaskPlan, build_task_plan
    from bot.services.airplane_3mf import airplane_requested, airplane_wants_realistic_mesh
    from bot.services.task_dispatch import execute_text_plan

    # Realistic airplane after intake confirmation → NACA CAD (hard-surface), not Meshy clay.
    if airplane_wants_realistic_mesh(original) or airplane_requested(original):
        plan = build_task_plan(original, user_model)
        delivery = await execute_text_plan(message, plan, phase="3d")
        await report_self_check(message, plan, delivery)
        return "handled"

    launch_text = (
        f"{original}\n\n"
        "Инженерные параметры подтверждены пользователем. "
        "Запусти именно print-project ZIP/assembly kit, не повторяй intake-вопрос."
    )
    plan = TaskPlan(
        kind=TaskKind.PRINT_PROJECT,
        label="Инженерный print-project после подтверждения",
        model=user_model,
        model_reason="Пользователь подтвердил pending engineering intake; запускаю сборку проекта.",
        capability="engineering_json",
        user_text=launch_text,
        file_fmt="zip",
        extra={"engineering_approved": True},
    )
    delivery = await _send_print_project(message, launch_text, user_model, context=original)
    await report_self_check(message, plan, delivery)
    return "handled"


async def _reply_articulated_3mf(
    message: Message,
    user_text: str,
    text_model: str,
) -> DeliveryResult:
    from bot.services.articulated_3mf import (
        assembly_hint,
        build_articulated_figurine_3mf,
        openscad_articulated_kind,
        requested_subject_label,
    )
    from bot.services.bambu_hints import (
        bambu_print_steps,
        articulated_3mf_filename,
        bambu_slicer_hint,
        merge_bambu_profile,
        nozzle_material_warnings,
    )
    from bot.services.openscad import openscad_available

    user_id = message.from_user.id
    indicator = StatusIndicator(message)

    if not openscad_available():
        await message.answer(
            "Для подвижной фигурки нужен OpenSCAD на сервере бота — он не найден. "
            "Напишите «статичная фигурка без шарниров» — сделаю через Meshy."
        )
        return DeliveryResult(summary="OpenSCAD missing", success=False)

    prof = merge_bambu_profile(await history.get_print_profile(user_id), user_text)
    set_busy(user_id, "articulated 3mf")
    try:
        await indicator.show("🟡", "Обрабатываю", "Собираю 3MF с шарнирами (OpenSCAD)…")
        data, fname, parts, parts_desc = await build_articulated_figurine_3mf(
            user_text, profile=prof
        )
    except Exception as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)

    fname = articulated_3mf_filename(user_text)
    art_kind = openscad_articulated_kind(user_text)

    from bot.services.generation_router import route_3d_request
    from bot.services.quality_gate import format_gate_failure, run_quality_gate
    from bot.services.self_check import DeliveredFile, DeliveryResult
    from bot.services.task_plan import TaskKind, TaskPlan

    plan = route_3d_request(user_text, text_model) or TaskPlan(
        kind=TaskKind.ARTICULATED_3MF,
        label="Articulated 3MF",
        model=text_model,
        model_reason="",
        capability="engineering_json",
        user_text=user_text,
        file_fmt="3mf",
        extra={"object_class": "organic", "procedural": True},
    )
    delivery = DeliveryResult(
        summary=f"Articulated 3MF ({len(parts)} parts)",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={
            "parts": parts,
            "articulated": True,
            "procedural": art_kind not in ("angel", "quadruped"),
            "kind": art_kind,
            "subject": requested_subject_label(user_text),
        },
        success=True,
    )
    gate = run_quality_gate(plan, delivery)
    if not gate.ok:
        await indicator.done()
        await message.answer(format_gate_failure(gate)[:1024], parse_mode="Markdown")
        return DeliveryResult(
            summary="Articulated failed quality gate",
            success=False,
            meta={"gate_failed": True, "issues": gate.issues},
        )

    await indicator.done()
    cap = (
        "🧩 **Один 3MF** — откройте в Bambu Studio и печатайте.\n"
        f"Деталей: {len(parts)} ({parts_desc}).\n"
        "ℹ️ Сообщение «не от Bambu Lab» — нормально: назначьте белый/чёрный/красный PLA "
        "по объектам в AMS.\n"
        f"🖨 {format_profile(prof)}\n"
        f"{bambu_slicer_hint(prof)}"
    )
    if art_kind not in ("angel", "quadruped"):
        cap += (
            "\n\n🧪 Это **процедурный v0**: бот сам сгенерировал OpenSCAD-код "
            "и собрал 3MF под ваш предмет, без подмены собакой/другим шаблоном."
        )
    warn = nozzle_material_warnings(prof, user_text)
    if warn:
        cap += f"\n\n{warn}"
    await message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=cap[:1024],
        parse_mode="Markdown",
    )
    hint = _plastic_budget_hint(user_text)
    if hint:
        await message.answer(hint)
    color_hint = _color_print_hint(user_text, prof)
    if color_hint:
        await message.answer(color_hint)
    await message.answer(assembly_hint(user_text), parse_mode="Markdown")
    await message.answer(bambu_print_steps(user_text, file_kind="3mf"), parse_mode=None)
    await history.set_print_profile(user_id, prof)
    await history.add_message(user_id, "user", user_text[:500])
    await history.add_message(user_id, "assistant", f"Articulated 3MF ({fname}, {len(parts)} parts).")
    return DeliveryResult(
        summary=f"Articulated 3MF ({len(parts)} parts)",
        files=[
            DeliveredFile(
                filename=fname,
                size_bytes=len(data),
                kind="3mf",
            )
        ],
        meta={
            "parts": parts,
            "articulated": True,
            "procedural": art_kind not in ("angel", "quadruped"),
            "kind": art_kind,
            "subject": requested_subject_label(user_text),
        },
        success=True,
    )


async def _reply_airplane_3mf(
    message: Message,
    user_text: str,
    text_model: str,
    *,
    plan=None,
    history_user_text: Optional[str] = None,
    high_detail: bool = False,
    print_tuned: bool = False,
) -> DeliveryResult:
    from bot.services.airplane_3mf import assembly_hint, build_airliner_hd_3mf, build_airliner_print_tuned_3mf
    from bot.services.bambu_hints import (
        bambu_print_steps,
        bambu_slicer_hint,
        merge_bambu_profile,
        nozzle_material_warnings,
        support_decision_hint,
    )
    from bot.services.quality_gate import run_quality_gate
    from bot.services.self_check import DeliveredFile, DeliveryResult
    from bot.services.task_plan import TaskKind, TaskPlan

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    prof = merge_bambu_profile(await history.get_print_profile(user_id), user_text)

    if plan is None:
        from bot.services.generation_router import route_3d_request

        plan = route_3d_request(user_text, text_model) or TaskPlan(
            kind=TaskKind.AIRPLANE_3MF,
            label="Boeing 747 NACA",
            model=text_model,
            model_reason="",
            capability="engineering_json",
            user_text=user_text,
            file_fmt="3mf",
            extra={"high_detail": True, "generator": "naca_hd"},
        )

    set_busy(user_id, "airplane 3mf")
    try:
        await indicator.show(
            "🟡",
            "Обрабатываю",
            "Hard-surface → NACA CAD: фюзеляж, профиль крыла, двигатели, хвост. "
            "Проверка качества перед отправкой…",
        )
        if print_tuned:
            data, fname, parts, parts_desc, dims = await build_airliner_print_tuned_3mf(
                user_text, profile=prof
            )
        else:
            data, fname, parts, parts_desc, dims = await build_airliner_hd_3mf(user_text, profile=prof)
    except Exception as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)

    delivery = DeliveryResult(
        summary=f"Airplane NACA HD 3MF ({len(parts)} parts)",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="3mf")],
        meta={
            "parts": parts,
            "procedural": True,
            "assembled": True,
            "high_detail": high_detail or True,
            "print_tuned": print_tuned,
            "print_ready_v3": print_tuned,
            "generator": "naca_hd",
            "object_class": (plan.extra or {}).get("object_class", "hard_surface"),
            "dimensions": dims,
            "object_level_colors": True,
            "kind": "airplane",
            "subject": "boeing_airliner",
        },
        success=True,
    )

    gate = run_quality_gate(plan, delivery)
    if not gate.ok:
        await indicator.done()
        from bot.services.quality_gate import format_gate_failure

        await message.answer(format_gate_failure(gate)[:1024], parse_mode="Markdown")
        return DeliveryResult(
            summary="Airplane failed quality gate",
            success=False,
            meta={"gate_failed": True, "issues": gate.issues},
        )

    await indicator.done()
    cap = (
        "✈️ **Boeing 747 — NACA CAD (3MF)**\n"
        "Hard-surface: инженерная геометрия (NACA-профиль, фюзеляж, 4 двигателя, хвост). "
        "Проверка пройдена — файл готов к Bambu Studio.\n"
        f"Деталей: {len(parts)}. {parts_desc}\n"
        f"🖨 {format_profile(prof)}\n"
        f"{bambu_slicer_hint(prof)}\n"
        f"✅ {gate.message}"
    )
    cap += f"\n{support_decision_hint(user_text, file_kind='3mf')}"
    warn = nozzle_material_warnings(prof, user_text)
    if warn:
        cap += f"\n\n{warn}"

    await message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=cap[:1024],
        parse_mode="Markdown",
    )
    hint = _plastic_budget_hint(user_text)
    if hint:
        await message.answer(hint)
    color_hint = _color_print_hint(user_text, prof)
    if color_hint:
        await message.answer(color_hint)
    await message.answer(assembly_hint(), parse_mode=None)
    await message.answer(bambu_print_steps(user_text, file_kind="3mf"), parse_mode=None)

    await history.set_print_profile(user_id, prof)
    await history.add_message(user_id, "user", (history_user_text or user_text)[:500])
    await history.add_message(user_id, "assistant", f"Airplane NACA 3MF ({fname}, {len(parts)} parts).")
    return delivery


async def _reply_unsupported_articulated(message: Message, plan) -> DeliveryResult:
    subject = str((plan.extra or {}).get("subject") or "фигурка")
    text = (
        f"🛑 Не буду подменять «{subject}» чужим шаблоном.\n\n"
        "Готовый шарнирный 3MF сейчас есть только для точных локальных шаблонов: "
        "ангел (крылья), собака/лабрадор/кот (лапы/голова/хвост).\n\n"
        f"Для «{subject}» я могу сделать **статичную** 3D-модель через Meshy "
        "(STL/GLB), но не буду обещать подвижные шарниры без шаблона. "
        "Напишите: «сделай статичную модель через Meshy» — и я соберу файл."
    )
    await message.answer(text, parse_mode="Markdown")
    return DeliveryResult(
        summary=f"Нет поддержанного шарнирного шаблона для: {subject}",
        success=True,
        meta={"unsupported_articulated": True, "subject": subject},
    )


async def _complete_3d_asset_command_from_text(message: Message, user_text: str, user_model: str):
    if not _looks_like_3d_asset_command(user_text):
        return None
    from bot.services.mesh_cache import load_mesh_asset, save_mesh_asset

    user_id = message.from_user.id
    cached = load_mesh_asset(user_id, "boeing_airliner_last_meshy") or load_mesh_asset(
        user_id, "last_3d_upload"
    )
    if not cached:
        text = (
            "Понял команду как работу с 3D-файлом, но не вижу сохранённого STL/3MF в кэше. "
            "Пришлите файл ещё раз как документ, затем напишите, что сделать: `почини для Bambu`, "
            "`усиль шасси/пилоны`, `добавь окна/панели`."
        )
        await message.answer(text, parse_mode="Markdown")
        await history.add_message(user_id, "user", user_text[:500])
        await history.add_message(user_id, "assistant", "3D asset command received, but no cached asset.")
        return DeliveryResult(
            summary="3D asset command without cached asset",
            text_reply=text,
            success=True,
            meta={"asset_command": True, "cache_hit": False},
        )

    t = user_text.lower()
    repair_only = bool(
        re.search(r"почини|repair|центр|масштаб|bambu|бамбу|на\s+стол|non.?manifold", t, re.I)
    ) and not bool(re.search(r"усиль|добавь|окн|панел|пилон|шасси|сохрани\s+meshy", t, re.I))

    if repair_only and cached.filename.lower().endswith(".stl"):
        await message.answer("Понял: команда относится к последнему загруженному STL. Делаю Bambu repair/центрирование.", parse_mode=None)
        try:
            from bot.services.stl_postprocess import prepare_meshy_stl_for_bambu

            prepared = await asyncio.to_thread(
                prepare_meshy_stl_for_bambu,
                cached.data,
                user_text=user_text,
            )
            out_name = cached.filename.rsplit(".", 1)[0] + "-bambu-repaired.stl"
            save_mesh_asset(
                user_id,
                "last_3d_upload_repaired",
                data=prepared.data,
                filename=out_name,
                meta={"source": "text_command_repair", "note": prepared.note},
            )
            if re.search(r"boeing|боинг|airliner|самол", cached.filename + " " + user_text, re.I):
                save_mesh_asset(
                    user_id,
                    "boeing_airliner_last_meshy",
                    data=prepared.data,
                    filename=out_name,
                    meta={"source": "text_command_repair", "note": prepared.note},
                )
            await message.answer_document(
                BufferedInputFile(prepared.data, filename=out_name),
                caption=(
                    "Готово: repair/центрирование для Bambu.\n"
                    f"Размеры ~{prepared.width_mm:.0f}×{prepared.depth_mm:.0f}×{prepared.height_mm:.0f} мм.\n"
                    f"{prepared.note}"
                )[:1024],
            )
            return DeliveryResult(
                summary="3D asset repaired from text command",
                files=[DeliveredFile(filename=out_name, size_bytes=len(prepared.data), kind="stl")],
                success=True,
                meta={"asset_command": True, "repair": True},
            )
        except Exception as e:
            await message.answer(f"Repair не прошёл: {type(e).__name__}: {str(e)[:160]}", parse_mode=None)
            return DeliveryResult(summary=str(e), success=False, meta={"asset_command": True})

    if re.search(r"усиль|добавь|окн|панел|пилон|шасси|сохрани\s+meshy|не\s+делай\s+procedural", t, re.I):
        text = (
            "Понял: это команда к последнему загруженному 3D-файлу, а не к старому концепту.\n\n"
            "Честно: локально я могу чинить/масштабировать STL, но не умею качественно редактировать Meshy-сетку так, "
            "чтобы реально усилить шасси, добавить окна/панели и сохранить ту же органическую форму без CAD-подмены. "
            "Для этого нужен новый Meshy-проход/концепт с этими требованиями или ручной mesh/CAD-редактор.\n\n"
            "Правильный следующий шаг: запустить свежий Meshy concept с промптом: "
            "«Boeing airliner, preserve the uploaded Meshy shape, stronger landing gear and engine pylons, "
            "subtle raised windows and panel lines, FDM printable, no procedural CAD look». "
            "Если хотите, напишите «да, новый Meshy-концепт»."
        )
        await message.answer(text, parse_mode=None)
        await history.add_message(user_id, "user", user_text[:500])
        await history.add_message(user_id, "assistant", "3D asset command recognized; Meshy regeneration recommended.")
        return DeliveryResult(
            summary="3D asset geometry edit requires Meshy regeneration/manual edit",
            text_reply=text,
            success=True,
            meta={"asset_command": True, "requires_regeneration": True},
        )

    return None


async def _reply_mechanical_project(message: Message, plan) -> DeliveryResult:
    from bot.services.engineering_intake import (
        printer_spec_from_text,
        render_engineering_intake,
        requested_dimensions_mm,
    )
    from bot.services.print_profile import ensure_profile

    user_id = message.from_user.id
    prof = ensure_profile(await history.get_print_profile(user_id), plan.user_text)
    spec = printer_spec_from_text(plan.user_text, prof)
    dims = requested_dimensions_mm(plan.user_text)
    subject = "Boeing/самолёт" if re.search(r"самол|боинг|airplane|boeing", plan.user_text, re.I) else "механическая модель"
    lines = [
        "Это механический проект, не обычная красивая 3D-модель.",
        f"Объект: {subject}.",
        "Для подвижности нужен 3MF/набор деталей: корпус, подвижный узел, оси/pins, посадочные отверстия, зазоры.",
    ]
    if spec:
        lines.append(f"Принтер: {spec.label}, стол {spec.bed_mm[0]}x{spec.bed_mm[1]}x{spec.bed_mm[2]} мм.")
    if dims:
        lines.append("Размеры: " + ", ".join(f"{k.replace('_mm', '')}={v:.0f} мм" for k, v in dims.items()))
    lines.extend(
        [
            "Уточните механику одним сообщением:",
            "1. Узел должен просто вращаться на оси или складываться/убираться?",
            "2. Печатать print-in-place или отдельными деталями со сборкой?",
            "3. Материал и сопло: PLA/PETG/ABS/nylon/resin, 0.2/0.4/0.6 мм?",
            "4. Нужна декоративная Meshy-геометрия сверху или инженерная упрощённая форма важнее?",
            "",
            render_engineering_intake(plan.user_text, prof),
        ]
    )
    text = "\n".join(lines)
    await message.answer(text[:4000], parse_mode=None)
    await history.add_message(user_id, "user", plan.user_text[:500])
    await history.add_message(user_id, "assistant", "Механический проект требует уточнения параметров.")
    return DeliveryResult(
        summary="Механический проект требует уточнения параметров",
        text_reply=text,
        meta={"mechanical_project": True, "awaiting_mechanical_specs": True},
        success=True,
    )


async def _reply_meshy_image(message: Message, user_text: str, plan=None) -> DeliveryResult:
    from uuid import uuid4

    from bot.config import MESHY_TIMEOUT_SEC
    from bot.services.image_output import format_method_label
    from bot.services.meshy_3d import MeshyError, meshy_text_to_image
    from bot.services.meshy_plan import plan_text_to_image
    from bot.services.airplane_3mf import airplane_requested
    from bot.services.pending_3d import PendingConcept3DJob, set_pending_concept

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    image_plan = plan_text_to_image(user_text)
    original_text = str((getattr(plan, "extra", {}) or {}).get("original_text") or user_text)
    concept_first = bool((getattr(plan, "extra", {}) or {}).get("concept_first"))
    image_prompt = user_text
    if concept_first:
        image_prompt = (
            f"{user_text}\n\n"
            f"Fresh concept variation id: {uuid4().hex[:8]}. "
            "Do not reuse previous composition; keep the same requirements but vary the angle/details."
        )[:1200]

    set_busy(user_id, "meshy image")
    try:
        await indicator.show(
            "🟡",
            "Рисую",
            f"Meshy {image_plan.status_hint()}…",
        )
        data, mime, method = await _wait_with_progress(
            indicator,
            meshy_text_to_image(image_prompt, user_request=original_text, plan=image_plan),
            timeout=min(MESHY_TIMEOUT_SEC, 180),
            eta_seconds=min(MESHY_TIMEOUT_SEC, 160),
            detail="Meshy text-to-image: генерирую новый concept, не беру старый файл",
        )
    except asyncio.TimeoutError:
        await indicator.error("Meshy не успел сделать картинку.")
        return DeliveryResult(summary="Meshy image timeout", success=False)
    except MeshyError as e:
        await indicator.error(f"Meshy: {e}")
        return DeliveryResult(summary=str(e), success=False)
    except Exception as e:
        await indicator.error(str(e))
        return DeliveryResult(summary=str(e), success=False)
    finally:
        clear_busy(user_id)

    ext = "png" if "png" in mime else "jpg"
    import hashlib

    image_id = hashlib.sha1(data).hexdigest()[:8]
    fname = f"meshy-image-{image_id}.{ext}"
    caption = f"🖼 {format_method_label(method)}"
    if concept_first or airplane_requested(user_text):
        subject = str((getattr(plan, "extra", {}) or {}).get("subject") or "boeing_airliner")
        caption += (
            "\n\nЭто только концепт перед 3D, не готовый файл для печати. "
            "Если внешний вид устраивает — ответьте «норм, делай 3D по этой картинке». "
            "Если нет — пришлите референс Boeing/ракурс, и я не буду тратить 3D-генерацию впустую."
        )
        set_pending_concept(
            user_id,
            PendingConcept3DJob(
                image_bytes=data,
                mime=mime,
                prompt=image_prompt,
                original_text=original_text,
                subject=subject,
            ),
        )
        await history.save_pending_concept(
            user_id,
            image_bytes=data,
            mime=mime,
            prompt=image_prompt,
            original_text=original_text,
            subject=subject,
        )
    await indicator.done()
    await message.answer_photo(
        BufferedInputFile(data, filename=fname),
        caption=caption[:1024],
    )
    await history.add_message(user_id, "user", original_text[:500])
    await history.add_message(user_id, "assistant", f"Meshy image ({method}).")
    return DeliveryResult(
        summary=f"Meshy image ({method})",
        files=[DeliveredFile(filename=fname, size_bytes=len(data), kind="image")],
        success=True,
    )


async def _reply_meshy_out_of_credits(message: Message, user_text: str) -> DeliveryResult:
    """Honest message when Meshy is out of credits — no primitive bait-and-switch."""
    balance = None
    try:
        from bot.services.meshy_3d import get_meshy_balance

        balance = await get_meshy_balance()
    except Exception:
        pass
    bal_line = f"Текущий баланс Meshy: {balance} кредитов.\n" if balance is not None else ""
    text = (
        "🔴 Не могу сделать реалистичную модель: **закончились кредиты Meshy** "
        "(API вернул 402 Insufficient funds).\n\n"
        f"{bal_line}"
        "Это не баг кода — генерацию реалистичного 3D делает платный Meshy, и на счёте "
        "не осталось кредитов на новую модель (Boeing требует ~10–15).\n\n"
        "Что делать:\n"
        "• Пополнить/обновить план на https://www.meshy.ai/settings/api — после этого "
        "запрос сразу заработает, код уже готов.\n"
        "• Либо напишите «сделай процедурный самолёт» — пришлю детерминированный 3MF "
        "(это упрощённая геометрия из примитивов, честно, не фотореализм).\n\n"
        "Я намеренно НЕ подсовываю примитивный кит вместо реалистичной модели — "
        "ты просил перестать это делать."
    )
    await message.answer(text, parse_mode="Markdown")
    await history.add_message(message.from_user.id, "user", user_text[:500])
    await history.add_message(
        message.from_user.id, "assistant", "Meshy: закончились кредиты — сообщил честно."
    )
    return DeliveryResult(
        summary="Meshy out of credits (HTTP 402)",
        text_reply=text,
        success=True,
        meta={"meshy_out_of_credits": True, "balance": balance},
    )


async def _reply_stl_from_text_meshy(
    message: Message,
    user_text: str,
    text_model: str,
) -> DeliveryResult:
    from bot.config import MESHY_TIMEOUT_SEC
    from bot.services.bambu_hints import (
        bambu_slicer_hint,
        extract_part_color_requests,
        merge_bambu_profile,
        meshy_export_filename,
        nozzle_material_warnings,
    )
    from bot.services.capabilities import stl_quality_disclaimer
    from bot.services.airplane_3mf import airplane_wants_realistic_mesh
    from bot.services.meshy_3d import (
        MeshyError,
        MeshyInsufficientFundsError,
        MeshyNetworkError,
        run_meshy_with_reference_level3,
    )
    from bot.services.meshy_plan import plan_airliner_text_to_3d, plan_text_to_3d, wants_glb_output
    from bot.services.meshy_route import meshy_prompt_from_text

    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    saved = await history.get_print_profile(user_id)
    prof = merge_bambu_profile(saved, user_text)
    prompt = meshy_prompt_from_text(user_text)
    airliner = airplane_wants_realistic_mesh(user_text)
    plan = (
        plan_airliner_text_to_3d(user_text, prompt, fast=True)
        if airliner
        else plan_text_to_3d(user_text, prompt)
    )

    if _needs_reference_before_meshy(user_text):
        text = (
            "Перед 3D-генерацией лучше согласовать внешний вид: пришлите картинку-референс "
            "или напишите «делай 3D сразу без референса».\n\n"
            f"Я понял задачу так: `{prompt[:300]}`\n"
            "Так меньше шанс получить красивый, но не тот объект."
        )
        await message.answer(text, parse_mode="Markdown")
        await history.add_message(user_id, "user", user_text[:500])
        await history.add_message(user_id, "assistant", "Ожидаю референс/подтверждение перед Meshy 3D.")
        return DeliveryResult(
            summary="Ожидаю референс/подтверждение перед Meshy 3D",
            text_reply=text,
            meta={"awaiting_reference": True},
            success=True,
        )

    set_busy(user_id, "meshy 3d")
    try:
        await indicator.show(
            "🟡",
            "Обрабатываю",
            f"Meshy: {plan.status_hint()} (~{min(MESHY_TIMEOUT_SEC // 60, 5)} мин)…",
        )
        from bot.config import MESHY_RIG_TIMEOUT_SEC
        from bot.services.meshy_plan import Meshy3DPipeline

        rig_timeout = (
            MESHY_RIG_TIMEOUT_SEC + 120
            if plan.pipeline == Meshy3DPipeline.RIG_ANIMATE
            else (max(MESHY_TIMEOUT_SEC + 420, 720) if airliner else MESHY_TIMEOUT_SEC + 120)
        )
        meshy_detail = (
            "Meshy text-to-3D Boeing (прямой путь, без mood board)"
            if airliner
            else "Meshy level3: mood board / text-to-3D + reference split"
        )
        delivery = await _wait_with_progress(
            indicator,
            run_meshy_with_reference_level3(
                prompt, user_request=user_text, plan=plan
            ),
            timeout=rig_timeout,
            eta_seconds=min(rig_timeout, 540 if airliner else 420),
            detail=meshy_detail,
        )
    except asyncio.TimeoutError:
        await indicator.error("Meshy timeout — файл не получен.")
        _, dr = await _reply_printable_fallback_after_meshy_failure(
            message,
            user_text,
            text_model,
            reason="Meshy text-to-3D timeout.",
        )
        return dr
    except MeshyInsufficientFundsError:
        await indicator.done()
        return await _reply_meshy_out_of_credits(message, user_text)
    except MeshyError as e:
        await indicator.error(f"Meshy error: {e}")
        _, dr = await _reply_printable_fallback_after_meshy_failure(
            message,
            user_text,
            text_model,
            reason=f"Meshy text-to-3D failed: {e}",
        )
        return dr
    except Exception as e:
        await indicator.error(f"Meshy crashed: {e}")
        _, dr = await _reply_printable_fallback_after_meshy_failure(
            message,
            user_text,
            text_model,
            reason=f"Meshy text-to-3D crashed: {e}",
        )
        return dr
    finally:
        clear_busy(user_id)

    if not delivery.primary:
        await indicator.error("Meshy не вернул файл модели.")
        _, dr = await _reply_printable_fallback_after_meshy_failure(
            message,
            user_text,
            text_model,
            reason="Meshy text-to-3D returned no primary model file.",
        )
        return dr

    if _needs_best_meshy_candidate(user_text):
        await indicator.show(
            "🟡",
            "Сравниваю",
            "Оцениваю Meshy-кандидат и при необходимости пробую второй high-detail вариант…",
        )
        delivery, chosen_score, other_score = await _try_better_text_meshy_candidate(
            delivery, user_text, indicator=indicator
        )
        if other_score is not None:
            score_txt = f"chosen={chosen_score.get('score')}, other={other_score.get('score')}"
            delivery.method = f"{delivery.method} · best-of-2 Meshy ({score_txt})"

    primary = delivery.primary
    is_anim = primary and primary.ext == "glb"
    fname = (
        meshy_export_filename(user_text, ext="glb").replace(
            "-meshy.glb", "-animated.glb"
        )
        if is_anim
        else meshy_export_filename(user_text, ext="stl")
    )
    await indicator.done()
    from bot.services.bambu_hints import support_decision_hint

    if is_anim:
        cap = (
            f"🎬 Анимированный персонаж (Meshy rig+anim).\n"
            f"· {delivery.method}\n· {plan.status_hint()}"
        )
    else:
        cap = stl_quality_disclaimer(
            from_photo=False,
            meshy=True,
            text_to_3d=True,
            meshy_hint=plan.status_hint(),
        )
    cap += f"\n🖨 {format_profile(prof)}\n· {delivery.method}\n· Промпт: {prompt[:120]}"
    cap += f"\n\n{bambu_slicer_hint(prof)}"
    if not is_anim and _meshy_delivery_has_repair_warning(delivery):
        cap += (
            "\n\n⚠️ Repair не смог гарантировать идеальную manifold-сетку, поэтому Bambu может показать предупреждение. "
            "Отправляю отредактированный Meshy-derived файл, а не процедурный fallback."
        )
    cap += f"\n{support_decision_hint(user_text, file_kind='stl')}"
    warn = nozzle_material_warnings(prof, user_text)
    if warn:
        cap += f"\n\n{warn}"
    await history.set_print_profile(user_id, prof)
    dr = await _send_meshy_3d_files(
        message,
        delivery,
        base_caption=cap,
        primary_fname=fname,
        user_id=user_id,
        history_user=user_text[:500],
        history_assistant=f"3D Meshy ({delivery.method}).",
        include_preview_glb=plan.deliver_glb or wants_glb_output(user_text),
        user_text_for_support=user_text,
        support_profile=prof,
        require_object_level_colors=_meshy_requires_object_level_result(user_text, is_anim=is_anim),
    )
    if (
        not dr.success
        and dr.meta.get("quality_gate_failed")
        and not dr.files
        and not dr.meta.get("native_3mf")
    ):
        _, fallback_dr = await _reply_printable_fallback_after_meshy_failure(
            message,
            user_text,
            text_model,
            reason=str(dr.meta.get("quality_gate_reason") or dr.summary),
        )
        return fallback_dr
    hint = _plastic_budget_hint(user_text)
    if hint:
        await message.answer(hint)
    color_hint = _color_print_hint(user_text, prof)
    if color_hint:
        await message.answer(color_hint)
    return dr


async def _reply_chat_with_model(
    message: Message,
    user_text: str,
    model: str,
    *,
    phase: str = "думаю",
) -> DeliveryResult:
    user_id = message.from_user.id
    label = AVAILABLE_MODELS.get(model, model)
    indicator = StatusIndicator(message)

    set_busy(user_id, phase)
    try:
        await indicator.thinking(label)
        past = await history.get_history(user_id)
        messages = [*past, {"role": "user", "content": user_text}]

        try:
            reply = await llm.chat_completion(messages, model)
        except llm.LLMError as e:
            await indicator.error(str(e))
            return DeliveryResult(summary=str(e), success=False)
        except Exception as e:
            await indicator.error(f"Ошибка: {e}")
            return DeliveryResult(summary=str(e), success=False)

        if llm.last_llm_provider() == "gemini":
            await message.answer(
                "ℹ️ KupiAPI недоступен — этот ответ через запасной Google Gemini.",
                parse_mode=None,
            )

        await history.add_message(user_id, "user", user_text)
        extra_files: list[DeliveredFile] = []

        if looks_like_file_refusal(reply):
            fmt = (
                resolve_output_file_format(user_text)
                or infer_format_from_refusal(reply)
                or infer_format_from_refusal(user_text)
            )
            if fmt:
                await indicator.show("🟡", "Обрабатываю", "Модель отказала — собираю файл сам…")
                dr = await _send_generated_file(
                    message, user_text, model, fmt, context=user_text
                )
                await history.add_message(
                    user_id, "assistant", f"Отправлен файл ({fmt.upper()})."
                )
                return dr

        await history.add_message(user_id, "assistant", reply)
        await indicator.done()
        parts = split_message(reply)
        await message.answer(parts[0], parse_mode=None)
        for part in parts[1:]:
            await message.answer(part)

        file_fmt = resolve_output_file_format(user_text)
        if file_fmt == "pdf" and wants_pdf_output(user_text):
            await _send_seo_pdf(message, user_text, reply, model)
        elif file_fmt and file_fmt != "stl":
            dr = await _send_generated_file(message, user_text, model, file_fmt, context=reply)
            extra_files.extend(dr.files)
        elif file_fmt == "stl":
            from bot.services.file_output import explicit_stl_file_requested

            if explicit_stl_file_requested(user_text):
                dr = await _send_generated_file(message, user_text, model, "stl", context=reply)
                extra_files.extend(dr.files)
        elif wants_pdf_output(user_text):
            await _send_seo_pdf(message, user_text, reply, model)

        return DeliveryResult(
            summary="Текстовый ответ",
            text_reply=reply,
            files=extra_files,
            success=True,
        )
    finally:
        clear_busy(user_id)


async def reply_with_llm(
    message: Message,
    user_text: str,
    *,
    phase: str = "думаю",
) -> None:
    from bot.services.pending_3d import get_pending
    from bot.services.print_profile import ensure_profile
    from bot.services.processing import get_phase, is_user_busy
    from bot.services.self_check import announce_task_plan, report_self_check
    from bot.services.task_dispatch import execute_text_plan
    from bot.services.task_plan import build_task_plan
    from bot.services.user_prefs import should_skip_questionnaire
    from bot.services.voice_reply import (
        is_voice_only_request,
        last_assistant_text,
        prepare_text_for_tts,
        send_voice_reply,
        strip_voice_request_phrases,
        wants_voice_reply,
    )

    user_id = message.from_user.id
    await history.ensure_user_bootstrapped(user_id)
    user_model = await history.get_model(user_id, DEFAULT_MODEL)

    if is_user_busy(user_id):
        current_phase = get_phase(user_id) or "предыдущий запрос"
        await message.answer(
            f"⏳ Подождите — ещё обрабатываю предыдущий запрос: {current_phase}. "
            "Когда закончу, пришлите следующее сообщение.",
            parse_mode=None,
        )
        return

    if is_voice_only_request(user_text):
        prev = await last_assistant_text(user_id)
        if prev:
            ok, err = await send_voice_reply(message, prev, force=True)
            if ok:
                await message.answer("🔊 Озвучил предыдущий ответ.")
                return
            await message.answer(f"🔴 Не удалось озвучить: {err}")
            return
        await message.answer("Нет предыдущего ответа для озвучки. Напишите вопрос или пришлите 🎤.")
        return

    from bot.services.hybrid_v3_figure8_corpus import (
        is_v3_3mf_request,
        is_v3_figure8_corpus_request,
        is_v3_print_approval,
    )
    from bot.services.pending_3d import has_pending_v3_figure8

    pending_v3 = has_pending_v3_figure8(user_id)

    if is_v3_figure8_corpus_request(user_text):
        await _send_v3_figure8_preview(message)
        return

    if pending_v3 and (
        is_v3_print_approval(user_text) or is_v3_3mf_request(user_text, pending_preview=True)
    ):
        await _send_v3_figure8_print_pack(message)
        return

    if is_v3_3mf_request(user_text, pending_preview=False):
        await _send_v3_figure8_print_pack(message)
        return

    if _is_print_instruction_request(user_text):
        from bot.services.bambu_hints import bambu_print_steps

        file_kind = "3mf" if re.search(r"\b3mf\b|проект", user_text, re.I) else "stl"
        await message.answer(bambu_print_steps(user_text, file_kind=file_kind), parse_mode=None)
        await history.add_message(user_id, "user", user_text[:500])
        await history.add_message(user_id, "assistant", "Инструкция Bambu Studio для печати.")
        return

    engineering_done = await _complete_pending_engineering_from_text(message, user_text, user_model)
    if engineering_done:
        return

    asset_done = await _complete_3d_asset_command_from_text(message, user_text, user_model)
    if asset_done:
        if isinstance(asset_done, DeliveryResult):
            from bot.services.self_check import report_self_check
            from bot.services.task_plan import TaskKind, TaskPlan

            asset_plan = TaskPlan(
                kind=TaskKind.CHAT,
                label="Команда к загруженному 3D-файлу",
                model=user_model,
                model_reason="Последний загруженный STL/3MF используется как контекст.",
                capability="engineering_json",
                user_text=user_text,
                extra={"asset_command": True},
            )
            await report_self_check(message, asset_plan, asset_done)
        return

    concept_done = await _complete_pending_concept_from_text(message, user_text, user_model)
    if concept_done == "handled":
        return
    if concept_done:
        concept_plan, concept_delivery = concept_done
        await report_self_check(message, concept_plan, concept_delivery)
        return

    if await _complete_pending_3d_from_text(message, user_text):
        return

    if _is_ambiguous_short_3d_command(user_text):
        await message.answer(
            "Не буду придумывать предмет из истории. Напишите, что именно делать в 3D: "
            "например «сделай 3D модель лабрадора», «Boeing 15 см», «ручка для 5л бутылки». "
            "Если вы подтверждаете картинку, напишите: «норм, делай 3D по этой картинке».",
            parse_mode=None,
        )
        await history.add_message(user_id, "user", user_text[:500])
        await history.add_message(
            user_id,
            "assistant",
            "Короткая 3D-команда без предмета остановлена, чтобы не подменять объект старым контекстом.",
        )
        return

    from bot.services.engineering_intake import needs_engineering_intake, render_engineering_intake

    pending = get_pending(user_id)
    prof = ensure_profile(
        merge_profiles(
            await history.get_print_profile(user_id),
            parse_print_profile(user_text),
        ),
        user_text,
    )
    skip_q = await should_skip_questionnaire(user_id)
    has_pending = (
        pending is not None and missing_fields(prof) and not skip_q
    )
    if skip_q and missing_fields(prof):
        await history.set_print_profile(user_id, prof)

    if needs_engineering_intake(user_text, prof):
        from bot.services.airplane_3mf import airplane_wants_realistic_mesh

        if not airplane_wants_realistic_mesh(user_text):
            set_pending_engineering(user_id, PendingEngineeringIntake(prompt=user_text))
            await message.answer(render_engineering_intake(user_text, prof), parse_mode=None)
            await history.add_message(user_id, "user", user_text[:500])
            await history.add_message(user_id, "assistant", "Ожидаю подтверждение инженерных параметров.")
            return

    plan_text, want_voice_extra = strip_voice_request_phrases(user_text)
    want_voice = want_voice_extra or wants_voice_reply(user_text)
    plan = build_task_plan(
        plan_text or user_text, user_model, has_pending_3d=has_pending
    )
    if plan.model != user_model and plan.capability not in ("chat", "meshy", "vision"):
        from bot.config import AUTO_SWITCH_MODEL

        if AUTO_SWITCH_MODEL:
            await history.set_model(user_id, plan.model)
    await announce_task_plan(message, plan)

    delivery = await execute_text_plan(message, plan, phase=phase)

    need_voice = (
        phase == "голос"
        or message.voice
        or message.audio
        or want_voice
    )
    if delivery.success and need_voice:
        voice_text = prepare_text_for_tts(delivery.text_reply or "")
        if not voice_text and delivery.summary and not delivery.files:
            voice_text = prepare_text_for_tts(delivery.summary)
        if voice_text:
            ok, err = await send_voice_reply(
                message,
                voice_text,
                force=want_voice,
            )
            if ok:
                delivery.meta["voice_sent"] = True
            elif err:
                await message.answer(f"🔴 Голосовой ответ: {err}")

    await report_self_check(message, plan, delivery)


async def _make_avito_card(
    message: Message,
    image_data: bytes,
    prompt_text: str,
    width: int,
    height: int,
    text_model: str,
    indicator: StatusIndicator,
) -> Optional[Tuple[str, str, str, bytes, str]]:
    """Возвращает (facts, caption, method, bytes, mime) или None при ошибке."""
    no_text = bool(re.search(r"без\s+текст", prompt_text, re.I))

    indicator.start_progress("Шаг 1/3: смотрю фото", eta_seconds=15)
    try:
        facts, _ = await asyncio.wait_for(
            llm.describe_image_facts(image_data, width, height),
            timeout=15,
        )
    except (asyncio.TimeoutError, llm.LLMError, Exception):
        facts = _local_card_facts(image_data, prompt_text, width, height)
    finally:
        indicator.stop_progress()

    indicator.start_progress("Шаг 2/3: текст для карточки", eta_seconds=8)
    try:
        card_copy = await asyncio.wait_for(
            llm.generate_avito_card_copy(prompt_text, facts, text_model),
            timeout=20,
        )
    except (asyncio.TimeoutError, llm.LLMError, Exception):
        from bot.services.avito_card import _parse_card_copy_fallback

        card_copy = _parse_card_copy_fallback(prompt_text, facts)
    finally:
        indicator.stop_progress()

    card_eta = 45
    indicator.start_progress("Шаг 3/3: собираю карточку", eta_seconds=card_eta)
    try:
        out_bytes, mime, method = await asyncio.wait_for(
            produce_image(
                image_data,
                prompt_text,
                facts,
                with_text=not no_text,
                card_copy=card_copy,
            ),
            timeout=75,
        )
    except asyncio.TimeoutError:
        await indicator.error(
            "Сборка карточки заняла слишком долго. Попробуйте ещё раз."
        )
        return None
    except Exception as e:
        await indicator.error(f"Не удалось сделать картинку: {e}")
        return None
    finally:
        indicator.stop_progress()

    lines = [card_copy.title]
    if card_copy.subtitle:
        lines.append(card_copy.subtitle)
    lines.extend(card_copy.bullets[:2])
    caption = "\n".join(lines)[:900]
    method_line = format_method_label(method)

    return facts, caption, method, out_bytes, mime


async def reply_with_vision(
    message: Message,
    image_data: bytes,
    prompt_text: str,
    image_bytes: int = 0,
    width: int = 0,
    height: int = 0,
    *,
    phase: str = "читаю фото",
    telegram_file_id: str = "",
) -> None:
    user_id = message.from_user.id
    text_model = await history.get_model(user_id, DEFAULT_MODEL)
    text_label = AVAILABLE_MODELS.get(text_model, text_model)
    indicator = StatusIndicator(message)

    from bot.services.portrait_figurine import is_portrait_figurine_request
    from bot.services.meshy_route import should_meshy_from_photo

    if is_portrait_figurine_request(prompt_text):
        set_busy(user_id, phase)
        try:
            await _reply_portrait_figurine_from_photo(
                message,
                image_data,
                prompt_text,
                width,
                height,
                text_model,
                telegram_file_id=telegram_file_id,
            )
        finally:
            clear_busy(user_id)
        return

    if should_meshy_from_photo(prompt_text):
        set_busy(user_id, phase)
        try:
            await _reply_stl_from_photo(
                message,
                image_data,
                prompt_text,
                width,
                height,
                text_model,
                telegram_file_id=telegram_file_id,
            )
        finally:
            clear_busy(user_id)
        return

    file_fmt = resolve_output_file_format(prompt_text)
    if not file_fmt and wants_3d_model_from_photo(prompt_text):
        file_fmt = "stl"
    file_count = parse_file_count(prompt_text, 1)
    make_image = wants_image_output(prompt_text) and not file_fmt
    want_pdf = wants_pdf_output(prompt_text)

    set_busy(user_id, phase)
    try:
        if file_fmt == "stl":
            await _reply_stl_from_photo(
                message,
                image_data,
                prompt_text,
                width,
                height,
                text_model,
                telegram_file_id=telegram_file_id,
            )
            return

        if file_fmt:
            facts = _local_card_facts(image_data, prompt_text, width, height)
            try:
                facts, _ = await asyncio.wait_for(
                    llm.describe_image_facts(image_data, width, height),
                    timeout=15,
                )
            except (asyncio.TimeoutError, llm.LLMError, Exception):
                pass
            await _send_generated_file(
                message,
                prompt_text,
                text_model,
                file_fmt,
                context=facts,
                count=file_count,
            )
            await history.add_message(
                user_id, "user", f"[Фото {width}x{height}] {prompt_text[:400]}"
            )
            await history.add_message(
                user_id,
                "assistant",
                f"Отправлено файлов: {file_count} ({file_fmt.upper()}).",
            )
            return

        if make_image:
            result = await _make_avito_card(
                message,
                image_data,
                prompt_text,
                width,
                height,
                text_model,
                indicator,
            )
            if result is None:
                return
            facts, answer, method, out_bytes, out_mime = result
        else:
            indicator.start_progress("Шаг 1/2: анализирую фото", eta_seconds=90)
            try:
                facts, answer, method, out_bytes, out_mime = await asyncio.wait_for(
                    llm.process_image_request(
                        image_data,
                        width,
                        height,
                        prompt_text,
                        text_model,
                        produce_image=False,
                    ),
                    timeout=120,
                )
            except asyncio.TimeoutError:
                await indicator.error(
                    "Анализ фото занял больше 2 минут. Проверьте интернет или /reset."
                )
                return
            except llm.LLMError as e:
                await indicator.error(str(e))
                return
            except Exception as e:
                await indicator.error(f"Ошибка: {e}")
                return
            finally:
                indicator.stop_progress()

        await indicator.thinking(text_label, eta_seconds=8)

        hist_user = f"[Фото {width}x{height}] {prompt_text[:400]}"
        await history.add_message(user_id, "user", hist_user)
        await history.add_message(user_id, "assistant", answer)

        await indicator.done()

        if out_bytes:
            ext = "jpg" if "jpeg" in (out_mime or "") else "png"
            method_human = format_method_label(method)
            cap = f"{answer}\n\n🖼 {method_human}"[:1024]
            await message.answer_photo(
                BufferedInputFile(out_bytes, filename=f"result.{ext}"),
                caption=cap,
            )
        else:
            parts = split_message(answer)
            if method.startswith("ocr/"):
                hints = [f"📷 Режим: OCR ({method.split('/', 1)[1]})"]
            else:
                hints = [f"📷 {format_method_label(method)}"]
            if image_bytes and image_bytes < 80_000:
                hints.append("💡 Для точности: отправьте как «Файл», не «Фото».")
            if "ocr/" in method and "не распознан" in facts.lower():
                hints.append("⚠️ Текст на фото не найден — добавьте подпись.")
            prefix = "\n".join(hints) + "\n\n"
            await message.answer(prefix + parts[0], parse_mode=None)
            for part in parts[1:]:
                await message.answer(part)

        facts_short = facts[:1500] + ("…" if len(facts) > 1500 else "")
        await message.answer(
            f"🔍 <b>Данные с фото:</b>\n<pre>{facts_short}</pre>\n"
            f"<i>Картинка: {format_method_label(method) if out_bytes else '—'}</i>",
            parse_mode="HTML",
        )

        if want_pdf or re.search(r"seo|сео|pdf|пдф", prompt_text, re.I):
            await _send_seo_pdf(
                message, prompt_text, facts, text_model, card_method=method or ""
            )
    finally:
        clear_busy(user_id)
