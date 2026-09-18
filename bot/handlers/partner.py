"""
/invite_partner — co-owner invite link + affinity system.
TODO (AGENT.md step 6):
  - Generate a signed/short-lived deep-link token (e.g. base64 of cat_id + secret) for /start payload.
  - On a new user opening that deep link: set cats.partner_id, award the one-time +50 bonus
    (guard: only once per unique partner per cat — check points_log/partner history first).
  - Partner actions (feed/play/walk) reuse care.py logic but also nudge partner_affinity upward.
  - Add a read-only affinity view command.
"""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.services.local_store import ensure_user

router = Router(name="partner")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
  await ensure_user(message.from_user.id)
  await message.answer("🐾 أهلاً بك في Catibot!\nاستخدم /adopt اسم_القطة حتى تتبنى قطتك.")


@router.message(Command("invite_partner"))
async def cmd_invite_partner(message: Message) -> None:
  await message.answer("🔗 دعوة الشريك ستتوفر لاحقاً. حالياً استخدم /adopt و /status و /feed.")
