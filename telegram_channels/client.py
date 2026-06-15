"""Telegram Bot API для управления каналами (@MOracul_bot — админ)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BOT_TOKEN = (
    os.getenv("CHANNEL_BOT_TOKEN", "").strip()
    or os.getenv("ORACLE_BOT_TOKEN", "").strip()
)


class ChannelBotError(Exception):
    pass


class ChannelBot:
    def __init__(self, token: str = "") -> None:
        self.token = token or BOT_TOKEN
        if not self.token:
            raise ChannelBotError("CHANNEL_BOT_TOKEN / ORACLE_BOT_TOKEN не задан")

    def _call(self, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = json.dumps(payload or {}).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.load(r)
        except urllib.error.HTTPError as e:
            raise ChannelBotError(e.read().decode()[:300]) from e
        if not body.get("ok"):
            raise ChannelBotError(body.get("description", str(body)))
        return body["result"]

    @staticmethod
    def normalize_username(username: str) -> str:
        u = username.strip().lstrip("@")
        u = u.replace("https://t.me/", "").split("/")[0].split("?")[0]
        return u

    def chat_id(self, username: str) -> str:
        return f"@{self.normalize_username(username)}"

    def get_me_id(self) -> int:
        return int(self._call("getMe")["id"])

    def get_chat(self, username: str) -> Dict[str, Any]:
        return self._call("getChat", {"chat_id": self.chat_id(username)})

    def admin_status(self, username: str) -> Dict[str, Any]:
        me = self.get_me_id()
        member = self._call(
            "getChatMember",
            {"chat_id": self.chat_id(username), "user_id": me},
        )
        status = member.get("status", "")
        is_admin = status in ("administrator", "creator")
        return {
            "status": status,
            "bot_admin": is_admin,
            "can_post": bool(member.get("can_post_messages", is_admin)),
            "can_edit": bool(member.get("can_change_info", is_admin)),
            "can_pin": bool(member.get("can_pin_messages", is_admin)),
        }

    def post(self, username: str, text: str, *, pin: bool = False) -> int:
        msg = self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id(username),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )
        mid = int(msg["message_id"])
        if pin:
            self._call(
                "pinChatMessage",
                {"chat_id": self.chat_id(username), "message_id": mid},
            )
        return mid

    def set_description(self, username: str, description: str) -> None:
        self._call(
            "setChatDescription",
            {"chat_id": self.chat_id(username), "description": description},
        )

    def list_admins(self, username: str) -> List[str]:
        try:
            rows = self._call("getChatAdministrators", {"chat_id": self.chat_id(username)})
            return [r["user"].get("username") or str(r["user"]["id"]) for r in rows]
        except ChannelBotError:
            return []
