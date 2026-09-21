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
from bot.services.media_runtime import resolve_cat_media
from bot.services.local_store import (
   apply_decay,
   collect_needs,
   finish_sleep,
   get_active_cats,
   get_cat_by_id,
   is_sleeping,
   notification_gap_seconds,
   sleep_ready_to_finish,
   update_cat,
   user_action_lock,
)

_scheduler: Any = None
_fallback_tasks: list[asyncio.Task] = []
_sweep_lock = asyncio.Lock()
logger = logging.getLogger("catibot.notification_sweep")

def _notification_visual_state(needs: list[str]) -> str:
   """Choose one visual state for a grouped needs notification."""
   priority = (
      ("starving", "hungry"),
      ("hungry", "hungry"),
      ("peckish", "hungry"),
      ("exhausted", "sick"),
      ("tired", "sick"),
      ("sleepy", "sick"),
      ("very_sad", "sick"),
      ("sad", "sick"),
      ("very_bored", "play"),
      ("bored", "play"),
      ("restless", "play"),
      ("walk_due", "walk"),
      ("attention_due", "talk"),
   )
   need_set = set(needs)
   for need, visual_state in priority:
      if need in need_set:
         return visual_state
   return "idle"


async def _send_need_notice(
   bot: Bot,
   cat: dict,
   user_id: int,
   message: str,
   needs: list[str],
   visual_state: str | None = None,
) -> None:
   """Send a notification with the best available cat asset."""
   visual_state = visual_state or _notification_visual_state(needs)
   try:
      resolved = await resolve_cat_media(
         bot,
         cat,
         visual_state,
         upload_chat_id=settings.media_cache_chat_id or user_id,
      )
      if resolved and resolved.media_type == "photo":
         await bot.send_photo(
            user_id,
            resolved.file_id,
            caption=message,
         )
         return
      if resolved and resolved.media_type == "video":
         await bot.send_video(
            user_id,
            resolved.file_id,
            caption=message,
         )
         return
   except Exception as exc:
      logger.warning(
         "Failed to resolve notification media user_id=%s: %s",
         user_id,
         exc,
      )
   await bot.send_message(user_id, message)


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

   recipients = {cat["owner_id"], cat.get("partner_id")} - {None}
   sent_to = {
      int(user_id)
      for user_id in cat.get("wake_notice_sent_to", [])
   }
   for user_id in recipients - sent_to:
      try:
         await bot.send_message(user_id, message)
         sent_to.add(user_id)
      except Exception as exc:
         logger.warning("Failed to send wake notice user_id=%s: %s", user_id, exc)

   if recipients.issubset(sent_to):
      cat.pop("wake_notice_pending", None)
      cat.pop("wake_notice_kind", None)
      cat.pop("wake_notice_at", None)
      cat.pop("wake_notice_sent_to", None)
      return True

   cat["wake_notice_sent_to"] = sorted(sent_to)
   return False


async def _send_fled_notice(bot: Bot, cat: dict) -> None:
   message = "💨 قطتك هربت بسبب الإهمال."
   for user_id in {cat["owner_id"], cat.get("partner_id")} - {None}:
      try:
         await _send_need_notice(
            bot,
            cat,
            user_id,
            message,
            [],
            visual_state="angry",
         )
      except Exception as exc:
         logger.warning("Failed to send flee notice user_id=%s: %s", user_id, exc)


async def _wake_sweep(bot: Bot) -> None:
   async with _sweep_lock:
      for snapshot in await get_active_cats():
         # The minute-level wake check should be almost free for awake cats.
         ready_to_wake = sleep_ready_to_finish(snapshot)
         pending = bool(snapshot.get("wake_notice_pending"))
         if not ready_to_wake and not pending:
            continue

         owner_id = int(snapshot["owner_id"])
         async with user_action_lock(owner_id):
            # Reload after acquiring the user lock so we never overwrite a
            # button/command interaction with an older sweep snapshot.
            cat = await get_cat_by_id(snapshot["cat_id"], include_fled=True)
            if cat is None:
               continue

            ready_to_wake = sleep_ready_to_finish(cat)
            pending = bool(cat.get("wake_notice_pending"))
            if not ready_to_wake and not pending:
               continue

            if ready_to_wake:
               apply_decay(cat)
               if cat.get("is_fled"):
                  await _send_fled_notice(bot, cat)
                  await update_cat(cat)
                  continue
               woke = finish_sleep(cat)
               if woke:
                  cat["last_notified_state"] = None
                  cat["last_notified_at"] = None
            await _send_wake_notice(bot, cat)
            await update_cat(cat)


async def _sweep(bot: Bot) -> None:
   async with _sweep_lock:
      for snapshot in await get_active_cats():
         owner_id = int(snapshot["owner_id"])
         async with user_action_lock(owner_id):
            cat = await get_cat_by_id(snapshot["cat_id"], include_fled=True)
            if cat is None:
               continue
            # Decay first while sleep interval metadata still exists, then finalize wake.
            apply_decay(cat)
            if cat.get("is_fled"):
               await _send_fled_notice(bot, cat)
               await update_cat(cat)
               continue
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
            urgent_set = {
               "love_critical",
               "trust_critical",
               "starving",
               "exhausted",
               "very_bored",
               "very_sad",
            }
            previous_needs = set((cat.get("last_notified_state") or "").split("|"))
            # A brand-new urgent need always breaks through immediately. Any
            # other change (mild need flipping in/out near a threshold) still
            # has to respect the gap, so the cat doesn't ping the owner every
            # few minutes while a stat oscillates around a boundary.
            new_urgent_need = bool((set(needs) & urgent_set) - previous_needs)

            if state and (enough_gap or new_urgent_need):
               top_needs = needs[:3]
               details = "\n".join(f"• {_NEED_MESSAGES[item]}" for item in top_needs)
               if len(needs) > len(top_needs):
                  details += f"\n• …وشوية أمور ثانية تحتاج وقتك."
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
                     await _send_need_notice(
                        bot,
                        cat,
                        user_id,
                        message,
                        needs,
                     )
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
   # Catch up immediately after a Railway restart if a sleep ended offline.
   asyncio.create_task(_wake_sweep(bot))
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
