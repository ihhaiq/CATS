"""
Last router in the chain.

Two jobs: answer stale callbacks so the user never stares at a loading spinner,
and give unknown text a useful nudge instead of silence.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot.core import keyboards as kb
from bot.services.cat_service import CatService
from bot.domain.entities import UserData

router = Router(name="fallback")


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer("🔄 هذا الزر قديم — افتح /menu من جديد.", show_alert=False)


@router.message()
async def unknown_message(
    message: Message, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    cat = await service.repo.get_active_cat_for(user.user_id)
    await message.answer(
        "🤔 ما فهمت هذا. جرب الأزرار أو /help.",
        reply_markup=kb.main_menu(has_cat=cat is not None, guest=is_guest_mode),
    )
