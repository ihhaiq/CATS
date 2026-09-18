"""/adopt, /status, /rename — the cat itself."""
from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.core import keyboards as kb
from bot.core import texts
from bot.domain import rules
from bot.domain.entities import UserData
from bot.handlers._shared import reply_text, send_cat_card
from bot.services.cat_service import CatService

router = Router(name="cat")

DEFAULT_NAMES = ["مشمش", "بسبوسة", "نمنم", "لولو", "سمسم", "قمر", "فستق", "زعفران"]


class CatForm(StatesGroup):
    naming = State()
    renaming = State()


async def _adopt_and_show(
    event: Message | CallbackQuery,
    service: CatService,
    user: UserData,
    name: str,
    guest: bool,
) -> None:
    try:
        cat = await service.adopt(user.user_id, name=name, is_guest=guest)
    except ValueError as exc:
        if str(exc) == "already_has_cat":
            await reply_text(event, texts.ALREADY_HAS_CAT, kb.back_to_menu())
        else:
            await reply_text(event, f"⚠️ {exc}", kb.back_to_menu())
        return
    user = await service.repo.get_or_create_user(user.user_id)
    await send_cat_card(
        event, service, user, cat, guest=guest, header=texts.adopted(cat, guest=guest)
    )


@router.message(Command("adopt"))
async def cmd_adopt(
    message: Message,
    command: CommandObject,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    if command.args:
        await _adopt_and_show(message, service, user, command.args, is_guest_mode)
        return
    existing = await service.repo.get_active_cat_for(user.user_id)
    if existing is not None:
        await message.answer(texts.ALREADY_HAS_CAT, reply_markup=kb.back_to_menu())
        return
    await message.answer(
        "🐾 <b>تبنّي قطة</b>\n\nتحب نختارلك وحدة عشوائية لو تسميها بنفسك؟",
        reply_markup=kb.adopt_prompt(guest=is_guest_mode),
    )


@router.callback_query(F.data.startswith("cat:adopt_random"))
async def cb_adopt_random(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    await callback.answer()
    await _adopt_and_show(
        callback, service, user, random.choice(DEFAULT_NAMES), is_guest_mode
    )


@router.callback_query(F.data.startswith("cat:adopt_named"))
async def cb_adopt_named(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CatForm.naming)
    await callback.answer()
    await reply_text(callback, texts.ASK_NAME)


@router.callback_query(F.data.startswith("cat:adopt"))
async def cb_adopt(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    await callback.answer()
    existing = await service.repo.get_active_cat_for(user.user_id)
    if existing is not None:
        await reply_text(callback, texts.ALREADY_HAS_CAT, kb.back_to_menu())
        return
    await reply_text(
        callback,
        "🐾 <b>تبنّي قطة</b>\n\nتحب نختارلك وحدة عشوائية لو تسميها بنفسك؟",
        kb.adopt_prompt(guest=is_guest_mode),
    )


@router.message(CatForm.naming)
async def on_name_given(
    message: Message,
    state: FSMContext,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    await state.clear()
    await _adopt_and_show(message, service, user, message.text or "", is_guest_mode)


# --- status ----------------------------------------------------------------
@router.message(Command("status", "cat"))
@router.callback_query(F.data.startswith("cat:status"))
async def show_status(
    event: Message | CallbackQuery,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        await reply_text(event, texts.NO_CAT, kb.adopt_prompt(guest=is_guest_mode))
        return
    await send_cat_card(event, service, user, cat, guest=is_guest_mode)


# --- rename ----------------------------------------------------------------
@router.message(Command("rename"))
@router.callback_query(F.data.startswith("cat:rename"))
async def ask_rename(event: Message | CallbackQuery, state: FSMContext) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(CatForm.renaming)
    await reply_text(event, texts.ASK_NAME)


@router.message(CatForm.renaming)
async def do_rename(
    message: Message,
    state: FSMContext,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    await state.clear()
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        await message.answer(texts.NO_CAT, reply_markup=kb.adopt_prompt(guest=is_guest_mode))
        return
    try:
        cat = await service.rename(cat, message.text or "")
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await send_cat_card(
        message, service, user, cat, guest=is_guest_mode, header="✅ تم تغيير الاسم."
    )


# --- guest-only reroll -----------------------------------------------------
@router.callback_query(F.data.startswith("cat:reroll"))
async def cb_reroll(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    """Guests can swap their trial cat freely; owners can't — that's the difference."""
    if not is_guest_mode:
        await callback.answer("هذا الخيار للضيوف بس.", show_alert=True)
        return
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is not None:
        await service.repo.delete_cat(cat.cat_id)
    await callback.answer("🎲 قطة جديدة!")
    await _adopt_and_show(
        callback, service, user, random.choice(DEFAULT_NAMES), True
    )
