"""Batch content factory: бриф → N вертикальных роликов с озвучкой и текстом на экране."""

from __future__ import annotations

import hashlib
import math
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from video_bot.generate import FPS, H, W, _draw_centered_text, _font

FFMPEG = None  # lazy: imageio_ffmpeg


def _ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        import imageio_ffmpeg

        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return FFMPEG


@dataclass
class Slide:
    on_screen: str
    voice: str


def synthesize_speech_mac(text: str, out_mp3: Path, voice: str = "Milena") -> Path:
    """macOS say → AIFF → MP3."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    aiff = out_mp3.with_suffix(".aiff")
    clean = text.replace('"', "'").strip()
    subprocess.run(
        ["say", "-v", voice, "-o", str(aiff), clean],
        check=True,
    )
    subprocess.run(
        [_ffmpeg(), "-y", "-i", str(aiff), "-ac", "1", "-ar", "44100", str(out_mp3)],
        check=True,
        capture_output=True,
    )
    aiff.unlink(missing_ok=True)
    return out_mp3


def _audio_duration_sec(path: Path) -> float:
    r = subprocess.run(
        [
            _ffmpeg(),
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    for line in (r.stderr or "").splitlines():
        if "Duration:" in line:
            part = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = part.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 3.0


def concat_audio(parts: Sequence[Path], out_mp3: Path, gap_sec: float = 0.35) -> Path:
    """Склеить MP3 с паузами между слайдами."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_mp3.with_suffix(".txt")
    lines: list[str] = []
    for i, p in enumerate(parts):
        lines.append(f"file '{p.resolve()}'")
        if i + 1 < len(parts) and gap_sec > 0:
            silence = out_mp3.parent / f"_gap_{i}.mp3"
            subprocess.run(
                [
                    _ffmpeg(),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-t",
                    str(gap_sec),
                    "-q:a",
                    "9",
                    str(silence),
                ],
                check=True,
                capture_output=True,
            )
            lines.append(f"file '{silence.resolve()}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_mp3),
        ],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    for i in range(len(parts)):
        (out_mp3.parent / f"_gap_{i}.mp3").unlink(missing_ok=True)
    return out_mp3


def _gradient_bg_seed(frame_i: int, total: int, seed: int) -> tuple[int, int, int]:
    t = frame_i / max(1, total)
    h = int(hashlib.md5(str(seed).encode()).hexdigest()[:6], 16)
    r0, g0, b0 = (h >> 16) & 255, (h >> 8) & 255, h & 255
    r = int(r0 * 0.15 + 40 * math.sin(t * math.pi) + 20)
    g = int(g0 * 0.12 + 35 * math.cos(t * math.pi * 0.6))
    b = int(b0 * 0.2 + 55 + 40 * t)
    return (min(255, r), min(255, g), min(255, b))


def build_slideshow_video(
    slides: Sequence[str],
    durations_sec: Sequence[float],
    out_path: Path,
    *,
    theme_seed: int = 0,
    subtitle: str = "",
) -> Path:
    import numpy as np
    from PIL import Image, ImageDraw
    import imageio

    if len(slides) != len(durations_sec):
        raise ValueError("slides and durations_sec length mismatch")
    title_font = _font(58)
    body_font = _font(46)
    sub_font = _font(34)
    frames: list = []
    total_frames = sum(int(d * FPS) for d in durations_sec)
    fi = 0
    for slide, dur in zip(slides, durations_sec):
        wrapped = textwrap.wrap(slide, width=22) or [slide]
        chunk = max(1, int(dur * FPS))
        for _ in range(chunk):
            img = Image.new("RGB", (W, H), _gradient_bg_seed(fi, total_frames, theme_seed))
            draw = ImageDraw.Draw(img)
            if subtitle:
                _draw_centered_text(draw, subtitle[:50], 90, sub_font, fill=(255, 210, 80))
            start_y = H // 2 - len(wrapped) * 30
            for j, wl in enumerate(wrapped[:10]):
                _draw_centered_text(draw, wl, start_y + j * 58, body_font)
            frames.append(np.array(img))
            fi += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(out_path), frames, fps=FPS, codec="libx264", quality=8)
    return out_path


def mux_video_audio(video: Path, audio: Path, out: Path, min_duration_sec: float = 0) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    if min_duration_sec > 0:
        dur = _audio_duration_sec(out)
        if dur < min_duration_sec:
            padded = out.with_suffix(".pad.mp4")
            subprocess.run(
                [
                    _ffmpeg(),
                    "-y",
                    "-i",
                    str(out),
                    "-vf",
                    f"tpad=stop_mode=clone:stop_duration={min_duration_sec - dur:.2f}",
                    "-af",
                    f"apad=pad_dur={min_duration_sec - dur:.2f}",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    str(padded),
                ],
                check=True,
                capture_output=True,
            )
            padded.replace(out)
    return out


def build_video_with_voiceover(
    slide_defs: Sequence[Slide],
    out_path: Path,
    *,
    theme_seed: int = 0,
    subtitle: str = "",
    work_dir: Path | None = None,
    min_duration_sec: float = 0,
    style: str = "faceless",
) -> Path:
    """Ролик с озвучкой. style=faceless — B-roll + kinetic captions (контент-ферма)."""
    if style == "faceless":
        import asyncio

        from video_bot.content_product.assembler import build_product_video
        from video_bot.content_product.script_engine import _fallback_earn_2026

        script = _fallback_earn_2026()
        if slide_defs and len(slide_defs) != len(script.scenes):
            for i, sd in enumerate(slide_defs[: len(script.scenes)]):
                sc = script.scenes[i]
                parts = [p for p in sd.on_screen.replace("\n", " ").split() if p]
                sc.caption_lines = [
                    " ".join(parts[: max(1, len(parts) // 2)]),
                    " ".join(parts[max(1, len(parts) // 2) :]),
                ][:2] or sc.caption_lines
                sc.voice = sd.voice or sd.on_screen
        return asyncio.run(
            build_product_video(
                script,
                out_path,
                work_dir=work_dir,
                min_duration_sec=min_duration_sec or 55.0,
            )
        )
    # legacy slideshow
    from video_bot.tts import synthesize_speech

    wd = work_dir or out_path.parent / "_tmp"
    wd.mkdir(parents=True, exist_ok=True)
    audio_parts: list[Path] = []
    durations: list[float] = []
    for i, sd in enumerate(slide_defs):
        mp3 = wd / f"slide_{i}.mp3"
        synthesize_speech(sd.voice or sd.on_screen, mp3)
        audio_parts.append(mp3)
        durations.append(max(2.5, _audio_duration_sec(mp3) + 0.2))
    full_audio = wd / "full.mp3"
    concat_audio(audio_parts, full_audio)
    silent = wd / "silent.mp4"
    build_slideshow_video(
        [s.on_screen for s in slide_defs],
        durations,
        silent,
        theme_seed=theme_seed,
        subtitle=subtitle,
    )
    mux_video_audio(silent, full_audio, out_path, min_duration_sec=min_duration_sec)
    return out_path


# --- Варианты из одного брифа (50+) ---

_HOOKS = [
    "Заработок в интернете без вложений",
    "Как монетизировать телефон в 2026",
    "5 способов заработать онлайн",
    "Деньги с TikTok и YouTube",
    "Партнёрки которые платят в РФ",
]

_CTA = [
    "Открой @M_onetest_bot",
    "Старт: t.me/M_onetest_bot",
    "Жми /start в @M_onetest_bot",
]


def brief_to_slide_sets(brief: str, count: int = 50) -> list[list[Slide]]:
    """Разбить бриф на N наборов слайдов (хуки + ядро + CTA)."""
    core_lines = [ln.strip() for ln in brief.splitlines() if ln.strip()]
    if not core_lines:
        core_lines = [
            "TikTok и YouTube — оплата за просмотры",
            "Авито — лиды и процент со сделки",
            "Партнёрки Яндекс, Ozon, банки",
            "Готовые материалы в боте",
            "Рефералка и бонусы за серии",
            "AI-агент и 3D на заказ",
            "Вывод от 5000 рублей",
        ]
    sets: list[list[Slide]] = []
    for n in range(count):
        hook = _HOOKS[n % len(_HOOKS)]
        cta = _CTA[n % len(_CTA)]
        slides: list[Slide] = [
            Slide(on_screen=hook, voice=hook),
        ]
        for j, line in enumerate(core_lines):
            variant = line
            if n % 3 == 1 and j == 0:
                variant = f"💰 {line}"
            elif n % 3 == 2 and j == 0:
                variant = line.upper()[:40] if len(line) > 10 else line
            slides.append(Slide(on_screen=variant[:80], voice=line))
        slides.append(Slide(on_screen=cta, voice=cta.replace("@", "")))
        sets.append(slides)
    return sets


def build_batch_from_brief(
    brief: str,
    out_dir: Path,
    *,
    count: int = 50,
    max_workers: int = 1,
) -> list[Path]:
    """Конвейер: один бриф → count MP4 в out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sets = brief_to_slide_sets(brief, count)
    results: list[Path] = []
    for i, slide_set in enumerate(sets):
        out = out_dir / f"batch_{i+1:03d}.mp4"
        build_video_with_voiceover(
            slide_set,
            out,
            theme_seed=i * 17 + 3,
            subtitle="M · Центр доходов",
            work_dir=out_dir / f"_tmp_{i+1}",
        )
        results.append(out)
    return results


PROMO_EARN_2026: list[Slide] = [
    Slide(
        "Как зарабатывать\nв интернете в 2026?",
        "Как реально зарабатывать в интернете в две тысячи двадцать шестом году?",
    ),
    Slide(
        "@M_onetest_bot\nЦентр онлайн-дохода",
        "Всё собрано в одном боте — эм онтест в телеграм. Центр вашего онлайн-дохода.",
    ),
    Slide(
        "TikTok · YouTube · VK\nПлата за просмотры",
        "ТикТок, Ютуб и ВКонтакте — платят за просмотры. Берёшь задание, снимаешь, получаешь деньги.",
    ),
    Slide(
        "Авито\nЛиды и % со сделки",
        "Авито — размещаешь объявления, получаешь лиды и процент с каждой сделки.",
    ),
    Slide(
        "Свои каналы\nПосты и охваты",
        "Ведёшь свои каналы — оплата за посты и реальный охват аудитории.",
    ),
    Slide(
        "Партнёрки\nЯндекс · Ozon · банки",
        "Партнёрки Яндекса, Озона, банков и страховок — рекомендуешь и зарабатываешь.",
    ),
    Slide(
        "Материалы в боте\nБери и публикуй",
        "Готовые материалы уже внутри — бери и публикуй, не трать часы на подготовку.",
    ),
    Slide(
        "Бонусы\nРефералка · серии · топ",
        "Рефералка, бонусы за серии заданий и топ недели — доход растёт быстрее.",
    ),
    Slide(
        "AI-агент с Mac\nВидео · код · файлы",
        "ИИ-агент с твоего Мака — видео, код, файлы. Полный цифровой помощник.",
    ),
    Slide(
        "3D-печать\nМодели на заказ",
        "Три Д печать и модели на заказ — в экосистеме бота Мо Розов.",
    ),
    Slide(
        "Вывод от 5000 ₽\nПосле проверки",
        "Вывод от пяти тысяч рублей — после быстрой проверки, без лишней бюрократии.",
    ),
    Slide(
        "Начни сейчас\nt.me/M_onetest_bot",
        "Начни прямо сейчас. Открой телеграм — эм онтест бот. Ссылка в описании.",
    ),
]
