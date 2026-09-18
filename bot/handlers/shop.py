from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.services.local_store import clear_purchases, ensure_user, get_purchases, get_user_points
from bot.services.shop import buy_item, list_items, open_shop
from bot.services.shop_card import build_shop_card
from bot.utils.telegram import edit_callback_rich_message

router = Router(name="shop")


@router.message(Command("shop", "متجر"))
async def cmd_shop(message: Message) -> None:
    items = await open_shop(message.from_user.id)
    await message.bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=build_shop_card(
            items,
            await get_purchases(message.from_user.id),
            await get_user_points(message.from_user.id),
        ),
    )


@router.callback_query(lambda query: query.data and query.data.startswith("shop:buy:"))
async def cb_buy(query: CallbackQuery) -> None:
    item_id = query.data.rsplit(":", 1)[1]
    if not item_id.isdigit():
        await query.answer()
        return

    ok, result, balance = await buy_item(query.from_user.id, int(item_id))
    await query.answer(result)
    if not ok:
        # Failed purchases do not change the card; don't ask Telegram to edit it.
        return

    items = await list_items()
    card = build_shop_card(items, await get_purchases(query.from_user.id), balance)
    await edit_callback_rich_message(query, card)


@router.message(Command("buy", "شراء"))
async def cmd_buy(message: Message, command: CommandObject) -> None:
    raw_id = (command.args or "").strip()
    if not raw_id.isdigit():
        await message.answer("استخدم /buy رقم_الغرض، مثلاً: /buy 1")
        return

    await ensure_user(message.from_user.id)
    _, result, balance = await buy_item(message.from_user.id, int(raw_id))
    await message.answer(f"{result}\n🐾 رصيدك: {balance}")
