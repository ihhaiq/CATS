"""Guest Mode replies for messages that summon the bot by username."""
import logging
import random
import re
from datetime import datetime

from aiogram import Router
from aiogram.types import InlineQueryResultArticle, InputRichMessageContent, InputTextMessageContent, Message

from bot.services.economy import assign_random_breed
from bot.services.local_store import apply_care_effects, apply_decay, ensure_user, finish_sleep, get_user_cat, update_cat
from bot.services.local_store import create_cat, now_iso
from bot.services.local_store import get_user_points
from bot.services.rich_card import build_rich_card
from bot.services.shop import list_items, open_shop
from bot.services.shop_card import build_shop_card

router = Router(name="guest")
logger = logging.getLogger("catibot.guest")

_ALIASES = {
    "status": "status",
    "cat": "status",
    "state": "status",
    "حالة": "status",
    "الحالة": "status",
    "قطتي": "status",

    "feed": "feed",
    "food": "feed",
    "eat": "feed",
    "اطعام": "feed",
    "طعام": "feed",
    "اكل": "feed",
    "أكل": "feed",

    "play": "play",
    "لعب": "play",

    "walk": "walk",
    "نزهة": "walk",
    "نزه": "walk",
    "تمشية": "walk",

    "talk": "talk",
    "chat": "talk",
    "تحدث": "talk",
    "احجي": "talk",

    "sleep": "sleep",
    "نوم": "sleep",
    "نام": "sleep",

    "wake": "wake",
    "ايقاظ": "wake",
    "إيقاظ": "wake",
    "صحّي": "wake",
    "صحي": "wake",

    "adopt": "adopt",
    "تبني": "adopt",
    "تبنّي": "adopt",

    "shop": "shop",
    "store": "shop",
    "متجر": "shop",

    "help": "help",
    "guide": "help",
    "دليل": "help",
    "مساعدة": "help",
}

_GUEST_HELP = (
    "🐾 أوامر Catibot في وضع الضيف:\n"
    "حالة / status\n"
    "إطعام / feed\n"
    "لعب / play\n"
    "نزهة / walk\n"
    "تحدث / talk\n"
    "نوم / sleep\n"
    "إيقاظ / wake\n"
    "متجر / shop\n"
    "تبني اسم / adopt name"
)



async def _build_guest_card(message: Message, caller, cat: dict, points: int, state: str = "status"):
    return await build_rich_card(
        message.bot,
        cat,
        points,
        state,
        upload_chat_id=caller.id,
    )


def _state_text(cat: dict) -> str:
    return (
        f"🐾 {cat['name']}\n"
        f"السلالة: {cat['breed']} | #{cat['id_number']}\n"
        f"الجوع: {cat['hunger']}/100\n"
        f"السعادة: {cat['happiness']}/100\n"
        f"الحب: {cat['love_bar']}/100"
    )


def _normalize_command(value: str) -> str:
    value = value.casefold().strip()
    value = value.replace("ـ", "")
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = value.strip("!?؟.,،:;؛()[]{}<>«»'\"")
    return value


def _requested_command(message: Message) -> tuple[str | None, str]:
    text = (message.text or message.caption or "").strip()
    if not text:
        return None, ""

    # Guest invocation may include the @bot mention in the text. Remove mention
    # tokens wherever Telegram leaves them, then parse the actual command.
    words = [
        word
        for word in text.split()
        if not word.startswith("@")
    ]
    if not words:
        return "help", ""

    command = _normalize_command(
        words[0].lstrip("/").split("@", 1)[0]
    )
    argument = " ".join(words[1:]).strip()
    return _ALIASES.get(command), argument



@router.guest_message()
async def guest_message(message: Message) -> None:
    if not message.guest_query_id:
        logger.warning("Guest update without guest_query_id: %r", message.text)
        return

    caller = message.from_user or message.guest_bot_caller_user
    if caller is None:
        logger.warning(
            "Guest query has no caller user: chat_id=%s text=%r",
            message.chat.id,
            message.text,
        )
        return

    action, argument = _requested_command(message)
    logger.info(
        "Guest query user_id=%s text=%r action=%r",
        caller.id,
        message.text or message.caption,
        action,
    )
    if action is None:
        result = InlineQueryResultArticle(
            id="guest-help-unknown",
            title="دليل Catibot",
            description="الأمر غير معروف — افتح قائمة الأوامر",
            input_message_content=InputTextMessageContent(
                message_text=_GUEST_HELP
            ),
        )
        await message.bot.answer_guest_query(message.guest_query_id, result)
        return

    if action == "help":
        result = InlineQueryResultArticle(
            id="guest-help",
            title="دليل Catibot",
            description="الأوامر العربية والإنكليزية",
            input_message_content=InputTextMessageContent(
                message_text=_GUEST_HELP
            ),
        )
        await message.bot.answer_guest_query(message.guest_query_id, result)
        return
    if action == "shop":
        user_id = caller.id
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
        user_id = caller.id
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
                "rest_level": 100,
                "rest_updated_at": stamp,
            }
            await create_cat(cat)
            text = (
                f"🐾 تم تبني {cat['name']} من Guest Mode!\n"
                f"السلالة: {cat['breed']} | الرقم: #{cat['id_number']}\n"
                "استخدم @RichsCatBot حالة لمشاهدة الحالة."
            )
            title = "تم التبني"
    elif action != "adopt":
        user_id = caller.id
        await ensure_user(user_id)
        cat = await get_user_cat(user_id)
        if cat is None:
            text = "🐾 ما عندك قطة بعد. افتح محادثة البوت وأرسل /تبني اسم_القطة أولاً."
            title = "لا توجد قطة"
        else:
            apply_decay(cat)
            finish_sleep(cat)
            await update_cat(cat)
            if action == "status":
                result = InlineQueryResultArticle(
                    id="guest-status",
                    title="حالة القطة",
                    description=f"{cat['name']} | الجوع {cat['hunger']}% | السعادة {cat['happiness']}%",
                    input_message_content=InputRichMessageContent(
                        rich_message=await _build_guest_card(
                            message,
                            caller,
                            cat,
                            await get_user_points(user_id),
                            "status",
                        ),
                    ),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            if action == "feed":
                preview = dict(cat)
                apply_care_effects(preview, "feed")
                card = await _build_guest_card(message, caller, preview, await get_user_points(user_id), "feed")
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
                apply_care_effects(preview, "play")
                card = await _build_guest_card(message, caller, preview, await get_user_points(user_id), "play")
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
                apply_care_effects(preview, "walk")
                card = await _build_guest_card(message, caller, preview, await get_user_points(user_id), "walk")
                result = InlineQueryResultArticle(
                    id="guest-walk",
                    title="معاينة النزهة",
                    description=f"{cat['name']} بعد النزهة",
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            elif action == "talk":
                card = await _build_guest_card(message, caller, cat, await get_user_points(user_id), "talk")
                result = InlineQueryResultArticle(
                    id="guest-talk",
                    title="التحدث مع القطة",
                    description=cat["name"],
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            elif action == "sleep":
                card = await _build_guest_card(message, caller, cat, await get_user_points(user_id), "sleep")
                result = InlineQueryResultArticle(
                    id="guest-sleep",
                    title="نوم القطة",
                    description=cat["name"],
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            elif action == "wake":
                card = await _build_guest_card(message, caller, cat, await get_user_points(user_id), "status")
                result = InlineQueryResultArticle(
                    id="guest-wake",
                    title="إيقاظ القطة",
                    description=cat["name"],
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