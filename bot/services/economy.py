"""
Points, cooldowns, and breed assignment helpers.
TODO (AGENT.md step 4 & 5):
  - award_points(session, user_id, delta, reason): update users.points AND insert
    a points_log row in the same transaction — never update one without the other.
  - check_cooldown(last_action_time, cooldown_seconds) -> (bool ready, int seconds_left).
  - assign_random_breed() -> str: pick from a fixed BREED_POOL list (keep this list
    in sync with the folders actually present under bot/assets/cats/).
  - generate_unique_id_number(session): generate a random 4-6 digit string, retry
    on unique-constraint collision against cats.id_number.
"""
from datetime import datetime

from bot.services.cat_assets import BREED_POOL


def check_cooldown(last_action_time: datetime, cooldown_seconds: int) -> tuple[bool, int]:
    elapsed = (datetime.utcnow() - last_action_time).total_seconds()
    remaining = cooldown_seconds - elapsed
    return remaining <= 0, max(0, int(remaining))


def assign_random_breed() -> str:
    import random
    return random.choice(BREED_POOL)


async def award_points(session, user_id: int, delta: int, reason: str) -> None:
    # TODO: implement — see docstring above (update users.points + insert points_log row)
    raise NotImplementedError
