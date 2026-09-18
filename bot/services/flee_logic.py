"""
Checks & applies the runaway (FLED) event.
TODO (AGENT.md step 9):
  - check_flee(cat) -> bool: if love_bar <= 0 and not cat.is_fled, set is_fled=True,
    stamp a fled_at timestamp (add this column), return True so the caller can
    trigger the "cat ran away" notification image + shelter listing.
  - Owner's next /adopt should work immediately even with a FLED cat on record
    (don't block adoption on old fled rows).
"""


def check_flee(cat) -> bool:
    if not cat.is_fled and cat.love_bar <= 0:
        cat.is_fled = True
        return True
    return False
