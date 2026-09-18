"""Admin media uploader for Rich Message state assets."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.services.economy import BREED_POOL
from bot.services.local_store import set_media_file

router = Router(name="media_dev")
pending: dict[int, tuple[str | None, str]] = {}
KINDS = {"status", "feed", "play", "walk", "talk", "sleep", "cat_angry_sleep"}
BREED_LABELS = {
    "orange_tabby": "برتقالي مخطط",
    "black": "أسود",
    "siamese": "سيامي",
    "british_shorthair_grey": "بريطاني رمادي",
    "calico": "كاليكو",
    "white": "أبيض",
}
BREEDS = ["عام", *BREED_POOL]


def allowed(user_id: int) -> bool:
    return user_id in (settings.admin_ids or [])


def media_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼️ تحرير الوسائط", callback_data="media:edit")]])


def breed_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BREED_LABELS.get(breed, breed), callback_data=f"media:breed:{breed}")
    ] for breed in BREEDS])


def state_menu(breed: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=kind, callback_data=f"media:state:{breed}:{kind}")] for kind in sorted(KINDS)])


@router.message(Command("dev"))
async def dev_media(message: Message) -> None:
    if not allowed(message.from_user.id):
        await message.answer("هذا الأمر للأدمن فقط.")
        return
    await message.answer("🛠️ لوحة المطور", reply_markup=media_menu())


@router.callback_query(F.data == "media:edit")
async def choose_breed(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text("اختر السلالة:", reply_markup=breed_menu())


@router.callback_query(F.data.startswith("media:breed:"))
async def choose_state(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    await query.answer()
    breed = query.data.split(":", 2)[2]
    await query.message.edit_text(f"السلالة: {breed}\nاختر الحالة:", reply_markup=state_menu(breed))


@router.callback_query(F.data.startswith("media:state:"))
async def request_media(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    _, _, breed, kind = query.data.split(":", 3)
    pending[query.from_user.id] = (None if breed == "عام" else breed, kind)
    await query.answer()
    await query.message.edit_text(f"ارفع الآن ملف {kind} للسلالة {breed}.")


async def save(message: Message, file_id: str, media_type: str) -> None:
    if not allowed(message.from_user.id):
        return
    selection = pending.get(message.from_user.id)
    if not selection:
        return
    breed, kind = selection
    await set_media_file(kind, file_id, media_type, breed)
    pending.pop(message.from_user.id, None)
    await message.answer(f"تم حفظ ملف حالة {kind} للسلالة {breed or 'عام'} تلقائياً.")


@router.message(lambda message: bool(message.photo))
async def save_photo(message: Message) -> None:
    await save(message, message.photo[-1].file_id, "photo")


@router.message(lambda message: bool(message.video))
async def save_video(message: Message) -> None:
    await save(message, message.video.file_id, "video")


@router.message(lambda message: bool(message.animation))
async def save_animation(message: Message) -> None:
    await save(message, message.animation.file_id, "video")
