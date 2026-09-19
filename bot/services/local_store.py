"""Small JSON-backed store used for local development."""
import asyncio
import json
from datetime import datetime
from pathlib import Path

from bot.config import settings
from bot.services.cat_assets import normalize_cat_state, resolve_media_value

_lock = asyncio.Lock()


def _path() -> Path:
    path = Path(settings.json_data_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _read() -> dict:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {"users": {}, "cats": [], "items": [], "user_inventory": [], "points_log": [], "media": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, default in {
        "users": {},
        "cats": [],
        "items": [],
        "user_inventory": [],
        "points_log": [],
        "media": {},
        "media_types": {},
        "media_cache": {},
        "media_overrides": {},
    }.items():
        data.setdefault(key, default)
    return data


def _write(data: dict) -> None:
    path = _path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def is_sleeping(cat: dict) -> bool:
    sleep_until = cat.get("sleep_until")
    return bool(sleep_until and parse_time(sleep_until) > datetime.utcnow())


REST_FALL_PER_AWAKE_HOUR = 8.0
REST_RECOVERY_PER_SLEEP_HOUR = 10.0
BOREDOM_RISE_PER_AWAKE_HOUR = 1.25
BOREDOM_RISE_PER_SLEEP_HOUR = 0.75
TRUST_FALL_PER_NEGLECT_HOUR = 0.9
HUNGER_RISE_PER_AWAKE_HOUR = 3.0
HUNGER_RISE_PER_SLEEP_HOUR = 1.5
WALK_DUE_HOURS = 18.0


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


def _refresh_rest(cat: dict, moment: datetime | None = None) -> int:
    """Keep a persistent rest meter: awake drains it, actual sleep restores it."""
    moment = moment or datetime.utcnow()
    anchor_raw = cat.get("rest_updated_at") or cat.get("last_wake_at") or cat.get("created_at")
    anchor = parse_time(anchor_raw) if anchor_raw else moment
    if anchor > moment:
        anchor = moment

    if "rest_level" in cat:
        rest = float(cat.get("rest_level", 100))
    else:
        # Backward compatible migration for cats created before rest_level existed.
        awake_hours = max(0.0, (moment - anchor).total_seconds() / 3600)
        rest = max(0.0, 100.0 - awake_hours * REST_FALL_PER_AWAKE_HOUR)
        anchor = moment

    elapsed = max(0.0, (moment - anchor).total_seconds() / 3600)
    asleep = min(elapsed, _sleep_overlap_hours(cat, anchor, moment))
    awake = max(0.0, elapsed - asleep)
    rest += asleep * REST_RECOVERY_PER_SLEEP_HOUR
    rest -= awake * REST_FALL_PER_AWAKE_HOUR

    cat["rest_level"] = max(0, min(100, round(rest)))
    cat["rest_updated_at"] = moment.isoformat()
    return int(cat["rest_level"])


def sleep_need_percent(cat: dict) -> int:
    """100 = fully rested, 0 = exhausted."""
    return _refresh_rest(cat)


def wake_if_ready(cat: dict) -> bool:
    if cat.get("sleep_until") and not is_sleeping(cat):
        return finish_sleep(cat)
    return False


def start_sleep(cat: dict) -> int:
    now = datetime.utcnow()
    _refresh_rest(cat, now)
    today = now.date().isoformat()
    if cat.get("sleep_day") != today:
        cat["sleep_day"] = today
        cat["slept_today_hours"] = 0.0
    remaining = max(0.5, 10.0 - float(cat.get("slept_today_hours", 0)))
    import random
    # A tired cat gets a longer useful sleep instead of many tiny random naps.
    rest = int(cat.get("rest_level", 100))
    target = 6.0 if rest <= 20 else 4.0 if rest <= 50 else 2.0
    hours = min(remaining, max(0.5, target + random.uniform(-0.25, 0.5)))
    cat["sleep_started_at"] = now.isoformat()
    cat["sleep_until"] = datetime.fromtimestamp(now.timestamp() + hours * 3600).isoformat()
    cat["sleep_planned_hours"] = hours
    cat["rest_updated_at"] = now.isoformat()
    return round(hours * 60)


def finish_sleep(cat: dict) -> bool:
    if not cat.get("sleep_until") or is_sleeping(cat):
        return False
    now = datetime.utcnow()
    _refresh_rest(cat, now)
    started = cat.get("sleep_started_at")
    if started:
        elapsed = max(0, (now - parse_time(started)).total_seconds() / 3600)
        cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + min(
            elapsed, float(cat.get("sleep_planned_hours", 0))
        )
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["last_wake_at"] = now.isoformat()
    cat["rest_updated_at"] = now.isoformat()
    return True


def wake_now(cat: dict) -> bool:
    if not cat.get("sleep_until"):
        return False
    now = datetime.utcnow()
    _refresh_rest(cat, now)
    started = cat.get("sleep_started_at")
    if started:
        elapsed = max(0, (now - parse_time(started)).total_seconds() / 3600)
        cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + min(
            elapsed, float(cat.get("sleep_planned_hours", 0))
        )
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["last_wake_at"] = now.isoformat()
    cat["rest_updated_at"] = now.isoformat()
    return True


def clear_action_notice(cat: dict) -> None:
    cat.pop("action_notice", None)
    cat.pop("action_notice_until", None)
    cat.pop("action_notice_token", None)


def apply_decay(cat: dict) -> None:
    """Advance all needs together so bad states reinforce each other."""
    now = datetime.utcnow()
    last_decay = parse_time(cat.get("last_decay_at") or cat.get("created_at") or cat["last_fed"])
    hours = max(0.0, (now - last_decay).total_seconds() / 3600)
    if hours <= 0:
        _refresh_rest(cat, now)
        return

    asleep = min(hours, _sleep_overlap_hours(cat, last_decay, now))
    awake = max(0.0, hours - asleep)
    rest = _refresh_rest(cat, now)

    old_hunger = float(cat.get("hunger", 0))
    hunger = old_hunger + awake * HUNGER_RISE_PER_AWAKE_HOUR + asleep * HUNGER_RISE_PER_SLEEP_HOUR
    cat["hunger"] = max(0, min(100, round(hunger)))

    # Boredom is an unmet stimulation need. Being awake without interaction
    # raises it, and oversleeping also raises it because the routine becomes flat.
    boredom = float(cat.get("boredom", 10))
    boredom += awake * BOREDOM_RISE_PER_AWAKE_HOUR
    boredom += asleep * BOREDOM_RISE_PER_SLEEP_HOUR
    repeated = int(cat.get("same_action_streak", 0))
    if repeated >= 3:
        boredom += hours * min(2.0, (repeated - 2) * 0.4)
    cat["boredom"] = max(0, min(100, round(boredom)))

    # Happiness falls slowly by itself, then faster when hunger, exhaustion or
    # being kept indoors for too long starts to hurt the cat.
    happiness_loss = awake * 1.0
    avg_hunger = (old_hunger + cat["hunger"]) / 2
    if avg_hunger >= 50:
        happiness_loss += awake * 0.75
    if avg_hunger >= 75:
        happiness_loss += awake * 1.25
    if rest <= 40:
        happiness_loss += awake * 1.0
    if rest <= 20:
        happiness_loss += awake * 1.5
    if cat["boredom"] >= 50:
        happiness_loss += awake * 0.75
    if cat["boredom"] >= 80:
        happiness_loss += awake * 1.25

    last_walk = cat.get("last_walk")
    if last_walk:
        walk_hours = max(0.0, (now - parse_time(last_walk)).total_seconds() / 3600)
        if walk_hours >= WALK_DUE_HOURS:
            happiness_loss += awake * 0.75

    cat["happiness"] = max(0, min(100, round(float(cat.get("happiness", 100)) - happiness_loss)))

    # Love is relationship health, not a clock. It only falls when actual
    # neglect exists, and severe needs compound the loss.
    severity = 0.0
    if cat["hunger"] >= 75:
        severity += 0.45
    if cat["happiness"] <= 35:
        severity += 0.35
    if rest <= 20:
        severity += 0.30
    severity = min(1.0, severity)
    if severity:
        cat["love_bar"] = max(
            0,
            min(100, round(float(cat.get("love_bar", 100)) - hours * 1.2 * severity)),
        )

    # Trust is slower and more structural than love: severe neglect teaches the
    # cat that care is unreliable. Ordinary passing time does not lower it.
    trust_severity = 0.0
    if cat["hunger"] >= 85:
        trust_severity += 0.45
    if rest <= 10:
        trust_severity += 0.35
    if cat["happiness"] <= 20:
        trust_severity += 0.25
    if cat["love_bar"] <= 25:
        trust_severity += 0.20
    if trust_severity:
        cat["trust"] = max(
            0,
            min(
                100,
                round(
                    float(cat.get("trust", 60))
                    - hours * TRUST_FALL_PER_NEGLECT_HOUR * min(1.0, trust_severity)
                ),
            ),
        )
    else:
        cat["trust"] = max(0, min(100, int(cat.get("trust", 60))))

    cat["last_decay_at"] = now.isoformat()


def apply_care_effects(cat: dict, action: str) -> None:
    """Apply care and relationship effects consistently across every surface."""
    previous = cat.get("last_care_action")
    streak = int(cat.get("same_action_streak", 0))
    if previous == action:
        streak += 1
    else:
        streak = 1
    cat["last_care_action"] = action
    cat["same_action_streak"] = streak

    boredom = int(cat.get("boredom", 10))
    trust = int(cat.get("trust", 60))

    if action == "feed":
        cat["hunger"] = max(0, int(cat["hunger"]) - 40)
        cat["happiness"] = min(100, int(cat["happiness"]) + 8)
        cat["love_bar"] = min(100, int(cat["love_bar"]) + 3)
        cat["trust"] = min(100, trust + 3)
        # Food fixes hunger, not boredom. Repeating only food becomes routine.
        if streak >= 3:
            cat["boredom"] = min(100, boredom + 3)
    elif action == "play":
        cat["happiness"] = min(100, int(cat["happiness"]) + 25)
        cat["love_bar"] = min(100, int(cat["love_bar"]) + 5)
        cat["trust"] = min(100, trust + 2)
        cat["boredom"] = max(0, boredom - 35)
        cat["hunger"] = min(100, int(cat["hunger"]) + 7)
        cat["rest_level"] = max(0, sleep_need_percent(cat) - 7)
    elif action == "walk":
        cat["happiness"] = min(100, int(cat["happiness"]) + 22)
        cat["love_bar"] = min(100, int(cat["love_bar"]) + 8)
        cat["trust"] = min(100, trust + 4)
        cat["boredom"] = max(0, boredom - 12)
        cat["hunger"] = min(100, int(cat["hunger"]) + 10)
        cat["rest_level"] = max(0, sleep_need_percent(cat) - 12)
    elif action == "talk":
        cat["happiness"] = min(100, int(cat["happiness"]) + 8)
        cat["love_bar"] = min(100, int(cat["love_bar"]) + 3)
        cat["trust"] = min(100, trust + 3)
        cat["boredom"] = max(0, boredom - 28)

    # Repeating the exact same interaction too many times makes it less novel.
    if action in {"play", "talk", "walk"} and streak >= 4:
        cat["boredom"] = min(100, int(cat.get("boredom", 0)) + min(12, (streak - 3) * 3))


def collect_needs(cat: dict) -> list[str]:
    """Return every currently unmet need, ordered from most urgent."""
    needs: list[str] = []
    rest = sleep_need_percent(cat)
    if int(cat.get("love_bar", 100)) <= 20:
        needs.append("love_low")
    if int(cat.get("trust", 60)) <= 25:
        needs.append("trust_low")
    if int(cat.get("hunger", 0)) >= settings.hunger_alert_threshold:
        needs.append("hungry")
    if rest <= 30 and not is_sleeping(cat):
        needs.append("tired")
    last_walk = cat.get("last_walk")
    if last_walk:
        walk_hours = max(0.0, (datetime.utcnow() - parse_time(last_walk)).total_seconds() / 3600)
        if walk_hours >= WALK_DUE_HOURS and int(cat.get("happiness", 100)) <= 70:
            needs.append("walk_due")
    if int(cat.get("boredom", 10)) >= 75:
        needs.append("bored")
    if int(cat.get("happiness", 100)) <= settings.happiness_alert_threshold:
        needs.append("sad")
    return needs


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
