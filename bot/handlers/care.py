"""/feed, /play, /walk — core care actions."""
from datetime import datetime
import random

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.services.action_locks import user_action_lock
from bot.services.economy import check_cooldown
from bot.services.local_store import (
    award_points,
    ensure_user,
    get_user_cat,
    is_sleeping,
    parse_time,
    refresh_cat_state,
    sleep_need_percent,
    update_cat,
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

    refresh_cat_state(cat)
    refusal_until = cat.get("action_refusal_until")

    if is_sleeping(cat):
        await update_cat(cat)
        await message.answer("😾 القطة تحتاج النوم الآن وترفض هذا الفعل.")
        return

    if refusal_until and datetime.utcnow().timestamp() < refusal_until:
        await update_cat(cat)
        await message.answer("😾 القطة ستقبل بعد دقائق قليلة.")
        return

    if refusal_until:
        cat.pop("action_refusal_until", None)
    elif sleep_need_percent(cat) <= 65:
        cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
        await update_cat(cat)
        await message.answer("😾 القطة تريد النوم الآن، جرّب بعد دقائق.")
        return

    timestamp_key = {
        "feed": "last_fed",
        "play": "last_played",
        "walk": "last_walk",
    }[action]
    cooldown = {
        "feed": settings.feed_cooldown,
        "play": settings.play_cooldown,
        "walk": settings.walk_cooldown,
    }[action]
    ready, seconds_left = check_cooldown(parse_time(cat[timestamp_key]), cooldown)
    if not ready:
        await update_cat(cat)
        minutes = max(1, (seconds_left + 59) // 60)
        await message.answer(f"⏳ انتظر {minutes} دقيقة قبل هذا الفعل مرة ثانية.")
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
    await message.answer(
        f"{text}!\n"
        f"الجوع: {cat['hunger']}/100 | السعادة: {cat['happiness']}/100\n"
        f"نقاطك: {balance}"
    )
