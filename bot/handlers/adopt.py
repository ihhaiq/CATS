"""Adoption and onboarding handlers."""
from datetime import datetime
import html
import random

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bot.services.economy import ACTIVE_BREEDS, assign_random_breed
from bot.services.local_store import (
  create_cat,
  ensure_user,
  get_user_cat,
  now_iso,
  update_cat,
  user_action_lock,
)

router = Router(name="adopt")

_BREED_LABELS = {
  "siamese": "Siamese",
  "black": "سوداء",
}


class AdoptFlow(StatesGroup):
  waiting_breed = State()
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


def _breed_keyboard() -> InlineKeyboardMarkup:
  return InlineKeyboardMarkup(
    inline_keyboard=[
      [
        InlineKeyboardButton(
          text="🐱 Siamese",
          callback_data="adopt:breed:siamese",
        ),
        InlineKeyboardButton(
          text="🐈‍⬛ سوداء",
          callback_data="adopt:breed:black",
        ),
      ]
    ]
  )


def _breed_label(breed: str) -> str:
  return _BREED_LABELS.get(breed, breed)


def _breed_change_card(cat: dict) -> InputRichMessage:
  current = html.escape(_breed_label(str(cat.get("breed") or "")))
  return InputRichMessage(
    html=f"""
<h2>🐾 تغيير سلالة القطة</h2>
<p>السلالة الحالية: <b>{current}</b></p>
<p>التغيير اختياري. إذا ما تريد تغيّرها، تبقى قطتك الحالية وتستمر بشكل طبيعي.</p>
<tg-button-row align="center">
<tg-button type="callback_data" style="secondary" data="cat:breed:siamese">🐱 Siamese</tg-button>
<tg-button type="callback_data" style="secondary" data="cat:breed:black">🐈‍⬛ سوداء</tg-button>
</tg-button-row>
""".strip(),
    is_rtl=True,
  )


def _adopted_card(
  cat: dict,
  *,
  newly_adopted: bool = True,
  show_breed_notice: bool = False,
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
  breed_notice = (
    "<h3>⚠️ سلالة قطتك معطلة مؤقتًا من التبنّي الجديد، "
    "لكن قطتك تستمر وتشتغل بشكل طبيعي.</h3>"
    "<tg-button-row align=\"center\">"
    "<tg-button type=\"callback_data\" style=\"secondary\" data=\"cat:breed:choose\">تغيير</tg-button>"
    "</tg-button-row>"
    if show_breed_notice and cat.get("breed") not in ACTIVE_BREEDS
    else ""
  )
  return InputRichMessage(
    html=f"""
<h2>{heading}</h2>
<p>السلالة: {html.escape(str(cat['breed']))}</p>
<p>رقمها: #{html.escape(str(cat['id_number']))}</p>
{breed_notice}
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
    rich_message=_adopted_card(
      cat,
      newly_adopted=newly_adopted,
      show_breed_notice=not newly_adopted,
    ),
  )


async def _create_cat_for_user(
  user_id: int,
  name: str,
  breed: str,
) -> dict:
  if breed not in ACTIVE_BREEDS:
    breed = assign_random_breed()

  stamp = now_iso()
  cat = {
    "owner_id": user_id,
    "partner_id": None,
    "adopted_at": stamp,
    "name": name,
    "title": "الأليف",
    "id_number": str(random.randint(100000, 999999)),
    "breed": breed,
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
    "last_toy": None,
    "last_relax": None,
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


async def _get_or_create_cat(
  user_id: int,
  name: str,
  breed: str,
) -> tuple[dict, bool]:
  async with user_action_lock(user_id):
    await ensure_user(user_id)
    existing = await get_user_cat(user_id)
    if existing is not None:
      return existing, False
    return await _create_cat_for_user(user_id, name, breed), True


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
  await ensure_user(message.from_user.id)
  cat = await get_user_cat(message.from_user.id)
  if cat is not None:
    await message.bot.send_rich_message(
      chat_id=message.chat.id,
      rich_message=_adopted_card(
        cat,
        newly_adopted=False,
        show_breed_notice=True,
      ),
    )
    return
  await message.answer(
    "🐾 <b>أهلاً بك في Catibot</b>\n\n"
    "هنا راح تتبنّى قطتك الخاصة وتعتني بيها يوم بعد يوم. "
    "تحتاج تطعمها، تلعب وياها، تطلعها بنزهة وتخليها ترتاح وتنام بوقتها.\n\n"
    "كل فعل يأثر على حالتها، سعادتها وحبها إلك، فحاول لا تهملها 😼\n\n"
    "ابدأ من الزر أدناه واختار قطتك واسمها.",
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
      "• 🧸 اللعبة ترفع السعادة والحب وتقتل الملل، بس إذا تكررها هواية راح تمل منها.\n"
      "• 😴 عداد الراحة ينزل بسرعة ويرتفع ببطء، يعني القطة تحتاج نوم فعلي وكافي.\n"
      "• 🌀 الأكل واللعب والتفاعل المتنوع يقللون الملل، لكن تكرار نفس الحديث أو النزهة والنوم الطويل يزيدوه.\n"
      "• 🤝 الثقة تزيد بالرعاية الثابتة، وتنزل إذا خليتها بدون أكل فترة طويلة أو أهملتها بقوة.\n"
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

  await state.clear()
  await state.set_state(AdoptFlow.waiting_breed)
  await query.answer()
  if query.message:
    await query.message.answer(
      "🐾 اختار نوع قطتك:",
      reply_markup=_breed_keyboard(),
    )


@router.callback_query(F.data.startswith("adopt:breed:"))
async def cb_adopt_breed(query: CallbackQuery, state: FSMContext) -> None:
  breed = (query.data or "").rsplit(":", maxsplit=1)[-1]
  if breed not in ACTIVE_BREEDS:
    await query.answer("هذا النوع مو متاح حاليًا.", show_alert=True)
    return

  user_id = query.from_user.id
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is not None:
    await state.clear()
    await query.answer("عندك قطة بالفعل.", show_alert=True)
    return

  data = await state.get_data()
  pending_name = str(data.get("pending_name") or "").strip()

  if pending_name:
    cat, created = await _get_or_create_cat(
      user_id,
      pending_name,
      breed,
    )
    await state.clear()
    await query.answer(f"🐾 اخترت {_breed_label(breed)}.")
    if query.message:
      await _send_adopted(
        query.message,
        cat,
        newly_adopted=created,
      )
    return

  await state.update_data(breed=breed)
  await state.set_state(AdoptFlow.waiting_name)
  await query.answer(f"🐾 اخترت {_breed_label(breed)}.")
  if query.message:
    await query.message.answer("شنو تريد تسمي قطتك؟ أرسل الاسم فقط.")


@router.message(AdoptFlow.waiting_name)
async def receive_adopt_name(message: Message, state: FSMContext) -> None:
  name = (message.text or "").strip()
  if not name:
    await message.answer("أرسل اسم القطة كنص.")
    return
  if len(name) > 40:
    await message.answer("اسم القطة طويل جداً، خلّه أقل من 40 حرفاً.")
    return

  data = await state.get_data()
  breed = str(data.get("breed") or "")
  if breed not in ACTIVE_BREEDS:
    await state.clear()
    await state.set_state(AdoptFlow.waiting_breed)
    await message.answer(
      "اختار نوع قطتك أولاً:",
      reply_markup=_breed_keyboard(),
    )
    return

  user_id = message.from_user.id
  cat, created = await _get_or_create_cat(user_id, name, breed)
  await state.clear()
  await _send_adopted(message, cat, newly_adopted=created)


@router.message(Command("adopt", "تبني", "تبنّي"))
async def cmd_adopt(message: Message, state: FSMContext) -> None:
  user_id = message.from_user.id
  await ensure_user(user_id)

  existing = await get_user_cat(user_id)
  if existing is not None:
    await _send_adopted(message, existing, newly_adopted=False)
    return

  parts = (message.text or "").split(maxsplit=1)
  name = parts[1].strip() if len(parts) > 1 else "لوز"
  if len(name) > 40:
    await message.answer("اسم القطة طويل جداً، خلّه أقل من 40 حرفاً.")
    return

  await state.clear()
  await state.update_data(pending_name=name)
  await state.set_state(AdoptFlow.waiting_breed)
  await message.answer(
    "🐾 اختار نوع قطتك:",
    reply_markup=_breed_keyboard(),
  )


@router.callback_query(F.data == "cat:breed:choose")
async def cb_choose_breed(query: CallbackQuery) -> None:
  """Open the optional breed switcher for an existing cat."""
  user_id = query.from_user.id
  await ensure_user(user_id)
  cat = await get_user_cat(user_id)
  if cat is None:
    await query.answer("ما عندك قطة بعد.", show_alert=True)
    return

  await query.answer()
  if query.message:
    await query.message.bot.send_rich_message(
      chat_id=query.message.chat.id,
      rich_message=_breed_change_card(cat),
    )


@router.callback_query(
  F.data.in_({"cat:breed:siamese", "cat:breed:black"})
)
async def cb_change_breed(query: CallbackQuery) -> None:
  """Allow an existing owner to switch to one of the active breeds."""
  breed = (query.data or "").rsplit(":", maxsplit=1)[-1]

  user_id = query.from_user.id
  async with user_action_lock(user_id):
    await ensure_user(user_id)
    cat = await get_user_cat(user_id)
    if cat is None:
      await query.answer("ما عندك قطة بعد.", show_alert=True)
      return

    if cat.get("breed") == breed:
      await query.answer(
        f"قطتك من نوع {_breed_label(breed)} بالفعل."
      )
      return

    cat["breed"] = breed
    await update_cat(cat)

  await query.answer(
    f"🐾 تغيّرت قطتك إلى {_breed_label(breed)}."
  )
  if query.message:
    await _send_adopted(query.message, cat, newly_adopted=False)
