"""Admin media uploader for age-aware Rich Message cat assets."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.services.cat_assets import (
    AGE_STAGES,
    BREED_POOL,
    CAT_STATES,
    inspect_cat_asset_library,
)
from bot.services.local_store import set_media_file

router = Router(name="media_dev")
pending: dict[int, tuple[str, str, str]] = {}

BREED_LABELS = {
    "orange_tabby": "برتقالي مخطط",
    "black": "أسود",
    "siamese": "سيامي",
    "british_shorthair_grey": "بريطاني رمادي",
    "calico": "كاليكو",
    "white": "أبيض",
}
AGE_LABELS = {
    "kitten": "kitten · صغير",
    "junior": "junior · ناشئ",
    "adult": "adult · بالغ",
    "senior": "senior · كبير",
}


def allowed(user_id: int) -> bool:
    return user_id in (settings.admin_ids or [])


def media_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼️ تحرير الوسائط", callback_data="media:edit")],
            [InlineKeyboardButton(text="🔎 فحص مكتبة القطط", callback_data="media:audit")],
        ]
    )


def breed_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=BREED_LABELS.get(breed, breed),
                callback_data=f"media:breed:{breed}",
            )
        ] for breed in BREED_POOL]
    )


def age_menu(breed: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=AGE_LABELS.get(age_stage, age_stage),
                callback_data=f"media:age:{breed}:{age_stage}",
            )
        ] for age_stage in AGE_STAGES]
    )


def state_menu(breed: str, age_stage: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=state,
                callback_data=f"media:state:{breed}:{age_stage}:{state}",
            )
        ] for state in CAT_STATES]
    )


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
async def choose_age(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    await query.answer()
    breed = query.data.split(":", 2)[2]
    await query.message.edit_text(
        f"السلالة: {breed}\nاختر مرحلة العمر:",
        reply_markup=age_menu(breed),
    )


@router.callback_query(F.data.startswith("media:age:"))
async def choose_state(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    await query.answer()
    _, _, breed, age_stage = query.data.split(":", 3)
    await query.message.edit_text(
        f"السلالة: {breed}\nالعمر: {age_stage}\nاختر الحالة:",
        reply_markup=state_menu(breed, age_stage),
    )


@router.callback_query(F.data.startswith("media:state:"))
async def request_media(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    _, _, breed, age_stage, state = query.data.split(":", 4)
    pending[query.from_user.id] = (breed, age_stage, state)
    await query.answer()
    await query.message.edit_text(
        "ارفع الآن الصورة/الفيديو.\n"
        f"السلالة: {breed}\n"
        f"العمر: {age_stage}\n"
        f"الحالة: {state}"
    )


@router.callback_query(F.data == "media:audit")
async def audit_assets(query: CallbackQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    report = inspect_cat_asset_library()
    await query.answer()
    lines = [
        "مكتبة الصور",
        f"✅ {report.present} / {report.total_expected}",
        f"❌ المتبقي: {report.missing_count}",
    ]
    if report.missing:
        lines.extend(["", "أول الملفات الناقصة:"])
        lines.extend(f"• {path}" for path in report.missing[:20])
        if report.missing_count > 20:
            lines.append(f"… و {report.missing_count - 20} ملف آخر")
    await query.message.edit_text("\n".join(lines), reply_markup=media_menu())


async def save(message: Message, file_id: str, media_type: str) -> None:
    if not allowed(message.from_user.id):
        return
    selection = pending.get(message.from_user.id)
    if not selection:
        return
    breed, age_stage, state = selection
    await set_media_file(
        state,
        file_id,
        media_type,
        breed=breed,
        age_stage=age_stage,
    )
    pending.pop(message.from_user.id, None)
    await message.answer(
        "تم حفظ الملف تلقائياً.\n"
        f"{breed} → {age_stage} → {state}"
    )


@router.message(lambda message: bool(message.photo))
async def save_photo(message: Message) -> None:
    await save(message, message.photo[-1].file_id, "photo")


@router.message(lambda message: bool(message.video))
async def save_video(message: Message) -> None:
    await save(message, message.video.file_id, "video")


@router.message(lambda message: bool(message.animation))
async def save_animation(message: Message) -> None:
    await save(message, message.animation.file_id, "video")
