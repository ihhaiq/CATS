"""Periodic maintenance and notification sweep for the active JSON runtime."""
import asyncio
import logging
from datetime import datetime
from typing import Any

from aiogram import Bot

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ModuleNotFoundError:
    AsyncIOScheduler = None

from bot.config import settings
from bot.services.action_locks import user_action_lock
from bot.services.local_store import (
    get_active_cats,
    is_sleeping,
    refresh_cat_state,
    update_cat,
)

logger = logging.getLogger("catibot.notifications")
_scheduler: Any = None
_fallback_task: asyncio.Task | None = None


async def _process_cat(bot: Bot, cat: dict) -> None:
    async with user_action_lock(cat["owner_id"]):
        woke = refresh_cat_state(cat)
        if woke:
            cat["last_notified_state"] = None
            cat["last_notified_at"] = None

        if is_sleeping(cat):
            await update_cat(cat)
            return

        state = None
        if cat["hunger"] >= settings.hunger_alert_threshold:
            state = "hungry"
        elif cat["happiness"] <= settings.happiness_alert_threshold:
            state = "sad"
        elif cat["love_bar"] <= 15:
            state = "love_low"

        last_at = cat.get("last_notified_at")
        enough_gap = (
            not last_at
            or (datetime.utcnow() - datetime.fromisoformat(last_at)).total_seconds()
            >= settings.notification_min_gap
        )

        if state and (state != cat.get("last_notified_state") or enough_gap):
            message = {
                "hungry": "🍖 قطتك جائعة وتحتاج إطعاماً.",
                "sad": "💔 قطتك حزينة وتحتاج اهتماماً.",
                "love_low": "🥺 قطتك تحتاج حباً ورعاية.",
            }[state]

            delivered = False
            for user_id in {cat["owner_id"], cat.get("partner_id")} - {None}:
                try:
                    await bot.send_message(user_id, message)
                    delivered = True
                except Exception as exc:
                    logger.warning(
                        "failed to notify user=%s cat_id=%s: %s",
                        user_id,
                        cat.get("cat_id"),
                        exc,
                    )

            # Don't suppress future retries if nobody received the notification.
            if delivered:
                cat["last_notified_state"] = state
                cat["last_notified_at"] = datetime.utcnow().isoformat()
        elif state is None:
            cat["last_notified_state"] = None
            cat["last_notified_at"] = None

        await update_cat(cat)


async def _sweep(bot: Bot) -> None:
    for cat in await get_active_cats():
        try:
            await _process_cat(bot, cat)
        except Exception:
            # One malformed cat must not abort maintenance for every other cat.
            logger.exception("notification sweep failed for cat_id=%s", cat.get("cat_id"))


def start_notification_sweep(bot: Bot) -> None:
    global _scheduler, _fallback_task

    if _scheduler is not None and getattr(_scheduler, "running", False):
        return
    if _fallback_task is not None and not _fallback_task.done():
        return

    if AsyncIOScheduler is not None:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            _sweep,
            "interval",
            minutes=max(1, settings.notification_interval_minutes),
            args=[bot],
            max_instances=1,
            coalesce=True,
        )
        _scheduler.start()
        return

    async def fallback_loop() -> None:
        while True:
            await asyncio.sleep(max(1, settings.notification_interval_minutes) * 60)
            await _sweep(bot)

    _fallback_task = asyncio.create_task(
        fallback_loop(),
        name="cat-notification-sweep",
    )


async def stop_notification_sweep() -> None:
    global _scheduler, _fallback_task

    if _scheduler is not None:
        if getattr(_scheduler, "running", False):
            _scheduler.shutdown(wait=False)
        _scheduler = None

    if _fallback_task is not None:
        task = _fallback_task
        _fallback_task = None
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
