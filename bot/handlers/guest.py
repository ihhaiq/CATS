"""Guest Mode replies for messages that summon the bot by username."""
import random
from datetime import datetime

from aiogram import Router
from aiogram.types import InlineQueryResultArticle, InputRichMessageContent, InputTextMessageContent, Message

from bot.services.economy import assign_random_breed
from bot.services.local_store import apply_decay, ensure_user, get_user_cat, update_cat
from bot.services.local_store import create_cat, now_iso
from bot.services.local_store import get_user_points
from bot.services.rich_card import build_rich_card
from bot.services.shop import list_items, open_shop
from bot.services.shop_card import build_shop_card

router = Router(name="guest")

_ALIASES = {
    "status": "status",
    "cat": "status",
    "حالة": "status",
    "قطتي": "status",
    "feed": "feed",
    "اطعام": "feed",
    "إطعام": "feed",
    "play": "play",
    "لعب": "play",
    "walk": "walk",
    "نزهة": "walk",
    "نزه": "walk",
    "adopt": "adopt",
    "تبني": "adopt",
    "تبنّي": "adopt",
    "shop": "shop",
    "متجر": "shop",
}


def _state_text(cat: dict) -> str:
    return (
        f"🐾 {cat['name']}\n"
        f"السلالة: {cat['breed']} | #{cat['id_number']}\n"
        f"الجوع: {cat['hunger']}/100\n"
        f"السعادة: {cat['happiness']}/100\n"
        f"الحب: {cat['love_bar']}/100"
    )


def _requested_command(message: Message) -> tuple[str | None, str]:
    text = (message.text or "").strip()
    words = text.split()
    if not words:
        return None, ""
    words = words[1:] if words[0].startswith("@") else words
    if not words:
        return None, ""
    command = words[0].lstrip("/").split("@", 1)[0].casefold()
    return _ALIASES.get(command), " ".join(words[1:]).strip()


@router.guest_message()
async def guest_message(message: Message) -> None:
    if not message.guest_query_id or not message.from_user:
        return

    action, argument = _requested_command(message)
    if action is None:
        return
    if action == "shop":
        user_id = message.from_user.id
        items = await open_shop(user_id)
        result = InlineQueryResultArticle(
            id="guest-shop",
            title="المتجر",
            description="افتح المتجر واشترِ بالأزرار",
            input_message_content=InputRichMessageContent(
                rich_message=build_shop_card(items, [], await get_user_points(user_id)),
            ),
        )
        await message.bot.answer_guest_query(message.guest_query_id, result)
        return
    if action == "adopt":
        user_id = message.from_user.id
        await ensure_user(user_id)
        if await get_user_cat(user_id):
            text = "🐾 عندك قطة بالفعل. استخدم @RichsCatBot حالة لمشاهدة حالتها."
            title = "لديك قطة بالفعل"
        elif not argument:
            text = "اكتب اسم القطة بعد الأمر، مثلاً: @RichsCatBot تبني لوز"
            title = "اسم القطة مطلوب"
        elif len(argument) > 40:
            text = "اسم القطة يجب أن يكون أقل من 40 حرفاً."
            title = "الاسم طويل"
        else:
            stamp = now_iso()
            cat = {
                "owner_id": user_id,
                "partner_id": None,
                "name": argument,
                "title": "الأليف",
                "id_number": str(random.randint(100000, 999999)),
                "breed": assign_random_breed(),
                "age_days": 30,
                "hunger": 20,
                "happiness": 100,
                "love_bar": 100,
                "partner_affinity": 0,
                "is_fled": False,
                "last_fed": stamp,
                "last_played": stamp,
                "last_walk": stamp,
                "last_decay_at": stamp,
                "sleep_day": datetime.utcnow().date().isoformat(),
                "slept_today_hours": 10.0,
                "sleep_until": None,
                "last_wake_at": stamp,
            }
            await create_cat(cat)
            text = (
                f"🐾 تم تبني {cat['name']} من Guest Mode!\n"
                f"السلالة: {cat['breed']} | الرقم: #{cat['id_number']}\n"
                "استخدم @RichsCatBot حالة لمشاهدة الحالة."
            )
            title = "تم التبني"
    elif action != "adopt":
        user_id = message.from_user.id
        await ensure_user(user_id)
        cat = await get_user_cat(user_id)
        if cat is None:
            text = "🐾 ما عندك قطة بعد. افتح محادثة البوت وأرسل /تبني اسم_القطة أولاً."
            title = "لا توجد قطة"
        else:
            apply_decay(cat)
            await update_cat(cat)
            if action == "status":
                result = InlineQueryResultArticle(
                    id="guest-status",
                    title="حالة القطة",
                    description=f"{cat['name']} | الجوع {cat['hunger']}% | السعادة {cat['happiness']}%",
                    input_message_content=InputRichMessageContent(
                        rich_message=build_rich_card(cat, await get_user_points(user_id)),
                    ),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            if action == "feed":
                preview = dict(cat)
                preview["hunger"] = max(0, preview["hunger"] - 30)
                card = build_rich_card(preview, await get_user_points(user_id), "feed")
                result = InlineQueryResultArticle(
                    id="guest-feed",
                    title="معاينة الإطعام",
                    description=f"{cat['name']} بعد الإطعام",
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            elif action == "play":
                preview = dict(cat)
                preview["happiness"] = min(100, preview["happiness"] + 25)
                card = build_rich_card(preview, await get_user_points(user_id), "play")
                result = InlineQueryResultArticle(
                    id="guest-play",
                    title="معاينة اللعب",
                    description=f"{cat['name']} بعد اللعب",
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            elif action == "walk":
                preview = dict(cat)
                preview["happiness"] = min(100, preview["happiness"] + 15)
                card = build_rich_card(preview, await get_user_points(user_id), "walk")
                result = InlineQueryResultArticle(
                    id="guest-walk",
                    title="معاينة النزهة",
                    description=f"{cat['name']} بعد النزهة",
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            else:
                text = _state_text(cat)
                title = "حالة القطة"

    result = InlineQueryResultArticle(
        id=f"guest-{action or 'help'}",
        title=title,
        description=text.replace("\n", " ")[:100],
        input_message_content=InputTextMessageContent(message_text=text),
    )
    await message.bot.answer_guest_query(message.guest_query_id, result)