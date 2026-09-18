"""/invite_partner and /shelter — the two social systems."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.core import keyboards as kb
from bot.core import texts
from bot.core.keyboards import CB
from bot.core.tokens import make_partner_token
from bot.domain.entities import UserData
from bot.handlers._shared import reply_text, send_cat_card
from bot.services.cat_service import CatService

router = Router(name="social")


@router.message(Command("invite_partner"))
@router.callback_query(F.data.startswith("partner:invite"))
async def invite_partner(
    event: Message | CallbackQuery,
    service: CatService,
    user: UserData,
    settings: Settings,
    is_guest_mode: bool,
) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        await reply_text(event, texts.NO_CAT, kb.adopt_prompt(guest=is_guest_mode))
        return
    if cat.owner_id != user.user_id:
        await reply_text(event, "🤝 الدعوة من صاحب القطة بس.", kb.back_to_menu())
        return
    if cat.partner_id:
        await reply_text(event, texts.PARTNER_ALREADY, kb.back_to_menu())
        return

    msg = event if isinstance(event, Message) else event.message
    me = await msg.bot.me()
    token = make_partner_token(cat.cat_id, settings.bot_token)
    link = f"https://t.me/{me.username}?start={token}"
    await reply_text(event, texts.partner_invite(link, cat), kb.back_to_menu())


@router.message(Command("shelter"))
@router.callback_query(F.data.startswith("shelter:open"))
async def show_shelter(event: Message | CallbackQuery, service: CatService) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    cats = await service.repo.list_fled_cats(limit=10)
    await reply_text(event, texts.shelter_text(cats), kb.shelter_keyboard(cats))


@router.callback_query(F.data.startswith("shelter:adopt"))
async def cb_readopt(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    parsed = CB.parse(callback.data or "")
    if not parsed.arg.isdigit():
        await callback.answer()
        return
    try:
        cat = await service.readopt(user.user_id, int(parsed.arg))
    except ValueError as exc:
        reason = {
            "already_has_cat": texts.ALREADY_HAS_CAT,
            "not_in_shelter": "🏠 هذي القطة ما عادت بالملجأ.",
        }.get(str(exc), texts.ERROR_GENERIC)
        await callback.answer(reason.replace("🐱 ", "").replace("🏠 ", ""), show_alert=True)
        return

    await callback.answer("🏡 رجعت للبيت!")
    await send_cat_card(
        callback, service, user, cat, guest=is_guest_mode, header=texts.readopted(cat)
    )
