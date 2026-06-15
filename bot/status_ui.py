import asyncio
import html
import time
from typing import Optional

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from aiogram.enums import ChatAction
from aiogram.types import Message


class StatusIndicator:
    """Сообщение-индикатор: 🟢 свободен / 🟡 обрабатывает / 🔴 ошибка."""

    def __init__(self, message: Message) -> None:
        self.message = message
        self._msg: Optional[Message] = None
        self._anim: Optional[asyncio.Task] = None
        self._progress_detail: str = ""
        self._progress_started: float = 0.0
        self._progress_eta: int = 0

    async def _safe_send_or_edit(self, text: str, *, parse_mode: Optional[str] = "HTML") -> None:
        """Отправка/редактирование статуса без падения обработчика."""
        try:
            if self._msg:
                await self._msg.edit_text(text, parse_mode=parse_mode)
            else:
                self._msg = await self.message.answer(text, parse_mode=parse_mode)
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(int(e.retry_after) + 1, 60))
            try:
                if self._msg:
                    await self._msg.edit_text(text, parse_mode=parse_mode)
                else:
                    self._msg = await self.message.answer(text, parse_mode=parse_mode)
            except Exception:
                pass
        except TelegramBadRequest:
            plain = html.unescape(text)
            plain = plain.replace("<b>", "").replace("</b>", "")
            plain = plain.replace("<i>", "").replace("</i>", "")
            plain = plain.replace("<pre>", "").replace("</pre>", "")
            try:
                if self._msg:
                    await self._msg.edit_text(plain, parse_mode=None)
                else:
                    self._msg = await self.message.answer(plain, parse_mode=None)
            except Exception:
                pass
        except Exception:
            pass

    async def show(self, icon: str, title: str, detail: str = "") -> None:
        safe_title = html.escape(title)
        text = f"{icon} <b>{safe_title}</b>"
        if detail:
            text += f"\n<i>{html.escape(detail)}</i>"
        try:
            await self.message.bot.send_chat_action(
                self.message.chat.id, ChatAction.TYPING
            )
        except Exception:
            pass
        await self._safe_send_or_edit(text, parse_mode="HTML")

    def start_progress(self, detail: str, *, eta_seconds: int = 45) -> None:
        self.stop_progress()
        self._progress_detail = detail
        self._progress_started = time.monotonic()
        self._progress_eta = eta_seconds

        async def _loop() -> None:
            while True:
                elapsed = int(time.monotonic() - self._progress_started)
                remaining = max(0, self._progress_eta - elapsed)
                line = f"{self._progress_detail} · прошло {elapsed} сек"
                if remaining:
                    line += f" · осталось ~{max(5, remaining)} сек"
                try:
                    await self.show("🟡", "Обрабатываю", line)
                except Exception:
                    pass
                await asyncio.sleep(8)

        self._anim = asyncio.create_task(_loop())

    def stop_progress(self) -> None:
        if self._anim and not self._anim.done():
            self._anim.cancel()
        self._anim = None

    async def viewing_image(self) -> None:
        await self.show("🟡", "Обрабатываю", "Смотрю изображение…")

    async def reading_file(self, filename: str) -> None:
        await self.show("🟡", "Обрабатываю", f"Скачиваю и читаю файл «{filename}»…")

    async def extracting(self, filename: str) -> None:
        await self.show("🟡", "Обрабатываю", f"Извлекаю текст из «{filename}»…")

    async def thinking(self, model_label: str, eta_seconds: Optional[int] = None) -> None:
        self.stop_progress()
        detail = f"Думаю · {model_label}"
        if eta_seconds:
            detail += f" · осталось ~{max(5, eta_seconds)} сек"
        await self.show("🟡", "Обрабатываю", detail)
        self._start_dots(model_label, eta_seconds=eta_seconds)

    def _start_dots(self, model_label: str, eta_seconds: Optional[int] = None) -> None:
        if self._anim and not self._anim.done():
            self._anim.cancel()

        async def _loop() -> None:
            frames = ["", ".", "..", "..."]
            i = 0
            remaining = eta_seconds
            while True:
                dots = frames[i % len(frames)]
                try:
                    if self._msg:
                        eta = ""
                        if remaining:
                            eta = f" · осталось ~{max(5, remaining)} сек"
                        await self._safe_send_or_edit(
                            f"🟡 <b>Обрабатываю</b>\n"
                            f"<i>{html.escape(f'Думаю{dots} · {model_label}{eta}')}</i>",
                            parse_mode="HTML",
                        )
                except Exception:
                    pass
                i += 1
                if remaining:
                    remaining = max(5, remaining - 7)
                await asyncio.sleep(7)

        self._anim = asyncio.create_task(_loop())

    async def done(self) -> None:
        self.stop_progress()
        if self._msg:
            try:
                await self._msg.delete()
            except Exception:
                pass
            self._msg = None

    async def error(self, text: str) -> None:
        self.stop_progress()
        safe = html.escape(str(text)[:1200])
        err_text = f"🔴 <b>Не работает</b>\n<i>{safe}</i>"
        await self._safe_send_or_edit(err_text, parse_mode="HTML")
