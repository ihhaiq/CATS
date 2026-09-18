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


def sleep_need_percent(cat: dict) -> int:
    """Return rest/readiness: 100 is rested, 65 or lower starts sleep requests."""
    if is_sleeping(cat):
        return 100
    last_wake = cat.get("last_wake_at")
    if not last_wake:
        return 100
    active_minutes = max(
        0,
        (datetime.utcnow() - parse_time(last_wake)).total_seconds() / 60,
    )
    steps = int(active_minutes // settings.sleep_decay_interval_minutes)
    return max(0, min(100, 100 - steps * settings.sleep_decay_amount))


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
    import random
    hours = min(remaining, random.uniform(0.5, 2.5))
    cat["sleep_started_at"] = now.isoformat()
    cat["sleep_until"] = datetime.fromtimestamp(now.timestamp() + hours * 3600).isoformat()
    cat["sleep_planned_hours"] = hours
    return round(hours * 60)


def finish_sleep(cat: dict) -> bool:
    if not cat.get("sleep_until") or is_sleeping(cat):
        return False
    cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + float(cat.get("sleep_planned_hours", 0))
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["last_wake_at"] = datetime.utcnow().isoformat()
    return True


def wake_now(cat: dict) -> bool:
    if not cat.get("sleep_until"):
        return False
    started = cat.get("sleep_started_at")
    if started:
        elapsed = max(0, (datetime.utcnow() - parse_time(started)).total_seconds() / 3600)
        cat["slept_today_hours"] = float(cat.get("slept_today_hours", 0)) + min(
            elapsed, float(cat.get("sleep_planned_hours", 0))
        )
    cat["sleep_until"] = None
    cat["sleep_started_at"] = None
    cat["sleep_planned_hours"] = 0
    cat["last_wake_at"] = datetime.utcnow().isoformat()
    return True


def clear_action_notice(cat: dict) -> None:
    cat.pop("action_notice", None)
    cat.pop("action_notice_until", None)
    cat.pop("action_notice_token", None)


def apply_decay(cat: dict) -> None:
    now = datetime.utcnow()
    last_decay = parse_time(cat.get("last_decay_at") or cat.get("created_at") or cat["last_fed"])
    hours = max(0, (now - last_decay).total_seconds() / 3600)
    cat["hunger"] = min(100, cat["hunger"] + int(hours * 4))
    cat["happiness"] = max(0, cat["happiness"] - int(hours * 3))
    if cat["hunger"] > 70 or cat["happiness"] < 30:
        cat["love_bar"] = max(0, cat["love_bar"] - int(hours * 2))
    cat["last_decay_at"] = now.isoformat()


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
