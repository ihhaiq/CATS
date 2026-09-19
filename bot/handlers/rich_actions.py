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
    action_block_reason,
    can_bypass_action_cooldown,
    care_reward_points,
    ensure_user,
    finish_sleep,
    get_cat_by_id,
    get_user_cat,
    get_user_points,
    is_sleeping,
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
        async with user_action_lock(user_id):
            cat = await get_user_cat(user_id)
            if cat is None or cat.get("action_notice_token") != notice_token:
                return

            clear_action_notice(cat)
            await update_cat(cat)
            await _edit_card(
                query,
                await _build_card(
                    query,
                    cat,
                    await get_user_points(user_id),
                    "sleep" if is_sleeping(cat) else "status",
                ),
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


def _parse_cat_action(data: str) -> tuple[int | None, str]:
    parts = data.split(":")
    if len(parts) >= 3 and parts[1].isdigit():
        return int(parts[1]), parts[2]
    return None, parts[1] if len(parts) > 1 else ""


@router.callback_query(lambda query: query.data and query.data.startswith("cat:"))
async def handle_rich_action(query: CallbackQuery) -> None:
    user_id = query.from_user.id
    cat_id, action = _parse_cat_action(query.data or "")

    lock_user_id = user_id
    if cat_id is not None:
        snapshot = await get_cat_by_id(cat_id)
        if snapshot is None:
            await query.answer("هذي البطاقة قديمة أو القطة ما عادت متاحة.", show_alert=True)
            return
        if int(snapshot.get("owner_id", 0)) != user_id:
            await query.answer("هذي مو قطتك 😼", show_alert=True)
            return
        lock_user_id = int(snapshot["owner_id"])

    async with user_action_lock(lock_user_id):
        await _handle_rich_action_locked(
            query,
            user_id,
            cat_id=cat_id,
            action=action,
        )


async def _handle_rich_action_locked(
    query: CallbackQuery,
    user_id: int,
    *,
    cat_id: int | None,
    action: str,
) -> None:
    await ensure_user(user_id)
    cat = (
        await get_cat_by_id(cat_id)
        if cat_id is not None
        else await get_user_cat(user_id)
    )
    if cat is None:
        await query.answer("ما عندك قطة بعد.", show_alert=True)
        return
    if int(cat.get("owner_id", 0)) != user_id:
        await query.answer("هذي مو قطتك 😼", show_alert=True)
        return

    # Any new action invalidates an older temporary notice/task.
    clear_action_notice(cat)
    apply_decay(cat)
    woke = finish_sleep(cat)
    if cat.get("is_fled"):
        await update_cat(cat)
        await _edit_card(query, build_fled_card(cat))
        await query.answer("💨 القطة هربت بسبب الإهمال.", show_alert=True)
        return
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

    if action == "wake" and not is_sleeping(cat):
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, cat, await get_user_points(user_id), "status"),
        )
        message = (
            "😺 صحت من نفسها بالفعل."
            if woke
            else "😺 القطة صاحية أصلًا."
        )
        await query.answer(message, show_alert=True)
        return

    if is_sleeping(cat) and action != "wake":
        await update_cat(cat)
        remaining = sleep_duration_text(sleep_remaining_minutes(cat))
        await query.answer(
            f"😴 القطة نائمة هسه. باقي تقريباً {remaining}.",
            show_alert=True,
        )
        return

    block_reason = action_block_reason(cat, action)
    if block_reason:
        await update_cat(cat)
        if block_reason == "full":
            await query.answer(
                "😺 القطة شبعانة هسه وما تحتاج أكل زيادة.",
                show_alert=True,
            )
        elif block_reason == "starving":
            await query.answer(
                "🚨🍖 جوعها شديد؛ أطعمها أولاً قبل اللعب أو النزهة.",
                show_alert=True,
            )
        elif block_reason == "bored_of_play":
            await query.answer(
                "😾 ملت من نفس اللعب. حچي وياها أو طلّعها نزهة وغيّر الروتين.",
                show_alert=True,
            )
        else:
            await query.answer(
                "🪫 القطة تعبانة وتحتاج نوم قبل اللعب أو النزهة.",
                show_alert=True,
            )
        return

    media_kind = action
    notice_token: str | None = None
    bypassed_cooldown = False

    if action == "feed":
        last_fed = cat.get("last_fed")
        if last_fed:
            ready, left = check_cooldown(
                parse_time(last_fed),
                settings.feed_cooldown,
            )
        else:
            ready, left = True, 0
        need_bypass = can_bypass_action_cooldown(cat, "feed")
        bypassed_cooldown = not ready and need_bypass
        if not ready and not need_bypass:
            await query.answer(
                f"الإطعام متاح بعد {max(1, left // 60)} دقيقة.",
                show_alert=True,
            )
            return
        apply_care_effects(cat, "feed")
        cat["last_fed"] = datetime.utcnow().isoformat()
        points = 0

    elif action == "play":
        last_played = cat.get("last_played")
        if last_played:
            ready, left = check_cooldown(
                parse_time(last_played),
                settings.play_cooldown,
            )
        else:
            ready, left = True, 0
        need_bypass = can_bypass_action_cooldown(cat, "play")
        bypassed_cooldown = not ready and need_bypass
        if not ready and not need_bypass:
            await query.answer(
                f"😼 شبعت لعب هسه، جرّب بعد {max(1, left // 60)} دقيقة.",
                show_alert=True,
            )
            return
        apply_care_effects(cat, "play")
        cat["last_played"] = datetime.utcnow().isoformat()
        play_streak = int(cat.get("same_action_streak", 1))
        if play_streak >= 5:
            points = 0
            notice_token = _set_action_notice(
                cat,
                "😾 ملت من نفس اللعب، جرّب تحچي وياها أو تطلعها نزهة.",
            )
        else:
            points = 0
            if random.random() < 0.15:
                notice_token = _set_action_notice(
                    cat,
                    "😻 اندمجت باللعب وياك وصارت تركض حولك!",
                )

    elif action == "walk":
        last_walk = cat.get("last_walk")
        if last_walk:
            ready, left = check_cooldown(
                parse_time(last_walk),
                settings.walk_cooldown,
            )
        else:
            ready, left = True, 0
        need_bypass = can_bypass_action_cooldown(cat, "walk")
        bypassed_cooldown = not ready and need_bypass
        if not ready and not need_bypass:
            await query.answer(
                f"🌿 توها طالعة نزهة، جرّب بعد {max(1, left // 60)} دقيقة.",
                show_alert=True,
            )
            return
        apply_care_effects(cat, "walk")
        cat["last_walk"] = datetime.utcnow().isoformat()
        points = 0

    elif action == "talk":
        last_talk = cat.get("last_talk")
        if last_talk:
            ready, left = check_cooldown(
                parse_time(last_talk),
                settings.talk_cooldown,
            )
        else:
            ready, left = True, 0
        need_bypass = can_bypass_action_cooldown(cat, "talk")
        bypassed_cooldown = not ready and need_bypass
        if not ready and not need_bypass:
            await query.answer(
                f"خليها تستوعب الحچي شوي 😺 ارجع بعد {max(1, left // 60)} دقيقة.",
                show_alert=True,
            )
            return
        apply_care_effects(cat, "talk")
        cat["last_talk"] = datetime.utcnow().isoformat()
        points = 0
        if cat.get("last_care_meaningful") and random.random() < 0.15:
            notice_token = _set_action_notice(
                cat,
                "😽 قربت منك وصارت تتمسح بيك من كثر ما ارتاحت للحچي.",
            )

    elif action == "sleep":
        rest_now = sleep_need_percent(cat)
        if rest_now >= 98:
            notice_token = _set_action_notice(
                cat,
                "😺 مرتاحة تقريباً بالكامل وما تحتاج تنام هسه.",
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

        planned_minutes = start_sleep(cat)
        points = 0
        media_kind = "sleep"
        duration = sleep_duration_text(planned_minutes)
        if cat.get("sleep_kind") == "main":
            notice_token = _set_action_notice(
                cat,
                f"😴 دخلت نوم رئيسي، تقريباً {duration}.",
            )
        else:
            notice_token = _set_action_notice(
                cat,
                f"💤 أخذت قيلولة، تقريباً {duration}.",
            )

    elif action == "wake":
        rest_before_wake = sleep_need_percent(cat)
        did_wake = wake_now(cat)
        if did_wake:
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
                notice_token = _set_action_notice(
                    cat,
                    f"😾 صحّيتها قبل ما تشبع نوم، الثقة نزلت {trust_loss}.",
                )
            else:
                notice_token = _set_action_notice(
                    cat,
                    "☀️ صحت القطة وهي مرتاحة.",
                )
        media_kind = "status"
        points = 0

    else:
        return

    if action in {"feed", "play", "walk", "talk"}:
        points = care_reward_points(
            cat,
            action,
            bypassed_cooldown=bypassed_cooldown,
        )

    if bypassed_cooldown and not notice_token:
        notice_token = _set_action_notice(
            cat,
            "⚡ انفتحت فترة التهدئة لأن قطتك كانت تحتاج هذا الفعل. الرعاية تنحسب، لكن بدون نقاط إضافية.",
        )
    elif (
        action in {"feed", "play", "walk", "talk"}
        and not cat.get("last_care_meaningful", False)
        and not notice_token
    ):
        notice_token = _set_action_notice(
            cat,
            "😺 هذا تفاعل اختياري؛ ما كانت محتاجته هسه، لذلك بدون نقاط.",
        )

    balance = await get_user_points(user_id)
    if points:
        balance = await award_points(user_id, points, action)

    await update_cat(cat)
    await _edit_card(query, await _build_card(query, cat, balance, media_kind))
    await query.answer()

    if notice_token:
        _schedule_notice_clear(query, user_id, notice_token)
