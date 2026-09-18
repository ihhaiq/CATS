"""Small JSON-backed store used for local development."""
import asyncio
import json
import random
import secrets
from datetime import datetime
from pathlib import Path

from bot.config import settings

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
    }.items():
        data.setdefault(key, default)
    return data


def _write(data: dict) -> None:
    """Write JSON atomically so a crash cannot leave a half-written store."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def is_sleeping(cat: dict) -> bool:
    sleep_until = cat.get("sleep_until")
    return bool(sleep_until and parse_time(sleep_until) > datetime.utcnow())


def sleep_need_percent(cat: dict) -> int:
    """Return rest/readiness. 100 is rested; the meter falls in visible minute steps."""
    if is_sleeping(cat):
        return 100
    last_wake = cat.get("last_wake_at")
    if not last_wake:
        return 100
    awake_minutes = max(0.0, (datetime.utcnow() - parse_time(last_wake)).total_seconds() / 60)
    interval = max(1, settings.sleep_need_drop_interval_minutes)
    drop = max(1, settings.sleep_need_drop_per_interval)
    elapsed_intervals = int(awake_minutes // interval)
    return max(0, min(100, 100 - elapsed_intervals * drop))


def wake_if_ready(cat: dict) -> bool:
    if cat.get("sleep_until") and not is_sleeping(cat):
        cat["sleep_until"] = None
        cat["sleep_started_at"] = None
        return True
    return False


def start_sleep(cat: dict) -> int:
    now = datetime.utcnow()
    today = now.date().isoformat()
    if cat.get("sleep_day") != today:
        cat["sleep_day"] = today
        cat["slept_today_hours"] = 0.0
    remaining = max(0.5, 10.0 - float(cat.get("slept_today_hours", 0)))
    hours = min(remaining, random.uniform(0.5, 2.5))
    cat["sleep_started_at"] = now.isoformat()
    cat["sleep_until"] = datetime.fromtimestamp(now.timestamp() + hours * 3600).isoformat()
    cat["sleep_planned_hours"] = hours
    # Decay is frozen during sleep, so start a fresh decay window here.
    cat["last_decay_at"] = now.isoformat()
    return round(hours * 60)


def finish_sleep(cat: dict) -> bool:
    sleep_until = cat.get("sleep_until")
    if not sleep_until or is_sleeping(cat):
        return False
    finished_at = parse_time(sleep_until)
    cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + float(cat.get("sleep_planned_hours", 0))
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    # Use the planned wake time, not the time somebody happened to open the bot.
    cat["last_wake_at"] = finished_at.isoformat()
    cat["last_decay_at"] = finished_at.isoformat()
    return True


def wake_now(cat: dict) -> bool:
    if not cat.get("sleep_until"):
        return False
    moment = datetime.utcnow()
    started = cat.get("sleep_started_at")
    if started:
        elapsed = max(0, (moment - parse_time(started)).total_seconds() / 3600)
        cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + min(
            elapsed, float(cat.get("sleep_planned_hours", 0))
        )
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["last_wake_at"] = moment.isoformat()
    cat["last_decay_at"] = moment.isoformat()
    return True


def set_action_notice(cat: dict, text: str) -> str:
    """Set a notice and return a token identifying this exact notice."""
    token = secrets.token_hex(8)
    cat["action_notice"] = text
    cat["action_notice_token"] = token
    return token


def clear_action_notice(cat: dict, expected_token: str | None = None) -> bool:
    """Clear only the expected notice; stale delayed tasks become harmless."""
    if expected_token is not None and cat.get("action_notice_token") != expected_token:
        return False
    changed = "action_notice" in cat or "action_notice_token" in cat or "action_notice_until" in cat
    cat.pop("action_notice", None)
    cat.pop("action_notice_token", None)
    cat.pop("action_notice_until", None)
    return changed


def _consume_decay(cat: dict, key: str, amount: float) -> int:
    total = max(0.0, float(cat.get(key, 0.0))) + max(0.0, amount)
    whole = int(total)
    cat[key] = total - whole
    return whole


def apply_decay(cat: dict) -> None:
    """Apply elapsed decay without losing fractional progress between frequent sweeps."""
    now = datetime.utcnow()
    last_decay = parse_time(cat.get("last_decay_at") or cat.get("created_at") or cat["last_fed"])

    # Sleep freezes hunger/happiness/love decay. Advancing the clock here prevents
    # the sleeping period from being charged retroactively on wake.
    if is_sleeping(cat):
        cat["last_decay_at"] = now.isoformat()
        return

    hours = max(0.0, (now - last_decay).total_seconds() / 3600)

    if cat["hunger"] >= 100:
        cat["hunger_decay_carry"] = 0.0
    else:
        hunger_up = _consume_decay(cat, "hunger_decay_carry", hours * 4)
        cat["hunger"] = min(100, cat["hunger"] + hunger_up)

    if cat["happiness"] <= 0:
        cat["happiness_decay_carry"] = 0.0
    else:
        happiness_down = _consume_decay(cat, "happiness_decay_carry", hours * 3)
        cat["happiness"] = max(0, cat["happiness"] - happiness_down)

    if cat["hunger"] > 70 or cat["happiness"] < 30:
        if cat["love_bar"] <= 0:
            cat["love_decay_carry"] = 0.0
        else:
            love_down = _consume_decay(cat, "love_decay_carry", hours * 2)
            cat["love_bar"] = max(0, cat["love_bar"] - love_down)
    else:
        # Neglect must be continuous; don't carry a partial penalty through recovery.
        cat["love_decay_carry"] = 0.0

    cat["last_decay_at"] = now.isoformat()


def refresh_cat_state(cat: dict) -> bool:
    """Finish elapsed sleep first, then apply only decay that happened while awake."""
    woke = finish_sleep(cat)
    apply_decay(cat)
    return woke


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
        used_ids = {str(item.get("id_number")) for item in data["cats"] if item.get("id_number") is not None}
        preferred = str(cat.get("id_number", ""))
        if not preferred or preferred in used_ids:
            for _ in range(100):
                candidate = str(random.randint(100000, 999999))
                if candidate not in used_ids:
                    cat["id_number"] = candidate
                    break
            else:
                raise RuntimeError("could not allocate a unique cat id_number")
        else:
            cat["id_number"] = preferred

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


async def get_media_file_id(kind: str, breed: str | None = None) -> str:
    async with _lock:
        data = _read().get("media", {})
        return data.get(f"{breed}:{kind}", "") if breed else data.get(kind, "")


def get_media_file_id_sync(kind: str, breed: str | None = None) -> str:
    data = _read().get("media", {})
    if breed and data.get(f"{breed}:{kind}"):
        return data[f"{breed}:{kind}"]
    return data.get(kind, "")


def get_media_type_sync(kind: str, breed: str | None = None) -> str:
    data = _read().get("media_types", {})
    return data.get(f"{breed}:{kind}", data.get(kind, "photo")) if breed else data.get(kind, "photo")


async def set_media_file_id(kind: str, file_id: str) -> None:
    async with _lock:
        data = _read()
        data.setdefault("media", {})[kind] = file_id
        _write(data)


async def set_media_file(kind: str, file_id: str, media_type: str, breed: str | None = None) -> None:
    async with _lock:
        data = _read()
        key = f"{breed}:{kind}" if breed else kind
        data.setdefault("media", {})[key] = file_id
        data.setdefault("media_types", {})[key] = media_type
        _write(data)
