"""Small economy helpers shared by active handlers."""
from datetime import datetime

from bot.services.cat_assets import BREED_POOL


# Temporarily enabled until the remaining breed assets are ready.
ACTIVE_BREEDS: tuple[str, ...] = ("siamese", "black")
DEFAULT_ACTIVE_BREED = "siamese"

# Backward-compatible alias for code that still expects one default breed.
ACTIVE_BREED = DEFAULT_ACTIVE_BREED


def check_cooldown(
    last_action_time: datetime,
    cooldown_seconds: int,
) -> tuple[bool, int]:
    elapsed = (datetime.utcnow() - last_action_time).total_seconds()
    remaining = cooldown_seconds - elapsed
    return remaining <= 0, max(0, int(remaining))


def is_active_breed(breed: str | None) -> bool:
    return bool(breed and breed in ACTIVE_BREEDS)


def assign_random_breed() -> str:
    # Keep BREED_POOL intact for the future multi-breed rollout.
    return DEFAULT_ACTIVE_BREED
