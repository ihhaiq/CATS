"""
A single source of truth for "now".

Every timestamp in the game goes through `clock.now()` instead of
`datetime.utcnow()`. That buys two things:

  * Tests can freeze or advance time without sleeping.
  * The /dev_time command can fast-forward the whole simulation, which is the
    only sane way to verify decay, alerts and the flee event by hand — the real
    thresholds take hours to reach.

The offset is process-local and never persisted; a restart drops it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class Clock:
    def __init__(self) -> None:
        self._offset = timedelta(0)
        self._frozen_at: datetime | None = None

    # -- reading -----------------------------------------------------------
    def now(self) -> datetime:
        """Timezone-naive UTC, to match what we store in the DB."""
        base = self._frozen_at or datetime.now(timezone.utc).replace(tzinfo=None)
        return base + self._offset

    @property
    def offset(self) -> timedelta:
        return self._offset

    @property
    def is_shifted(self) -> bool:
        return self._offset != timedelta(0) or self._frozen_at is not None

    def describe(self) -> str:
        if not self.is_shifted:
            return "real time"
        parts = []
        if self._frozen_at is not None:
            parts.append("frozen")
        if self._offset:
            hours = self._offset.total_seconds() / 3600
            parts.append(f"{hours:+.1f}h")
        return " / ".join(parts)

    # -- dev controls ------------------------------------------------------
    def advance(self, *, hours: float = 0, minutes: float = 0, days: float = 0) -> datetime:
        self._offset += timedelta(hours=hours, minutes=minutes, days=days)
        return self.now()

    def freeze(self, at: datetime | None = None) -> datetime:
        self._frozen_at = at or datetime.now(timezone.utc).replace(tzinfo=None)
        return self.now()

    def unfreeze(self) -> None:
        self._frozen_at = None

    def reset(self) -> None:
        self._offset = timedelta(0)
        self._frozen_at = None


clock = Clock()


def now() -> datetime:
    return clock.now()
