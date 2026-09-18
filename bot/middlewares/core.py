"""
Cross-cutting concerns, applied once instead of repeated in every handler.

  * DependenciesMiddleware — hands each handler its repo/service/settings plus
    the already-loaded UserData, so no handler builds its own session.
  * ThrottleMiddleware — a tiny per-user token gate. Button mashing on an
    inline keyboard is the normal failure mode for this kind of bot; without it
    a double-tap can double-award points.
  * LoggingMiddleware — one structured line per update, which is what makes
    production issues diagnosable at all.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from bot.config import Settings
from bot.core import texts
from bot.services.cat_service import CatService
from bot.storage.base import Repository

logger = logging.getLogger("catibot.mw")

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings
        self.service = CatService(repo, settings)

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        data["repo"] = self.repo
        data["settings"] = self.settings
        data["service"] = self.service

        tg_user = data.get("event_from_user")
        if tg_user is not None:
            data["user"] = await self.repo.get_or_create_user(
                tg_user.id,
                username=tg_user.username,
                is_guest=self.settings.is_guest_storage,
            )
            data["is_admin"] = self.settings.is_admin(tg_user.id)
            data["is_guest_mode"] = self.settings.is_guest_storage
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, min_interval: float = 0.7) -> None:
        self.min_interval = min_interval
        self._last: dict[int, float] = defaultdict(float)

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        now_ts = time.monotonic()
        if now_ts - self._last[tg_user.id] < self.min_interval:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.THROTTLED, show_alert=False)
            elif isinstance(event, Message):
                pass  # silently drop: replying would just add to the spam
            return None
        self._last[tg_user.id] = now_ts
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        started = time.monotonic()
        label = "update"
        if isinstance(event, Update):
            if event.message:
                label = f"msg:{(event.message.text or '')[:32]}"
            elif event.callback_query:
                label = f"cb:{event.callback_query.data}"
        try:
            return await handler(event, data)
        finally:
            elapsed = (time.monotonic() - started) * 1000
            user = data.get("event_from_user")
            logger.info("%s uid=%s %.0fms", label, getattr(user, "id", "-"), elapsed)
