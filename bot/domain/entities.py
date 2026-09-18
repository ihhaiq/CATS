"""
Plain dataclasses that the whole game logic operates on.

They deliberately know nothing about SQLAlchemy or aiogram: the guest store
holds them directly, and the Postgres store converts rows to and from them.
That's what lets one set of rules serve both modes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from bot.core.clock import now
from bot.core.enums import Breed


def _actionable() -> datetime:
    """
    Default for the last_* action stamps.

    A newly adopted cat must be feedable *right now*. Stamping these with `now`
    (as the original scaffold did) put every new cat on a 15-minute cooldown
    before its owner could touch it — the worst possible first impression.
    Decay is anchored on `last_decay_at`, so backdating these is safe.
    """
    return now() - timedelta(days=1)


@dataclass
class UserData:
    user_id: int
    points: int = 100
    is_guest: bool = False
    username: str | None = None
    created_at: datetime = field(default_factory=now)
    inventory: dict[int, int] = field(default_factory=dict)  # item_id -> qty


@dataclass
class CatData:
    cat_id: int
    owner_id: int
    name: str
    breed: Breed
    id_number: str
    title: str = "🏷️ الأليف"
    partner_id: int | None = None
    age_days: int = 30
    hunger: int = 50
    happiness: int = 100
    love_bar: int = 100
    partner_affinity: int = 0
    is_fled: bool = False
    is_guest: bool = False
    created_at: datetime = field(default_factory=now)
    last_fed: datetime = field(default_factory=_actionable)
    last_played: datetime = field(default_factory=_actionable)
    last_walk: datetime = field(default_factory=_actionable)
    last_decay_at: datetime = field(default_factory=now)
    fled_at: datetime | None = None
    last_notified_state: str | None = None
    last_notified_at: datetime | None = None

    def timestamp_for(self, action: str) -> datetime:
        return {
            "feed": self.last_fed,
            "play": self.last_played,
            "walk": self.last_walk,
        }[action]

    def touch(self, action: str, at: datetime) -> None:
        if action == "feed":
            self.last_fed = at
        elif action == "play":
            self.last_played = at
        elif action == "walk":
            self.last_walk = at

    def caretakers(self) -> list[int]:
        people = [self.owner_id]
        if self.partner_id and self.partner_id != self.owner_id:
            people.append(self.partner_id)
        return people


@dataclass
class ItemData:
    item_id: int
    name: str
    price: int
    effect_type: str
    effect_value: int
    emoji: str = "🎁"
    description: str = ""
