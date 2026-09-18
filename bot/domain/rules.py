"""
The whole game, as pure functions.

Nothing in this module imports aiogram, SQLAlchemy or the network. Every
function takes data in and gives data back, which means the entire rule set is
testable in milliseconds (`python -m tests.test_rules`) and behaves identically
in guest mode and Postgres mode.

Two correctness notes, both fixes to the original scaffold:

1. Decay is anchored on `last_decay_at`, not on `last_fed`/`last_played`.
   Anchoring on the action timestamps double-counted: every call re-applied the
   decay for the whole window since the last feed, on top of the value that
   already contained it. A cat could starve in three /status calls.

2. Love only drains during the hours the cat was actually neglected. The
   elapsed window is simulated in one-hour steps, so a cat that was fine for
   ten hours and hungry for two loses love for two.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.core.enums import AlertState, Breed, CareAction, Emotion

# --- balance ---------------------------------------------------------------
# Tuned so a cat left completely alone needs attention after ~half a day,
# and only runs away after ~3 neglected days. Adjust here, nowhere else.
HUNGER_RISE_PER_HOUR = 3.0
HAPPINESS_FALL_PER_HOUR = 2.5
LOVE_FALL_PER_HOUR_WHEN_NEGLECTED = 1.5

HUNGER_NEGLECT_AT = 70
HAPPINESS_NEGLECT_AT = 30
LOVE_CRITICAL_AT = 15

MAX_SIMULATED_HOURS = 24 * 60  # a cat idle for two months decays as if two months

CARE_EFFECTS: dict[CareAction, dict[str, int]] = {
    CareAction.FEED: {"hunger": -40, "happiness": +5, "love_bar": +2},
    CareAction.PLAY: {"happiness": +30, "hunger": +5, "love_bar": +3},
    CareAction.WALK: {"happiness": +20, "love_bar": +8, "hunger": +10},
}

CARE_POINTS: dict[CareAction, int] = {
    CareAction.FEED: 5,
    CareAction.PLAY: 5,
    CareAction.WALK: 12,
}

PARTNER_AFFINITY_PER_ACTION = 4
PARTNER_JOIN_BONUS = 50
ADOPT_BONUS = 10
SHELTER_READOPT_LOVE = 40


def clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(value))))


# --- decay -----------------------------------------------------------------
@dataclass
class DecayResult:
    hunger: int
    happiness: int
    love_bar: int
    hours: float
    love_lost: int

    @property
    def changed(self) -> bool:
        return self.hours > 0


def compute_decay(
    *,
    hunger: int,
    happiness: int,
    love_bar: int,
    since: datetime,
    now: datetime,
) -> DecayResult:
    """Simulate the elapsed window in one-hour steps and return the new stats."""
    elapsed_hours = (now - since).total_seconds() / 3600
    if elapsed_hours <= 0:
        return DecayResult(hunger, happiness, love_bar, 0.0, 0)

    elapsed_hours = min(elapsed_hours, MAX_SIMULATED_HOURS)
    h, p, love = float(hunger), float(happiness), float(love_bar)
    love_before = love
    remaining = elapsed_hours

    while remaining > 1e-9:
        step = min(1.0, remaining)
        neglected = h > HUNGER_NEGLECT_AT or p < HAPPINESS_NEGLECT_AT
        h = min(100.0, h + HUNGER_RISE_PER_HOUR * step)
        p = max(0.0, p - HAPPINESS_FALL_PER_HOUR * step)
        if neglected:
            love = max(0.0, love - LOVE_FALL_PER_HOUR_WHEN_NEGLECTED * step)
        remaining -= step

    return DecayResult(
        hunger=clamp(h),
        happiness=clamp(p),
        love_bar=clamp(love),
        hours=elapsed_hours,
        love_lost=clamp(love_before - love, 0, 100),
    )


# --- reading state ---------------------------------------------------------
def is_neglected(hunger: int, happiness: int) -> bool:
    return hunger > HUNGER_NEGLECT_AT or happiness < HAPPINESS_NEGLECT_AT


def emotion_of(*, hunger: int, happiness: int, is_fled: bool = False) -> Emotion:
    if is_fled:
        return Emotion.FLED
    if is_neglected(hunger, happiness):
        return Emotion.SAD
    if happiness > 70 and hunger < 50:
        return Emotion.HAPPY
    return Emotion.NEUTRAL


def alert_state(
    *,
    hunger: int,
    happiness: int,
    love_bar: int,
    is_fled: bool,
    hunger_threshold: int = HUNGER_NEGLECT_AT,
    happiness_threshold: int = HAPPINESS_NEGLECT_AT,
    love_threshold: int = LOVE_CRITICAL_AT,
) -> AlertState | None:
    """Most urgent unmet need, or None when the cat is fine."""
    if is_fled:
        return AlertState.FLED
    if love_bar <= love_threshold:
        return AlertState.LOVE_LOW
    if hunger > hunger_threshold:
        return AlertState.HUNGRY
    if happiness < happiness_threshold:
        return AlertState.SAD
    return None


def should_notify(
    *,
    state: AlertState | None,
    last_state: str | None,
    last_at: datetime | None,
    now: datetime,
    min_gap_seconds: int,
) -> bool:
    """
    Anti-spam gate. Notify when the condition is new, or when the same unresolved
    condition has been quiet for longer than the configured gap.
    """
    if state is None:
        return False
    if last_state != state.value:
        return True
    if last_at is None:
        return True
    return (now - last_at).total_seconds() >= min_gap_seconds


def should_flee(*, love_bar: int, is_fled: bool) -> bool:
    return not is_fled and love_bar <= 0


# --- cooldowns -------------------------------------------------------------
def check_cooldown(last_action_at: datetime, cooldown_seconds: int, now: datetime) -> tuple[bool, int]:
    remaining = cooldown_seconds - (now - last_action_at).total_seconds()
    return remaining <= 0, max(0, int(remaining))


def apply_care(
    *, action: CareAction, hunger: int, happiness: int, love_bar: int
) -> tuple[int, int, int]:
    effect = CARE_EFFECTS[action]
    return (
        clamp(hunger + effect.get("hunger", 0)),
        clamp(happiness + effect.get("happiness", 0)),
        clamp(love_bar + effect.get("love_bar", 0)),
    )


# --- creation --------------------------------------------------------------
def assign_random_breed(rng: random.Random | None = None) -> Breed:
    return (rng or random).choice(list(Breed))


def generate_id_number(rng: random.Random | None = None) -> str:
    return f"{(rng or random).randint(0, 999_999):06d}"


def age_in_days(created_at: datetime, now: datetime, base_days: int = 30) -> int:
    return base_days + max(0, (now - created_at).days)


def validate_cat_name(raw: str) -> str:
    """Raise ValueError with an Arabic reason, or return the cleaned name."""
    name = " ".join(raw.split())
    if len(name) < 2:
        raise ValueError("الاسم قصير جداً — حرفين على الأقل.")
    if len(name) > 20:
        raise ValueError("الاسم طويل — 20 حرف كحد أقصى.")
    if any(ch in name for ch in "<>{}[]|\\`"):
        raise ValueError("الاسم يحتوي رموز غير مسموحة.")
    return name


def human_duration_ar(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} ثانية"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} دقيقة"
    hours = minutes // 60
    rest = minutes % 60
    if hours < 24:
        return f"{hours} ساعة" + (f" و{rest} دقيقة" if rest else "")
    days = hours // 24
    return f"{days} يوم" + (f" و{hours % 24} ساعة" if hours % 24 else "")


def next_ready_at(last_action_at: datetime, cooldown_seconds: int) -> datetime:
    return last_action_at + timedelta(seconds=cooldown_seconds)
