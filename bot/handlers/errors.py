"""
One place where every uncaught handler exception lands.

Without this an exception means the user sees nothing at all and you find out
from a log you weren't reading. With it, the user gets an apology and you get a
stack trace tagged with the update that caused it.
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from bot.core import keyboards as kb
from bot.core import texts

logger = logging.getLogger("catibot.errors")

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    update = event.update
    logger.exception("unhandled error on update %s: %s", update.update_id, event.exception)

    try:
        if update.callback_query is not None:
            await update.callback_query.answer("⚠️ صار خطأ.", show_alert=False)
            if update.callback_query.message is not None:
                await update.callback_query.message.answer(
                    texts.ERROR_GENERIC, reply_markup=kb.back_to_menu()
                )
        elif update.message is not None:
            await update.message.answer(texts.ERROR_GENERIC, reply_markup=kb.back_to_menu())
    except Exception:
        logger.exception("failed to deliver the error notice")
    return True
