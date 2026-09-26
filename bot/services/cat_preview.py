"""Compact Telegram link previews for local cat PNG assets."""
from __future__ import annotations

import html
import logging
from urllib.parse import quote

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions

from bot.config import settings
from bot.services.cat_assets import (
    get_age_stage,
    resolve_cat_visual_state,
    resolve_local_asset,
)
from bot.services.cat_events import active_hiding

logger = logging.getLogger("catibot.cat_preview")
ASSET_ROUTE_PREFIX = "/cat-assets"
_preview_messages: dict[tuple[int, str], int] = {}


def cat_preview_url(
    cat: dict,
    requested_state: str = "status",
    *,
    base_url: str | None = None,
) -> str:
    """Return a public URL for the local PNG that represents this cat state."""
    breed = str(cat.get("breed") or "")
    if not breed or breed == "black" or active_hiding(cat):
        return ""

    asset_state = {
        "toy": "play",
        "treat": "feed",
    }.get(requested_state, requested_state)
    visual_state = resolve_cat_visual_state(
        cat,
        asset_state,
        hunger_threshold=settings.hunger_alert_threshold,
    )
    age_stage = get_age_stage(cat.get("age_days", 30))
    asset = resolve_local_asset(breed, age_stage, visual_state)
    if asset is None:
        return ""

    origin = (base_url if base_url is not None else settings.public_asset_base_url)
    origin = str(origin or "").rstrip("/")
    if not origin:
        return ""

    relative = quote(asset.relative_path, safe="/")
    return f"{origin}{ASSET_ROUTE_PREFIX}/{relative}"


def _preview_key(chat_id: int, cat: dict) -> tuple[int, str]:
    cat_id = cat.get("cat_id") or cat.get("id_number") or cat.get("owner_id") or "cat"
    return chat_id, str(cat_id)


async def sync_cat_preview(
    bot,
    chat_id: int,
    cat: dict,
    requested_state: str = "status",
    *,
    force_new: bool = False,
) -> bool:
    """Create or update the compact link-preview message for a cat card.

    Returns True only when Telegram accepted a preview message. Callers can then
    omit the full Rich Message photo block. If previews are unavailable, callers
    should keep the existing embedded-media behavior.
    """
    url = cat_preview_url(cat, requested_state)
    if not url:
        return False

    key = _preview_key(chat_id, cat)
    previous_id = _preview_messages.get(key)
    preview_text = f"🐈 {html.escape(str(cat.get('name') or 'قطتك'))}"
    options = LinkPreviewOptions(
        url=url,
        prefer_small_media=True,
        show_above_text=True,
    )

    if force_new and previous_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=previous_id)
        except Exception:
            pass
        _preview_messages.pop(key, None)
        previous_id = None

    if previous_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=previous_id,
                text=preview_text,
                link_preview_options=options,
            )
            return True
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return True
            logger.debug("Could not edit cat preview; recreating it: %s", exc)
        except Exception as exc:
            logger.warning("Could not edit cat preview: %s", exc)
        _preview_messages.pop(key, None)

    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=preview_text,
            link_preview_options=options,
            disable_notification=True,
        )
    except Exception as exc:
        logger.warning("Could not send cat preview url=%s: %s", url, exc)
        return False

    _preview_messages[key] = sent.message_id
    return True
