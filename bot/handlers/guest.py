"""Guest Mode replies for messages that summon the bot by username."""
import html
import logging
import random
import re
from datetime import datetime

from aiogram import Router
from aiogram.types import InlineQueryResultArticle, InputRichMessageContent, InputTextMessageContent, Message

from bot.config import settings
from bot.services.economy import assign_random_breed, check_cooldown
from bot.services.local_store import (
    action_block_reason,
    apply_care_effects,
    apply_decay,
    award_points,
    can_bypass_action_cooldown,
    care_reward_points,
    create_cat,
    ensure_user,
    finish_sleep,
    fullness_percent,
    get_user_cat,
    get_user_points,
    is_sleeping,
    now_iso,
    parse_time,
    sleep_duration_text,
    sleep_need_percent,
    sleep_remaining_minutes,
    start_sleep,
    update_cat,
    user_action_lock,
    wake_now,
)
from bot.services.rich_card import build_fled_card, build_rich_card
from bot.services.shop import open_shop
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
        f"🐾 {html.escape(str(cat['name']))}\n"
        f"السلالة: {html.escape(str(cat['breed']))} | #{html.escape(str(cat['id_number']))}\n"
        f"الشبع: {fullness_percent(cat)}/100\n"
        f"السعادة: {cat['happiness']}/100\n"
        f"الحب: {cat['love_bar']}/100\n"
        f"الثقة: {cat.get('trust', 60)}/100\n"
        f"الملل: {cat.get('boredom', 10)}/100"
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
    caller = message.from_user or message.guest_bot_caller_user
    if caller is None:
        await _guest_message_locked(message)
        return
    async with user_action_lock(caller.id):
        await _guest_message_locked(message)


async def _guest_message_locked(message: Message) -> None:
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
            text = (
                f"🐾 تم تبني {html.escape(str(cat['name']))} من Guest Mode!\n"
                f"السلالة: {html.escape(str(cat['breed']))} | الرقم: #{html.escape(str(cat['id_number']))}\n"
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
            woke = finish_sleep(cat)
            await update_cat(cat)
            if cat.get("is_fled"):
                result = InlineQueryResultArticle(
                    id="guest-fled",
                    title="💨 هربت قطتك",
                    description="وصل الحب إلى 0 بسبب الإهمال.",
                    input_message_content=InputRichMessageContent(
                        rich_message=build_fled_card(cat),
                    ),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return
            if action == "status":
                result = InlineQueryResultArticle(
                    id="guest-status",
                    title="حالة القطة",
                    description=f"{cat['name']} | الشبع {fullness_percent(cat)}% | السعادة {cat['happiness']}%",
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
            if action in {"feed", "play", "walk", "talk"}:
                if is_sleeping(cat):
                    card = await _build_guest_card(
                        message,
                        caller,
                        cat,
                        await get_user_points(user_id),
                        "status",
                    )
                    result = InlineQueryResultArticle(
                        id=f"guest-{action}-sleeping",
                        title="😴 القطة نائمة",
                        description=(
                            "باقي تقريباً "
                            f"{sleep_duration_text(sleep_remaining_minutes(cat))}. "
                            "صحّيها أولاً حتى تتفاعل وياها."
                        ),
                        input_message_content=InputRichMessageContent(rich_message=card),
                    )
                    await message.bot.answer_guest_query(message.guest_query_id, result)
                    return

                block_reason = action_block_reason(cat, action)
                if block_reason:
                    if block_reason == "full":
                        title = "😺 القطة شبعانة"
                        description = "ما تحتاج أكل زيادة هسه."
                    elif block_reason == "starving":
                        title = "🚨 الجوع أولاً"
                        description = "أطعمها قبل اللعب أو النزهة."
                    elif block_reason == "bored_of_play":
                        title = "😾 ملت من نفس اللعب"
                        description = "غيّر النشاط: حچي وياها أو طلّعها نزهة."
                    else:
                        title = "🪫 تحتاج نوم"
                        description = "خليها ترتاح قبل اللعب أو النزهة."
                    await update_cat(cat)
                    card = await _build_guest_card(
                        message,
                        caller,
                        cat,
                        await get_user_points(user_id),
                        "status",
                    )
                    result = InlineQueryResultArticle(
                        id=f"guest-{action}-blocked",
                        title=title,
                        description=description,
                        input_message_content=InputRichMessageContent(rich_message=card),
                    )
                    await message.bot.answer_guest_query(message.guest_query_id, result)
                    return

                timestamp_key = {
                    "feed": "last_fed",
                    "play": "last_played",
                    "walk": "last_walk",
                    "talk": "last_talk",
                }[action]
                cooldown = {
                    "feed": settings.feed_cooldown,
                    "play": settings.play_cooldown,
                    "walk": settings.walk_cooldown,
                    "talk": settings.talk_cooldown,
                }[action]
                last_action = cat.get(timestamp_key)
                if last_action:
                    ready, seconds_left = check_cooldown(
                        parse_time(last_action),
                        cooldown,
                    )
                else:
                    ready, seconds_left = True, 0

                need_bypass = can_bypass_action_cooldown(cat, action)
                bypassed = not ready and need_bypass
                if not ready and not need_bypass:
                    await update_cat(cat)
                    card = await _build_guest_card(
                        message,
                        caller,
                        cat,
                        await get_user_points(user_id),
                        "status",
                    )
                    result = InlineQueryResultArticle(
                        id=f"guest-{action}-cooldown",
                        title="⏳ فترة تهدئة",
                        description=f"ارجع بعد {max(1, seconds_left // 60)} دقيقة.",
                        input_message_content=InputRichMessageContent(rich_message=card),
                    )
                    await message.bot.answer_guest_query(message.guest_query_id, result)
                    return

                apply_care_effects(cat, action)
                cat[timestamp_key] = datetime.utcnow().isoformat()

                if action == "feed":
                    title = "🍖 تم الإطعام"
                elif action == "play":
                    if int(cat.get("same_action_streak", 1)) >= 5:
                        title = "😾 ملت من نفس اللعب"
                    else:
                        title = "🎾 لعبت وياها"
                elif action == "walk":
                    title = "🌿 طلعت نزهة"
                else:
                    title = "💬 حچيت وياها"

                points = care_reward_points(
                    cat,
                    action,
                    bypassed_cooldown=bypassed,
                )
                await update_cat(cat)
                if points:
                    balance = await award_points(user_id, points, action)
                else:
                    balance = await get_user_points(user_id)

                description = (
                    "⚡ التهدئة انفتحت للحاجة؛ الرعاية تنحسب بدون نقاط إضافية."
                    if bypassed
                    else cat["name"]
                )
                card = await _build_guest_card(
                    message,
                    caller,
                    cat,
                    balance,
                    action,
                )
                result = InlineQueryResultArticle(
                    id=f"guest-{action}",
                    title=title,
                    description=description,
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return

            elif action == "sleep":
                if is_sleeping(cat):
                    title = "😴 القطة نائمة أصلًا"
                    description = cat["name"]
                else:
                    rest_now = sleep_need_percent(cat)
                    if rest_now >= 98:
                        title = "😺 ما تحتاج تنام"
                        description = "طاقتها وراحتها شبه كاملة."
                    else:
                        planned_minutes = start_sleep(cat)
                        await update_cat(cat)
                        duration = sleep_duration_text(planned_minutes)
                        if cat.get("sleep_kind") == "main":
                            title = "😴 نامت القطة"
                            description = f"نوم رئيسي، تقريباً {duration}."
                        else:
                            title = "💤 أخذت قيلولة"
                            description = f"قيلولة، تقريباً {duration}."
                card = await _build_guest_card(
                    message,
                    caller,
                    cat,
                    await get_user_points(user_id),
                    "sleep" if is_sleeping(cat) else "status",
                )
                result = InlineQueryResultArticle(
                    id="guest-sleep",
                    title=title,
                    description=description,
                    input_message_content=InputRichMessageContent(rich_message=card),
                )
                await message.bot.answer_guest_query(message.guest_query_id, result)
                return

            elif action == "wake":
                if is_sleeping(cat):
                    rest_before_wake = sleep_need_percent(cat)
                    if wake_now(cat):
                        trust_loss = 0
                        if rest_before_wake < 30:
                            trust_loss = 3
                        elif rest_before_wake < 50:
                            trust_loss = 2
                        elif rest_before_wake < 70:
                            trust_loss = 1
                        if trust_loss:
                            cat["trust"] = max(
                                0,
                                int(cat.get("trust", 60)) - trust_loss,
                            )
                    await update_cat(cat)
                    title = "☀️ صحت القطة"
                    description = (
                        "صحّيتها بدري، فثقتها نزلت شوي."
                        if rest_before_wake < 70
                        else cat["name"]
                    )
                else:
                    title = "😺 صحت من نفسها" if woke else "😺 القطة صاحية أصلًا"
                    description = (
                        "خلص نومها قبل ما تطلب الإيقاظ."
                        if woke
                        else cat["name"]
                    )

                card = await _build_guest_card(
                    message,
                    caller,
                    cat,
                    await get_user_points(user_id),
                    "status",
                )
                result = InlineQueryResultArticle(
                    id="guest-wake",
                    title=title,
                    description=description,
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