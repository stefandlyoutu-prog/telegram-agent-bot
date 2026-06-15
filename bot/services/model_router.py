"""Выбор модели по capability."""

import os
from typing import Optional

from bot.config import DEFAULT_MODEL, VISION_MODEL

_CAPABILITY_ENV = {
    "engineering_json": "MODEL_ENGINEERING",
    "seo_copy": "MODEL_SEO",
    "file_doc": "MODEL_FILE_DOC",
    "file_xlsx": "MODEL_FILE_XLSX",
    "stl_spec": "MODEL_STL_SPEC",
    "avito_copy": "MODEL_AVITO",
    "chat": "MODEL_CHAT",
    "complex_chat": "MODEL_COMPLEX",
    "code": "MODEL_CODE",
    "vision": "MODEL_VISION",
    "self_check": "MODEL_SELF_CHECK",
}

_DEFAULTS = {
    "engineering_json": "gpt-5.4",
    "seo_copy": "claude-haiku-4.5",
    "file_doc": "gpt-5.4-mini",
    "file_xlsx": "gpt-5.4-mini",
    "stl_spec": "gpt-5.4",
    "avito_copy": "claude-haiku-4.5",
    "chat": DEFAULT_MODEL,
    "complex_chat": "gpt-5.5",
    "code": "gpt-5.5-codex",
    "vision": VISION_MODEL,
    "self_check": "gpt-5.4-mini",
}


def model_for_capability(capability: str, user_model: Optional[str] = None) -> str:
    if capability == "chat":
        return user_model or os.getenv("MODEL_CHAT", DEFAULT_MODEL)
    if capability == "meshy":
        return user_model or DEFAULT_MODEL
    env_key = _CAPABILITY_ENV.get(capability)
    default = _DEFAULTS.get(capability, DEFAULT_MODEL)
    if env_key:
        return os.getenv(env_key, default).strip() or default
    return default
