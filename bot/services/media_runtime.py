"""Runtime bridge: filesystem assets first, Telegram file_id as cache/fallback."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiogram.types import FSInputFile

from bot.config import settings
from bot.services.cat_assets import (
    file_sha256,
    get_age_stage,
    resolve_cat_visual_state,
    resolve_local_asset,
)
from bot.services.local_store import (
    get_media_cache_entry,
    get_media_file_id_sync,
    get_media_override,
    get_media_type_sync,
    set_media_cache_entry,
)

logger = logging.getLogger("catibot.media_runtime")
_upload_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class ResolvedCatMedia:
    file_id: str
    media_type: str
    visual_state: str
    source: str
    cache_key: str | None = None
    path: str | None = None


def _lock_for(cache_key: str) -> asyncio.Lock:
    lock = _upload_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _upload_locks[cache_key] = lock
    return lock


def _settings_fallback_id(state: str) -> str:
    legacy_name = {
        "idle": "status",
        "angry": "cat_angry_sleep",
    }.get(state, state)
    return getattr(settings, f"{legacy_name}_media_file_id", "") or ""


async def _upload_local_asset(
    bot: Any,
    path: Path,
    *,
    upload_chat_id: int | str | None,
) -> str:
    target = settings.media_cache_chat_id or upload_chat_id
    if not bot or not target:
        return ""

    sent = await bot.send_photo(
        chat_id=target,
        photo=FSInputFile(str(path)),
        disable_notification=True,
    )
    photos = getattr(sent, "photo", None) or []
    if not photos:
        return ""
    file_id = photos[-1].file_id

    # The upload message is only a transport mechanism for obtaining a reusable
    # file_id. Delete it best-effort so users/cache chats are not cluttered.
    message_id = getattr(sent, "message_id", None)
    if message_id is not None:
        try:
            await bot.delete_message(chat_id=target, message_id=message_id)
        except Exception as exc:  # cache creation succeeded; deletion is cosmetic
            logger.debug("Could not delete media cache upload: %s", exc)
    return file_id


async def resolve_cat_media(
    bot: Any,
    cat: dict,
    requested_state: str = "status",
    *,
    upload_chat_id: int | str | None = None,
    assets_root: Path | None = None,
) -> ResolvedCatMedia | None:
    """Resolve media with filesystem as the primary source of truth.

    Precedence:
      1. explicit admin override
      2. local filesystem asset (with adult/legacy local fallback)
         - reuse Telegram cache when hash matches
         - lazy upload and refresh cache when missing/stale
      3. legacy JSON file_id
      4. legacy environment file_id
    """
    visual_state = resolve_cat_visual_state(
        cat,
        requested_state,
        hunger_threshold=settings.hunger_alert_threshold,
    )
    breed = str(cat.get("breed") or "")
    age_stage = get_age_stage(cat.get("age_days", 30))

    override = await get_media_override(visual_state, breed, age_stage)
    if override:
        return ResolvedCatMedia(
            file_id=str(override["file_id"]),
            media_type=str(override.get("media_type") or "photo"),
            visual_state=visual_state,
            source="admin_override",
        )

    local = resolve_local_asset(
        breed,
        age_stage,
        visual_state,
        root=assets_root,
    )
    if local is not None:
        asset_hash = file_sha256(local.path)
        cached = await get_media_cache_entry(local.cache_key)
        if (
            cached
            and cached.get("file_id")
            and cached.get("file_hash") == asset_hash
        ):
            return ResolvedCatMedia(
                file_id=str(cached["file_id"]),
                media_type=str(cached.get("media_type") or "photo"),
                visual_state=visual_state,
                source="local_cache",
                cache_key=local.cache_key,
                path=local.relative_path,
            )

        async with _lock_for(local.cache_key):
            # Another concurrent request may have populated the cache while we
            # waited for the per-asset lock.
            cached = await get_media_cache_entry(local.cache_key)
            if (
                cached
                and cached.get("file_id")
                and cached.get("file_hash") == asset_hash
            ):
                return ResolvedCatMedia(
                    file_id=str(cached["file_id"]),
                    media_type=str(cached.get("media_type") or "photo"),
                    visual_state=visual_state,
                    source="local_cache",
                    cache_key=local.cache_key,
                    path=local.relative_path,
                )

            try:
                file_id = await _upload_local_asset(
                    bot,
                    local.path,
                    upload_chat_id=upload_chat_id,
                )
            except Exception as exc:
                logger.warning(
                    "Local cat asset upload failed path=%s: %s",
                    local.path,
                    exc,
                )
                file_id = ""

            if file_id:
                await set_media_cache_entry(
                    local.cache_key,
                    file_id=file_id,
                    file_hash=asset_hash,
                    media_type="photo",
                    path=local.relative_path,
                )
                return ResolvedCatMedia(
                    file_id=file_id,
                    media_type="photo",
                    visual_state=visual_state,
                    source="local_upload",
                    cache_key=local.cache_key,
                    path=local.relative_path,
                )

    legacy_lookup_states = [visual_state]
    original_request = str(requested_state or "").strip().lower()
    if original_request and original_request not in legacy_lookup_states:
        legacy_lookup_states.append(original_request)

    for legacy_state in legacy_lookup_states:
        legacy_file_id = get_media_file_id_sync(
            legacy_state,
            breed,
            age_stage,
        )
        if legacy_file_id:
            return ResolvedCatMedia(
                file_id=legacy_file_id,
                media_type=get_media_type_sync(
                    legacy_state,
                    breed,
                    age_stage,
                ),
                visual_state=visual_state,
                source="legacy_json",
            )

    env_file_id = _settings_fallback_id(visual_state)
    if env_file_id:
        return ResolvedCatMedia(
            file_id=env_file_id,
            media_type="photo",
            visual_state=visual_state,
            source="legacy_env",
        )
    return None
