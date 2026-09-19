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
import random

from bot.config import settings
from bot.services.economy import check_cooldown
from bot.services.local_store import apply_care_effects, apply_decay, award_points, get_user_cat, ensure_user, parse_time, update_cat, is_sleeping, sleep_need_percent

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
  refusal_until = cat.get("action_refusal_until")
  if is_sleeping(cat):
    await update_cat(cat)
    await message.answer("😾 القطة تحتاج النوم الآن وترفض هذا الفعل.")
    return
  if (
    refusal_until
    and datetime.utcnow().timestamp() < refusal_until
    and action in {"play", "walk"}
  ):
    await update_cat(cat)
    await message.answer("😾 القطة مرهقة، خليها ترتاح شوي قبل اللعب أو النزهة.")
    return
  if refusal_until:
    cat.pop("action_refusal_until", None)
  elif sleep_need_percent(cat) <= 20 and action in {"play", "walk"}:
    cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
    await update_cat(cat)
    await message.answer("😾 القطة مرهقة جداً وتحتاج تنام قبل اللعب أو النزهة.")
    return
  if action == "feed" and int(cat.get("hunger", 20)) <= 15:
    await update_cat(cat)
    await message.answer("😺 القطة شبعانة هسه وما تحتاج أكل زيادة.")
    return
  timestamp_key = {"feed": "last_fed", "play": "last_played", "walk": "last_walk"}[action]
  cooldown = {"feed": settings.feed_cooldown, "play": settings.play_cooldown, "walk": settings.walk_cooldown}[action]
  ready, seconds_left = check_cooldown(parse_time(cat[timestamp_key]), cooldown)
  if not ready:
    await message.answer(f"⏳ انتظر {seconds_left // 60} دقيقة قبل هذا الفعل مرة ثانية.")
    await update_cat(cat)
    return

  apply_care_effects(cat, action)
  if action == "feed":
    text = "🍖 شبعت القطة وصارت أهدأ وأسعد"
    points = 5
  elif action == "play":
    text = "🎾 انبسطت القطة باللعب"
    points = 5
  else:
    text = "🚶 طلعت القطة نزهة وانبسطت"
    points = 10
  cat[timestamp_key] = datetime.utcnow().isoformat()
  await update_cat(cat)
  balance = await award_points(user_id, points, action)
  await message.answer(f"{text}!\nالجوع: {cat['hunger']}/100 | السعادة: {cat['happiness']}/100\nنقاطك: {balance}")
