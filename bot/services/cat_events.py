"""Spontaneous cat-life events: hiding, requests, and social visits."""
from __future__ import annotations

import copy
import random
from datetime import datetime, timedelta

from bot.services.local_store import (
    is_sleeping,
    owner_is_away,
    parse_time,
    recommended_action,
    state_transaction,
    sync_decay_accumulators,
)

HIDE_SPOTS = ("bed", "box", "curtain")
HIDE_SPOT_LABELS = {
    "bed": "تحت السرير",
    "box": "داخل الكارتونة",
    "curtain": "ورا الستارة",
}
HIDE_DURATION_HOURS = 6
HIDE_COOLDOWN_HOURS = 24

REQUEST_DURATION_HOURS = 2
REQUEST_COOLDOWN_HOURS = 8
REQUEST_ACTIONS = ("feed", "play", "toy", "walk", "talk", "relax")
REQUEST_LABELS = {
    "feed": "🍖 أكل",
    "play": "🎾 لعب",
    "toy": "🧸 لعبة",
    "walk": "🌿 نزهة",
    "talk": "💬 حچي",
    "relax": "🛋 استلقاء",
}
REQUEST_MESSAGES = {
    "feed": "🍽️ گعدت يم صحنها وتباوعلك — تريد تاكل.",
    "play": "🎾 جابت لعبتها وگعدت يمك — تريد تلعب وياك.",
    "toy": "🧸 قاعدة تدفش لعبتها باتجاهك — تريد لعبة.",
    "walk": "🚪 واقفة يم الباب وتباوعلك — تريد تطلع نزهة.",
    "talk": "🥺 إجت تتمسح برجلك — تريدك تحچي وياها.",
    "relax": "🛋 تمددت يم مكانك — تريد تستلقي وياك.",
}

VISIT_COOLDOWN_HOURS = 18
VISIT_AWAY_COOLDOWN_HOURS = 4
VISIT_HISTORY_LIMIT = 12


def _now(moment: datetime | None = None) -> datetime:
    return moment or datetime.utcnow()


def _future(raw: str | None, moment: datetime) -> bool:
    if not raw:
        return False
    try:
        return parse_time(raw) > moment
    except (TypeError, ValueError):
        return False


def _cooldown_ready(
    raw: str | None,
    hours: float,
    moment: datetime,
) -> bool:
    if not raw:
        return True
    try:
        return moment - parse_time(raw) >= timedelta(hours=hours)
    except (TypeError, ValueError):
        return True


def active_hiding(cat: dict, moment: datetime | None = None) -> bool:
    """Whether the cat is currently hidden and waiting to be found."""
    now = _now(moment)
    return bool(cat.get("hidden_spot") and _future(cat.get("hidden_until"), now))


def can_start_hiding(cat: dict, moment: datetime | None = None) -> bool:
    now = _now(moment)
    if cat.get("is_fled") or is_sleeping(cat) or active_hiding(cat, now):
        return False
    if active_cat_request(cat, now):
        return False
    if not _cooldown_ready(cat.get("last_hidden_at"), HIDE_COOLDOWN_HOURS, now):
        return False

    # Don't hide during an emergency state where the owner needs direct access.
    hunger = int(cat.get("hunger", 20))
    rest = int(round(float(cat.get("rest_level", 100))))
    love = int(cat.get("love_bar", 100))
    return hunger < 90 and rest > 10 and love > 12


def start_hiding(
    cat: dict,
    *,
    spot: str | None = None,
    moment: datetime | None = None,
) -> str:
    now = _now(moment)
    chosen = spot if spot in HIDE_SPOTS else random.choice(HIDE_SPOTS)
    cat["hidden_spot"] = chosen
    cat["hidden_started_at"] = now.isoformat()
    cat["hidden_until"] = (now + timedelta(hours=HIDE_DURATION_HOURS)).isoformat()
    cat["last_hidden_at"] = now.isoformat()
    cat["hidden_attempts"] = 0
    return chosen


def clear_hiding(cat: dict) -> None:
    cat.pop("hidden_spot", None)
    cat.pop("hidden_started_at", None)
    cat.pop("hidden_until", None)
    cat.pop("hidden_attempts", None)


def _finish_hiding(cat: dict) -> None:
    clear_hiding(cat)
    cat["happiness"] = min(100, int(cat.get("happiness", 100)) + 3)
    cat["love_bar"] = min(100, int(cat.get("love_bar", 100)) + 2)
    cat["trust"] = min(100, int(cat.get("trust", 60)) + 1)
    cat["boredom"] = max(0, int(cat.get("boredom", 10)) - 6)
    sync_decay_accumulators(cat)


def search_hidden_cat(cat: dict, spot: str) -> bool:
    """Search one place. Correct place finds the cat; wrong place keeps it hidden."""
    if not active_hiding(cat):
        clear_hiding(cat)
        return False
    cat["hidden_attempts"] = int(cat.get("hidden_attempts", 0)) + 1
    if spot != cat.get("hidden_spot"):
        return False
    _finish_hiding(cat)
    return True


def call_hidden_cat(cat: dict, *, roll: float | None = None) -> bool:
    """Call the cat by name; stronger love/trust makes it more likely to come out."""
    if not active_hiding(cat):
        clear_hiding(cat)
        return False

    love = max(0, min(100, int(cat.get("love_bar", 100))))
    trust = max(0, min(100, int(cat.get("trust", 60))))
    chance = min(0.80, 0.25 + love * 0.003 + trust * 0.003)
    value = random.random() if roll is None else float(roll)
    cat["hidden_attempts"] = int(cat.get("hidden_attempts", 0)) + 1
    if value >= chance:
        return False

    _finish_hiding(cat)
    return True


def active_cat_request(cat: dict, moment: datetime | None = None) -> str | None:
    """Return the currently active spontaneous request action, if any."""
    now = _now(moment)
    action = cat.get("active_request_action")
    if action not in REQUEST_ACTIONS:
        return None
    if not _future(cat.get("active_request_until"), now):
        return None
    return str(action)


def request_message(action: str) -> str:
    return REQUEST_MESSAGES.get(action, "🐾 قطتك تريد تسوي شي وياك.")


def request_label(action: str) -> str:
    return REQUEST_LABELS.get(action, "🐾 سوي اللي تريده")


def can_start_request(cat: dict, moment: datetime | None = None) -> bool:
    now = _now(moment)
    if cat.get("is_fled") or is_sleeping(cat) or active_hiding(cat, now):
        return False
    if active_cat_request(cat, now):
        return False
    return _cooldown_ready(
        cat.get("last_request_at"),
        REQUEST_COOLDOWN_HOURS,
        now,
    )


def _choose_request_action(cat: dict) -> str:
    recommended = recommended_action(cat)
    if recommended in REQUEST_ACTIONS:
        return str(recommended)
    if recommended == "sleep":
        return "relax"

    boredom = int(cat.get("boredom", 10))
    happiness = int(cat.get("happiness", 100))
    love = int(cat.get("love_bar", 100))
    trust = int(cat.get("trust", 60))
    hunger = int(cat.get("hunger", 20))

    weighted: list[str] = ["play", "toy", "talk", "relax"]
    if hunger >= 45:
        weighted.extend(["feed", "feed"])
    if boredom >= 35:
        weighted.extend(["play", "toy", "play"])
    if happiness <= 65 or love <= 60 or trust <= 50:
        weighted.extend(["talk", "talk"])
    return random.choice(weighted)


def start_cat_request(
    cat: dict,
    *,
    action: str | None = None,
    moment: datetime | None = None,
) -> str:
    now = _now(moment)
    chosen = action if action in REQUEST_ACTIONS else _choose_request_action(cat)
    cat["active_request_action"] = chosen
    cat["active_request_started_at"] = now.isoformat()
    cat["active_request_until"] = (
        now + timedelta(hours=REQUEST_DURATION_HOURS)
    ).isoformat()
    cat["last_request_at"] = now.isoformat()
    return chosen


def clear_cat_request(cat: dict) -> None:
    cat.pop("active_request_action", None)
    cat.pop("active_request_started_at", None)
    cat.pop("active_request_until", None)


def fulfill_cat_request(cat: dict, action: str) -> bool:
    current = active_cat_request(cat)
    if current != action:
        return False
    clear_cat_request(cat)
    cat["happiness"] = min(100, int(cat.get("happiness", 100)) + 4)
    cat["love_bar"] = min(100, int(cat.get("love_bar", 100)) + 2)
    cat["trust"] = min(100, int(cat.get("trust", 60)) + 1)
    cat["boredom"] = max(0, int(cat.get("boredom", 10)) - 4)
    sync_decay_accumulators(cat)
    return True


def ignore_cat_request(cat: dict) -> str | None:
    current = active_cat_request(cat)
    if current is None:
        clear_cat_request(cat)
        return None
    clear_cat_request(cat)
    cat["happiness"] = max(0, int(cat.get("happiness", 100)) - 2)
    cat["love_bar"] = max(0, int(cat.get("love_bar", 100)) - 1)
    cat["boredom"] = min(100, int(cat.get("boredom", 10)) + 2)
    sync_decay_accumulators(cat)
    return current


def visit_eligible(cat: dict, moment: datetime | None = None) -> bool:
    now = _now(moment)
    if cat.get("is_fled") or is_sleeping(cat) or active_hiding(cat, now):
        return False
    if active_cat_request(cat, now):
        return False

    cooldown_hours = (
        VISIT_AWAY_COOLDOWN_HOURS
        if owner_is_away(cat, now)
        else VISIT_COOLDOWN_HOURS
    )
    return (
        _cooldown_ready(cat.get("last_visit_at"), cooldown_hours, now)
        and _cooldown_ready(
            cat.get("last_visitor_at"),
            cooldown_hours,
            now,
        )
    )


async def record_cat_visit(
    visitor_cat_id: int,
    host_cat_id: int,
    *,
    moment: datetime | None = None,
) -> tuple[dict, dict] | None:
    """Persist a visit atomically and return updated visitor/host copies."""
    now = _now(moment)
    stamp = now.isoformat()

    async with state_transaction() as data:
        visitor = next(
            (
                item
                for item in data["cats"]
                if int(item.get("cat_id", 0)) == int(visitor_cat_id)
                and not item.get("is_fled")
            ),
            None,
        )
        host = next(
            (
                item
                for item in data["cats"]
                if int(item.get("cat_id", 0)) == int(host_cat_id)
                and not item.get("is_fled")
            ),
            None,
        )
        if visitor is None or host is None:
            return None
        if int(visitor.get("owner_id", 0)) == int(host.get("owner_id", 0)):
            return None
        if not visit_eligible(visitor, now) or not visit_eligible(host, now):
            return None

        visitor["last_visit_at"] = stamp
        visitor["last_visit_peer_cat_id"] = int(host_cat_id)
        visitor["visit_count"] = int(visitor.get("visit_count", 0)) + 1
        host["last_visitor_at"] = stamp
        host["last_visitor_cat_id"] = int(visitor_cat_id)
        host["visitor_count"] = int(host.get("visitor_count", 0)) + 1

        for cat in (visitor, host):
            cat["happiness"] = min(100, int(cat.get("happiness", 100)) + 3)
            cat["boredom"] = max(0, int(cat.get("boredom", 10)) - 7)
            history = list(cat.get("visit_history", []))
            history.append(
                {
                    "at": stamp,
                    "visitor_cat_id": int(visitor_cat_id),
                    "host_cat_id": int(host_cat_id),
                }
            )
            cat["visit_history"] = history[-VISIT_HISTORY_LIMIT:]
            sync_decay_accumulators(cat)

        return copy.deepcopy(visitor), copy.deepcopy(host)
