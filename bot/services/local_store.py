"""Small JSON-backed store used for local development."""
import asyncio
import json
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
    return json.loads(path.read_text(encoding="utf-8"))


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
    """Return rest/readiness: 100 is rested, 65 starts sleep requests."""
    if is_sleeping(cat):
        return 100
    last_wake = cat.get("last_wake_at")
    if not last_wake:
        return 100
    active_hours = max(0, (datetime.utcnow() - parse_time(last_wake)).total_seconds() / 3600)
    return max(0, min(100, round(100 - active_hours * 5)))


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
    cat["sleep_until"] = (now.timestamp() + hours * 3600)
    cat["sleep_until"] = datetime.fromtimestamp(cat["sleep_until"]).isoformat()
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
            "created_at": now_iso(),
        })
        _write(data)
        return user


async def get_user_points(user_id: int) -> int:
    user = await ensure_user(user_id)
    return user["points"]


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
