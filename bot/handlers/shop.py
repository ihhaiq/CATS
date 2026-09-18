"""
/shop, /buy <item_id> — spend points on items/cosmetics.
TODO (AGENT.md step 8):
  - List items from the `items` table with inline keyboard (paginate if many).
  - On /buy: check user.points >= item.price, deduct, insert/increment user_inventory row,
    log a negative points_log entry.
  - effect_type/effect_value on an item defines what it does when *used* (e.g. instant
    happiness +20) — used items differ from permanent cosmetics (collar skins); model both.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="shop")


@router.message(Command("shop", "متجر"))
async def cmd_shop(message: Message) -> None:
  await message.answer("🛍️ المتجر المحلي\nحالياً لا توجد أغراض مضافة. اجمع النقاط من /feed و /play و /walk.")
