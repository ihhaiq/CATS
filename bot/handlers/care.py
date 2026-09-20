"""/feed, /play, /walk and /talk care actions."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from datetime import datetime

from bot.config import settings
from bot.services.economy import check_cooldown
from bot.services.local_store import (
  action_block_reason,
  apply_care_effects,
  apply_decay,
  apply_light_interaction,
  award_points,
  can_bypass_action_cooldown,
  care_reward_points,
  ensure_user,
  finish_sleep,
  fullness_percent,
  get_latest_cat_for_user,
  get_user_cat,
  get_user_points,
  is_sleeping,
  mark_fled_if_needed,
  parse_time,
  sleep_duration_text,
  sleep_need_percent,
  sleep_remaining_minutes,
  update_cat,
  user_action_lock,
)

router = Router(name="care")


@router.message(Command("feed", "اطعام", "إطعام"))
async def cmd_feed(message: Message) -> None:
  await _care(message, "feed")


@router.message(Command("play", "لعب"))
async def cmd_play(message: Message) -> None:
  await _care(message, "play")


@router.message(Command("walk", "نزهة", "نزه"))
async def cmd_walk(message: Message) -> None:
  await _care(message, "walk")


@router.message(Command("talk", "تحدث", "احجي", "حچي"))
async def cmd_talk(message: Message) -> None:
  await _care(message, "talk")


@router.message(Command("relax", "استلقاء", "استرخاء", "تلفاز"))
async def cmd_relax(message: Message) -> None:
  await _care(message, "relax")


async def _care(message: Message, action: str) -> None:
  user_id = message.from_user.id
  async with user_action_lock(user_id):
    await _care_locked(message, action, user_id)


async def _care_locked(message: Message, action: str, user_id: int) -> None:
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    latest = await get_latest_cat_for_user(user_id)
    if latest is not None and latest.get("is_fled"):
      await message.answer("💨 قطتك هربت بسبب الإهمال، وما عادت أفعال العناية متاحة.")
      return
    await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
    return

  apply_decay(cat)
  finish_sleep(cat)
  if mark_fled_if_needed(cat):
    await update_cat(cat)
    await message.answer("💨 القطة هربت بسبب الإهمال.")
    return
  if is_sleeping(cat):
    await update_cat(cat)
    remaining = sleep_duration_text(sleep_remaining_minutes(cat))
    await message.answer(
      f"😴 القطة نائمة هسه، باقي تقريباً {remaining}. "
      "إذا تريد تتفاعل وياها، صحّيها أولاً."
    )
    return

  block_reason = action_block_reason(cat, action)
  if block_reason:
    await update_cat(cat)
    if block_reason == "starving":
      await message.answer("🚨🍖 جوعها شديد؛ أطعمها أولاً قبل اللعب أو النزهة.")
    else:
      await message.answer("🪫 القطة منهكة وتحتاج ترتاح قبل اللعب أو النزهة.")
    return

  timestamp_key = {
    "feed": "last_fed",
    "play": "last_played",
    "walk": "last_walk",
    "talk": "last_talk",
    "relax": "last_relax",
  }[action]
  cooldown = {
    "feed": settings.feed_cooldown,
    "play": settings.play_cooldown,
    "walk": settings.walk_cooldown,
    "talk": settings.talk_cooldown,
    "relax": settings.relax_cooldown,
  }[action]

  last_action = cat.get(timestamp_key)
  if last_action:
    ready, seconds_left = check_cooldown(parse_time(last_action), cooldown)
  else:
    ready, seconds_left = True, 0

  bypass_cooldown = can_bypass_action_cooldown(cat, action)
  bypassed = not ready and bypass_cooldown
  soft_interaction = not ready and not bypass_cooldown

  if soft_interaction:
    apply_light_interaction(cat, action)
  else:
    apply_care_effects(cat, action)
    cat[timestamp_key] = datetime.utcnow().isoformat()

  if action == "feed":
    text = "🍖 أكلت القطة وصارت أهدأ وأسعد"
  elif action == "play":
    if int(cat.get("same_action_streak", 1)) >= 5:
      text = "😾 ملت من نفس اللعب؛ غيّر النشاط وياها"
    else:
      text = "🎾 انبسطت القطة باللعب"
  elif action == "walk":
    text = "🌿 طلعت القطة نزهة وانبسطت"
  elif action == "talk":
    text = "💬 ارتاحت القطة للحچي وياك"
  else:
    text = "🛋 استلقت يمك وصارت تتابع التلفاز بهدوء"

  points = care_reward_points(cat, action, bypassed_cooldown=bypassed)
  await update_cat(cat)
  balance = await award_points(user_id, points, action) if points else await get_user_points(user_id)
  if soft_interaction:
    reward_note = (
      "\n😺 التفاعل مسموح، بس التهدئة بعدها شغالة؛ تأثيره خفيف وبدون نقاط."
    )
  elif bypassed:
    reward_note = (
      "\n⚡ قطتك كانت تحتاج هذا الفعل، لذلك تجاهلت التهدئة؛ بدون نقاط إضافية."
    )
  elif not cat.get("last_care_meaningful", False):
    reward_note = (
      "\n😺 هذا تفاعل اختياري؛ مسموح عادي، بس فائدته بسيطة وبدون نقاط."
    )
  else:
    reward_note = ""
  await message.answer(
    f"{text}!{reward_note}\n"
    f"الشبع: {fullness_percent(cat)}/100 | السعادة: {cat['happiness']}/100 | "
    f"الملل: {cat.get('boredom', 10)}/100 | الراحة: {sleep_need_percent(cat)}/100\n"
    f"نقاطك: {balance}"
  )
