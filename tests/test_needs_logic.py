"""Regression tests for coupled cat needs."""
import unittest
from datetime import datetime, timedelta

from bot.services.local_store import (
    action_block_reason,
    apply_care_effects,
    apply_decay,
    can_bypass_action_cooldown,
    care_reward_points,
    collect_needs,
    notification_gap_seconds,
    finish_sleep,
    recommended_action,
    sleep_plan,
    sleep_need_percent,
    start_sleep,
    wake_now,
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
        "last_care_at": None,
        "last_social_at": stamp,
        "last_talk": None,
        "same_action_streak": 0,
        "sleep_day": datetime.utcnow().date().isoformat(),
        "slept_today_hours": 0.0,
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
        self.assertIn("starving", needs)
        self.assertIn("exhausted", needs)

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
        self.assertGreaterEqual(cat["trust"], trust_before)
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

    def test_repeated_play_eventually_causes_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 20
        previous = cat["boredom"]
        for index in range(5):
            if index:
                cat["last_care_at"] = datetime.utcnow().isoformat()
            apply_care_effects(cat, "play")
            if index == 3:
                previous = cat["boredom"]
        self.assertGreater(cat["boredom"], previous)
        self.assertEqual(action_block_reason(cat, "play"), "bored_of_play")
        self.assertFalse(can_bypass_action_cooldown(cat, "play"))
        self.assertEqual(recommended_action(cat), "talk")

    def test_routine_streak_expires_after_six_hours(self) -> None:
        cat = old_cat(0)
        cat["last_care_action"] = "talk"
        cat["same_action_streak"] = 5
        cat["last_care_at"] = (datetime.utcnow() - timedelta(hours=7)).isoformat()
        cat["boredom"] = 70
        apply_care_effects(cat, "talk")
        self.assertEqual(cat["same_action_streak"], 1)

    def test_normal_sleep_does_not_create_oversleep_boredom(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["boredom"] = 20
        cat["rest_level"] = 20
        cat["rest_updated_at"] = (now - timedelta(hours=2)).isoformat()
        cat["last_decay_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=4)).isoformat()
        cat["slept_today_hours"] = 0.0
        apply_decay(cat)
        self.assertEqual(cat["boredom"], 20)

    def test_oversleep_adds_boredom(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["boredom"] = 20
        cat["rest_level"] = 90
        cat["rest_updated_at"] = (now - timedelta(hours=2)).isoformat()
        cat["last_decay_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=1)).isoformat()
        cat["slept_today_hours"] = 16.0
        apply_decay(cat)
        self.assertGreater(cat["boredom"], 20)

    def test_exhausted_cat_gets_real_main_sleep(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 20
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        kind, hours = sleep_plan(cat)
        self.assertEqual(kind, "main")
        self.assertGreaterEqual(hours, 4.0)
        self.assertLessEqual(hours, 10.0)

    def test_moderately_tired_cat_gets_nap(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 70
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        kind, hours = sleep_plan(cat)
        self.assertEqual(kind, "nap")
        self.assertGreaterEqual(hours, 0.75)
        self.assertLessEqual(hours, 2.5)

    def test_natural_wake_queues_notification(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["rest_level"] = 50
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now - timedelta(seconds=1)).isoformat()
        cat["sleep_planned_hours"] = 1.0
        cat["sleep_kind"] = "nap"
        self.assertTrue(finish_sleep(cat))
        self.assertTrue(cat["wake_notice_pending"])
        self.assertEqual(cat["wake_notice_kind"], "nap")
        self.assertIsNone(cat["sleep_until"])

    def test_manual_wake_does_not_queue_natural_notice(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 60
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        start_sleep(cat)
        self.assertTrue(wake_now(cat))
        self.assertFalse(cat.get("wake_notice_pending", False))
        self.assertIsNone(cat["sleep_until"])

    def test_hungry_cat_bypasses_feed_cooldown(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 69
        self.assertFalse(can_bypass_action_cooldown(cat, "feed"))
        cat["hunger"] = 70
        self.assertTrue(can_bypass_action_cooldown(cat, "feed"))
        apply_care_effects(cat, "feed")
        self.assertFalse(can_bypass_action_cooldown(cat, "feed"))

    def test_bored_cat_bypasses_play_cooldown_until_need_is_met(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 34
        self.assertFalse(can_bypass_action_cooldown(cat, "play"))
        cat["boredom"] = 70
        self.assertTrue(can_bypass_action_cooldown(cat, "play"))
        apply_care_effects(cat, "play")
        self.assertTrue(cat["boredom"] < 70)

    def test_overdue_walk_bypasses_walk_cooldown(self) -> None:
        cat = old_cat(0)
        cat["happiness"] = 100
        cat["last_walk"] = (datetime.utcnow() - timedelta(hours=15)).isoformat()
        self.assertTrue(can_bypass_action_cooldown(cat, "walk"))
        self.assertIn("walk_due", collect_needs(cat))
        cat["last_walk"] = datetime.utcnow().isoformat()
        self.assertFalse(can_bypass_action_cooldown(cat, "walk"))

    def test_social_need_bypasses_talk_cooldown_once(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 30
        cat["last_social_at"] = (
            datetime.utcnow() - timedelta(hours=11)
        ).isoformat()
        self.assertTrue(can_bypass_action_cooldown(cat, "talk"))
        apply_care_effects(cat, "talk")
        self.assertFalse(can_bypass_action_cooldown(cat, "talk"))

    def test_physical_actions_yield_to_hunger_and_sleep(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 90
        self.assertEqual(action_block_reason(cat, "play"), "starving")
        self.assertEqual(action_block_reason(cat, "walk"), "starving")

        cat["hunger"] = 20
        cat["rest_level"] = 30
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        self.assertEqual(action_block_reason(cat, "play"), "tired")
        self.assertEqual(action_block_reason(cat, "walk"), "tired")

    def test_recommended_action_uses_real_priority(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 10
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        cat["hunger"] = 95
        self.assertEqual(recommended_action(cat), "feed")

        cat["hunger"] = 20
        self.assertEqual(recommended_action(cat), "sleep")

    def test_alerts_have_progressive_severity(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 60
        self.assertIn("peckish", collect_needs(cat))
        cat["hunger"] = 75
        self.assertIn("hungry", collect_needs(cat))
        cat["hunger"] = 95
        self.assertIn("starving", collect_needs(cat))

    def test_urgent_alerts_repeat_sooner(self) -> None:
        mild = notification_gap_seconds(["peckish"])
        urgent = notification_gap_seconds(["starving"])
        self.assertLess(urgent, mild)

    def test_need_bypass_never_awards_points(self) -> None:
        cat = old_cat(0)
        self.assertEqual(
            care_reward_points(cat, "feed", bypassed_cooldown=True),
            0,
        )
        self.assertEqual(
            care_reward_points(cat, "talk", bypassed_cooldown=True),
            0,
        )

    def test_low_relationship_needs_talk_immediately(self) -> None:
        cat = old_cat(0)
        cat["last_social_at"] = datetime.utcnow().isoformat()
        cat["love_bar"] = 20
        self.assertTrue(can_bypass_action_cooldown(cat, "talk"))
        self.assertEqual(recommended_action(cat), "talk")

    def test_social_attention_warning_precedes_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 30
        cat["last_social_at"] = (datetime.utcnow() - timedelta(hours=11)).isoformat()
        needs = collect_needs(cat)
        self.assertIn("attention_due", needs)
        self.assertNotIn("restless", needs)

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
        self.assertIn("trust_critical", needs)
        self.assertIn("very_bored", needs)
        self.assertIn("starving", needs)
        self.assertIn("exhausted", needs)
        self.assertIn("walk_due", needs)
        self.assertIn("very_sad", needs)


if __name__ == "__main__":
    unittest.main()
