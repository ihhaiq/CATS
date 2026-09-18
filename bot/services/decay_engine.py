"""
Lazy state calculation — computed on read, not by a constant background timer.
TODO (AGENT.md step 4):
  - Pick decay rates (points/hour) for hunger (up), happiness (down), love (down,
    conditional on hunger/happiness being bad) — tune these as actual game balance
    numbers, current values below are placeholders only.
  - apply_lazy_decay(cat) should mutate + persist the cat row (hunger/happiness/love,
    clamped 0-100) based on time elapsed since last_fed/last_played/last_walk,
    and return the updated cat so callers don't need a second DB round-trip.
  - Call this at the START of every handler that reads or shows cat state
    (status, feed, play, walk, notification sweep) before anything else runs.
"""
from datetime import datetime

HUNGER_RISE_PER_HOUR = 4          # placeholder — tune for game balance
HAPPINESS_FALL_PER_HOUR = 3       # placeholder
LOVE_FALL_PER_HOUR_WHEN_NEGLECTED = 2  # placeholder, only applies when hunger>70 or happiness<30


def clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def apply_lazy_decay(cat) -> None:
    """
    Mutates `cat` in place based on elapsed hours since its last_* timestamps.
    Caller is responsible for committing the session afterward.
    TODO: implement the actual math described in the docstring above.
    """
    now = datetime.utcnow()
    hours_since_fed = (now - cat.last_fed).total_seconds() / 3600
    hours_since_played = (now - cat.last_played).total_seconds() / 3600

    cat.hunger = clamp(cat.hunger + int(hours_since_fed * HUNGER_RISE_PER_HOUR))
    cat.happiness = clamp(cat.happiness - int(hours_since_played * HAPPINESS_FALL_PER_HOUR))

    if cat.hunger > 70 or cat.happiness < 30:
        # TODO: base this on hours since state *entered* neglect, not just a flat tick
        cat.love_bar = clamp(cat.love_bar - LOVE_FALL_PER_HOUR_WHEN_NEGLECTED)
