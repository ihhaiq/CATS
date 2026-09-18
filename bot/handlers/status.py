"""
/status (or /cat) — show current state + rendered image.
TODO (AGENT.md step 7):
  - Load cat, apply lazy decay, check flee_logic.check_flee() (may flip is_fled here).
  - If fled: show shelter-eligible message instead of normal status.
  - Otherwise call image_renderer.render_cat() with a cache key of
    (breed, emotion_bucket, hunger//10, happiness//10) so unchanged states reuse the cached PNG.
  - Send photo + a short text summary (age, hunger/happiness/love bars as emoji or numbers).
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.local_store import apply_decay, ensure_user, finish_sleep, get_user_cat, get_user_points, update_cat
from bot.services.rich_card import build_rich_card

router = Router(name="status")


@router.message(Command("status", "cat", "حالة", "قطتي"))
async def cmd_status(message: Message) -> None:
  user_id = message.from_user.id
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    await message.answer("ما عندك قطة. استخدم /adopt اسم_القطة أولاً.")
    return
  finish_sleep(cat)
  apply_decay(cat)
  if cat["love_bar"] <= 0:
    cat["is_fled"] = True
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
