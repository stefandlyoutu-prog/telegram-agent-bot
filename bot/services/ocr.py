"""Локальное распознавание текста на фото — дополнение к vision API."""

import asyncio
import io
import logging
import os
import shutil
from typing import Tuple

logger = logging.getLogger(__name__)

_reader = None


def _preprocess_for_ocr(img):
    from PIL import Image, ImageEnhance, ImageOps

    img = img.convert("RGB")
    w, h = img.size
    min_side = min(w, h)
    if min_side < 800:
        scale = 800 / min_side
        img = img.resize(
            (int(w * scale), int(h * scale)),
            Image.Resampling.LANCZOS,
        )
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.35)
    img = ImageEnhance.Sharpness(img).enhance(1.2)
    return img


def _numpy_available() -> bool:
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _ocr_easyocr(data: bytes) -> Tuple[str, float]:
    if not _numpy_available():
        raise RuntimeError("numpy недоступен")

    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import numpy as np
    from PIL import Image

    import easyocr

    global _reader
    if _reader is None:
        logger.info("Загрузка OCR (первый раз может занять 1–2 мин)…")
        _reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)

    img = _preprocess_for_ocr(Image.open(io.BytesIO(data)))
    arr = np.array(img)
    results = _reader.readtext(arr)

    lines = []
    confs = []
    for _box, text, conf in results:
        t = text.strip()
        if t and conf > 0.15:
            lines.append(t)
            confs.append(float(conf))

    text = "\n".join(lines)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    return text, avg_conf


def _ocr_tesseract(data: bytes) -> Tuple[str, float]:
    from PIL import Image
    import pytesseract

    img = _preprocess_for_ocr(Image.open(io.BytesIO(data)))
    text = pytesseract.image_to_string(img, lang="rus+eng")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text, 0.7 if text else 0.0


def _extract_sync(data: bytes) -> Tuple[str, float, str]:
    if shutil.which("tesseract"):
        try:
            text, conf = _ocr_tesseract(data)
            if text.strip():
                return text, conf, "tesseract"
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)

    if _numpy_available():
        try:
            text, conf = _ocr_easyocr(data)
            return text, conf, "easyocr"
        except Exception as e:
            logger.warning("EasyOCR failed: %s", e)

    return "", 0.0, "skip"


async def extract_text_from_image(data: bytes) -> Tuple[str, float, str]:
    """Текст с картинки, средняя уверенность, движок."""
    return await asyncio.to_thread(_extract_sync, data)
