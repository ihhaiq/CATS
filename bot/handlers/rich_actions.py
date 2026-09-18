"""Callbacks for Rich Message action buttons."""
import random
import asyncio
from datetime import datetime

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.services.economy import check_cooldown
from bot.services.local_store import (
    apply_decay,
    award_points,
    ensure_user,
    get_user_cat,
    get_user_points,
    parse_time,
    update_cat,
    finish_sleep,
    is_sleeping,
    start_sleep,
    clear_action_notice,
    wake_now,
    sleep_need_percent,
)
from bot.services.rich_card import build_rich_card

router = Router(name="rich_actions")


async def _edit_card(query: CallbackQuery, card) -> None:
    if query.inline_message_id:
        await query.bot.edit_message_text(inline_message_id=query.inline_message_id, rich_message=card)
    elif query.message:
        await query.bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            rich_message=card,
        )


async def _clear_notice_later(query: CallbackQuery, cat: dict, points: int) -> None:
    await asyncio.sleep(10)
    clear_action_notice(cat)
    await _edit_card(query, build_rich_card(cat, points, "status"))


@router.callback_query(lambda query: query.data and query.data.startswith("cat:"))
async def handle_rich_action(query: CallbackQuery) -> None:
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    await ensure_user(user_id)
    cat = await get_user_cat(user_id)
    if cat is None:
        await query.answer("ما عندك قطة بعد.", show_alert=True)
        return

    clear_action_notice(cat)
    apply_decay(cat)
    if finish_sleep(cat):
        await update_cat(cat)
    if is_sleeping(cat) and action != "wake":
        await update_cat(cat)
        await query.answer()
        return
    if action == "wake" and random.random() < 0.2:
        cat["action_notice"] = "😾 القطة ترفض النهوض!"
        await update_cat(cat)
        await _edit_card(query, build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"))
        await query.answer()
        asyncio.create_task(_clear_notice_later(query, cat, await get_user_points(user_id)))
        return
    refusal_until = cat.get("action_refusal_until")
    if refusal_until and datetime.utcnow().timestamp() < refusal_until and action in {"feed", "play", "walk", "talk"}:
        cat["action_notice"] = "😾 القطة ستقبل بعد دقائق قليلة!"
        await update_cat(cat)
        await _edit_card(query, build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"))
        await query.answer()
        asyncio.create_task(_clear_notice_later(query, cat, await get_user_points(user_id)))
        return
    if refusal_until:
        cat.pop("action_refusal_until", None)
    elif sleep_need_percent(cat) <= 65 and action in {"feed", "play", "walk", "talk"}:
        cat["action_notice"] = "😾 القطة مرهقة وتحتاج النوم!"
        cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
        await update_cat(cat)
        await _edit_card(query, build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"))
        await query.answer()
        asyncio.create_task(_clear_notice_later(query, cat, await get_user_points(user_id)))
        return
    media_kind = action
    if action == "feed":
        ready, left = check_cooldown(parse_time(cat["last_fed"]), settings.feed_cooldown)
        if not ready:
            await query.answer(f"الإطعام متاح بعد {left // 60} دقيقة.", show_alert=True)
            return
        cat["hunger"] = max(0, cat["hunger"] - 30)
        cat["last_fed"] = datetime.utcnow().isoformat()
        points = random.choice([0, 0, 2, 5, 8])
    elif action in {"play", "walk"} and random.random() < 0.2:
        media_kind = "cat_angry_sleep"
        points = 0
        cat["action_notice"] = "😾 القطة تريد النوم!"
        cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
    elif action == "play":
        cat["happiness"] = min(100, cat["happiness"] + 25)
        cat["hunger"] = min(100, cat["hunger"] + 5)
        cat["last_played"] = datetime.utcnow().isoformat()
        points = random.choice([0, 1, 3, 5, 10])
        if random.random() < 0.15:
            cat["action_notice"] = "🥰 نامت القطة على صدرك!"
    elif action == "walk":
        cat["happiness"] = min(100, cat["happiness"] + 15)
        cat["last_walk"] = datetime.utcnow().isoformat()
        points = random.choice([0, 2, 5, 10, 15])
    elif action == "talk":
        cat["happiness"] = min(100, cat["happiness"] + 5)
        points = random.choice([0, 1, 2, 4])
        if random.random() < 0.15:
            cat["action_notice"] = "🥰 نامت القطة على صدرك!"
    elif action == "sleep":
        minutes = start_sleep(cat)
        points = random.choice([0, 1, 2])
        media_kind = "sleep"
        if random.random() < 0.15:
            cat["action_notice"] = "🥰 نامت القطة على صدرك!"
    elif action == "wake":
        wake_now(cat)
        media_kind = "status"
        points = 0
    else:
        return

    await update_cat(cat)
    balance = await get_user_points(user_id)
    if points:
        balance = await award_points(user_id, points, action)
    await update_cat(cat)
    await _edit_card(query, build_rich_card(cat, balance, media_kind))
    await query.answer()
    if cat.get("action_notice"):
        asyncio.create_task(_clear_notice_later(query, cat, balance))