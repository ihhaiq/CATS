"""Small helpers every handler needs, so none of them reinvent reply plumbing."""
from __future__ import annotations

import logging

from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.core import keyboards as kb
from bot.core import texts
from bot.domain.entities import CatData, UserData
from bot.services.cat_service import CatService
from bot.services.image_renderer import render_cat

logger = logging.getLogger("catibot.reply")


def target_message(event: Message | CallbackQuery) -> Message | None:
    return event if isinstance(event, Message) else event.message


async def reply_text(event: Message | CallbackQuery, text: str, markup=None) -> None:
    msg = target_message(event)
    if msg is None:
        return
    if isinstance(event, CallbackQuery) and msg.photo is None and msg.text is not None:
        try:
            await msg.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass  # message unchanged or too old — fall through to a new one
    await msg.answer(text, reply_markup=markup)


async def send_cat_card(
    event: Message | CallbackQuery,
    service: CatService,
    user: UserData,
    cat: CatData,
    *,
    guest: bool,
    header: str = "",
) -> None:
    """Render the cat, then send picture + card + action keyboard as one message."""
    result = await service.refresh(cat)
    cat = result.cat
    msg = target_message(event)
    if msg is None:
        return

    if cat.is_fled:
        await msg.answer(texts.fled_card(cat), reply_markup=kb.fled_actions())
        return

    caption = texts.cat_card(cat, user, emotion=result.emotion, guest=guest)
    if header:
        caption = f"{header}\n\n{caption}"

    markup = kb.cat_actions(cat, cooldowns=service.cooldowns_for(cat), guest=guest)
    try:
        photo = BufferedInputFile(
            render_cat(cat, result.emotion), filename=f"cat_{cat.id_number}.png"
        )
        await msg.answer_photo(photo, caption=caption, reply_markup=markup)
    except Exception as exc:
        # Never let an image problem swallow the state update.
        logger.warning("photo send failed, falling back to text: %s", exc)
        await msg.answer(caption, reply_markup=markup)
