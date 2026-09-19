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
_fallback_task: asyncio.Task | None = None
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


async def _sweep(bot: Bot) -> None:
   for cat in await get_active_cats():
      # Decay first while sleep interval metadata still exists, then finalize wake.
      apply_decay(cat)
      woke = finish_sleep(cat)
      if woke:
         cat["last_notified_state"] = None
         cat["last_notified_at"] = None

      if is_sleeping(cat):
         await update_cat(cat)
         continue

      needs = collect_needs(cat)
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
   global _scheduler, _fallback_task
   if AsyncIOScheduler is not None:
      _scheduler = AsyncIOScheduler()
      _scheduler.add_job(
         _sweep,
         "interval",
         minutes=settings.notification_interval_minutes,
         args=[bot],
      )
      _scheduler.start()
      return

   async def fallback_loop() -> None:
      while True:
         await asyncio.sleep(settings.notification_interval_minutes * 60)
         try:
            await _sweep(bot)
         except asyncio.CancelledError:
            raise
         except Exception:
            logger.exception("Notification sweep failed")

   _fallback_task = asyncio.create_task(fallback_loop())
