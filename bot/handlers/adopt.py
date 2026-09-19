"""Adoption and onboarding handlers."""
from datetime import datetime
import html
import random

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bot.services.economy import assign_random_breed
from bot.services.local_store import (
  create_cat,
  ensure_user,
  get_user_cat,
  now_iso,
  user_action_lock,
)

router = Router(name="adopt")


class AdoptFlow(StatesGroup):
  waiting_name = State()


def _welcome_keyboard() -> InlineKeyboardMarkup:
  return InlineKeyboardMarkup(
    inline_keyboard=[
      [
        InlineKeyboardButton(
          text="🐾 تبنّي قطة",
          callback_data="adopt:start",
        ),
        InlineKeyboardButton(
          text="📖 الدليل",
          callback_data="guide:open",
        ),
      ]
    ]
  )


def _adopted_card(
  cat: dict,
  *,
  newly_adopted: bool = True,
) -> InputRichMessage:
  heading = (
    f"🐾 تم تبني {html.escape(str(cat['name']))}!"
    if newly_adopted
    else f"🐾 قطتك {html.escape(str(cat['name']))}"
  )
  status_data = (
    f"cat:{cat['cat_id']}:status"
    if cat.get("cat_id")
    else "cat:status"
  )
  return InputRichMessage(
    html=f"""
<h2>{heading}</h2>
<p>السلالة: {html.escape(str(cat['breed']))}</p>
<p>رقمها: #{html.escape(str(cat['id_number']))}</p>
<tg-button-row align="center">
<tg-button type="callback_data" style="primary" data="{status_data}">عرض القطة</tg-button>
</tg-button-row>
""".strip(),
    is_rtl=True,
  )


async def _send_adopted(
  message: Message,
  cat: dict,
  *,
  newly_adopted: bool = True,
) -> None:
  await message.bot.send_rich_message(
    chat_id=message.chat.id,
    rich_message=_adopted_card(cat, newly_adopted=newly_adopted),
  )


async def _create_cat_for_user(user_id: int, name: str) -> dict:
  stamp = now_iso()
  cat = {
    "owner_id": user_id,
    "partner_id": None,
    "adopted_at": stamp,
    "name": name,
    "title": "الأليف",
    "id_number": str(random.randint(100000, 999999)),
    "breed": assign_random_breed(),
    "age_days": 30,
    "hunger": 20,
    "happiness": 100,
    "love_bar": 100,
    "trust": 60,
    "boredom": 10,
    "last_care_action": None,
    "last_care_at": None,
    "last_social_at": stamp,
    "last_talk": None,
    "same_action_streak": 0,
    "partner_affinity": 0,
    "is_fled": False,
    "last_fed": stamp,
    "last_played": None,
    "last_walk": None,
    "last_decay_at": stamp,
    "sleep_day": datetime.utcnow().date().isoformat(),
    "slept_today_hours": 0.0,
    "sleep_until": None,
    "sleep_kind": None,
    "sleep_planned_hours": 0.0,
    "last_wake_at": stamp,
    "rest_level": 100,
    "rest_updated_at": stamp,
  }
  await create_cat(cat)
  return cat


async def _get_or_create_cat(user_id: int, name: str) -> tuple[dict, bool]:
  async with user_action_lock(user_id):
    await ensure_user(user_id)
    existing = await get_user_cat(user_id)
    if existing is not None:
      return existing, False
    return await _create_cat_for_user(user_id, name), True


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
  await ensure_user(message.from_user.id)
  cat = await get_user_cat(message.from_user.id)
  if cat is not None:
    await message.bot.send_rich_message(
      chat_id=message.chat.id,
      rich_message=_adopted_card(cat, newly_adopted=False),
    )
    return
  await message.answer(
    "🐾 <b>أهلاً بك في Catibot</b>\n\n"
    "هنا راح تتبنّى قطتك الخاصة وتعتني بيها يوم بعد يوم. "
    "تحتاج تطعمها، تلعب وياها، تطلعها بنزهة وتخليها ترتاح وتنام بوقتها.\n\n"
    "كل فعل يأثر على حالتها، سعادتها وحبها إلك، فحاول لا تهملها 😼\n\n"
    "ابدأ من الزر أدناه واختار اسم قطتك.",
    reply_markup=_welcome_keyboard(),
  )


@router.callback_query(F.data == "guide:open")
async def cb_guide_open(query: CallbackQuery) -> None:
  await query.answer()
  if query.message:
    await query.message.answer(
      "📖 <b>دليل Catibot</b>\n\n"
      "• 🐾 تبنّى قطة واختار إلها اسم.\n"
      "• 🍖 حافظ على الشبع بالإطعام.\n"
      "• 🎾 اللعب والنزهة يرفعون السعادة.\n"
      "• 😴 عداد الراحة ينزل بسرعة ويرتفع ببطء، يعني القطة تحتاج نوم فعلي وكافي.\n"
      "• 🌀 اللعب والحديث يقللون الملل، والروتين والنوم الكثير يزيدوه.\n"
      "• 🤝 الثقة تزيد بالرعاية الثابتة وتنزل بالإهمال الشديد.\n"
      "• ❤️ الإهمال يأثر على الحب وحالة القطة.\n"
      "• 🐾 بعض الأفعال تكافئك بعملة قططية تقدر تستخدمها داخل البوت.\n\n"
      "تگدر ترجع للواجهة وتبدأ من زر <b>تبنّي قطة</b>."
    )


@router.callback_query(F.data == "adopt:start")
async def cb_adopt_start(query: CallbackQuery, state: FSMContext) -> None:
  user_id = query.from_user.id
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is not None:
    await query.answer("عندك قطة بالفعل.", show_alert=True)
    return

  await state.set_state(AdoptFlow.waiting_name)
  await query.answer()
  if query.message:
    await query.message.answer("🐾 شنو تريد تسمي قطتك؟ أرسل الاسم فقط.")


@router.message(AdoptFlow.waiting_name)
async def receive_adopt_name(message: Message, state: FSMContext) -> None:
  name = (message.text or "").strip()
  if not name:
    await message.answer("أرسل اسم القطة كنص.")
    return
  if len(name) > 40:
    await message.answer("اسم القطة طويل جداً، خلّه أقل من 40 حرفاً.")
    return

  user_id = message.from_user.id
  cat, created = await _get_or_create_cat(user_id, name)
  await state.clear()
  await _send_adopted(message, cat, newly_adopted=created)


@router.message(Command("adopt", "تبني", "تبنّي"))
async def cmd_adopt(message: Message) -> None:
  user_id = message.from_user.id
  parts = (message.text or "").split(maxsplit=1)
  name = parts[1].strip() if len(parts) > 1 else "لوز"
  if len(name) > 40:
    await message.answer("اسم القطة طويل جداً، خلّه أقل من 40 حرفاً.")
    return

  cat, created = await _get_or_create_cat(user_id, name)
  await _send_adopted(message, cat, newly_adopted=created)
