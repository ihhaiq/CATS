"""Occasional cat-life events: hiding, owner requests, and social visits."""
import html
import logging
import random

from aiogram import Bot

from bot.services.cat_events import (
    active_boredom_escape,
    active_cat_request,
    active_hiding,
    can_start_boredom_escape,
    can_start_hiding,
    can_start_request,
    record_boredom_escape,
    record_cat_visit,
    start_cat_request,
    start_hiding,
    visit_eligible,
)
from bot.services.local_store import (
    get_active_cats,
    get_cat_by_id,
    get_user_points,
    is_sleeping,
    owner_is_away,
    update_cat,
    user_action_lock,
)
from bot.services.rich_card import build_rich_card

logger = logging.getLogger("catibot.activity_sweep")

HIDE_EVENT_CHANCE_PER_SWEEP = 0.006
REQUEST_EVENT_CHANCE_PER_SWEEP = 0.010
VISIT_EVENT_CHANCE_PER_SWEEP = 0.003
VISIT_AWAY_EVENT_CHANCE_PER_SWEEP = 0.15


async def _display_name(bot: Bot, user_id: int) -> str:
    try:
        chat = await bot.get_chat(user_id)
        name = (
            getattr(chat, "first_name", None)
            or getattr(chat, "title", None)
            or getattr(chat, "username", None)
        )
        if name:
            return str(name)
    except Exception as exc:
        logger.debug(
            "Could not resolve user display name user_id=%s: %s",
            user_id,
            exc,
        )
    return "أحد المستخدمين"


async def _send_event_card(bot: Bot, cat: dict, user_id: int) -> None:
    card = await build_rich_card(
        bot,
        cat,
        await get_user_points(int(cat["owner_id"])),
        "status",
        upload_chat_id=user_id,
    )
    await bot.send_rich_message(chat_id=user_id, rich_message=card)


async def _start_personal_event(bot: Bot, snapshot: dict) -> bool:
    owner_id = int(snapshot["owner_id"])
    async with user_action_lock(owner_id):
        cat = await get_cat_by_id(snapshot["cat_id"], include_fled=True)
        if (
            cat is None
            or cat.get("is_fled")
            or is_sleeping(cat)
            or active_boredom_escape(cat)
        ):
            return False

        if (
            not active_hiding(cat)
            and can_start_hiding(cat)
            and random.random() < HIDE_EVENT_CHANCE_PER_SWEEP
        ):
            start_hiding(cat)
            await update_cat(cat)
            try:
                await _send_event_card(bot, cat, owner_id)
            except Exception as exc:
                logger.warning(
                    "Failed to send hiding event owner_id=%s cat_id=%s: %s",
                    owner_id,
                    cat.get("cat_id"),
                    exc,
                )
            return True

        if (
            can_start_request(cat)
            and random.random() < REQUEST_EVENT_CHANCE_PER_SWEEP
        ):
            action = start_cat_request(cat)
            await update_cat(cat)
            try:
                await _send_event_card(bot, cat, owner_id)
            except Exception as exc:
                logger.warning(
                    "Failed to send request event owner_id=%s cat_id=%s "
                    "action=%s: %s",
                    owner_id,
                    cat.get("cat_id"),
                    action,
                    exc,
                )
            return True

    return False


def _duration_text(minutes: int) -> str:
    minutes = max(1, int(minutes))
    if minutes < 60:
        return f"{minutes} دقيقة"
    hours, remainder = divmod(minutes, 60)
    if remainder:
        return f"{hours} ساعة و{remainder} دقيقة"
    return f"{hours} ساعة"


async def _send_boredom_escape_notifications(
    bot: Bot,
    visitor: dict,
    host: dict,
    duration_minutes: int,
) -> None:
    visitor_owner_id = int(visitor["owner_id"])
    host_owner_id = int(host["owner_id"])
    visitor_owner = html.escape(await _display_name(bot, visitor_owner_id))
    host_owner = html.escape(await _display_name(bot, host_owner_id))
    visitor_cat = html.escape(str(visitor.get("name", "قطتك")))
    host_cat = html.escape(str(host.get("name", "قطتهم")))
    duration = _duration_text(duration_minutes)

    visitor_message = (
        f"🌀 الملل وصل مرحلة عالية، فـ <b>{visitor_cat}</b> هربت من البيت "
        f"وراحت تدور قطة تلعب وياها. لقت قطة <b>{host_owner}</b> — "
        f"<b>{host_cat}</b>.
"
        f"🐾 راح تتأخر بالرجعة؛ تقريباً <b>{duration}</b>."
    )
    host_message = (
        f"🐾 قطة <b>{visitor_owner}</b> — <b>{visitor_cat}</b> "
        f"هربت من الملل وجت تلعب ويا <b>{host_cat}</b>."
    )

    for user_id, message in (
        (visitor_owner_id, visitor_message),
        (host_owner_id, host_message),
    ):
        try:
            await bot.send_message(user_id, message)
        except Exception as exc:
            logger.warning(
                "Failed to send boredom escape notice user_id=%s: %s",
                user_id,
                exc,
            )


async def _start_boredom_escape_event(
    bot: Bot,
    snapshot: dict,
    candidates: list[dict],
) -> bool:
    owner_id = int(snapshot["owner_id"])
    async with user_action_lock(owner_id):
        cat = await get_cat_by_id(snapshot["cat_id"], include_fled=True)
        if cat is None or not can_start_boredom_escape(cat):
            return False

        hosts = [
            item
            for item in candidates
            if int(item.get("cat_id", 0)) != int(cat.get("cat_id", 0))
            and int(item.get("owner_id", 0)) != owner_id
            and not item.get("is_fled")
            and not is_sleeping(item)
            and not active_hiding(item)
            and not active_cat_request(item)
            and not active_boredom_escape(item)
        ]
        random.shuffle(hosts)
        for host in hosts:
            recorded = await record_boredom_escape(
                int(cat["cat_id"]),
                int(host["cat_id"]),
            )
            if recorded is None:
                continue
            saved_visitor, saved_host, duration = recorded
            await _send_boredom_escape_notifications(
                bot,
                saved_visitor,
                saved_host,
                duration,
            )
            return True
    return False


async def _send_visit_notifications(
    bot: Bot,
    visitor: dict,
    host: dict,
) -> None:
    visitor_owner_id = int(visitor["owner_id"])
    host_owner_id = int(host["owner_id"])
    visitor_owner = html.escape(await _display_name(bot, visitor_owner_id))
    host_owner = html.escape(await _display_name(bot, host_owner_id))
    visitor_cat = html.escape(str(visitor.get("name", "قطتك")))
    host_cat = html.escape(str(host.get("name", "قطتهم")))

    visitor_message = (
        f"🐾 قطتك <b>{visitor_cat}</b> راحت تزور قطة "
        f"<b>{host_owner}</b> — <b>{host_cat}</b>. 😺"
    )
    host_message = (
        f"🐾 قطة <b>{visitor_owner}</b> — <b>{visitor_cat}</b> "
        f"زارتكم وجت تلعب ويا <b>{host_cat}</b>. 😸"
    )

    for user_id, message in (
        (visitor_owner_id, visitor_message),
        (host_owner_id, host_message),
    ):
        try:
            await bot.send_message(user_id, message)
        except Exception as exc:
            logger.warning(
                "Failed to send cat visit notice user_id=%s: %s",
                user_id,
                exc,
            )


async def run_activity_sweep(bot: Bot) -> None:
    """Create occasional events without flooding owners."""
    snapshots = await get_active_cats()
    if not snapshots:
        return

    # Extreme boredom takes priority over routine hiding/requests/visits.
    for snapshot in snapshots:
        if not can_start_boredom_escape(snapshot):
            continue
        try:
            await _start_boredom_escape_event(bot, snapshot, snapshots)
        except Exception:
            logger.exception(
                "Boredom escape event failed cat_id=%s",
                snapshot.get("cat_id"),
            )

    refreshed_for_personal = await get_active_cats()
    for snapshot in refreshed_for_personal:
        try:
            await _start_personal_event(bot, snapshot)
        except Exception:
            logger.exception(
                "Personal cat event failed cat_id=%s",
                snapshot.get("cat_id"),
            )

    refreshed = await get_active_cats()
    eligible = [cat for cat in refreshed if visit_eligible(cat)]
    random.shuffle(eligible)
    used_cat_ids: set[int] = set()

    for visitor in eligible:
        visitor_id = int(visitor.get("cat_id", 0))
        if visitor_id in used_cat_ids:
            continue
        visit_chance = (
            VISIT_AWAY_EVENT_CHANCE_PER_SWEEP
            if owner_is_away(visitor)
            else VISIT_EVENT_CHANCE_PER_SWEEP
        )
        if random.random() >= visit_chance:
            continue

        hosts = [
            cat
            for cat in eligible
            if int(cat.get("cat_id", 0)) not in used_cat_ids
            and int(cat.get("cat_id", 0)) != visitor_id
            and int(cat.get("owner_id", 0)) != int(visitor.get("owner_id", 0))
        ]
        if not hosts:
            continue

        host = random.choice(hosts)
        host_id = int(host.get("cat_id", 0))
        recorded = await record_cat_visit(visitor_id, host_id)
        if recorded is None:
            continue

        saved_visitor, saved_host = recorded
        used_cat_ids.update({visitor_id, host_id})
        await _send_visit_notifications(bot, saved_visitor, saved_host)
