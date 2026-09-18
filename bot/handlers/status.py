"""/status (or /cat) — show the current Rich cat state."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.action_locks import user_action_lock
from bot.services.local_store import (
    ensure_user,
    get_user_cat,
    get_user_points,
    refresh_cat_state,
    update_cat,
)
from bot.services.rich_card import build_rich_card

router = Router(name="status")


@router.message(Command("status", "cat", "حالة", "قطتي"))
async def cmd_status(message: Message) -> None:
    user_id = message.from_user.id
    async with user_action_lock(user_id):
        await ensure_user(user_id)
        cat = await get_user_cat(user_id)
        if cat is None:
            await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
            return

        refresh_cat_state(cat)
        if cat["love_bar"] <= 0:
            cat["is_fled"] = True
            await update_cat(cat)
            await message.answer("💨 القطة هربت بسبب الإهمال.")
            return

        await update_cat(cat)
        card = build_rich_card(cat, await get_user_points(user_id))

    await message.bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=card,
    )
