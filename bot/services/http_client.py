"""Общий aiohttp-клиент: KupiAPI через LLM_PROXY с fallback на прямое соединение."""

from typing import Any, Dict, Optional, Tuple

import aiohttp
from aiohttp import ClientError, ClientConnectorError

from bot.config import LLM_PROXY


def proxy_for_request(use_proxy: bool) -> Optional[str]:
    if not use_proxy or not LLM_PROXY:
        return None
    if str(LLM_PROXY).startswith(("socks4", "socks5")):
        return None
    return LLM_PROXY


def session_kwargs(use_proxy: bool) -> Dict[str, Any]:
    if not use_proxy or not LLM_PROXY:
        return {}
    if str(LLM_PROXY).startswith(("socks4", "socks5")):
        from aiohttp_socks import ProxyConnector

        return {"connector": ProxyConnector.from_url(LLM_PROXY, rdns=True)}
    return {}


def llm_connection_modes() -> Tuple[bool, ...]:
    """Если LLM_PROXY задан — сначала через прокси, затем напрямую как fallback."""
    if LLM_PROXY:
        return (True, False)
    return (False,)


def format_client_error(exc: Exception) -> str:
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}" + (f" ({exc.args[0]})" if exc.args else "")
