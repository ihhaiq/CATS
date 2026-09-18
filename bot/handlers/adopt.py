"""
/adopt <name> <title> — free cat adoption.
"""
from datetime import datetime
import random

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.action_locks import user_action_lock
from bot.services.economy import assign_random_breed
from bot.services.local_store import create_cat, ensure_user, get_user_cat, now_iso
from bot.services.rich_card import build_adoption_card

router = Router(name="adopt")


@router.message(Command("adopt", "تبني", "تبنّي"))
async def cmd_adopt(message: Message) -> None:
    user_id = message.from_user.id
    async with user_action_lock(user_id):
        await ensure_user(user_id)
        if await get_user_cat(user_id):
            await message.answer("عندك قطة بالفعل. استخدم /status لمشاهدة حالتها.")
            return

        parts = (message.text or "").split(maxsplit=1)
        name = parts[1].strip() if len(parts) > 1 else "لوز"
        if len(name) > 40:
            await message.answer("اسم القطة طويل جداً، خلّه أقل من 40 حرفاً.")
            return

        stamp = now_iso()
        cat = {
            "owner_id": user_id,
            "partner_id": None,
            "name": name,
            "title": "الأليف",
            "id_number": str(random.randint(100000, 999999)),
            "breed": assign_random_breed(),
            "age_days": 30,
            "hunger": 20,
            "happiness": 100,
            "love_bar": 100,
            "partner_affinity": 0,
            "is_fled": False,
            "last_fed": stamp,
            "last_played": stamp,
            "last_walk": stamp,
            "last_talked": stamp,
            "last_decay_at": stamp,
            "sleep_day": datetime.utcnow().date().isoformat(),
            "slept_today_hours": 10.0,
            "sleep_until": None,
            "last_wake_at": stamp,
        }
        await create_cat(cat)

    await message.bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=build_adoption_card(cat),
    )
