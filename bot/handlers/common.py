"""/start, /help, menu navigation, and the guest entry point."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.core import keyboards as kb
from bot.core import texts
from bot.core.tokens import parse_partner_token
from bot.domain import rules
from bot.domain.entities import UserData
from bot.handlers._shared import reply_text, send_cat_card
from bot.services.cat_service import CatService

router = Router(name="common")


@router.message(CommandStart(deep_link=True))
async def start_deeplink(
    message: Message,
    command: CommandObject,
    service: CatService,
    user: UserData,
    settings: Settings,
    is_guest_mode: bool,
) -> None:
    cat_id = parse_partner_token(command.args or "", settings.bot_token)
    if cat_id is None:
        await message.answer(texts.PARTNER_INVALID, reply_markup=kb.back_to_menu())
        return

    cat = await service.repo.get_cat(cat_id)
    if cat is None or cat.is_fled:
        await message.answer(texts.PARTNER_INVALID, reply_markup=kb.back_to_menu())
        return

    ok, reason = await service.attach_partner(cat, user.user_id)
    if not ok:
        await message.answer(
            texts.PARTNER_SELF if reason == "self" else texts.PARTNER_ALREADY,
            reply_markup=kb.back_to_menu(),
        )
        return

    await send_cat_card(
        message, service, user, cat, guest=is_guest_mode, header=texts.PARTNER_JOINED
    )


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(
    message: Message, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    cat = await service.repo.get_active_cat_for(user.user_id)
    intro = texts.GUEST_WELCOME if is_guest_mode else texts.WELCOME
    await message.answer(
        intro, reply_markup=kb.main_menu(has_cat=cat is not None, guest=is_guest_mode)
    )


@router.callback_query(F.data.startswith("nav:menu"))
async def cb_menu(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    cat = await service.repo.get_active_cat_for(user.user_id)
    await reply_text(
        callback,
        texts.GUEST_WELCOME if is_guest_mode else texts.MENU,
        kb.main_menu(has_cat=cat is not None, guest=is_guest_mode),
    )
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool) -> None:
    await message.answer(texts.help_text(is_admin=is_admin), reply_markup=kb.back_to_menu())


@router.callback_query(F.data.startswith("nav:help"))
async def cb_help(callback: CallbackQuery, is_admin: bool) -> None:
    await reply_text(callback, texts.help_text(is_admin=is_admin), kb.back_to_menu())
    await callback.answer()


@router.message(Command("points"))
async def cmd_points(message: Message, service: CatService, user: UserData) -> None:
    history = await service.repo.points_history(user.user_id, limit=8)
    lines = [f"⭐ <b>رصيدك: {user.points} نقطة</b>", ""]
    if history:
        lines.append("<b>آخر الحركات</b>")
        for delta, reason in history:
            sign = "＋" if delta >= 0 else "－"
            lines.append(f"{sign}{abs(delta)} · <i>{texts.esc(reason)}</i>")
    else:
        lines.append("<i>ما اكو حركات بعد — العب وياها حتى تجمع نقاط.</i>")
    await message.answer("\n".join(lines), reply_markup=kb.back_to_menu())


# --- guest -----------------------------------------------------------------
@router.callback_query(F.data.startswith("guest:quickstart"))
async def cb_quickstart(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    """One tap from zero to a playable cat — the whole point of guest mode."""
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        cat = await service.adopt(
            user.user_id,
            name=rules.assign_random_breed().label_ar.split(" ", 1)[-1],
            is_guest=True,
        )
        user = await service.repo.get_or_create_user(user.user_id)
    await callback.answer()
    await send_cat_card(
        callback, service, user, cat, guest=is_guest_mode, header=texts.GUEST_ADOPT_INTRO
    )


@router.message(Command("save"))
@router.callback_query(F.data.startswith("guest:save"))
async def guest_save(
    event: Message | CallbackQuery, is_guest_mode: bool
) -> None:
    text = texts.SAVE_IN_GUEST if is_guest_mode else texts.SAVE_OK
    if isinstance(event, CallbackQuery):
        await event.answer()
    await reply_text(event, text, kb.back_to_menu())

