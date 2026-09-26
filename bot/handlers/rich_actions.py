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
from bot.services.cat_events import (
    HIDE_SPOT_LABELS,
    active_hiding,
    call_hidden_cat,
    fulfill_cat_request,
    ignore_cat_request,
    search_hidden_cat,
)
from bot.services.economy import check_cooldown
from bot.services.local_store import (
    apply_care_effects,
    apply_decay,
    apply_light_interaction,
    award_points,
    clear_action_notice,
    action_block_reason,
    can_bypass_action_cooldown,
    care_reward_points,
    ensure_user,
    defer_sleep_for_owner,
    finish_sleep,
    fullness_percent,
    get_cat_by_id,
    get_user_cat,
    get_user_points,
    is_sleeping,
    mark_owner_interaction,
    parse_time,
    sleep_duration_text,
    sleep_need_percent,
    sleep_remaining_minutes,
    start_sleep,
    stubborn_care_refusal_reason,
    stubborn_refusal_text,
    stubbornly_refuses_sleep,
    stubbornly_refuses_wake,
    sync_decay_accumulators,
    TREAT_FULLNESS_THRESHOLD,
    update_cat,
    user_action_lock,
    wake_now,
)
from bot.services.cat_preview import sync_cat_preview
from bot.services.rich_card import build_fled_card, build_rich_card

router = Router(name="rich_actions")
logger = logging.getLogger("catibot.rich_actions")


async def _build_card(query: CallbackQuery, cat: dict, points: int, state: str = "status"):
    upload_chat_id = query.message.chat.id if query.message else query.from_user.id
    preview_ok = False
    if query.message and not query.inline_message_id:
        preview_ok = await sync_cat_preview(
            query.bot,
            query.message.chat.id,
            cat,
            state,
        )
    return await build_rich_card(
        query.bot,
        cat,
        points,
        state,
        upload_chat_id=upload_chat_id,
        embed_media=not preview_ok,
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
        snapshot = await get_cat_by_id(cat_id, include_fled=True)
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
        await get_cat_by_id(cat_id, include_fled=True)
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
    woke = finish_sleep(cat, owner_present=True)
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

    if action.startswith("hide_"):
        if not active_hiding(cat):
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
            await query.answer("😺 رجعت من مخباها بالفعل.", show_alert=True)
            return

        notice_token: str | None = None
        found = False
        if action == "hide_call":
            found = call_hidden_cat(cat)
            if found:
                notice_token = _set_action_notice(
                    cat,
                    f"😺 ناديتها باسمها وطلعتلك {cat['name']}!",
                )
            else:
                notice_token = _set_action_notice(
                    cat,
                    f"📣 ناديت {cat['name']}... سمعتك بس بعد ما طلعت 😼",
                )
        else:
            spot = action.removeprefix("hide_")
            if spot not in HIDE_SPOT_LABELS:
                await query.answer("هذا مكان بحث قديم.", show_alert=True)
                return
            found = search_hidden_cat(cat, spot)
            if found:
                notice_token = _set_action_notice(
                    cat,
                    f"😺 لقيتها {HIDE_SPOT_LABELS[spot]}!",
                )
            else:
                notice_token = _set_action_notice(
                    cat,
                    f"👀 دورت {HIDE_SPOT_LABELS[spot]}... مو هنا.",
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
        if notice_token:
            _schedule_notice_clear(query, user_id, notice_token)
        return

    if active_hiding(cat):
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
        await query.answer(
            "🙀 قطتك مختفية هسه؛ دور عليها أو ناديها باسمها.",
            show_alert=True,
        )
        return

    if action == "request_ignore":
        ignored = ignore_cat_request(cat)
        if ignored is None:
            await query.answer("ماكو طلب فعال هسه.", show_alert=True)
            return
        notice_token = _set_action_notice(
            cat,
            "😿 طنشت طلبها؛ زعلت شوي وراحت تشغل نفسها.",
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
        if block_reason == "starving":
            await query.answer(
                "🚨🍖 جوعها شديد؛ أطعمها أولاً قبل اللعب أو اللعبة أو النزهة.",
                show_alert=True,
            )
        else:
            await query.answer(
                "🪫 القطة منهكة وتحتاج ترتاح قبل اللعب أو اللعبة أو النزهة.",
                show_alert=True,
            )
        return

    if action == "treat" and fullness_percent(cat) < TREAT_FULLNESS_THRESHOLD:
        await update_cat(cat)
        await _edit_card(
            query,
            await _build_card(query, cat, await get_user_points(user_id), "status"),
        )
        await query.answer(
            "🍬 التحلية تظهر من يصير الشبع 75% وفوك.",
            show_alert=True,
        )
        return

    if action in {"feed", "treat", "play", "toy", "walk", "talk", "relax"}:
        refusal_reason = stubborn_care_refusal_reason(cat, action)
        if refusal_reason:
            notice_token = _set_action_notice(
                cat,
                stubborn_refusal_text(action, refusal_reason),
            )
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

    if action in {"treat", "play", "toy", "walk", "talk", "relax"}:
        defer_sleep_for_owner(cat)

    media_kind = action
    notice_token: str | None = None
    bypassed_cooldown = False
    soft_interaction = False

    care_specs = {
        "feed": ("last_fed", settings.feed_cooldown),
        "treat": ("last_treat", settings.treat_cooldown),
        "play": ("last_played", settings.play_cooldown),
        "toy": ("last_toy", settings.toy_cooldown),
        "walk": ("last_walk", settings.walk_cooldown),
        "talk": ("last_talk", settings.talk_cooldown),
        "relax": ("last_relax", settings.relax_cooldown),
    }

    if action in care_specs:
        timestamp_key, cooldown = care_specs[action]
        last_action = cat.get(timestamp_key)
        if last_action:
            ready, left = check_cooldown(parse_time(last_action), cooldown)
        else:
            ready, left = True, 0

        need_bypass = can_bypass_action_cooldown(cat, action)
        bypassed_cooldown = not ready and need_bypass
        soft_interaction = not ready and not need_bypass

        if soft_interaction:
            apply_light_interaction(cat, action)
        else:
            apply_care_effects(cat, action)
            cat[timestamp_key] = datetime.utcnow().isoformat()

        points = care_reward_points(
            cat,
            action,
            bypassed_cooldown=bypassed_cooldown,
        )
        request_fulfilled = fulfill_cat_request(cat, action)

        streak = int(cat.get("same_action_streak", 1))
        if action == "treat":
            notice_token = _set_action_notice(
                cat,
                "🍬 أخذت التحلية؛ شبعت أكثر، حبها زاد هواية ومللها نزل.",
            )
        elif action == "play" and streak >= 5:
            notice_token = _set_action_notice(
                cat,
                "😾 ملت من نفس اللعب؛ تگدر تبقى تتفاعل وياها، بس غيّر النشاط حتى تستمتع أكثر.",
            )
        elif action == "toy" and streak >= 4:
            notice_token = _set_action_notice(
                cat,
                "😾 كثرت عليها الألعاب وبدت تمل؛ بدّل النشاط وياها شوي.",
            )
        elif action == "toy":
            notice_token = _set_action_notice(
                cat,
                "🧸 أخذت اللعبة واندمجت بيها؛ زادت سعادتها وحبها وقل مللها.",
            )
        elif action == "talk" and streak >= 4:
            notice_token = _set_action_notice(
                cat,
                "😾 طولت بالحچي بنفس الروتين وبدت تمل؛ جرّب لعب، استلقاء أو نزهة.",
            )
        elif action == "walk" and streak >= 4:
            notice_token = _set_action_notice(
                cat,
                "😾 كثرت النزهات بنفس الروتين وبدت تمل؛ غيّر النشاط شوي.",
            )
        elif action == "relax":
            notice_token = _set_action_notice(
                cat,
                "🛋 استلقت يمك بهدوء وصارت تتابع التلفاز وياك.",
            )
        elif (
            action in {"play", "talk"}
            and not soft_interaction
            and cat.get("last_care_meaningful")
            and random.random() < 0.15
        ):
            notice_token = _set_action_notice(
                cat,
                (
                    "😻 اندمجت باللعب وياك وصارت تركض حولك!"
                    if action == "play"
                    else "😽 قربت منك وصارت تتمسح بيك من كثر ما ارتاحت للحچي."
                ),
            )

        if request_fulfilled:
            notice_token = _set_action_notice(
                cat,
                "😻 هذا بالضبط اللي كانت تريده منك!",
            )

    elif action == "sleep":
        mark_owner_interaction(cat)
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

        if stubbornly_refuses_sleep(cat):
            notice_token = _set_action_notice(
                cat,
                "😾 عاندت وما رضت تنام هسه! جرّب وياها مرة ثانية.",
            )
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
        mark_owner_interaction(cat)
        if stubbornly_refuses_wake(cat):
            notice_token = _set_action_notice(
                cat,
                "😾 عاندت وما رضت تكعد؛ تريد تكمل نومها شوي.",
            )
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
                sync_decay_accumulators(cat)
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

    if action in {"feed", "play", "toy", "walk", "talk", "relax"}:
        points = care_reward_points(
            cat,
            action,
            bypassed_cooldown=bypassed_cooldown,
        )

    if soft_interaction and not notice_token:
        notice_token = _set_action_notice(
            cat,
            "😺 التفاعل مسموح، بس التهدئة بعدها شغالة؛ تأثيره خفيف وبدون نقاط.",
        )
    elif bypassed_cooldown and not notice_token:
        notice_token = _set_action_notice(
            cat,
            "⚡ قطتك كانت تحتاج هذا الفعل، لذلك تجاهلت التهدئة؛ بدون نقاط إضافية.",
        )
    elif (
        action in {"feed", "play", "toy", "walk", "talk", "relax"}
        and not cat.get("last_care_meaningful", False)
        and not notice_token
    ):
        notice_token = _set_action_notice(
            cat,
            "😺 هذا تفاعل اختياري؛ مسموح عادي، بس فائدته بسيطة وبدون نقاط.",
        )

    balance = await get_user_points(user_id)
    if points:
        balance = await award_points(user_id, points, action)

    await update_cat(cat)
    await _edit_card(query, await _build_card(query, cat, balance, media_kind))
    await query.answer()

    if notice_token:
        _schedule_notice_clear(query, user_id, notice_token)
