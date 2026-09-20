"""Partner/co-owner entry point."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="partner")


@router.message(Command("invite_partner"))
async def cmd_invite_partner(message: Message) -> None:
    await message.answer(
        "🔗 دعوة الشريك ستتوفر لاحقاً. حالياً استخدم /adopt و /status و /feed."
    )
