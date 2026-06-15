from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message

from bot.config import DEFAULT_MODEL
from bot.handlers.chat_logic import _send_print_project, reply_with_llm, reply_with_vision
from bot.services import history
from bot.services.files import FileError, _decode_text, download_document, extract_text
from bot.services.print_project import wants_print_project
from bot.services.vision import (
    IMAGE_EXTENSIONS,
    build_vision_prompt,
    image_dimensions,
)
from bot.services.processing import clear_busy, set_busy
from bot.status_ui import StatusIndicator

router = Router()

_THREE_D_EXTENSIONS = {".stl", ".3mf", ".obj", ".glb", ".gltf", ".step", ".stp"}
_THREE_D_ARCHIVE_EXTENSIONS = {".zip"}
_ARCHIVE_3D_EXTENSIONS = {".stl", ".3mf", ".obj", ".glb", ".gltf", ".step", ".stp", ".scad", ".f3d"}


def _looks_like_boeing_asset(filename: str, caption: str) -> bool:
    import re

    blob = f"{filename} {caption}".lower()
    return bool(re.search(r"boeing|боинг|airliner|airplane|самол[её]т", blob, re.I))


def _wants_3d_file_action(caption: str) -> bool:
    import re

    return bool(
        re.search(
            r"тест\s*2|улучши|доработ|почини|repair|исправ|bambu|бамбу|масштаб|"
            r"поддержк|support|центр|на\s+стол|печат|сделай",
            caption or "",
            re.I,
        )
    )


async def _handle_3d_document(message: Message, filename: str, ext: str, data: bytes) -> None:
    """Accept uploaded mesh/CAD files as 3D assets, not unsupported text documents."""
    import re

    user_id = message.from_user.id
    caption = (message.caption or "").strip()
    lower_name = filename.lower()

    from bot.services.mesh_cache import save_mesh_asset

    save_mesh_asset(
        user_id,
        "last_3d_upload",
        data=data,
        filename=filename,
        meta={"source": "user_upload", "caption": caption, "ext": ext},
    )

    if _looks_like_boeing_asset(filename, caption):
        save_mesh_asset(
            user_id,
            "boeing_airliner_last_meshy",
            data=data,
            filename=filename,
            meta={"source": "user_upload", "caption": caption, "ext": ext},
        )

    if ext == ".stl" and _wants_3d_file_action(caption):
        await message.answer(
            "Принял STL как 3D-ассет. Сейчас сделаю быстрый Bambu-проход: масштаб/центрирование/repair.",
            parse_mode=None,
        )
        try:
            from bot.services.stl_postprocess import prepare_meshy_stl_for_bambu

            user_text = caption or filename
            prepared = prepare_meshy_stl_for_bambu(data, user_text=user_text)
            out_name = filename.rsplit(".", 1)[0] + "-bambu-repaired.stl"
            save_mesh_asset(
                user_id,
                "last_3d_upload_repaired",
                data=prepared.data,
                filename=out_name,
                meta={
                    "source": "user_upload_repaired",
                    "note": prepared.note,
                    "width_mm": prepared.width_mm,
                    "depth_mm": prepared.depth_mm,
                    "height_mm": prepared.height_mm,
                },
            )
            if _looks_like_boeing_asset(filename, caption):
                save_mesh_asset(
                    user_id,
                    "boeing_airliner_last_meshy",
                    data=prepared.data,
                    filename=out_name,
                    meta={"source": "user_upload_repaired", "note": prepared.note},
                )
            await message.answer_document(
                BufferedInputFile(prepared.data, filename=out_name),
                caption=(
                    "STL подготовлен для Bambu: центрирование/масштаб/repair.\n"
                    f"Размеры ~{prepared.width_mm:.0f}×{prepared.depth_mm:.0f}×{prepared.height_mm:.0f} мм.\n"
                    f"{prepared.note}"
                )[:1024],
            )
            await history.add_message(user_id, "assistant", f"3D upload repaired ({out_name}).")
            return
        except Exception as e:
            await message.answer(
                f"Файл принял и сохранил, но быстрый repair не прошёл: {type(e).__name__}: {str(e)[:160]}",
                parse_mode=None,
            )

    await message.answer(
        (
            f"Принял 3D-файл `{filename}` ({len(data) // 1024} KB) и сохранил его как ассет.\n\n"
            "Что могу сделать дальше:\n"
            "1. `почини для Bambu` — STL repair, центрирование, масштаб.\n"
            "2. `сделай supports/3MF` — подготовить проект под Bambu Studio.\n"
            "3. `улучши Boeing` — использовать файл как основу/референс, без CAD-подмены.\n\n"
            "Напишите команду следующим сообщением."
        ),
        parse_mode="Markdown",
    )
    await history.add_message(user_id, "user", f"[3D file upload] {filename} {caption[:300]}")
    await history.add_message(user_id, "assistant", "3D file accepted and cached.")


def _safe_stl_metrics(stl_bytes: bytes, name: str) -> dict:
    """Parse mesh metrics in a worker so malformed STL cannot crash the bot."""
    import json
    import os
    import subprocess
    import sys
    import tempfile

    from pathlib import Path as _Path

    project_root = str(_Path(__file__).resolve().parents[2])
    fd, path = tempfile.mkstemp(suffix=".stl")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(stl_bytes)
        script = (
            "import json, sys\n"
            "try:\n"
            "    import trimesh\n"
            "    mesh = trimesh.load(sys.argv[1], file_type='stl', force='mesh')\n"
            "    comps = mesh.split(only_watertight=False)\n"
            "    extents = [round(float(x), 1) for x in mesh.extents]\n"
            "    out = {'faces': int(len(mesh.faces)), 'watertight': bool(mesh.is_watertight), 'components': int(len(comps)), 'extents': extents}\n"
            "    try:\n"
            "        sys.path.insert(0, sys.argv[2])\n"
            "        from bot.services import mesh_engineering as ME\n"
            "        rep = ME.analyze_mesh(mesh, material='pla', do_thickness=True, do_orientation=True)\n"
            "        out['engineering'] = {\n"
            "            'mass_g': round(rep.mass.mass_g, 1),\n"
            "            'volume_cm3': round(rep.mass.volume_mm3/1000.0, 1),\n"
            "            'com_height_mm': round(rep.stability.com_height_mm, 1),\n"
            "            'stability': rep.stability.verdict,\n"
            "            'topple_angle_deg': round(rep.stability.topple_angle_deg, 0),\n"
            "            'overhang_pct': round(rep.overhang.overhang_fraction*100, 0),\n"
            "            'needs_support': bool(rep.overhang.needs_support),\n"
            "            'min_wall_mm': round(rep.thickness.min_thickness_mm, 2) if rep.thickness else None,\n"
            "            'best_orientation': rep.recommended_orientation.name if rep.recommended_orientation else None,\n"
            "            'notes': rep.notes,\n"
            "        }\n"
            "        try:\n"
            "            gate = ME.printability_gate(rep)\n"
            "            out['engineering']['gate'] = gate.severity\n"
            "            out['engineering']['gate_issues'] = gate.issues\n"
            "            out['engineering']['load_capacity_kg'] = round(ME.safe_cantilever_load_kg(rep.mass, 'pla'), 1)\n"
            "        except Exception:\n"
            "            pass\n"
            "    except Exception as ee:\n"
            "        out['engineering_error'] = type(ee).__name__ + ': ' + str(ee)[:80]\n"
            "    print(json.dumps(out))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'error': type(e).__name__ + ': ' + str(e)[:80]}))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script, path, project_root],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            return {
                "name": name,
                "error": f"mesh worker crashed: exit {proc.returncode}; {proc.stderr.strip()[:80]}",
            }
        payload = json.loads((proc.stdout or "{}").strip() or "{}")
        payload["name"] = name
        return payload
    except subprocess.TimeoutExpired:
        return {"name": name, "error": "mesh worker timeout"}
    except Exception as e:
        return {"name": name, "error": f"{type(e).__name__}: {str(e)[:80]}"}
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _zip_3d_inventory(data: bytes) -> dict:
    import io
    import zipfile
    from pathlib import Path
    from collections import Counter

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        exts = Counter(Path(i.filename).suffix.lower() or "(none)" for i in infos)
        model_infos = [i for i in infos if Path(i.filename).suffix.lower() in _ARCHIVE_3D_EXTENSIONS]
        stl_infos = [i for i in infos if Path(i.filename).suffix.lower() == ".stl"]
        text_infos = [
            i
            for i in infos
            if Path(i.filename).suffix.lower() in {".txt", ".md"}
            or "readme" in i.filename.lower()
            or "instruction" in i.filename.lower()
        ]
        snippets = []
        for info in text_infos[:3]:
            try:
                txt = zf.read(info).decode("utf-8", errors="ignore")
            except Exception:
                continue
            clean = " ".join(txt.split())
            if clean:
                snippets.append((info.filename, clean[:500]))

        metrics = []
        for info in stl_infos[:8]:
            try:
                metrics.append(_safe_stl_metrics(zf.read(info), info.filename))
            except Exception as e:
                metrics.append({"name": info.filename, "error": f"{type(e).__name__}: {str(e)[:80]}"})

    return {
        "files_count": len(infos),
        "extensions": dict(sorted(exts.items())),
        "model_files_count": len(model_infos),
        "stl_count": len(stl_infos),
        "model_names": [i.filename for i in model_infos[:30]],
        "readme_snippets": snippets,
        "metrics": metrics,
    }


async def _handle_3d_archive_document(message: Message, filename: str, data: bytes) -> bool:
    import zipfile

    user_id = message.from_user.id
    try:
        inv = _zip_3d_inventory(data)
    except zipfile.BadZipFile:
        return False
    except Exception as e:
        await message.answer(
            f"ZIP получил, но аудит архива не прошёл: {type(e).__name__}: {str(e)[:140]}",
            parse_mode=None,
        )
        return True

    if not inv["model_files_count"]:
        return False

    from bot.services.mesh_cache import save_mesh_asset

    save_mesh_asset(
        user_id,
        "last_3d_archive_upload",
        data=data,
        filename=filename,
        meta={"source": "user_zip_upload", "inventory": inv},
    )

    lines = [
        f"Принял ZIP `{filename}` как 3D-проект, не как текстовый файл.",
        f"Файлов: {inv['files_count']}; 3D/CAD: {inv['model_files_count']}; STL: {inv['stl_count']}.",
        f"Форматы: {inv['extensions']}",
        "",
        "Первые 3D-файлы:",
    ]
    for name in inv["model_names"][:10]:
        lines.append(f"- {name}")
    if inv["metrics"]:
        lines.append("")
        lines.append("Mesh audit sample:")
        for m in inv["metrics"][:5]:
            if "error" in m:
                lines.append(f"- {m['name']}: {m['error']}")
            else:
                lines.append(
                    f"- {m['name']}: faces={m['faces']}, watertight={m['watertight']}, "
                    f"components={m['components']}, size={m['extents']} мм"
                )
    if inv["readme_snippets"]:
        lines.append("")
        lines.append("README/инструкции найдены: да.")
    lines.append("")
    lines.append(
        "Следующий шаг: напишите `подготовь архив к Bambu` — бот должен выбрать strategy: "
        "repair/split/assembly/kit-card/supports, а не слепо сшивать всё в один mesh."
    )
    await message.answer("\n".join(lines)[:3500], parse_mode="Markdown")
    await history.add_message(user_id, "user", f"[3D archive upload] {filename}")
    await history.add_message(user_id, "assistant", "3D archive audited and cached.")
    return True


@router.message(F.document)
async def on_document(message: Message) -> None:
    doc = message.document
    if not doc.file_name:
        await message.answer("Отправьте файл с именем (расширением): .txt, .html, .pdf, .docx …")
        return

    ext = ("." + doc.file_name.rsplit(".", 1)[-1].lower()) if "." in doc.file_name else ""
    user_id = message.from_user.id
    indicator = StatusIndicator(message)
    set_busy(user_id, "читаю файл")

    try:
        await indicator.reading_file(doc.file_name)
        data = await download_document(message.bot, doc.file_id)

        if ext in _THREE_D_EXTENSIONS:
            await indicator.done()
            await _handle_3d_document(message, doc.file_name, ext, data)
            clear_busy(user_id)
            return

        if ext in _THREE_D_ARCHIVE_EXTENSIONS:
            handled = await _handle_3d_archive_document(message, doc.file_name, data)
            if handled:
                await indicator.done()
                clear_busy(user_id)
                return

        if ext in IMAGE_EXTENSIONS:
            await indicator.viewing_image()
            w, h = image_dimensions(data)
            prompt = build_vision_prompt(message.caption)
            await indicator.done()
            await reply_with_vision(
                message,
                data,
                prompt,
                image_bytes=len(data),
                width=w,
                height=h,
                phase="читаю фото",
            )
            return

        await indicator.extracting(doc.file_name)
        text = extract_text(doc.file_name, data)
    except FileError as e:
        await indicator.error(str(e))
        clear_busy(user_id)
        return
    except Exception as e:
        await indicator.error(f"Не удалось обработать файл: {e}")
        clear_busy(user_id)
        return

    caption = (message.caption or "").strip()
    wants_pack = wants_print_project(caption) or (
        ext in {".html", ".htm"} and wants_print_project(text[:4000])
    )

    if wants_pack:
        storyboard_frames = []
        if ext in {".html", ".htm"}:
            from bot.services.storyboard import (
                extract_embedded_images,
                is_storyboard_document,
                parse_storyboard,
            )
            from bot.config import MESHY_API_KEY
            from bot.services.meshy_3d import MeshyError, image_to_stl_mesh
            from bot.services.vision import detect_mime

            try:
                raw_html = _decode_text(data)
                if is_storyboard_document(doc.file_name, raw_html):
                    storyboard_frames = parse_storyboard(raw_html)
                    embedded = extract_embedded_images(raw_html)
                    if embedded and MESHY_API_KEY:
                        await indicator.show(
                            "🟡",
                            "Обрабатываю",
                            f"Meshy: 3D по картинкам из HTML ({len(embedded)} шт.)…",
                        )
                        sent = 0
                        for idx, img_bytes in enumerate(embedded[:5], start=1):
                            try:
                                mesh = await image_to_stl_mesh(
                                    img_bytes,
                                    detect_mime(img_bytes),
                                    caption or f"кадр {idx} storyboard",
                                )
                                if mesh:
                                    stl_data, method = mesh
                                    mesh_ext = "glb" if "GLB" in method.upper() else "stl"
                                    await message.answer_document(
                                        BufferedInputFile(
                                            stl_data,
                                            filename=f"storyboard-meshy-{idx:02d}.{mesh_ext}",
                                        ),
                                        caption=f"🧊 Meshy · кадр {idx}/{len(embedded[:5])} · {method}"[:1024],
                                    )
                                    sent += 1
                            except MeshyError as e:
                                await message.answer(f"Meshy кадр {idx}: {e}")
                        if sent:
                            await indicator.done()
                            await history.add_message(
                                user_id,
                                "assistant",
                                f"Meshy: отправлено {sent} 3D-моделей из HTML.",
                            )
                            clear_busy(user_id)
                            return
            except Exception:
                storyboard_frames = parse_storyboard(text)

        prompt = (
            f"Пользователь отправил файл «{doc.file_name}».\n"
            f"Запрос: {caption or 'сделай проект на печать по этому файлу'}\n\n"
            f"--- Содержимое ---\n\n{text[:12000]}"
        )
        await indicator.done()
        try:
            model = await history.get_model(user_id, DEFAULT_MODEL)
            await _send_print_project(
                message,
                prompt,
                model,
                context=text[:12000],
                storyboard_frames=storyboard_frames or None,
            )
        finally:
            clear_busy(user_id)
        return

    if caption:
        prompt = (
            f"Пользователь отправил файл «{doc.file_name}» и просит:\n{caption}\n\n"
            f"--- Содержимое файла ---\n\n{text}"
        )
    else:
        prompt = (
            f"Пользователь отправил файл «{doc.file_name}».\n"
            "Кратко опиши содержание и дай полезный отзыв: что понятно, "
            "есть ли неточности, как структура.\n\n"
            f"--- Содержимое файла ---\n\n{text}"
        )

    await indicator.done()
    await reply_with_llm(message, prompt, phase="анализирую файл")
