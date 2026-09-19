"""Regression tests for coupled cat needs."""
import unittest
from datetime import datetime, timedelta

from bot.services.local_store import (
    apply_care_effects,
    apply_decay,
    collect_needs,
    sleep_need_percent,
)


def old_cat(hours: float = 24) -> dict:
    stamp = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    return {
        "cat_id": 1,
        "owner_id": 1,
        "name": "Test",
        "hunger": 20,
        "happiness": 100,
        "love_bar": 100,
        "trust": 60,
        "boredom": 10,
        "last_care_action": None,
        "same_action_streak": 0,
        "last_fed": stamp,
        "last_played": stamp,
        "last_walk": stamp,
        "last_decay_at": stamp,
        "last_wake_at": stamp,
        "rest_level": 100,
        "rest_updated_at": stamp,
        "sleep_until": None,
        "sleep_started_at": None,
    }


class CoupledNeedsTests(unittest.TestCase):
    def test_long_neglect_couples_needs(self) -> None:
        cat = old_cat(24)
        apply_decay(cat)

        self.assertGreaterEqual(cat["hunger"], 85)
        self.assertLess(cat["happiness"], 70)
        self.assertLess(cat["love_bar"], 100)
        self.assertEqual(sleep_need_percent(cat), 0)
        self.assertGreater(cat["boredom"], 10)
        self.assertLess(cat["trust"], 60)

        needs = collect_needs(cat)
        self.assertIn("hungry", needs)
        self.assertIn("tired", needs)

    def test_feeding_improves_mood_and_love_not_rest(self) -> None:
        cat = old_cat(12)
        apply_decay(cat)
        rest_before = sleep_need_percent(cat)
        happiness_before = cat["happiness"]
        love_before = cat["love_bar"]
        trust_before = cat["trust"]
        boredom_before = cat["boredom"]
        hunger_before = cat["hunger"]

        apply_care_effects(cat, "feed")

        self.assertLess(cat["hunger"], hunger_before)
        self.assertGreater(cat["happiness"], happiness_before)
        self.assertGreaterEqual(cat["love_bar"], love_before)
        self.assertGreater(cat["trust"], trust_before)
        self.assertEqual(cat["boredom"], boredom_before)
        self.assertEqual(sleep_need_percent(cat), rest_before)

    def test_play_and_walk_cost_energy(self) -> None:
        cat = old_cat(1)
        apply_decay(cat)
        rest = sleep_need_percent(cat)

        apply_care_effects(cat, "play")
        after_play = sleep_need_percent(cat)
        self.assertLess(after_play, rest)

        apply_care_effects(cat, "walk")
        self.assertLess(sleep_need_percent(cat), after_play)

    def test_play_and_talk_reduce_boredom(self) -> None:
        cat = old_cat(1)
        cat["boredom"] = 90
        apply_care_effects(cat, "talk")
        self.assertLess(cat["boredom"], 90)
        after_talk = cat["boredom"]
        apply_care_effects(cat, "play")
        self.assertLess(cat["boredom"], after_talk)

    def test_sleep_recovers_slower_than_awake_drain(self) -> None:
        cat = old_cat(10)
        apply_decay(cat)
        self.assertLessEqual(sleep_need_percent(cat), 20)

        now = datetime.utcnow()
        cat["sleep_started_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=1)).isoformat()
        cat["rest_updated_at"] = (now - timedelta(hours=2)).isoformat()
        before = cat["rest_level"]
        after = sleep_need_percent(cat)
        self.assertGreater(after, before)
        self.assertLess(after - before, 25)

    def test_repetitive_routine_adds_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 20
        for _ in range(5):
            apply_care_effects(cat, "feed")
        self.assertGreater(cat["boredom"], 20)

    def test_multiple_needs_are_reported_together(self) -> None:
        cat = old_cat(24)
        cat["hunger"] = 95
        cat["happiness"] = 20
        cat["love_bar"] = 15
        cat["trust"] = 15
        cat["boredom"] = 90
        cat["rest_level"] = 10
        cat["rest_updated_at"] = datetime.utcnow().isoformat()

        needs = collect_needs(cat)
        self.assertIn("love_low", needs)
        self.assertIn("trust_low", needs)
        self.assertIn("bored", needs)
        self.assertIn("hungry", needs)
        self.assertIn("tired", needs)
        self.assertIn("walk_due", needs)
        self.assertIn("sad", needs)


if __name__ == "__main__":
    unittest.main()
