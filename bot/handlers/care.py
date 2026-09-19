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
  award_points,
  can_bypass_action_cooldown,
  ensure_user,
  fullness_percent,
  get_user_cat,
  get_user_points,
  is_sleeping,
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


async def _care(message: Message, action: str) -> None:
  user_id = message.from_user.id
  async with user_action_lock(user_id):
    await _care_locked(message, action, user_id)


async def _care_locked(message: Message, action: str, user_id: int) -> None:
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
    return

  apply_decay(cat)
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
    if block_reason == "full":
      await message.answer("😺 القطة شبعانة هسه وما تحتاج أكل زيادة.")
    elif block_reason == "starving":
      await message.answer("🚨🍖 جوعها شديد؛ أطعمها أولاً قبل اللعب أو النزهة.")
    elif block_reason == "bored_of_play":
      await message.answer("😾 ملت من نفس اللعب. حچي وياها أو طلّعها نزهة وغيّر الروتين.")
    else:
      await message.answer("🪫 القطة تعبانة وتحتاج نوم قبل اللعب أو النزهة.")
    return

  timestamp_key = {
    "feed": "last_fed",
    "play": "last_played",
    "walk": "last_walk",
    "talk": "last_talk",
  }[action]
  cooldown = {
    "feed": settings.feed_cooldown,
    "play": settings.play_cooldown,
    "walk": settings.walk_cooldown,
    "talk": settings.talk_cooldown,
  }[action]

  last_action = cat.get(timestamp_key)
  if last_action:
    ready, seconds_left = check_cooldown(parse_time(last_action), cooldown)
  else:
    ready, seconds_left = True, 0

  bypass_cooldown = can_bypass_action_cooldown(cat, action)
  if not ready and not bypass_cooldown:
    await message.answer(
      f"⏳ انتظر {max(1, seconds_left // 60)} دقيقة قبل هذا الفعل مرة ثانية."
    )
    await update_cat(cat)
    return

  apply_care_effects(cat, action)
  cat[timestamp_key] = datetime.utcnow().isoformat()

  if action == "feed":
    text = "🍖 أكلت القطة وصارت أهدأ وأسعد"
    points = 5
  elif action == "play":
    if int(cat.get("same_action_streak", 1)) >= 5:
      text = "😾 ملت من نفس اللعب؛ غيّر النشاط وياها"
      points = 0
    else:
      text = "🎾 انبسطت القطة باللعب"
      points = 5
  elif action == "walk":
    text = "🌿 طلعت القطة نزهة وانبسطت"
    points = 10
  else:
    text = "💬 ارتاحت القطة للحچي وياك"
    points = 3

  await update_cat(cat)
  balance = await award_points(user_id, points, action) if points else await get_user_points(user_id)
  bypass_note = (
    "\n⚡ انفتحت فترة التهدئة لأن قطتك كانت تحتاج هذا الفعل."
    if bypass_cooldown and not ready
    else ""
  )
  await message.answer(
    f"{text}!{bypass_note}\n"
    f"الشبع: {fullness_percent(cat)}/100 | السعادة: {cat['happiness']}/100 | "
    f"الملل: {cat.get('boredom', 10)}/100 | الراحة: {sleep_need_percent(cat)}/100\n"
    f"نقاطك: {balance}"
  )
