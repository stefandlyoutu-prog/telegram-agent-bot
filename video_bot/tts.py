"""Озвучка edge-tts (нейросеть Microsoft) — качество выше macOS say."""

from __future__ import annotations

import asyncio
from pathlib import Path

DEFAULT_VOICE = "ru-RU-DmitryNeural"  # мужской, живой тон для finance/shorts
ALT_VOICE = "ru-RU-SvetlanaNeural"


def synthesize_speech(
    text: str,
    out_mp3: Path,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = "+5%",
    pitch: str = "+0Hz",
) -> Path:
    """Синтез речи → MP3."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        import edge_tts

        comm = edge_tts.Communicate(text.strip(), voice, rate=rate, pitch=pitch)
        await comm.save(str(out_mp3))

    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _run()).result()
    except RuntimeError:
        asyncio.run(_run())
    return out_mp3
