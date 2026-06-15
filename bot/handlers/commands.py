from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import AVAILABLE_MODELS, DEFAULT_MODEL
from bot.services import history

router = Router()


def model_keyboard(current: str) -> InlineKeyboardMarkup:
    from bot.services.model_catalog import PRIMARY_MODEL_IDS, model_label

    buttons = []
    for model_id in PRIMARY_MODEL_IDS:
        label = model_label(model_id)
        prefix = "✓ " if model_id == current else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{label}"[:60],
                    callback_data=f"model:{model_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    from bot.config import DEFAULT_AUTO_PROCEED, LLM_API_KEY
    from bot.services.model_catalog import model_label

    user_id = message.from_user.id
    await history.ensure_user_bootstrapped(user_id)
    model = await history.get_model(user_id, DEFAULT_MODEL)
    label = model_label(model)
    api_note = (
        "\n\n⚠️ Не настроен LLM_API_KEY — ответы не генерируются."
        if not LLM_API_KEY
        else ""
    )
    await message.answer(
        "Привет. Я ассистент в стиле Cursor-агента: отвечаю структурно, по делу, на русском.\n\n"
        f"Текущая модель: <b>{label}</b>\n\n"
        "Команды:\n"
        "/model — выбрать модель\n"
        "/status — работает ли бот и API\n"
        "/laozhang — модели картинок LaoZhang\n"
        "/reset — очистить историю диалога\n"
        "/printer — профиль 3D-печати (принтер, материал)\n"
        "/project — последний проект на печать\n"
        "/gcp — Google Cloud (голос, ADC)\n"
        "/autopilot — не спрашивать принтер, сразу делать\n"
        "/voice — ответ голосом вкл/выкл\n"
        "/money — Центр доходов (план, отчёт, +₽)\n"
        "/help — справка\n\n"
        + (
            "⚡ <b>Автопилот включён</b> — пишите задачу сразу, без анкет.\n\n"
            if DEFAULT_AUTO_PROCEED
            else ""
        )
        + "Индикатор: 🟢 свободен · 🟡 обрабатывает · 🔴 ошибка\n\n"
        "Напишите, пришлите 🎤 голосовое, фото или файл — отвечу.\n"
        "Фото человека + «портретная фигурка bobblehead/chibi» → concept → 3D."
        f"{api_note}",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Как пользоваться</b>\n\n"
        "• Фото: бот <b>видит</b> картинку и может <b>вернуть готовое изображение</b>.\n"
        "  Подпись: «сделай карточку для авито», «обложка», «без текста».\n"
        "  Сначала пробует KupiAPI image API, затем локальный макет на Mac.\n"
        "  Лучше отправлять как «Файл» (jpg/png), не сжатое «Фото».\n"
        "• Файлы на выход: <b>PDF, Word (DOCX), Excel (XLSX), STL, CSV, TXT</b> — "
        "напишите «сделай excel / word / stl».\n"
        "• <b>Портретная фигурка:</b> фото человека + «bobblehead/chibi/cartoon, поза как на фото» "
        "→ 2D concept → 3D Meshy (STL/GLB).\n"
        "• <b>3D с фото:</b> фото + «сделай 3D / STL» — сразу Meshy (автопилот: P2S+PLA).\n"
        "• <b>Анимация персонажа:</b> «человек/герой + анимация/ходьба» → Meshy rig+GLB.\n"
        "• <b>Проект на печать (локально):</b> «сделай проект на печать» или HTML + подпись — "
        "ZIP с OpenSCAD (.scad), планом, сборкой, BOM (+ STL если OpenSCAD на Mac).\n"
        "• /project — последний сохранённый проект\n"
        "• /printer — сохранить Bambu, PLA, сопло 0.4 …\n"
        "• Файлы на вход: txt, html, pdf, docx…\n"
        "• /model — сменить нейросеть.\n"
        "• /status — 🟢 работает / 🔴 не работает, занят ли сейчас.\n"
        "• <b>Голосовые</b> — 🎤 → распознавание → ответ текстом и <b>голосом</b> (GCP).\n"
        "• /autopilot — один раз «да», дальше без опросников.\n"
        "• /voice on|off — ответ голосом.\n"
        "• /gcp — Google Cloud: STT, TTS, Vision, Translate.\n"
        "• /reset — забыть предыдущий контекст.\n"
        "• При ответе: 🟡 «Обрабатываю» с анимацией, потом ответ.\n"
        "• История хранится локально на сервере бота.\n\n"
        "API: KupiAPI (kupiapi.ru/v1). Ключ и баланс — в личном кабинете.",
        parse_mode="HTML",
    )


@router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    from bot.services.model_catalog import model_label

    current = await history.get_model(message.from_user.id, DEFAULT_MODEL)
    label = model_label(current)
    await message.answer(
        f"Выберите модель (сейчас: <b>{label}</b>):",
        reply_markup=model_keyboard(current),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("model:"))
async def on_model_selected(callback: CallbackQuery) -> None:
    from bot.services.model_catalog import merged_available_models, model_label

    model_id = callback.data.removeprefix("model:")
    available = merged_available_models()
    if model_id not in available:
        await callback.answer("Неизвестная модель", show_alert=True)
        return

    await history.set_model(callback.from_user.id, model_id)
    label = model_label(model_id)
    await callback.message.edit_text(
        f"Модель изменена на <b>{label}</b>\n\n/model — сменить снова",
        parse_mode="HTML",
    )
    await callback.answer(f"Выбрано: {label}")


@router.message(Command("models"))
async def cmd_models(message: Message) -> None:
    from bot.services.model_catalog import model_label, refresh_from_api

    ids = await refresh_from_api()
    if not ids:
        await message.answer("Не удалось получить список моделей KupiAPI.")
        return
    lines = ["<b>Модели KupiAPI</b> (авто-выбор под задачу включён):\n"]
    for mid in ids:
        if mid.startswith("kupi-"):
            continue
        lines.append(f"• <code>{mid}</code> — {model_label(mid)}")
    lines.append(
        "\nGoogle Gemini — запасной LLM и картинки через GEMINI_API_KEY "
        "(LLM_GEMINI_FALLBACK=1, если KupiAPI недоступен)."
    )
    lines.append("Голос — Google Cloud Speech (ADC), не KupiAPI.")
    await message.answer("\n".join(lines)[:4000], parse_mode="HTML")


@router.message(Command("autopilot"))
async def cmd_autopilot(message: Message) -> None:
    from bot.services.print_profile import ensure_profile, format_profile
    from bot.services.user_prefs import set_auto_proceed

    user_id = message.from_user.id
    text = (message.text or "").replace("/autopilot", "", 1).strip().lower()
    if text in ("off", "0", "выкл", "нет"):
        await set_auto_proceed(user_id, False)
        await message.answer(
            "Автопилот выключен. Для STL без Meshy бот может снова спросить принтер."
        )
        return
    await set_auto_proceed(user_id, True)
    prof = ensure_profile(await history.get_print_profile(user_id))
    await history.set_print_profile(user_id, prof)
    await message.answer(
        "✅ <b>Автопилот включён</b>\n\n"
        "Больше не буду присылать анкету принтера — сразу делаю задачу.\n"
        "Профиль по умолчанию:\n"
        f"{format_profile(prof)}\n\n"
        "Изменить: /printer …",
        parse_mode="HTML",
    )


@router.message(Command("voice"))
async def cmd_voice(message: Message) -> None:
    from bot.services.google_cloud import RUSSIAN_TTS_VOICES, format_tts_voice_list
    from bot.services.user_prefs import (
        get_tts_voice,
        get_voice_reply,
        set_tts_voice,
        set_voice_reply,
    )

    user_id = message.from_user.id
    raw_arg = (message.text or "").replace("/voice", "", 1).strip()
    arg = raw_arg.lower()
    if arg in ("off", "0", "выкл", "нет"):
        await set_voice_reply(user_id, False)
        await message.answer("🔇 Ответ голосом выключен.")
        return
    if arg in ("on", "1", "вкл", "да"):
        await set_voice_reply(user_id, True)
        await message.answer(
            "🔊 Ответ голосом включён — после 🎤 и по запросу «ответь голосом»."
        )
        return
    if arg in ("list", "voices", "голоса", "список"):
        await message.answer(format_tts_voice_list(), parse_mode="HTML")
        return
    if arg.startswith("set ") or arg.startswith("голос "):
        name = raw_arg.split(maxsplit=1)[1].strip()
        known = {v[0] for v in RUSSIAN_TTS_VOICES}
        if name not in known:
            await message.answer(
                f"Неизвестный голос <code>{name}</code>.\n/voice list — список.",
                parse_mode="HTML",
            )
            return
        await set_tts_voice(user_id, name)
        await message.answer(f"🔊 Голос озвучки: <code>{name}</code>", parse_mode="HTML")
        return
    on = await get_voice_reply(user_id)
    cur_voice = await get_tts_voice(user_id)
    await message.answer(
        f"Ответ голосом: <b>{'вкл' if on else 'выкл'}</b>\n"
        f"Голос TTS: <code>{cur_voice}</code>\n\n"
        "<code>/voice on</code> · <code>/voice off</code>\n"
        "<code>/voice list</code> — все голоса\n"
        "<code>/voice set ru-RU-Chirp3-HD-Kore</code> — сменить голос",
        parse_mode="HTML",
    )


@router.message(Command("gcp"))
async def cmd_gcp(message: Message) -> None:
    from bot.config import GCP_PROJECT_ID, GCP_SPEECH_ENABLED, GCP_TTS_ENABLED
    from bot.services.google_cloud import (
        adc_available,
        check_gcp_all,
        gcp_services_overview,
        setup_hint,
    )

    adc = adc_available()
    lines = [
        gcp_services_overview(),
        "",
        f"ADC: {'✅ найден' if adc else '❌ нет'}",
        f"GCP_PROJECT_ID: <code>{GCP_PROJECT_ID or '—'}</code>",
        f"STT enabled: {'да' if GCP_SPEECH_ENABLED else 'нет'}",
        f"TTS enabled: {'да' if GCP_TTS_ENABLED else 'нет'}",
        "",
    ]
    for name, ok, detail in await check_gcp_all():
        lines.append(f"{'🟢' if ok else '🔴'} {name}: {detail}")
    if not adc:
        lines.extend(["", setup_hint()])
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    from bot.services.health import build_status_report
    from bot.services.model_catalog import model_label

    model = await history.get_model(message.from_user.id, DEFAULT_MODEL)
    label = model_label(model)
    report = await build_status_report(message.bot, message.from_user.id, label)
    await message.answer(report, parse_mode="HTML")


@router.message(Command("laozhang"))
async def cmd_laozhang(message: Message) -> None:
    from bot.services.laozhang_image import list_image_models_report

    try:
        report = await list_image_models_report()
    except Exception as e:
        report = f"Не удалось получить список: {e}"
    await message.answer(report, parse_mode="HTML")


@router.message(Command("printer"))
async def cmd_printer(message: Message) -> None:
    from bot.services.print_profile import format_profile, parse_print_profile

    user_id = message.from_user.id
    text = (message.text or "").replace("/printer", "", 1).strip()
    if text:
        from bot.services.print_profile import ensure_profile

        profile = ensure_profile(parse_print_profile(text))
        await history.set_print_profile(user_id, profile)
        await message.answer(
            "🖨 Профиль печати сохранён:\n\n"
            f"{format_profile(profile)}\n\n"
            "Теперь пришлите фото с подписью «сделай STL для печати»."
        )
        return
    profile = await history.get_print_profile(user_id)
    await message.answer(
        "🖨 <b>Профиль 3D-печати</b>\n\n"
        f"{format_profile(profile)}\n\n"
        "Чтобы изменить, отправьте:\n"
        "<code>/printer Bambu P2S, PETG, сопло 0.4, Bambu Studio</code>",
        parse_mode="HTML",
    )


@router.message(Command("project"))
async def cmd_project(message: Message) -> None:
    from bot.services.openscad import openscad_available

    user_id = message.from_user.id
    name = await history.get_project_name(user_id)
    ctx = await history.get_project_context(user_id)
    oscad = "установлен ✅" if openscad_available() else "не найден — ставьте с brew install openscad"
    if not ctx:
        await message.answer(
            "📦 Проектов пока нет.\n\n"
            "Отправьте HTML/описание и напишите:\n"
            "«сделай проект на печать на каждую деталь»\n\n"
            f"OpenSCAD на сервере: {oscad}",
            parse_mode=None,
        )
        return
    preview = ctx[:600] + ("…" if len(ctx) > 600 else "")
    await message.answer(
        f"📦 Последний проект: <b>{name or '—'}</b>\n\n"
        f"OpenSCAD: {oscad}\n\n"
        f"<pre>{preview}</pre>\n\n"
        "Чтобы продолжить — напишите «добавь деталь …» или «пересобери проект».",
        parse_mode="HTML",
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    from bot.services.pending_3d import clear_pending, clear_pending_concept
    from bot.services.telegram_net import telegram_retry

    user_id = message.from_user.id
    await history.clear_all_user_context(user_id, keep_settings=True)
    clear_pending(user_id)
    clear_pending_concept(user_id)
    await telegram_retry(
        "reset_answer",
        lambda: message.answer(
            "Полный сброс: история, проект, профиль принтера, незавершённые 3D-задачи "
            "и ожидающие концепты удалены.\n"
            "Модель нейросети (/model) сохранена."
        ),
    )
