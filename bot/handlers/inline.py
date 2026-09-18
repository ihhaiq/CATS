"""Inline mode for quick, read-only cat status previews in groups."""
from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from bot.services.local_store import ensure_user, get_user_cat, refresh_cat_state, update_cat

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
}


def _state_text(cat: dict) -> str:
    return (
        f"🐾 {cat['name']}\n"
        f"السلالة: {cat['breed']} | #{cat['id_number']}\n"
        f"الجوع: {cat['hunger']}/100\n"
        f"السعادة: {cat['happiness']}/100\n"
        f"الحب: {cat['love_bar']}/100"
    )


@router.inline_query()
async def inline_cat(inline_query: InlineQuery) -> None:
    requested = inline_query.query.strip().casefold()
    action = _ALIASES.get(requested)
    if action is None:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    user_id = inline_query.from_user.id
    await ensure_user(user_id)
    cat = await get_user_cat(user_id)
    if cat is None:
        text = "🐾 ما عندك قطة بعد. أرسل /adopt اسم_القطة إلى البوت أولاً."
        title = "لا توجد قطة"
    else:
        refresh_cat_state(cat)
        await update_cat(cat)
        if action == "feed":
            preview = dict(cat)
            preview["hunger"] = max(0, preview["hunger"] - 30)
            title = "معاينة الإطعام"
            text = "🍖 معاينة بعد الإطعام\n" + _state_text(preview)
        elif action == "play":
            preview = dict(cat)
            preview["happiness"] = min(100, preview["happiness"] + 25)
            title = "معاينة اللعب"
            text = "🎾 معاينة بعد اللعب\n" + _state_text(preview)
        elif action == "walk":
            preview = dict(cat)
            preview["happiness"] = min(100, preview["happiness"] + 15)
            title = "معاينة النزهة"
            text = "🚶 معاينة بعد النزهة\n" + _state_text(preview)
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