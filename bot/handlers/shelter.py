"""Shelter command placeholder kept as a visible user-facing route."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="shelter")


@router.message(Command("shelter", "ملجأ", "ملجا"))
async def cmd_shelter(message: Message) -> None:
    await message.answer("🏠 الملجأ فارغ حالياً. القطط الهاربة ستظهر هنا لاحقاً.")
