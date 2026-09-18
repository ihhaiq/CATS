"""
/shelter — browse & re-adopt fled cats.
TODO (AGENT.md step 9):
  - List cats WHERE is_fled = TRUE AND owner_id NOT current-user-only-restriction (open pool),
    ordered by fled_at (add that column) or love_bar history if you want "hardest to win back" flavor.
  - /shelter_adopt <cat_id>: reassign owner_id to the new user, reset is_fled = FALSE,
    partial reset of love_bar (e.g. start at 40%, not 100% — re-adoption should feel earned),
    keep name/breed/age intact (this is the point of the shelter — continuity, not a fresh cat).
  - Guard: a user can't re-adopt their own fled cat back for free (optional design decision — confirm with H).
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="shelter")


@router.message(Command("shelter", "ملجأ", "ملجا"))
async def cmd_shelter(message: Message) -> None:
  await message.answer("🏠 الملجأ فارغ حالياً. القطط الهاربة ستظهر هنا لاحقاً.")
