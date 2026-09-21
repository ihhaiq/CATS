"""Small economy helpers shared by active handlers."""
import random
from datetime import datetime

from bot.services.cat_assets import BREED_POOL


# Temporarily enabled until the remaining breed assets are ready.
ACTIVE_BREED = "siamese"


def check_cooldown(
    last_action_time: datetime,
    cooldown_seconds: int,
) -> tuple[bool, int]:
    elapsed = (datetime.utcnow() - last_action_time).total_seconds()
    remaining = cooldown_seconds - elapsed
    return remaining <= 0, max(0, int(remaining))


def assign_random_breed() -> str:
    # Keep BREED_POOL intact for the future multi-breed rollout.
  return ACTIVE_BREED
