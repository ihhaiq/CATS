from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.services.local_store import ensure_user, get_purchases, get_user_points
from bot.services.shop import buy_item, list_items, open_shop
from bot.services.shop_card import build_shop_card
from bot.utils.telegram import edit_callback_rich_message

router = Router(name="shop")


def _parse_buy_data(data: str) -> tuple[int | None, int | None]:
    parts = data.split(":")
    if len(parts) == 3 and parts[2].isdigit():
        # Legacy card: shop:buy:<item_id>
        return None, int(parts[2])
    if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
        return int(parts[2]), int(parts[3])
    return None, None


@router.message(Command("shop", "متجر"))
async def cmd_shop(message: Message) -> None:
    user_id = message.from_user.id
    items = await open_shop(user_id)
    await message.bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=build_shop_card(
            items,
            await get_purchases(user_id),
            await get_user_points(user_id),
            owner_id=user_id,
        ),
    )


@router.callback_query(lambda query: query.data and query.data.startswith("shop:buy:"))
async def cb_buy(query: CallbackQuery) -> None:
    owner_id, item_id = _parse_buy_data(query.data)
    if item_id is None:
        await query.answer()
        return

    if owner_id is not None and owner_id != query.from_user.id:
        await query.answer("هذه أزرار متجر مستخدم آخر.", show_alert=True)
        return

    user_id = owner_id or query.from_user.id
    ok, result, balance = await buy_item(user_id, item_id)
    await query.answer(result)
    if not ok:
        # Failed purchases do not change the card; don't ask Telegram to edit it.
        return

    items = await list_items()
    card = build_shop_card(
        items,
        await get_purchases(user_id),
        balance,
        owner_id=user_id,
    )
    await edit_callback_rich_message(query, card)


@router.message(Command("buy", "شراء"))
async def cmd_buy(message: Message, command: CommandObject) -> None:
    raw_id = (command.args or "").strip()
    if not raw_id.isdigit():
        await message.answer("استخدم /buy رقم_الغرض، مثلاً: /buy 1")
        return

    user_id = message.from_user.id
    await ensure_user(user_id)
    _, result, balance = await buy_item(user_id, int(raw_id))
    await message.answer(f"{result}\n🐾 رصيدك: {balance}")
