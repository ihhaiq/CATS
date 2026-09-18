"""Small Telegram helpers shared by Rich Message callback handlers."""
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


async def edit_callback_rich_message(query: CallbackQuery, rich_message) -> bool:
    """Edit a callback message and treat Telegram's no-op edit as success."""
    try:
        if query.inline_message_id:
            await query.bot.edit_message_text(
                inline_message_id=query.inline_message_id,
                rich_message=rich_message,
            )
        elif query.message:
            await query.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                rich_message=rich_message,
            )
        else:
            return False
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).casefold():
            return False
        raise
    return True
