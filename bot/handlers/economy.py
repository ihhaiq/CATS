"""/shop, /bag — spending points and using items."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.core import keyboards as kb
from bot.core import texts
from bot.core.keyboards import CB
from bot.domain.entities import UserData
from bot.handlers._shared import reply_text, send_cat_card
from bot.services.cat_service import CatService

router = Router(name="economy")


@router.message(Command("shop"))
@router.callback_query(F.data.startswith("shop:open"))
async def show_shop(
    event: Message | CallbackQuery, service: CatService, user: UserData
) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    items = await service.repo.list_items()
    await reply_text(event, texts.shop_text(items, user.points), kb.shop_keyboard(items, user.points))


@router.callback_query(F.data.startswith("shop:buy"))
async def cb_buy(callback: CallbackQuery, service: CatService, user: UserData) -> None:
    parsed = CB.parse(callback.data or "")
    if not parsed.arg.isdigit():
        await callback.answer()
        return
    item = await service.repo.get_item(int(parsed.arg))
    if item is None:
        await callback.answer("الغرض مو موجود.", show_alert=True)
        return

    ok, balance = await service.buy(user, item)
    if not ok:
        await callback.answer(texts.NOT_ENOUGH_POINTS.replace("😅 ", ""), show_alert=True)
        return

    await callback.answer("✅ تم الشراء")
    items = await service.repo.list_items()
    await reply_text(callback, texts.bought(item, balance), kb.shop_keyboard(items, balance))


@router.message(Command("bag"))
@router.callback_query(F.data.startswith("bag:open"))
async def show_bag(event: Message | CallbackQuery, service: CatService, user: UserData) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
    rows = await service.repo.inventory(user.user_id)
    await reply_text(event, texts.bag_text(rows), kb.bag_keyboard(rows))


@router.callback_query(F.data.startswith("bag:use"))
async def cb_use(
    callback: CallbackQuery, service: CatService, user: UserData, is_guest_mode: bool
) -> None:
    parsed = CB.parse(callback.data or "")
    if not parsed.arg.isdigit():
        await callback.answer()
        return

    owned = {item.item_id: qty for item, qty in await service.repo.inventory(user.user_id)}
    item_id = int(parsed.arg)
    if owned.get(item_id, 0) <= 0:
        await callback.answer("ما عندك هذا الغرض.", show_alert=True)
        return

    item = await service.repo.get_item(item_id)
    cat = await service.repo.get_active_cat_for(user.user_id)
    if item is None or cat is None:
        await callback.answer(texts.NO_CAT.replace("🐾 ", ""), show_alert=True)
        return

    cat = await service.use_item(user, cat, item)
    await callback.answer("✨ تم الاستخدام")
    await send_cat_card(
        callback, service, user, cat, guest=is_guest_mode, header=texts.item_used(item, cat)
    )
