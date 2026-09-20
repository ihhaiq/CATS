"""Small JSON-backed store used for local development."""
import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from bot.config import settings
from bot.services.cat_assets import normalize_cat_state, resolve_media_value

_lock = asyncio.Lock()
_action_locks: dict[int, asyncio.Lock] = {}
logger = logging.getLogger("catibot.local_store")


def user_action_lock(user_id: int) -> asyncio.Lock:
    """Serialize stateful operations for one cat owner/user."""
    lock = _action_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _action_locks[user_id] = lock
    return lock



def _path() -> Path:
    path = Path(settings.json_data_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _empty_store() -> dict:
    return {
        "users": {},
        "cats": [],
        "items": [],
        "user_inventory": [],
        "points_log": [],
        "media": {},
        "media_types": {},
        "media_cache": {},
        "media_overrides": {},
    }


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _atomic_write_text(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON store root must be an object")
    return data


def _restore_backup(path: Path) -> dict | None:
    backup = _backup_path(path)
    if not backup.exists():
        return None
    try:
        data = _load_json(backup)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("JSON backup is invalid: %s", backup)
        return None

    _atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
    )
    logger.warning("Restored JSON store from backup: %s", backup)
    return data


def _read() -> dict:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        data = _restore_backup(path)
        if data is None:
            return _empty_store()
    else:
        try:
            data = _load_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.error("Primary JSON store is unreadable: %s", exc)
            data = _restore_backup(path)
            if data is None:
                raise RuntimeError(
                    "Cat data store is damaged and no valid backup is available; "
                    "refusing to start with an empty store."
                ) from exc

    for key, default in _empty_store().items():
        data.setdefault(key, default)
    return data


def _write(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup_path(path)

    if path.exists():
        try:
            _load_json(path)
        except (OSError, json.JSONDecodeError, ValueError):
            logger.error(
                "Refusing to replace backup with an invalid primary JSON store: %s",
                path,
            )
        else:
            shutil.copy2(path, backup)

    _atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def is_sleeping(cat: dict) -> bool:
    sleep_until = cat.get("sleep_until")
    return bool(sleep_until and parse_time(sleep_until) > datetime.utcnow())


def sleep_remaining_minutes(cat: dict) -> int:
    sleep_until = cat.get("sleep_until")
    if not sleep_until:
        return 0
    seconds = max(
        0.0,
        (parse_time(sleep_until) - datetime.utcnow()).total_seconds(),
    )
    return int((seconds + 59) // 60)


def sleep_duration_text(minutes: int) -> str:
    minutes = max(1, int(minutes))
    if minutes < 60:
        return f"{minutes} دقيقة"
    hours, remainder = divmod(minutes, 60)
    if remainder:
        return f"{hours} ساعة و{remainder} دقيقة"
    return f"{hours} ساعة"


REST_FALL_PER_AWAKE_HOUR = 8.0
REST_RECOVERY_PER_SLEEP_HOUR = 10.0
HUNGER_RISE_PER_AWAKE_HOUR = 3.0
HUNGER_RISE_PER_SLEEP_HOUR = 1.0
BOREDOM_RISE_PER_AWAKE_HOUR = 1.5
BOREDOM_RISE_PER_OVERSLEEP_HOUR = 2.0
BOREDOM_RISE_PER_LONG_SLEEP_HOUR = 1.5
LONG_SLEEP_SESSION_HOURS = 10.0
TRUST_FALL_PER_NEGLECT_HOUR = 0.7
UNFED_TRUST_GRACE_HOURS = 10.0
TRUST_FALL_PER_UNFED_HOUR = 0.45
WALK_DUE_HOURS = 14.0
ROUTINE_WINDOW_HOURS = 6.0
CAT_DAILY_SLEEP_TARGET_HOURS = 14.0
HEALTHY_SLEEP_HOURS = 16.0
MAIN_SLEEP_REST_THRESHOLD = 35
MAIN_SLEEP_MIN_HOURS = 4.0
MAIN_SLEEP_MAX_HOURS = 12.5
NAP_MIN_HOURS = 0.75
NAP_MAX_HOURS = 2.5


def _sleep_overlap_hours(cat: dict, start: datetime, end: datetime) -> float:
    sleep_started = cat.get("sleep_started_at")
    sleep_until = cat.get("sleep_until")
    if not sleep_started or not sleep_until or end <= start:
        return 0.0
    sleep_start = parse_time(sleep_started)
    sleep_end = parse_time(sleep_until)
    overlap_start = max(start, sleep_start)
    overlap_end = min(end, sleep_end)
    return max(0.0, (overlap_end - overlap_start).total_seconds() / 3600)


def _day_start(moment: datetime) -> datetime:
    return datetime.combine(moment.date(), datetime.min.time())


def _session_sleep_until(cat: dict, moment: datetime) -> float:
    """Hours from the active sleep session that belong to moment's UTC day."""
    started = cat.get("sleep_started_at")
    until = cat.get("sleep_until")
    if not started or not until:
        return 0.0

    day_start = _day_start(moment)
    day_end = day_start + timedelta(days=1)
    sleep_start = max(parse_time(started), day_start)
    sleep_end = min(moment, parse_time(until), day_end)
    if sleep_end <= sleep_start:
        return 0.0
    return (sleep_end - sleep_start).total_seconds() / 3600


def _effective_slept_today(cat: dict, moment: datetime) -> float:
    saved = (
        float(cat.get("slept_today_hours", 0.0))
        if cat.get("sleep_day") == moment.date().isoformat()
        else 0.0
    )
    return saved + _session_sleep_until(cat, moment)


def _oversleep_segment(cat: dict, start: datetime, end: datetime) -> float:
    before = _effective_slept_today(cat, start)
    slept = _sleep_overlap_hours(cat, start, end)
    after = before + slept
    return max(0.0, after - HEALTHY_SLEEP_HOURS) - max(
        0.0, before - HEALTHY_SLEEP_HOURS
    )


def _oversleep_between(cat: dict, start: datetime, end: datetime) -> float:
    """Only sleep beyond the healthy daily amount adds boredom, per UTC day."""
    if end <= start:
        return 0.0
    if start.date() == end.date():
        return _oversleep_segment(cat, start, end)

    midnight = _day_start(end)
    return (
        _oversleep_segment(cat, start, midnight)
        + _oversleep_segment(cat, midnight, end)
    )


def _long_sleep_between(cat: dict, start: datetime, end: datetime) -> float:
    """Sleep beyond 10 continuous hours starts becoming boring."""
    started = cat.get("sleep_started_at")
    until = cat.get("sleep_until")
    if not started or not until or end <= start:
        return 0.0

    threshold = parse_time(started) + timedelta(hours=LONG_SLEEP_SESSION_HOURS)
    sleep_end = parse_time(until)
    overlap_start = max(start, threshold)
    overlap_end = min(end, sleep_end)
    if overlap_end <= overlap_start:
        return 0.0
    return (overlap_end - overlap_start).total_seconds() / 3600


def _commit_sleep_today(cat: dict, moment: datetime) -> None:
    """Commit only the part of the finished session that belongs to today."""
    saved = (
        float(cat.get("slept_today_hours", 0.0))
        if cat.get("sleep_day") == moment.date().isoformat()
        else 0.0
    )
    cat["sleep_day"] = moment.date().isoformat()
    cat["slept_today_hours"] = saved + _session_sleep_until(cat, moment)


def _refresh_rest(cat: dict, moment: datetime | None = None) -> int:
    """Persistent rest meter: awake drains quickly, sleep restores slowly."""
    moment = moment or datetime.utcnow()
    anchor_raw = (
        cat.get("rest_updated_at")
        or cat.get("last_wake_at")
        or cat.get("created_at")
    )
    anchor = parse_time(anchor_raw) if anchor_raw else moment
    if anchor > moment:
        anchor = moment

    if "rest_level" in cat:
        rest = float(cat.get("rest_level", 100))
    else:
        awake_hours = max(0.0, (moment - anchor).total_seconds() / 3600)
        rest = max(0.0, 100.0 - awake_hours * REST_FALL_PER_AWAKE_HOUR)
        anchor = moment

    elapsed = max(0.0, (moment - anchor).total_seconds() / 3600)
    asleep = min(elapsed, _sleep_overlap_hours(cat, anchor, moment))
    awake = max(0.0, elapsed - asleep)
    recovery = REST_RECOVERY_PER_SLEEP_HOUR
    if int(cat.get("hunger", 20)) >= 85:
        recovery *= 0.8
    rest += asleep * recovery
    rest -= awake * REST_FALL_PER_AWAKE_HOUR

    cat["rest_level"] = max(0.0, min(100.0, rest))
    cat["rest_updated_at"] = moment.isoformat()
    return int(round(cat["rest_level"]))


def sleep_need_percent(cat: dict) -> int:
    """100 = fully rested, 0 = exhausted."""
    return _refresh_rest(cat)


def fullness_percent(cat: dict) -> int:
    """User-facing fullness: 100 = full, 0 = starving."""
    return max(0, min(100, 100 - int(cat.get("hunger", 20))))


def wake_if_ready(cat: dict) -> bool:
    if cat.get("sleep_until") and not is_sleeping(cat):
        return finish_sleep(cat)
    return False


def sleep_plan(cat: dict, moment: datetime | None = None) -> tuple[str, float]:
    """Plan a real-time main sleep or nap from rest deficit and today's sleep."""
    now = moment or datetime.utcnow()
    rest = _refresh_rest(cat, now)
    today = now.date().isoformat()
    if cat.get("sleep_day") != today and not is_sleeping(cat):
        cat["sleep_day"] = today
        cat["slept_today_hours"] = 0.0

    slept = _effective_slept_today(cat, now)
    recovery = REST_RECOVERY_PER_SLEEP_HOUR
    if int(cat.get("hunger", 20)) >= 85:
        recovery *= 0.8
    deficit_hours = max(
        NAP_MIN_HOURS,
        (100 - rest) / recovery,
    )

    # A deeply tired cat takes a real main sleep. Otherwise it takes one of
    # several shorter naps, which is closer to a cat's normal daily rhythm.
    if rest <= MAIN_SLEEP_REST_THRESHOLD:
        kind = "main"
        hours = max(
            MAIN_SLEEP_MIN_HOURS,
            min(MAIN_SLEEP_MAX_HOURS, deficit_hours),
        )
    else:
        kind = "nap"
        hours = min(NAP_MAX_HOURS, max(NAP_MIN_HOURS, deficit_hours))
        if slept >= CAT_DAILY_SLEEP_TARGET_HOURS:
            hours = min(hours, 1.0)

    return kind, hours


def start_sleep(cat: dict) -> int:
    now = datetime.utcnow()
    kind, hours = sleep_plan(cat, now)

    # Starting a new session means any older undelivered wake event is stale.
    cat.pop("wake_notice_pending", None)
    cat.pop("wake_notice_kind", None)
    cat.pop("wake_notice_at", None)
    cat.pop("wake_notice_sent_to", None)

    cat["sleep_started_at"] = now.isoformat()
    cat["sleep_until"] = (now + timedelta(hours=hours)).isoformat()
    cat["sleep_planned_hours"] = hours
    cat["sleep_kind"] = kind
    cat["rest_updated_at"] = now.isoformat()
    return round(hours * 60)


def sleep_ready_to_finish(
    cat: dict,
    moment: datetime | None = None,
) -> bool:
    """Nap wakes on time; main sleep also wakes as soon as rest is effectively full."""
    sleep_until = cat.get("sleep_until")
    if not sleep_until:
        return False

    now = moment or datetime.utcnow()
    if parse_time(sleep_until) <= now:
        return True
    if cat.get("sleep_kind") != "main":
        return False

    probe = dict(cat)
    return _refresh_rest(probe, now) >= 98


def finish_sleep(cat: dict) -> bool:
    """Finish naps on time; main sleep ends only when the cat is actually rested."""
    if not sleep_ready_to_finish(cat):
        return False

    now = datetime.utcnow()
    rest = _refresh_rest(cat, now)

    if cat.get("sleep_kind") == "main":
        if rest < 98:
            # Hunger can become severe during a long sleep and slow recovery.
            # Extend the session from the current state instead of waking a
            # still-tired cat just because the original estimate expired.
            recovery = REST_RECOVERY_PER_SLEEP_HOUR
            if int(cat.get("hunger", 20)) >= 85:
                recovery *= 0.8
            extra_hours = max(0.25, (98 - rest) / recovery)
            cat["sleep_until"] = (
                now + timedelta(hours=extra_hours)
            ).isoformat()
            cat["sleep_planned_hours"] = (
                float(cat.get("sleep_planned_hours", 0.0)) + extra_hours
            )
            cat["rest_updated_at"] = now.isoformat()
            return False

        # Main sleep may finish before the original estimate once rest is full.
        cat["sleep_until"] = now.isoformat()

    _commit_sleep_today(cat, now)

    kind = cat.get("sleep_kind") or "sleep"
    cat["last_sleep_kind"] = kind
    cat["wake_notice_pending"] = True
    cat["wake_notice_kind"] = kind
    cat["wake_notice_at"] = now.isoformat()
    cat["wake_notice_sent_to"] = []
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["sleep_kind"] = None
    cat["last_wake_at"] = now.isoformat()
    cat["rest_updated_at"] = now.isoformat()
    # A natural wake is a fresh lifecycle event; old need-notification
    # suppression must not hide the next state update.
    cat["last_notified_state"] = None
    cat["last_notified_at"] = None
    return True


def wake_now(cat: dict) -> bool:
    if not cat.get("sleep_until"):
        return False
    now = datetime.utcnow()
    _refresh_rest(cat, now)
    _commit_sleep_today(cat, now)
    cat["last_sleep_kind"] = cat.get("sleep_kind") or "sleep"
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["sleep_kind"] = None
    cat.pop("wake_notice_pending", None)
    cat.pop("wake_notice_kind", None)
    cat.pop("wake_notice_at", None)
    cat.pop("wake_notice_sent_to", None)
    cat["last_wake_at"] = now.isoformat()
    cat["rest_updated_at"] = now.isoformat()
    return True


def clear_action_notice(cat: dict) -> None:
    cat.pop("action_notice", None)
    cat.pop("action_notice_until", None)
    cat.pop("action_notice_token", None)


def _walk_hours(cat: dict, moment: datetime) -> float:
    value = (
        cat.get("last_walk")
        or cat.get("adopted_at")
        or cat.get("created_at")
    )
    if not value:
        return 0.0
    return max(0.0, (moment - parse_time(value)).total_seconds() / 3600)


def _social_hours(cat: dict, moment: datetime) -> float:
    value = cat.get("last_social_at") or cat.get("last_played")
    if not value:
        return 0.0
    return max(0.0, (moment - parse_time(value)).total_seconds() / 3600)


def _unfed_hours(cat: dict, moment: datetime) -> float:
    value = (
        cat.get("last_fed")
        or cat.get("adopted_at")
        or cat.get("created_at")
    )
    if not value:
        return 0.0
    return max(0.0, (moment - parse_time(value)).total_seconds() / 3600)


def mark_fled_if_needed(cat: dict) -> bool:
    """Make fleeing a single runtime state, independent of which UI is used."""
    if cat.get("is_fled"):
        return True
    if int(cat.get("love_bar", 100)) > 0:
        return False

    cat["is_fled"] = True
    cat["fled_at"] = cat.get("fled_at") or now_iso()
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["sleep_kind"] = None
    cat.pop("wake_notice_pending", None)
    cat.pop("wake_notice_kind", None)
    cat.pop("wake_notice_at", None)
    cat.pop("wake_notice_sent_to", None)
    clear_action_notice(cat)
    return True


def _decay_value(cat: dict, key: str, default: int) -> float:
    """Keep fractional decay so frequent refreshes never erase slow changes."""
    hidden_key = f"_decay_{key}"
    visible = float(cat.get(key, default))
    stored = cat.get(hidden_key)
    if stored is None:
        return visible

    stored_value = float(stored)
    # If another action changed the visible stat, trust the visible value and
    # restart the fractional accumulator from there.
    if round(stored_value) != round(visible):
        return visible
    return stored_value


def sync_decay_accumulators(cat: dict) -> None:
    """Sync hidden fractional counters after an explicit interaction change."""
    for key, default in {
        "hunger": 20,
        "happiness": 100,
        "love_bar": 100,
        "trust": 60,
        "boredom": 10,
    }.items():
        cat[f"_decay_{key}"] = float(cat.get(key, default))


def apply_decay(cat: dict) -> None:
    """Advance needs in small time slices so neglect is never backdated."""
    if cat.get("is_fled"):
        return

    now = datetime.utcnow()
    last_decay = parse_time(
        cat.get("last_decay_at") or cat.get("created_at") or cat["last_fed"]
    )
    elapsed = max(0.0, (now - last_decay).total_seconds() / 3600)
    if elapsed <= 0:
        _refresh_rest(cat, now)
        mark_fled_if_needed(cat)
        return

    rest_before = float(cat.get("rest_level", 100))
    rest_after = _refresh_rest(cat, now)

    hunger = _decay_value(cat, "hunger", 20)
    happiness = _decay_value(cat, "happiness", 100)
    love = _decay_value(cat, "love_bar", 100)
    trust = _decay_value(cat, "trust", 60)
    boredom = _decay_value(cat, "boredom", 10)

    cursor = last_decay
    total_seconds = max(1.0, (now - last_decay).total_seconds())
    while cursor < now:
        step_end = min(now, cursor + timedelta(hours=1))
        step_hours = (step_end - cursor).total_seconds() / 3600
        asleep = min(step_hours, _sleep_overlap_hours(cat, cursor, step_end))
        awake = max(0.0, step_hours - asleep)

        progress = (step_end - last_decay).total_seconds() / total_seconds
        rest = rest_before + (rest_after - rest_before) * progress

        hunger = min(
            100.0,
            hunger
            + awake * HUNGER_RISE_PER_AWAKE_HOUR
            + asleep * HUNGER_RISE_PER_SLEEP_HOUR,
        )

        boredom += awake * BOREDOM_RISE_PER_AWAKE_HOUR
        social_hours = _social_hours(cat, step_end)
        if social_hours >= 8:
            boredom += awake * 0.5
        if social_hours >= 14:
            boredom += awake * 0.75
        boredom += (
            _oversleep_between(cat, cursor, step_end)
            * BOREDOM_RISE_PER_OVERSLEEP_HOUR
        )
        boredom += (
            _long_sleep_between(cat, cursor, step_end)
            * BOREDOM_RISE_PER_LONG_SLEEP_HOUR
        )
        boredom = min(100.0, boredom)

        # Happiness is affected by actual current needs, not just elapsed time.
        happiness_loss = awake * 0.6
        if hunger >= 75:
            happiness_loss += asleep * 0.20
        if hunger >= 90:
            happiness_loss += asleep * 0.20
        if hunger >= 55:
            happiness_loss += awake * 0.5
        if hunger >= 75:
            happiness_loss += awake * 0.8
        if hunger >= 90:
            happiness_loss += awake * 0.8
        if rest <= 50:
            happiness_loss += awake * 0.5
        if rest <= 30:
            happiness_loss += awake * 0.8
        if rest <= 10:
            happiness_loss += awake * 1.0
        if boredom >= 50:
            happiness_loss += awake * 0.5
        if boredom >= 75:
            happiness_loss += awake * 0.8
        if _walk_hours(cat, step_end) >= WALK_DUE_HOURS:
            happiness_loss += awake * 0.35
        happiness = max(0.0, happiness - happiness_loss)

        # Love starts dropping only after real neglect has begun.
        love_severity = 0.0
        if hunger >= 75:
            love_severity += 0.35
        if happiness <= 35:
            love_severity += 0.30
        if rest <= 20:
            love_severity += 0.25
        if boredom >= 85:
            love_severity += 0.10
        love -= step_hours * 0.9 * min(1.0, love_severity)
        love = max(0.0, love)

        # Trust is harder to lose and recover than mood/love. Only severe,
        # sustained neglect damages it.
        trust_severity = 0.0
        if hunger >= 90:
            trust_severity += 0.40
        if rest <= 10:
            trust_severity += 0.30
        if happiness <= 20:
            trust_severity += 0.20
        if love <= 20:
            trust_severity += 0.15
        trust -= step_hours * TRUST_FALL_PER_NEGLECT_HOUR * min(
            1.0, trust_severity
        )

        # Going a long time without food damages trust on its own. The grace
        # period prevents normal meal spacing from being punished.
        unfed_hours = _unfed_hours(cat, step_end)
        if hunger >= 75 and unfed_hours >= UNFED_TRUST_GRACE_HOURS:
            starvation_pressure = min(
                1.5,
                0.35 + (unfed_hours - UNFED_TRUST_GRACE_HOURS) * 0.06,
            )
            trust -= (
                step_hours
                * TRUST_FALL_PER_UNFED_HOUR
                * starvation_pressure
            )

        trust = max(0.0, trust)

        cursor = step_end

    hunger = max(0.0, min(100.0, hunger))
    happiness = max(0.0, min(100.0, happiness))
    love = max(0.0, min(100.0, love))
    trust = max(0.0, min(100.0, trust))
    boredom = max(0.0, min(100.0, boredom))
    cat["_decay_hunger"] = hunger
    cat["_decay_happiness"] = happiness
    cat["_decay_love_bar"] = love
    cat["_decay_trust"] = trust
    cat["_decay_boredom"] = boredom
    cat["hunger"] = round(hunger)
    cat["happiness"] = round(happiness)
    cat["love_bar"] = round(love)
    cat["trust"] = round(trust)
    cat["boredom"] = round(boredom)
    cat["last_decay_at"] = now.isoformat()
    mark_fled_if_needed(cat)


def _routine_streak(cat: dict, action: str, moment: datetime) -> int:
    previous = cat.get("last_care_action")
    previous_at = cat.get("last_care_at")
    recent = False
    if previous_at:
        recent = (
            moment - parse_time(previous_at)
        ).total_seconds() <= ROUTINE_WINDOW_HOURS * 3600

    if previous == action and recent:
        return int(cat.get("same_action_streak", 0)) + 1
    return 1


def _action_overused(cat: dict, action: str, moment: datetime) -> bool:
    previous_at = cat.get("last_care_at")
    if cat.get("last_care_action") != action or not previous_at:
        return False
    recent = (
        moment - parse_time(previous_at)
    ).total_seconds() <= ROUTINE_WINDOW_HOURS * 3600
    threshold = 4 if action in {"talk", "walk", "relax", "toy"} else 5
    return recent and int(cat.get("same_action_streak", 0)) >= threshold


def apply_light_interaction(cat: dict, action: str) -> None:
    """Accept interaction during cooldown without turning it into stat farming."""
    moment = datetime.utcnow()
    streak = _routine_streak(cat, action, moment)
    cat["last_care_action"] = action
    cat["same_action_streak"] = streak
    cat["last_care_at"] = moment.isoformat()

    if action in {"play", "walk", "talk", "relax", "toy"}:
        cat["last_social_at"] = moment.isoformat()

    boredom_penalty = 0
    if action == "play" and streak >= 5:
        boredom_penalty = min(15, 5 + (streak - 5) * 3)
    elif action == "toy" and streak >= 4:
        boredom_penalty = min(18, 6 + (streak - 4) * 4)
    elif action in {"talk", "walk"} and streak >= 4:
        boredom_penalty = min(15, (streak - 3) * 4)

    if boredom_penalty:
        cat["boredom"] = min(
            100,
            int(cat.get("boredom", 10)) + boredom_penalty,
        )
        sync_decay_accumulators(cat)

    cat["last_care_meaningful"] = False



def apply_care_effects(cat: dict, action: str) -> None:
    """Apply full care; stable cats can still interact without stat farming."""
    moment = datetime.utcnow()
    streak = _routine_streak(cat, action, moment)
    cat["last_care_action"] = action
    cat["same_action_streak"] = streak
    cat["last_care_at"] = moment.isoformat()

    boredom = int(cat.get("boredom", 10))
    trust = int(cat.get("trust", 60))
    love_before = int(cat.get("love_bar", 100))
    rest_before = sleep_need_percent(cat)
    novelty = max(0.25, 1.0 - max(0, streak - 2) * 0.25)
    hunger_before = int(cat.get("hunger", 20))
    happiness_before = int(cat.get("happiness", 100))

    meaningful = True
    if action == "feed":
        meaningful = hunger_before >= 35
        if meaningful:
            cat["hunger"] = max(0, hunger_before - 40)
            boredom_drop = 10
        elif hunger_before > 15:
            cat["hunger"] = max(15, hunger_before - 10)
            boredom_drop = 4
        else:
            cat["hunger"] = hunger_before
            boredom_drop = 1
        cat["happiness"] = min(100, happiness_before + (8 if meaningful else 1))
        cat["love_bar"] = min(100, love_before + (3 if meaningful else 0))
        cat["boredom"] = max(0, boredom - boredom_drop)

    elif action == "play":
        meaningful = (boredom >= 20 or happiness_before <= 80) and streak < 5
        if not meaningful and streak < 5:
            happiness_gain, love_gain, boredom_delta = 1, 1, 0
        elif streak == 1:
            happiness_gain, love_gain, boredom_delta = 24, 5, -35
        elif streak == 2:
            happiness_gain, love_gain, boredom_delta = 20, 4, -28
        elif streak == 3:
            happiness_gain, love_gain, boredom_delta = 12, 3, -16
        elif streak == 4:
            happiness_gain, love_gain, boredom_delta = 6, 2, -6
        else:
            happiness_gain, love_gain = 0, 0
            boredom_delta = min(20, 8 + (streak - 5) * 4)

        cat["happiness"] = min(100, happiness_before + happiness_gain)
        cat["love_bar"] = min(100, love_before + love_gain)
        if streak >= 5:
            cat["boredom"] = min(100, max(45, boredom + boredom_delta))
        else:
            cat["boredom"] = max(0, min(100, boredom + boredom_delta))
        cat["hunger"] = min(100, hunger_before + (7 if meaningful else 3))
        cat["rest_level"] = max(0, rest_before - (7 if meaningful else 3))

    elif action == "toy":
        meaningful = (
            boredom >= 10
            or happiness_before <= 90
            or love_before <= 90
        ) and streak < 4

        if streak == 1:
            happiness_gain, love_gain, boredom_delta = 18, 6, -45
        elif streak == 2:
            happiness_gain, love_gain, boredom_delta = 12, 4, -28
        elif streak == 3:
            happiness_gain, love_gain, boredom_delta = 6, 2, -12
        else:
            happiness_gain, love_gain = 0, 0
            boredom_delta = min(22, 8 + (streak - 4) * 4)

        cat["happiness"] = min(100, happiness_before + happiness_gain)
        cat["love_bar"] = min(100, love_before + love_gain)
        cat["boredom"] = max(0, min(100, boredom + boredom_delta))
        cat["hunger"] = min(100, hunger_before + (4 if meaningful else 2))
        cat["rest_level"] = max(0, rest_before - (4 if meaningful else 2))
        cat["last_social_at"] = moment.isoformat()

    elif action == "walk":
        meaningful = boredom >= 25 or _walk_hours(cat, moment) >= 8

        if streak == 1:
            happiness_gain, love_gain = ((20, 7) if meaningful else (2, 1))
            boredom_delta = -22 if meaningful else -2
        elif streak == 2:
            happiness_gain, love_gain = ((12, 5) if meaningful else (1, 1))
            boredom_delta = -14 if meaningful else 0
        elif streak == 3:
            happiness_gain, love_gain = ((6, 3) if meaningful else (1, 0))
            boredom_delta = -6 if meaningful else 2
        elif streak == 4:
            happiness_gain, love_gain, boredom_delta = 2, 1, 4
        elif streak == 5:
            happiness_gain, love_gain, boredom_delta = 1, 0, 8
        else:
            happiness_gain, love_gain = 0, 0
            boredom_delta = min(15, 10 + (streak - 6) * 2)

        cat["happiness"] = min(100, happiness_before + happiness_gain)
        cat["love_bar"] = min(100, love_before + love_gain)
        cat["boredom"] = max(0, min(100, boredom + boredom_delta))
        cat["hunger"] = min(100, hunger_before + (10 if meaningful else 4))
        cat["rest_level"] = max(0, rest_before - (12 if meaningful else 5))

    elif action == "talk":
        meaningful = (
            boredom >= 15
            or happiness_before <= 85
            or trust <= 65
            or love_before <= 50
        )

        if streak == 1:
            happiness_gain, love_gain = ((7, 3) if meaningful else (1, 1))
            boredom_delta = -20 if meaningful else 0
        elif streak == 2:
            happiness_gain, love_gain = ((5, 2) if meaningful else (1, 0))
            boredom_delta = -12 if meaningful else 0
        elif streak == 3:
            happiness_gain, love_gain = ((3, 1) if meaningful else (1, 0))
            boredom_delta = -5 if meaningful else 0
        elif streak == 4:
            happiness_gain, love_gain, boredom_delta = 1, 0, 3
        elif streak == 5:
            happiness_gain, love_gain, boredom_delta = 0, 0, 7
        else:
            happiness_gain, love_gain = 0, 0
            boredom_delta = min(15, 10 + (streak - 6) * 2)

        cat["happiness"] = min(100, happiness_before + happiness_gain)
        cat["love_bar"] = min(100, love_before + love_gain)
        cat["boredom"] = max(0, min(100, boredom + boredom_delta))
        cat["last_social_at"] = moment.isoformat()

    elif action == "relax":
        meaningful = (
            rest_before <= 85
            or boredom >= 15
            or happiness_before <= 85
        )
        if meaningful:
            happiness_gain, love_gain, boredom_drop, rest_gain = 4, 2, 10, 8
        else:
            happiness_gain, love_gain, boredom_drop, rest_gain = 1, 1, 0, 2
        cat["happiness"] = min(100, happiness_before + happiness_gain)
        cat["love_bar"] = min(100, love_before + love_gain)
        cat["boredom"] = max(0, boredom - boredom_drop)
        cat["rest_level"] = min(100, rest_before + rest_gain)
        cat["hunger"] = min(100, hunger_before + 1)
        cat["last_social_at"] = moment.isoformat()

    else:
        return

    if action in {"play", "walk", "toy"}:
        cat["last_social_at"] = moment.isoformat()

    if action in {"talk", "walk", "toy"} and streak >= 4:
        meaningful = False

    trust_gain = {
        "feed": 2,
        "play": 2,
        "toy": 1,
        "walk": 3,
        "talk": 2,
        "relax": 1,
    }[action]
    if not meaningful:
        trust_gain = 0
    elif streak >= 3:
        trust_gain = max(0, trust_gain - (streak - 2))
    cat["trust"] = min(100, trust + trust_gain)
    cat["last_care_meaningful"] = bool(meaningful)

    if action == "relax" and streak >= 4:
        cat["boredom"] = min(
            100,
            int(cat.get("boredom", 0)) + min(12, (streak - 3) * 3),
        )

    sync_decay_accumulators(cat)


def _attention_due(cat: dict, moment: datetime) -> bool:
    """Whether the cat currently needs a real social interaction."""
    boredom = int(cat.get("boredom", 10))
    happiness = int(cat.get("happiness", 100))
    trust = int(cat.get("trust", 60))
    love = int(cat.get("love_bar", 100))

    # Relationship or mood trouble is actionable immediately. Mild loneliness
    # still needs time without interaction before it becomes a real need.
    if love <= 30 or trust <= 35 or happiness <= 40 or boredom >= 65:
        return True

    social_hours = _social_hours(cat, moment)
    return social_hours >= 10 and (boredom >= 25 or happiness <= 50)


def is_action_cooldown_bypassed(cat: dict, action: str) -> bool:
    """True only when a current need is actively overriding a live cooldown."""
    if not can_bypass_action_cooldown(cat, action):
        return False

    specs = {
        "feed": ("last_fed", settings.feed_cooldown),
        "play": ("last_played", settings.play_cooldown),
        "toy": ("last_toy", settings.toy_cooldown),
        "walk": ("last_walk", settings.walk_cooldown),
        "talk": ("last_talk", settings.talk_cooldown),
        "relax": ("last_relax", settings.relax_cooldown),
    }
    spec = specs.get(action)
    if spec is None:
        return False

    timestamp_key, cooldown = spec
    last_action = cat.get(timestamp_key)
    if not last_action:
        return False

    elapsed = (datetime.utcnow() - parse_time(last_action)).total_seconds()
    return elapsed < cooldown


def can_bypass_action_cooldown(cat: dict, action: str) -> bool:
    """Needs override cooldowns; optional interactions still respect them."""
    moment = datetime.utcnow()
    if action == "feed":
        return int(cat.get("hunger", 20)) >= settings.hunger_alert_threshold
    if action == "play":
        return (
            int(cat.get("boredom", 10)) >= 35
            and not _action_overused(cat, "play", moment)
        )
    if action == "toy":
        return (
            int(cat.get("boredom", 10)) >= 35
            and not _action_overused(cat, "toy", moment)
        )
    if action == "walk":
        return (
            _walk_hours(cat, moment) >= WALK_DUE_HOURS
            and not _action_overused(cat, "walk", moment)
        )
    if action == "talk":
        return (
            _attention_due(cat, moment)
            and not _action_overused(cat, "talk", moment)
        )
    if action == "relax":
        return (
            (sleep_need_percent(cat) <= 75 or int(cat.get("boredom", 10)) >= 35)
            and not _action_overused(cat, "relax", moment)
        )
    return False


def action_block_reason(cat: dict, action: str) -> str | None:
    """Only block interactions that are physically unreasonable."""
    hunger = int(cat.get("hunger", 20))
    if action in {"play", "walk", "toy"}:
        if hunger >= 90:
            return "starving"
        if sleep_need_percent(cat) <= 30:
            return "tired"
    return None


def recommended_action(cat: dict) -> str | None:
    """Choose one useful next action for the current state."""
    if is_sleeping(cat):
        return None

    hunger = int(cat.get("hunger", 20))
    rest = sleep_need_percent(cat)
    moment = datetime.utcnow()

    if hunger >= settings.hunger_alert_threshold:
        return "feed"
    if rest <= 30:
        return "sleep"

    attention_due = _attention_due(cat, moment)
    talk_overused = _action_overused(cat, "talk", moment)
    walk_overused = _action_overused(cat, "walk", moment)
    play_overused = _action_overused(cat, "play", moment)
    toy_overused = _action_overused(cat, "toy", moment)

    if attention_due and not talk_overused:
        return "talk"
    if _walk_hours(cat, moment) >= WALK_DUE_HOURS and not walk_overused:
        return "walk"
    if int(cat.get("boredom", 10)) >= 35:
        if not play_overused:
            return "play"
        if not toy_overused:
            return "toy"
        return "relax"
    if attention_due:
        return "relax"
    if rest <= 50:
        return "sleep"
    if rest <= 75:
        return "relax"
    return None


def care_reward_points(
    cat: dict,
    action: str,
    *,
    bypassed_cooldown: bool = False,
) -> int:
    """Same reward on every surface; need-rescue bypasses never farm points."""
    if bypassed_cooldown or not bool(cat.get("last_care_meaningful", False)):
        return 0
    streak = int(cat.get("same_action_streak", 1))
    if action == "play" and streak >= 5:
        return 0
    if action in {"talk", "walk", "toy"} and streak >= 4:
        return 0
    return {
        "feed": 5,
        "play": 5,
        "toy": 4,
        "walk": 10,
        "talk": 3,
        "relax": 2,
    }.get(action, 0)


def collect_needs(cat: dict) -> list[str]:
    """One severity tier per need, ordered from relationship to physical needs."""
    needs: list[str] = []
    rest = sleep_need_percent(cat)
    hunger = int(cat.get("hunger", 20))
    happiness = int(cat.get("happiness", 100))
    love = int(cat.get("love_bar", 100))
    trust = int(cat.get("trust", 60))
    boredom = int(cat.get("boredom", 10))

    if love <= 12:
        needs.append("love_critical")
    elif love <= 30:
        needs.append("love_low")

    if trust <= 15:
        needs.append("trust_critical")
    elif trust <= 35:
        needs.append("trust_low")

    if hunger >= 90:
        needs.append("starving")
    elif hunger >= settings.hunger_alert_threshold:
        needs.append("hungry")
    elif hunger >= 55:
        needs.append("peckish")

    if not is_sleeping(cat):
        if rest <= 10:
            needs.append("exhausted")
        elif rest <= 30:
            needs.append("tired")
        elif rest <= 50:
            needs.append("sleepy")

    moment = datetime.utcnow()
    walk_hours = _walk_hours(cat, moment)
    if walk_hours >= WALK_DUE_HOURS:
        needs.append("walk_due")

    if _attention_due(cat, moment):
        needs.append("attention_due")

    if boredom >= 85:
        needs.append("very_bored")
    elif boredom >= 65:
        needs.append("bored")
    elif boredom >= 35:
        needs.append("restless")

    if happiness <= 20:
        needs.append("very_sad")
    elif happiness <= 40:
        needs.append("sad")

    return needs


def notification_gap_seconds(needs: list[str]) -> int:
    """Urgent needs remind sooner; mild warnings stay quiet longer."""
    urgent = {
        "love_critical",
        "trust_critical",
        "starving",
        "exhausted",
        "very_bored",
        "very_sad",
    }
    moderate = {
        "love_low",
        "trust_low",
        "hungry",
        "tired",
        "bored",
        "sad",
        "walk_due",
    }
    if any(item in urgent for item in needs):
        return min(settings.notification_min_gap, 2 * 60 * 60)
    if any(item in moderate for item in needs):
        return min(settings.notification_min_gap, 4 * 60 * 60)
    return settings.notification_min_gap


async def ensure_user(user_id: int) -> dict:
    async with _lock:
        data = _read()
        user = data["users"].setdefault(str(user_id), {
            "user_id": user_id,
            "points": 100,
            "purchases": [],
            "created_at": now_iso(),
        })
        user.setdefault("purchases", [])
        _write(data)
        return user


async def get_user_points(user_id: int) -> int:
    user = await ensure_user(user_id)
    return user["points"]


async def clear_purchases(user_id: int) -> None:
    async with _lock:
        data = _read()
        user = data["users"].setdefault(str(user_id), {"user_id": user_id, "points": 100, "purchases": [], "created_at": now_iso()})
        user["purchases"] = []
        _write(data)


async def get_purchases(user_id: int) -> list[str]:
    user = await ensure_user(user_id)
    return list(user.get("purchases", []))


async def get_user_cat(user_id: int) -> dict | None:
    async with _lock:
        data = _read()
        return next((cat for cat in data["cats"] if cat["owner_id"] == user_id and not cat["is_fled"]), None)


async def get_cat_by_id(
    cat_id: int,
    *,
    include_fled: bool = False,
) -> dict | None:
    async with _lock:
        data = _read()
        return next(
            (
                cat
                for cat in data["cats"]
                if int(cat.get("cat_id", 0)) == int(cat_id)
                and (include_fled or not cat.get("is_fled"))
            ),
            None,
        )


async def get_latest_cat_for_user(
    user_id: int,
    *,
    include_fled: bool = True,
) -> dict | None:
    async with _lock:
        cats = [
            cat
            for cat in _read()["cats"]
            if int(cat.get("owner_id", 0)) == int(user_id)
            and (include_fled or not cat.get("is_fled"))
        ]
        return max(cats, key=lambda cat: int(cat.get("cat_id", 0))) if cats else None


async def get_active_cats() -> list[dict]:
    async with _lock:
        return [cat for cat in _read()["cats"] if not cat.get("is_fled")]


async def create_cat(cat: dict) -> dict:
    async with _lock:
        data = _read()
        cat["cat_id"] = max((item.get("cat_id", 0) for item in data["cats"]), default=0) + 1
        data["cats"].append(cat)
        _write(data)
        return cat


async def update_cat(cat: dict) -> None:
    async with _lock:
        data = _read()
        for index, saved in enumerate(data["cats"]):
            if saved["cat_id"] == cat["cat_id"]:
                data["cats"][index] = cat
                _write(data)
                return


async def award_points(user_id: int, delta: int, reason: str) -> int:
    async with _lock:
        data = _read()
        user = data["users"].setdefault(str(user_id), {
            "user_id": user_id,
            "points": 100,
            "created_at": now_iso(),
        })
        user["points"] += delta
        data["points_log"].append({
            "user_id": user_id,
            "delta": delta,
            "reason": reason,
            "ts": now_iso(),
        })
        _write(data)
        return user["points"]


async def get_media_file_id(
    kind: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> str:
    async with _lock:
        value, _ = resolve_media_value(
            _read().get("media", {}),
            kind,
            breed,
            age_stage,
        )
        return value


def get_media_file_id_sync(
    kind: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> str:
    value, _ = resolve_media_value(
        _read().get("media", {}),
        kind,
        breed,
        age_stage,
    )
    return value


def get_media_type_sync(
    kind: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> str:
    value, _ = resolve_media_value(
        _read().get("media_types", {}),
        kind,
        breed,
        age_stage,
        default="photo",
    )
    return value or "photo"


async def set_media_file_id(
    kind: str,
    file_id: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> None:
    async with _lock:
        data = _read()
        state = normalize_cat_state(kind)
        if breed and age_stage:
            key = f"{breed}:{age_stage}:{state}"
        elif breed:
            key = f"{breed}:{kind}"
        else:
            key = kind
        data.setdefault("media", {})[key] = file_id
        _write(data)


async def set_media_file(
    kind: str,
    file_id: str,
    media_type: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> None:
    async with _lock:
        data = _read()
        state = normalize_cat_state(kind)
        if breed and age_stage:
            key = f"{breed}:{age_stage}:{state}"
        elif breed:
            # Keep the two-part write contract for old callers and JSON data.
            key = f"{breed}:{kind}"
        else:
            key = kind
        data.setdefault("media", {})[key] = file_id
        data.setdefault("media_types", {})[key] = media_type
        _write(data)



async def get_media_cache_entry(cache_key: str) -> dict | None:
    """Return cached Telegram metadata for one local asset."""
    async with _lock:
        entry = _read().get("media_cache", {}).get(cache_key)
        return dict(entry) if isinstance(entry, dict) else None


async def set_media_cache_entry(
    cache_key: str,
    *,
    file_id: str,
    file_hash: str,
    media_type: str,
    path: str,
) -> None:
    """Persist metadata only; asset bytes stay on the filesystem."""
    async with _lock:
        data = _read()
        data.setdefault("media_cache", {})[cache_key] = {
            "file_id": file_id,
            "file_hash": file_hash,
            "media_type": media_type,
            "path": path,
            "updated_at": now_iso(),
        }
        _write(data)


async def get_media_override(
    kind: str,
    breed: str,
    age_stage: str,
) -> dict | None:
    """Return only an exact explicit /dev override for this asset identity."""
    async with _lock:
        overrides = _read().get("media_overrides", {})
        state = normalize_cat_state(kind)
        key = f"{breed}:{age_stage}:{state}"
        value = overrides.get(key)
        if isinstance(value, dict) and value.get("file_id"):
            result = dict(value)
            result["key"] = key
            return result
        return None


async def set_media_override(
    kind: str,
    file_id: str,
    media_type: str,
    *,
    breed: str,
    age_stage: str,
) -> None:
    """Store an explicit admin override separately from automatic local cache."""
    async with _lock:
        data = _read()
        state = normalize_cat_state(kind)
        key = f"{breed}:{age_stage}:{state}"
        data.setdefault("media_overrides", {})[key] = {
            "file_id": file_id,
            "media_type": media_type,
            "updated_at": now_iso(),
        }
        _write(data)
