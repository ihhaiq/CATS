"""
/feed, /play, /walk — core care actions.
TODO (AGENT.md step 5):
  - For each action: load cat, run decay_engine.apply_lazy_decay() first to get true current state,
    then check server-side cooldown (config.settings.*_cooldown) against last_fed/last_played/last_walk.
  - On success: update the relevant stat(s), update last_* timestamp, award points via economy.py
    (which also writes a points_log row), clear last_notified_state if the triggering condition resolved.
  - On cooldown: reply with remaining time, no state change, no points.
  - Re-render and send the updated status image after every successful action.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from datetime import datetime

from bot.config import settings
from bot.services.economy import check_cooldown
from bot.services.local_store import apply_decay, award_points, get_user_cat, ensure_user, parse_time, update_cat, is_sleeping, sleep_need_percent

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


async def _care(message: Message, action: str) -> None:
  user_id = message.from_user.id
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
    return

  apply_decay(cat)
  if is_sleeping(cat) or sleep_need_percent(cat) >= 85:
    await update_cat(cat)
    await message.answer("😾 القطة تحتاج النوم الآن وترفض هذا الفعل.")
    return
  timestamp_key = {"feed": "last_fed", "play": "last_played", "walk": "last_walk"}[action]
  cooldown = {"feed": settings.feed_cooldown, "play": settings.play_cooldown, "walk": settings.walk_cooldown}[action]
  ready, seconds_left = check_cooldown(parse_time(cat[timestamp_key]), cooldown)
  if not ready:
    await message.answer(f"⏳ انتظر {seconds_left // 60} دقيقة قبل هذا الفعل مرة ثانية.")
    await update_cat(cat)
    return

  if action == "feed":
    cat["hunger"] = max(0, cat["hunger"] - 30)
    text = "🍖 شبعت القطة"
    points = 5
  elif action == "play":
    cat["happiness"] = min(100, cat["happiness"] + 25)
    cat["hunger"] = min(100, cat["hunger"] + 5)
    text = "🎾 انبسطت القطة باللعب"
    points = 5
  else:
    cat["happiness"] = min(100, cat["happiness"] + 15)
    text = "🚶 طلعت القطة نزهة"
    points = 10
  cat[timestamp_key] = datetime.utcnow().isoformat()
  await update_cat(cat)
  balance = await award_points(user_id, points, action)
  await message.answer(f"{text}!\nالجوع: {cat['hunger']}/100 | السعادة: {cat['happiness']}/100\nنقاطك: {balance}")
