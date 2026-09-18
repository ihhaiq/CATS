"""Callbacks for Rich Message action buttons."""
import asyncio
import logging
import random
from datetime import datetime

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.services.action_locks import user_action_lock
from bot.services.economy import check_cooldown
from bot.services.local_store import (
    award_points,
    clear_action_notice,
    ensure_user,
    get_user_cat,
    get_user_points,
    is_sleeping,
    parse_time,
    refresh_cat_state,
    set_action_notice,
    sleep_need_percent,
    start_sleep,
    update_cat,
    wake_now,
)
from bot.services.rich_card import build_rich_card
from bot.utils.telegram import edit_callback_rich_message

router = Router(name="rich_actions")
logger = logging.getLogger("catibot.rich_actions")

_NOTICE_SECONDS = 10
_ACTIONS = {"status", "feed", "play", "walk", "talk", "sleep", "wake"}


async def _edit_card(query: CallbackQuery, card) -> bool:
    return await edit_callback_rich_message(query, card)


def _default_media_kind(cat: dict) -> str:
    return "sleep" if is_sleeping(cat) else "status"


def _observe_task(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "delayed rich-card task failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def _schedule_notice_clear(query: CallbackQuery, user_id: int, notice_token: str) -> None:
    task = asyncio.create_task(
        _clear_notice_later(query, user_id, notice_token),
        name=f"clear-cat-notice:{user_id}",
    )
    task.add_done_callback(_observe_task)


async def _clear_notice_later(query: CallbackQuery, user_id: int, notice_token: str) -> None:
    await asyncio.sleep(_NOTICE_SECONDS)
    async with user_action_lock(user_id):
        cat = await get_user_cat(user_id)
        if cat is None:
            return

        # A newer action either removed this notice or replaced it with a new token.
        if not clear_action_notice(cat, expected_token=notice_token):
            return

        refresh_cat_state(cat)
        await update_cat(cat)
        points = await get_user_points(user_id)
        await _edit_card(
            query,
            build_rich_card(cat, points, _default_media_kind(cat)),
        )


def _parse_action_data(data: str) -> tuple[int | None, str | None]:
    parts = data.split(":")
    if len(parts) == 2:
        # Legacy cards created before owner-bound callback data.
        return None, parts[1]
    if len(parts) == 3 and parts[1].isdigit():
        return int(parts[1]), parts[2]
    return None, None


@router.callback_query(lambda query: query.data and query.data.startswith("cat:"))
async def handle_rich_action(query: CallbackQuery) -> None:
    owner_id, action = _parse_action_data(query.data)
    if action not in _ACTIONS:
        await query.answer()
        return

    if owner_id is not None and query.from_user.id != owner_id:
        await query.answer("هذه الأزرار خاصة بصاحب القطة.", show_alert=True)
        return

    user_id = owner_id or query.from_user.id
    async with user_action_lock(user_id):
        await _handle_rich_action(query, user_id, action)


async def _handle_rich_action(query: CallbackQuery, user_id: int, action: str) -> None:
    await ensure_user(user_id)
    cat = await get_user_cat(user_id)
    if cat is None:
        await query.answer("ما عندك قطة بعد.", show_alert=True)
        return

    clear_action_notice(cat)
    refresh_cat_state(cat)
    # Persist the refreshed clocks/decay even if this action exits on a cooldown.
    await update_cat(cat)

    if action == "status":
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), _default_media_kind(cat)),
        )
        await query.answer()
        return

    sleeping = is_sleeping(cat)
    if sleeping and action != "wake":
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "sleep"),
        )
        await query.answer("😴 القطة نائمة حالياً.", show_alert=True)
        return

    if action == "wake" and not sleeping:
        cat["wake_attempts"] = 0
        await update_cat(cat)
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "status"),
        )
        await query.answer("القطة مستيقظة بالفعل.")
        return

    if action == "wake" and cat.get("wake_attempts", 0) == 0:
        notice_token = set_action_notice(cat, "😾 القطة ترفض النهوض!")
        cat["wake_attempts"] = 1
        await update_cat(cat)
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    if action == "wake" and random.random() < 0.35:
        notice_token = set_action_notice(cat, "😾 القطة ترفض النهوض!")
        cat["wake_attempts"] = cat.get("wake_attempts", 0) + 1
        await update_cat(cat)
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    refusal_until = cat.get("action_refusal_until")
    if (
        refusal_until
        and datetime.utcnow().timestamp() < refusal_until
        and action in {"feed", "play", "walk", "talk"}
    ):
        notice_token = set_action_notice(cat, "😾 القطة ستقبل بعد دقائق قليلة!")
        await update_cat(cat)
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    if refusal_until:
        cat.pop("action_refusal_until", None)
    elif sleep_need_percent(cat) <= 65 and action in {"feed", "play", "walk", "talk"}:
        notice_token = set_action_notice(cat, "😾 القطة مرهقة وتحتاج النوم!")
        cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
        await update_cat(cat)
        await _edit_card(
            query,
            build_rich_card(cat, await get_user_points(user_id), "cat_angry_sleep"),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    cooldowns = {
        "feed": ("last_fed", settings.feed_cooldown),
        "play": ("last_played", settings.play_cooldown),
        "walk": ("last_walk", settings.walk_cooldown),
        "talk": ("last_talked", settings.talk_cooldown),
    }
    if action in cooldowns:
        timestamp_key, cooldown = cooldowns[action]
        last_action = cat.get(timestamp_key)
        if last_action:
            ready, left = check_cooldown(parse_time(last_action), cooldown)
            if not ready:
                await update_cat(cat)
                await _edit_card(
                    query,
                    build_rich_card(
                        cat,
                        await get_user_points(user_id),
                        _default_media_kind(cat),
                    ),
                )
                minutes = max(1, (left + 59) // 60)
                await query.answer(
                    f"هذا الفعل متاح بعد {minutes} دقيقة.",
                    show_alert=True,
                )
                return

    media_kind = action
    notice_token: str | None = None

    if action == "feed":
        cat["hunger"] = max(0, cat["hunger"] - 30)
        cat["last_fed"] = datetime.utcnow().isoformat()
        points = random.choice([0, 0, 2, 5, 8])
    elif action in {"play", "walk"} and random.random() < 0.2:
        media_kind = "cat_angry_sleep"
        points = 0
        notice_token = set_action_notice(cat, "😾 القطة تريد النوم!")
        cat["action_refusal_until"] = datetime.utcnow().timestamp() + random.randint(120, 300)
        # An attempted action consumes its cooldown even if the cat refuses it.
        cat["last_played" if action == "play" else "last_walk"] = datetime.utcnow().isoformat()
    elif action == "play":
        cat["happiness"] = min(100, cat["happiness"] + 25)
        cat["hunger"] = min(100, cat["hunger"] + 5)
        cat["last_played"] = datetime.utcnow().isoformat()
        points = random.choice([0, 1, 3, 5, 10])
        if random.random() < 0.15:
            notice_token = set_action_notice(cat, "🥰 نامت القطة على صدرك!")
    elif action == "walk":
        cat["happiness"] = min(100, cat["happiness"] + 15)
        cat["last_walk"] = datetime.utcnow().isoformat()
        points = random.choice([0, 2, 5, 10, 15])
    elif action == "talk":
        cat["happiness"] = min(100, cat["happiness"] + 5)
        cat["last_talked"] = datetime.utcnow().isoformat()
        points = random.choice([0, 1, 2, 4])
        if random.random() < 0.15:
            notice_token = set_action_notice(cat, "🥰 نامت القطة على صدرك!")
    elif action == "sleep":
        if cat["hunger"] > 70 or cat["happiness"] < 30:
            notice_token = set_action_notice(
                cat,
                "😾 القطة لا تستطيع النوم الآن، إنها تحتاج رعاية!",
            )
            await update_cat(cat)
            await _edit_card(
                query,
                build_rich_card(
                    cat,
                    await get_user_points(user_id),
                    "cat_angry_sleep",
                ),
            )
            await query.answer()
            _schedule_notice_clear(query, user_id, notice_token)
            return

        if random.random() < 0.25:
            notice_token = set_action_notice(cat, "😾 القطة رفضت النوم!")
            await update_cat(cat)
            await _edit_card(
                query,
                build_rich_card(
                    cat,
                    await get_user_points(user_id),
                    "cat_angry_sleep",
                ),
            )
            await query.answer()
            _schedule_notice_clear(query, user_id, notice_token)
            return

        start_sleep(cat)
        cat["wake_attempts"] = 0
        points = random.choice([0, 1, 2])
        media_kind = "sleep"
        if random.random() < 0.15:
            notice_token = set_action_notice(cat, "🥰 نامت القطة على صدرك!")
    elif action == "wake":
        wake_now(cat)
        cat["wake_attempts"] = 0
        media_kind = "status"
        points = 0
    else:
        await query.answer()
        return

    await update_cat(cat)
    balance = await get_user_points(user_id)
    if points:
        balance = await award_points(user_id, points, action)

    await _edit_card(query, build_rich_card(cat, balance, media_kind))
    await query.answer()
    if notice_token:
        _schedule_notice_clear(query, user_id, notice_token)
