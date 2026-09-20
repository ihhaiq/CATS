"""Inline mode for quick, read-only cat status previews in groups."""
import html
from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from bot.services.local_store import (
    action_block_reason,
    apply_care_effects,
    apply_decay,
    ensure_user,
    finish_sleep,
    fullness_percent,
    get_latest_cat_for_user,
    get_user_cat,
    is_sleeping,
    sleep_duration_text,
    sleep_need_percent,
    sleep_remaining_minutes,
    update_cat,
    user_action_lock,
)

router = Router(name="inline")

_ALIASES = {
    "": "status",
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
    "relax": "relax",
    "استلقاء": "relax",
    "استرخاء": "relax",
    "تلفاز": "relax",
}


def _state_text(cat: dict) -> str:
    return (
        f"🐾 {html.escape(str(cat['name']))}\n"
        f"السلالة: {html.escape(str(cat['breed']))} | #{html.escape(str(cat['id_number']))}\n"
        f"الشبع: {fullness_percent(cat)}/100\n"
        f"السعادة: {cat['happiness']}/100\n"
        f"الحب: {cat['love_bar']}/100\n"
        f"الثقة: {cat.get('trust', 60)}/100\n"
        f"الملل: {cat.get('boredom', 10)}/100\n"
        f"الراحة: {sleep_need_percent(cat)}/100"
    )


@router.inline_query()
async def inline_cat(inline_query: InlineQuery) -> None:
    requested = inline_query.query.strip().casefold()
    action = _ALIASES.get(requested)
    if action is None:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    user_id = inline_query.from_user.id
    async with user_action_lock(user_id):
        await ensure_user(user_id)
        cat = await get_user_cat(user_id)
        if cat is None:
            latest = await get_latest_cat_for_user(user_id)
            if latest is not None and latest.get("is_fled"):
                text = "💨 قطتك هربت بسبب الإهمال، وما عادت أفعال العناية متاحة."
                title = "💨 هربت قطتك"
            else:
                text = "🐾 ما عندك قطة بعد. أرسل /adopt اسم_القطة إلى البوت أولاً."
                title = "لا توجد قطة"
        else:
            apply_decay(cat)
            finish_sleep(cat)
            await update_cat(cat)
            if cat.get("is_fled"):
                title = "💨 هربت قطتك"
                text = "وصل الحب إلى 0 بسبب الإهمال، وما عادت أفعال العناية متاحة."
            elif action in {"feed", "play", "walk", "relax"}:
                if is_sleeping(cat):
                    title = "😴 القطة نائمة"
                    text = (
                        "ما تگدر تسوي هذا الفعل هسه. باقي تقريباً "
                        f"{sleep_duration_text(sleep_remaining_minutes(cat))}.\n"
                        + _state_text(cat)
                    )
                else:
                    block_reason = action_block_reason(cat, action)
                    if block_reason:
                        title = "الفعل مو مناسب هسه"
                        reason = {
                            "full": "😺 القطة شبعانة وما تحتاج أكل زيادة.",
                            "starving": "🚨🍖 أطعمها أولاً قبل اللعب أو النزهة.",
                            "tired": "🪫 خليها تنام قبل اللعب أو النزهة.",
                            "bored_of_play": "😾 ملت من نفس اللعب؛ غيّر النشاط.",
                        }.get(block_reason, "هذا الفعل مو مناسب لحالتها الحالية.")
                        text = reason + "\n" + _state_text(cat)
                    else:
                        preview = dict(cat)
                        apply_care_effects(preview, action)
                        title = {
                            "feed": "معاينة الإطعام",
                            "play": "معاينة اللعب",
                            "walk": "معاينة النزهة",
                            "relax": "معاينة الاستلقاء",
                        }[action]
                        icon = {
                            "feed": "🍖",
                            "play": "🎾",
                            "walk": "🌿",
                            "relax": "🛋",
                        }[action]
                        text = (
                            f"{icon} معاينة فقط — ما تغير حالة القطة فعلياً\n"
                            + _state_text(preview)
                        )
            else:
                title = "حالة قطتك"
                text = _state_text(cat)

    result = InlineQueryResultArticle(
        id=f"catibot-{action}",
        title=title,
        description=text.replace("\n", " ")[:100],
        input_message_content=InputTextMessageContent(message_text=text),
    )
    await inline_query.answer([result], cache_time=1, is_personal=True)
