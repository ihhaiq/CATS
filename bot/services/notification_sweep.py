"""
Periodic background sweep: for every active (non-FLED) cat, apply lazy decay,
check alert thresholds, and send a notification (with a fresh state image) if
a threshold was just crossed and hasn't already been notified within the
configured gap.
TODO (AGENT.md step 11) — this is the piece that ties everything else together:
  1. Loop all non-FLED cats in DB (paginate if the bot grows large).
  2. For each: decay_engine.apply_lazy_decay(cat).
  3. Determine current_state:
       "hungry"  if cat.hunger > settings.hunger_alert_threshold
       "sad"     if cat.happiness < settings.happiness_alert_threshold
       "love_low" if cat.love_bar is close to 0 (e.g. <= 15) and not yet fled
       else None
  4. If current_state and (current_state != cat.last_notified_state or
     enough time passed since last_notified_at per settings.notification_min_gap):
       - render image_renderer.render_cat(cat) for this exact state
       - send to cat.owner_id (and partner_id if set) via bot.send_photo
       - update cat.last_notified_state / last_notified_at
  5. If current_state is None, clear last_notified_state so a future re-trigger
     of the same condition notifies again.
  6. Also call flee_logic.check_flee(cat) here — if it just flipped to fled,
     send the "ran away" notification instead of a normal alert, skip steps 3-5.
  7. Run this on an interval (e.g. every 15-30 min) via APScheduler
     AsyncIOScheduler, started from main.py's on_startup.
"""
import asyncio
from datetime import datetime
from typing import Any

from aiogram import Bot
try:
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ModuleNotFoundError:
   AsyncIOScheduler = None

from bot.config import settings
from bot.services.local_store import (
   apply_decay,
   finish_sleep,
   get_active_cats,
   is_sleeping,
   update_cat,
)

_scheduler: Any = None
_fallback_task: asyncio.Task | None = None


async def _sweep(bot: Bot) -> None:
   for cat in await get_active_cats():
      woke = finish_sleep(cat)
      if woke:
         apply_decay(cat)
         cat["last_notified_state"] = None
      if is_sleeping(cat):
         await update_cat(cat)
         continue
      apply_decay(cat)
      state = None
      if cat["hunger"] >= settings.hunger_alert_threshold:
         state = "hungry"
      elif cat["happiness"] <= settings.happiness_alert_threshold:
         state = "sad"
      elif cat["love_bar"] <= 15:
         state = "love_low"
      last_at = cat.get("last_notified_at")
      enough_gap = not last_at or (datetime.utcnow() - datetime.fromisoformat(last_at)).total_seconds() >= settings.notification_min_gap
      if state and (state != cat.get("last_notified_state") or enough_gap):
         message = {
            "hungry": "🍖 قطتك جائعة وتحتاج إطعاماً.",
            "sad": "💔 قطتك حزينة وتحتاج اهتماماً.",
            "love_low": "🥺 قطتك تحتاج حباً ورعاية.",
         }[state]
         for user_id in {cat["owner_id"], cat.get("partner_id")} - {None}:
            try:
               await bot.send_message(user_id, message)
            except Exception:
               pass
         cat["last_notified_state"] = state
         cat["last_notified_at"] = datetime.utcnow().isoformat()
      elif state is None:
         cat["last_notified_state"] = None
      await update_cat(cat)


def start_notification_sweep(bot: Bot) -> None:
   global _scheduler, _fallback_task
   if AsyncIOScheduler is not None:
      _scheduler = AsyncIOScheduler()
      _scheduler.add_job(_sweep, "interval", minutes=settings.notification_interval_minutes, args=[bot])
      _scheduler.start()
      return

   async def fallback_loop() -> None:
      while True:
         await asyncio.sleep(settings.notification_interval_minutes * 60)
         await _sweep(bot)

   _fallback_task = asyncio.create_task(fallback_loop())
