"""/status and /cat render the current persisted Rich Card state."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.local_store import (
  apply_decay,
  ensure_user,
  finish_sleep,
  get_latest_cat_for_user,
  get_user_cat,
  get_user_points,
  update_cat,
  user_action_lock,
)
from bot.services.rich_card import build_fled_card, build_rich_card

router = Router(name="status")


@router.message(Command("status", "cat", "حالة", "قطتي"))
async def cmd_status(message: Message) -> None:
  user_id = message.from_user.id
  async with user_action_lock(user_id):
    await _cmd_status_locked(message, user_id)


async def _cmd_status_locked(message: Message, user_id: int) -> None:
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    latest = await get_latest_cat_for_user(user_id)
    if latest is not None and latest.get("is_fled"):
      await message.bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=build_fled_card(latest),
      )
      return
    await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
    return
  apply_decay(cat)
  finish_sleep(cat, owner_present=True)
  if cat.get("is_fled"):
    await update_cat(cat)
    await message.answer("💨 القطة هربت بسبب الإهمال.")
    return
  await update_cat(cat)
  await message.bot.send_rich_message(
    chat_id=message.chat.id,
    rich_message=await build_rich_card(
      message.bot,
      cat,
      await get_user_points(user_id),
      "status",
      upload_chat_id=message.chat.id,
    ),
  )
