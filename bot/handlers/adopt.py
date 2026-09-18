"""
/adopt <name> <title> — free cat adoption.
TODO (AGENT.md step 4):
  - Parse args, validate name/title length & profanity filter.
  - Reject if user already has a live (non-FLED) cat.
  - Randomly assign a breed (or offer a small free-pick pool) via services/economy.py helper.
  - Generate unique id_number (4-6 digits, retry on collision).
  - Insert cat row, render first status image, reply with it.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from datetime import datetime
import random

from bot.services.local_store import create_cat, ensure_user, get_user_cat, now_iso
from bot.services.economy import assign_random_breed

router = Router(name="adopt")


@router.message(Command("adopt", "تبني", "تبنّي"))
async def cmd_adopt(message: Message) -> None:
  user_id = message.from_user.id
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
    "last_decay_at": stamp,
    "sleep_day": datetime.utcnow().date().isoformat(),
    "slept_today_hours": 10.0,
    "sleep_until": None,
  }
  await create_cat(cat)
  await message.answer(f"🐾 تم تبني {name}!\nالسلالة: {cat['breed']}\nرقمها: #{cat['id_number']}\nاستخدم /status لمشاهدتها.")
