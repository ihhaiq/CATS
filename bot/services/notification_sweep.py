"""Periodic coupled-needs notification sweep."""
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
from bot.services.local_store import (
   apply_decay,
   collect_needs,
   finish_sleep,
   get_active_cats,
   is_sleeping,
   notification_gap_seconds,
   update_cat,
)

_scheduler: Any = None
_fallback_tasks: list[asyncio.Task] = []
_sweep_lock = asyncio.Lock()
logger = logging.getLogger("catibot.notification_sweep")

_NEED_MESSAGES = {
   "love_critical": "💔 حبها ورابطتها وياك صارت بحالة حرجة وتحتاج اهتمام حقيقي.",
   "love_low": "🥺 حست بالإهمال وحبها إلك بدأ ينزل.",
   "trust_critical": "🧊 ثقتها بيك صارت ضعيفة جداً؛ تحتاج رعاية ثابتة وبدون إزعاج.",
   "trust_low": "🤝 ثقتها بيك نازلة وتحتاج تعامل ثابت وهادئ.",
   "starving": "🚨🍖 جوعها صار شديد جداً، أطعمها بأقرب وقت.",
   "hungry": "🍗 قطتك جائعة وتدور على أكل.",
   "peckish": "🥣 بدت تجوع شوي، قريب راح تحتاج أكل.",
   "exhausted": "🪫 قطتك منهكة جداً وتحتاج نوم طويل.",
   "tired": "😴 تعبت وتحتاج ترتاح وتنام.",
   "sleepy": "🥱 بدت تنعس؛ طاقتها قاعدة تنزل.",
   "walk_due": "🌿 ضاقت من القعدة وتحتاج نزهة وتغيير جو.",
   "attention_due": "💭 قطتك مشتاقتلك وتريد تحچي أو تلعب وياك.",
   "very_bored": "🙀 الملل عندها صار شديد؛ تريد لعب أو حديث وتغيير بالروتين.",
   "bored": "🌀 قطتك حست بالملل وتريد تسوي شي وياك.",
   "restless": "😼 بدت تمل وتدور شي يشغلها.",
   "very_sad": "💔😿 حزينة جداً وحالتها النفسية نازلة.",
   "sad": "😿 مزاجها مو زين وتحتاج اهتمام.",
}


async def _send_wake_notice(bot: Bot, cat: dict) -> bool:
   if not cat.get("wake_notice_pending"):
      return False

   kind = cat.get("wake_notice_kind")
   if kind == "nap":
      message = "استيقظت قطتك 🐈\n💤 خلصت قيلولتها وصحت من نفسها."
   else:
      message = "استيقظت قطتك 🐈\n😺 شبعت نوم وصحت من نفسها."

   sent = False
   for user_id in {cat["owner_id"], cat.get("partner_id")} - {None}:
      try:
         await bot.send_message(user_id, message)
         sent = True
      except Exception as exc:
         logger.warning("Failed to send wake notice user_id=%s: %s", user_id, exc)

   # A wake event is delivered at most once. If Telegram failed for every
   # recipient, keep it pending so the next sweep can retry.
   if sent:
      cat.pop("wake_notice_pending", None)
      cat.pop("wake_notice_kind", None)
      cat.pop("wake_notice_at", None)
   return sent


async def _wake_sweep(bot: Bot) -> None:
   async with _sweep_lock:
      for cat in await get_active_cats():
         apply_decay(cat)
         finish_sleep(cat)
         await _send_wake_notice(bot, cat)
         await update_cat(cat)


async def _sweep(bot: Bot) -> None:
   async with _sweep_lock:
      for cat in await get_active_cats():
         # Decay first while sleep interval metadata still exists, then finalize wake.
         apply_decay(cat)
         woke = finish_sleep(cat)
         if woke:
            cat["last_notified_state"] = None
            cat["last_notified_at"] = None
         await _send_wake_notice(bot, cat)

         sleeping = is_sleeping(cat)
         needs = collect_needs(cat)
         if sleeping:
            # Sleeping suppresses routine activity reminders, not emergencies.
            needs = [
               item
               for item in needs
               if item in {"starving", "love_critical", "trust_critical"}
            ]
            if not needs:
               await update_cat(cat)
               continue
         state = "|".join(needs) if needs else None
         last_at = cat.get("last_notified_at")
         gap = notification_gap_seconds(needs)
         enough_gap = (
            not last_at
            or (datetime.utcnow() - datetime.fromisoformat(last_at)).total_seconds()
            >= gap
         )

         if state and (state != cat.get("last_notified_state") or enough_gap):
            details = "\n".join(f"• {_NEED_MESSAGES[item]}" for item in needs)
            urgent = any(
               item in {
                  "love_critical",
                  "trust_critical",
                  "starving",
                  "exhausted",
                  "very_bored",
                  "very_sad",
               }
               for item in needs
            )
            header = "🚨 قطتك تحتاجك هسه:" if urgent else "🐾 تحديث حالة قطتك:"
            message = f"{header}\n{details}"
            for user_id in {cat["owner_id"], cat.get("partner_id")} - {None}:
               try:
                  await bot.send_message(user_id, message)
               except Exception as exc:
                  logger.warning("Failed to notify user_id=%s: %s", user_id, exc)
            cat["last_notified_state"] = state
            cat["last_notified_at"] = datetime.utcnow().isoformat()
         elif state is None:
            cat["last_notified_state"] = None
            cat["last_notified_at"] = None

         await update_cat(cat)


def start_notification_sweep(bot: Bot) -> None:
   global _scheduler, _fallback_tasks
   if AsyncIOScheduler is not None:
      _scheduler = AsyncIOScheduler()
      _scheduler.add_job(
         _wake_sweep,
         "interval",
         minutes=settings.wake_check_interval_minutes,
         args=[bot],
         max_instances=1,
         coalesce=True,
      )
      _scheduler.add_job(
         _sweep,
         "interval",
         minutes=settings.notification_interval_minutes,
         args=[bot],
         max_instances=1,
         coalesce=True,
      )
      _scheduler.start()
      return

   async def wake_loop() -> None:
      while True:
         await asyncio.sleep(settings.wake_check_interval_minutes * 60)
         try:
            await _wake_sweep(bot)
         except asyncio.CancelledError:
            raise
         except Exception:
            logger.exception("Wake sweep failed")

   async def needs_loop() -> None:
      while True:
         await asyncio.sleep(settings.notification_interval_minutes * 60)
         try:
            await _sweep(bot)
         except asyncio.CancelledError:
            raise
         except Exception:
            logger.exception("Notification sweep failed")

   _fallback_tasks = [
      asyncio.create_task(wake_loop()),
      asyncio.create_task(needs_loop()),
   ]
