"""Callbacks for Rich Message action buttons."""
import asyncio
import logging
import random
import secrets
from datetime import datetime

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.services.economy import check_cooldown
from bot.services.local_store import (
    apply_care_effects,
    apply_decay,
    award_points,
    clear_action_notice,
    ensure_user,
    finish_sleep,
    get_user_cat,
    get_user_points,
    is_sleeping,
    parse_time,
    sleep_need_percent,
    start_sleep,
    update_cat,
    wake_now,
)
from bot.services.rich_card import build_rich_card

router = Router(name="rich_actions")
logger = logging.getLogger("catibot.rich_actions")


async def _build_card(query: CallbackQuery, cat: dict, points: int, state: str = "status"):
    upload_chat_id = query.message.chat.id if query.message else query.from_user.id
    return await build_rich_card(
        query.bot,
        cat,
        points,
        state,
        upload_chat_id=upload_chat_id,
    )


def _set_action_notice(cat: dict, text: str) -> str:
    token = secrets.token_hex(8)
    cat["action_notice"] = text
    cat["action_notice_token"] = token
    return token


async def _edit_card(query: CallbackQuery, card) -> bool:
    """Edit a Rich Card and treat Telegram's no-op edit as success."""
    try:
        if query.inline_message_id:
            await query.bot.edit_message_text(
                inline_message_id=query.inline_message_id,
                rich_message=card,
            )
            return True
        if query.message:
            await query.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                rich_message=card,
            )
            return True
        return False
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def _clear_notice_later(
    query: CallbackQuery,
    user_id: int,
    notice_token: str,
) -> None:
    """Clear only the notice that scheduled this task.

    A fresh cat snapshot is loaded after the delay so an older task cannot
    overwrite newer state or clear a newer notice.
    """
    try:
        await asyncio.sleep(10)
        cat = await get_user_cat(user_id)
        if cat is None or cat.get("action_notice_token") != notice_token:
            return

        clear_action_notice(cat)
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, cat, await get_user_points(user_id), "status"),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Failed to clear action notice safely for user_id=%s",
            user_id,
        )


def _schedule_notice_clear(
    query: CallbackQuery,
    user_id: int,
    notice_token: str,
) -> None:
    asyncio.create_task(_clear_notice_later(query, user_id, notice_token))


@router.callback_query(lambda query: query.data and query.data.startswith("cat:"))
async def handle_rich_action(query: CallbackQuery) -> None:
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    await ensure_user(user_id)
    cat = await get_user_cat(user_id)
    if cat is None:
        await query.answer("ما عندك قطة بعد.", show_alert=True)
        return

    # Any new action invalidates an older temporary notice/task.
    clear_action_notice(cat)
    apply_decay(cat)
    woke = finish_sleep(cat)
    if woke:
        await update_cat(cat)

    if action == "status":
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, cat, await get_user_points(user_id), "status"),
        )
        await query.answer()
        return

    if is_sleeping(cat) and action != "wake":
        await update_cat(cat)
        await query.answer()
        return

    if action == "wake" and is_sleeping(cat):
        rest_now = sleep_need_percent(cat)
        attempts = int(cat.get("wake_attempts", 0))
        should_refuse = (
            (rest_now < 30 and attempts == 0)
            or (30 <= rest_now < 50 and random.random() < 0.20)
        )
        if should_refuse:
            notice_token = _set_action_notice(
                cat,
                "😾 بعدني تعبانة، خليني أنام شوي بعد!",
            )
            cat["wake_attempts"] = attempts + 1
            await update_cat(cat)
            await _edit_card(
                query,
                await _build_card(
                    query,
                    cat,
                    await get_user_points(user_id),
                    "cat_angry_sleep",
                ),
            )
            await query.answer()
            _schedule_notice_clear(query, user_id, notice_token)
            return

    refusal_until = cat.get("action_refusal_until")
    if (
        refusal_until
        and datetime.utcnow().timestamp() < refusal_until
        and action in {"play", "walk"}
    ):
        notice_token = _set_action_notice(
            cat,
            "😾 القطة مرهقة، خليها ترتاح شوي قبل اللعب أو النزهة.",
        )
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, 
                cat,
                await get_user_points(user_id),
                "cat_angry_sleep",
            ),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    if refusal_until:
        cat.pop("action_refusal_until", None)
    elif (
        sleep_need_percent(cat) <= 20
        and action in {"play", "walk"}
    ):
        notice_token = _set_action_notice(
            cat,
            "😾 القطة مرهقة وتحتاج النوم!",
        )
        cat["action_refusal_until"] = (
            datetime.utcnow().timestamp() + random.randint(120, 300)
        )
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, 
                cat,
                await get_user_points(user_id),
                "cat_angry_sleep",
            ),
        )
        await query.answer()
        _schedule_notice_clear(query, user_id, notice_token)
        return

    media_kind = action
    notice_token: str | None = None

    if action == "feed":
        ready, left = check_cooldown(
            parse_time(cat["last_fed"]),
            settings.feed_cooldown,
        )
        if not ready:
            await query.answer(
                f"الإطعام متاح بعد {left // 60} دقيقة.",
                show_alert=True,
            )
            return
        apply_care_effects(cat, "feed")
        cat["last_fed"] = datetime.utcnow().isoformat()
        points = random.choice([0, 0, 2, 5, 8])

    elif action == "play":
        apply_care_effects(cat, "play")
        cat["last_played"] = datetime.utcnow().isoformat()
        points = random.choice([0, 1, 3, 5, 10])
        if random.random() < 0.15:
            notice_token = _set_action_notice(
                cat,
                "😻 اندمجت باللعب وياك وصارت تركض حولك!",
            )

    elif action == "walk":
        apply_care_effects(cat, "walk")
        cat["last_walk"] = datetime.utcnow().isoformat()
        points = random.choice([0, 2, 5, 10, 15])

    elif action == "talk":
        last_talk = cat.get("last_talk")
        if last_talk:
            ready, left = check_cooldown(
                parse_time(last_talk),
                settings.talk_cooldown,
            )
            if not ready:
                await query.answer(
                    f"خليها تستوعب الحچي شوي 😺 ارجع بعد {max(1, left // 60)} دقيقة.",
                    show_alert=True,
                )
                return
        apply_care_effects(cat, "talk")
        cat["last_talk"] = datetime.utcnow().isoformat()
        points = random.choice([0, 1, 2, 4])
        if random.random() < 0.15:
            notice_token = _set_action_notice(
                cat,
                "😽 قربت منك وصارت تتمسح بيك من كثر ما ارتاحت للحچي.",
            )

    elif action == "sleep":
        rest_now = sleep_need_percent(cat)
        if rest_now >= 85:
            notice_token = _set_action_notice(
                cat,
                "😺 مو نعسانة هسه، بعد عندها طاقة.",
            )
            await update_cat(cat)
            await _edit_card(
                query,
                await _build_card(
                    query,
                    cat,
                    await get_user_points(user_id),
                    "status",
                ),
            )
            await query.answer()
            _schedule_notice_clear(query, user_id, notice_token)
            return

        start_sleep(cat)
        cat["wake_attempts"] = 0
        points = random.choice([0, 1, 2])
        media_kind = "sleep"
        if rest_now <= 25:
            notice_token = _set_action_notice(
                cat,
                "😴 نامت بسرعة لأنها كانت منهكة.",
            )
        elif random.random() < 0.15:
            notice_token = _set_action_notice(
                cat,
                "💤 لفت نفسها ونامت بهدوء.",
            )

    elif action == "wake":
        rest_before_wake = sleep_need_percent(cat)
        wake_now(cat)
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
        cat["wake_attempts"] = 0
        media_kind = "status"
        points = 0

    else:
        return

    balance = await get_user_points(user_id)
    if points:
        balance = await award_points(user_id, points, action)

    await update_cat(cat)
    await _edit_card(query, await _build_card(query, cat, balance, media_kind))
    await query.answer()

    if notice_token:
        _schedule_notice_clear(query, user_id, notice_token)
