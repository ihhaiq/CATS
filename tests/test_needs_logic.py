"""Regression tests for coupled cat needs."""
import unittest
from datetime import datetime, timedelta

from bot.services.local_store import (
    _effective_slept_today,
    action_block_reason,
    apply_care_effects,
    apply_decay,
    apply_light_interaction,
    can_bypass_action_cooldown,
    care_reward_points,
    collect_needs,
    defer_sleep_for_owner,
    notification_gap_seconds,
    finish_sleep,
    is_action_cooldown_bypassed,
    recommended_action,
    should_auto_sleep,
    sleep_plan,
    sleep_need_percent,
    sleep_ready_to_finish,
    start_sleep,
    stubbornly_refuses_sleep,
    stubbornly_refuses_wake,
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
        "last_toy": None,
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
        self.assertLessEqual(sleep_need_percent(cat), 5)
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
        self.assertLess(cat["boredom"], boredom_before)
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

    def test_toy_boosts_love_happiness_and_kills_boredom(self) -> None:
        cat = old_cat(0)
        cat["happiness"] = 55
        cat["love_bar"] = 50
        cat["boredom"] = 85

        apply_care_effects(cat, "toy")

        self.assertGreater(cat["happiness"], 55)
        self.assertGreater(cat["love_bar"], 50)
        self.assertEqual(cat["boredom"], 0)

    def test_repeated_toys_eventually_create_boredom(self) -> None:
        cat = old_cat(0)
        cat["happiness"] = 60
        cat["love_bar"] = 60
        cat["boredom"] = 50

        for _ in range(3):
            apply_care_effects(cat, "toy")
        before_overuse = cat["boredom"]

        apply_care_effects(cat, "toy")
        apply_care_effects(cat, "toy")

        self.assertGreater(cat["boredom"], before_overuse)
        self.assertEqual(care_reward_points(cat, "toy"), 0)

    def test_long_time_without_food_reduces_trust_more(self) -> None:
        now = datetime.utcnow()
        neglected = old_cat(0)
        recent = old_cat(0)

        for cat in (neglected, recent):
            cat["trust"] = 80
            cat["hunger"] = 78
            cat["happiness"] = 80
            cat["love_bar"] = 80
            cat["last_decay_at"] = (now - timedelta(hours=2)).isoformat()
            cat["rest_updated_at"] = now.isoformat()
            cat["last_wake_at"] = now.isoformat()

        neglected["last_fed"] = (now - timedelta(hours=14)).isoformat()
        recent["last_fed"] = now.isoformat()

        apply_decay(neglected)
        apply_decay(recent)

        self.assertLess(neglected["trust"], recent["trust"])

    def test_sleep_pressure_builds_slowly_and_sleep_recovers_rest(self) -> None:
        cat = old_cat(10)
        apply_decay(cat)
        self.assertLessEqual(sleep_need_percent(cat), 65)
        self.assertGreaterEqual(sleep_need_percent(cat), 55)

        now = datetime.utcnow()
        cat["sleep_started_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=1)).isoformat()
        cat["rest_updated_at"] = (now - timedelta(hours=2)).isoformat()
        before = cat["rest_level"]
        after = sleep_need_percent(cat)
        self.assertGreater(after, before)
        self.assertLessEqual(after - before, 30)

    def test_repeated_talk_eventually_adds_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 40
        for _ in range(3):
            apply_care_effects(cat, "talk")
        before_overuse = cat["boredom"]
        apply_care_effects(cat, "talk")
        apply_care_effects(cat, "talk")
        self.assertGreater(cat["boredom"], before_overuse)

    def test_repeated_walk_eventually_adds_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 40
        for _ in range(3):
            apply_care_effects(cat, "walk")
        before_overuse = cat["boredom"]
        apply_care_effects(cat, "walk")
        apply_care_effects(cat, "walk")
        self.assertGreater(cat["boredom"], before_overuse)

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
        self.assertIsNone(action_block_reason(cat, "play"))
        self.assertFalse(can_bypass_action_cooldown(cat, "play"))
        self.assertEqual(recommended_action(cat), "talk")

    def test_soft_cooldown_interaction_does_not_farm_stats(self) -> None:
        cat = old_cat(0)
        cat["happiness"] = 80
        cat["love_bar"] = 70
        cat["boredom"] = 20
        before = (
            cat["happiness"],
            cat["love_bar"],
            cat["boredom"],
            cat["hunger"],
        )
        apply_light_interaction(cat, "talk")
        self.assertEqual(
            before,
            (
                cat["happiness"],
                cat["love_bar"],
                cat["boredom"],
                cat["hunger"],
            ),
        )
        self.assertFalse(cat["last_care_meaningful"])

    def test_repeated_soft_talk_and_walk_can_add_boredom(self) -> None:
        for action in ("talk", "walk"):
            cat = old_cat(0)
            cat["boredom"] = 20
            for _ in range(5):
                apply_light_interaction(cat, action)
            self.assertGreater(cat["boredom"], 20)

    def test_relax_is_a_gentle_resting_interaction(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 60
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        cat["boredom"] = 30
        rest_before = sleep_need_percent(cat)
        boredom_before = cat["boredom"]
        apply_care_effects(cat, "relax")
        self.assertGreater(sleep_need_percent(cat), rest_before)
        self.assertLess(cat["boredom"], boredom_before)

    def test_frequent_refreshes_do_not_freeze_boredom(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 0
        cat["last_social_at"] = datetime.utcnow().isoformat()
        for _ in range(12):
            cat["last_decay_at"] = (
                datetime.utcnow() - timedelta(minutes=5)
            ).isoformat()
            apply_decay(cat)
        self.assertGreater(cat["boredom"], 0)

    def test_frequent_refreshes_do_not_freeze_rest(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 100.0
        for _ in range(12):
            cat["rest_updated_at"] = (
                datetime.utcnow() - timedelta(minutes=5)
            ).isoformat()
            sleep_need_percent(cat)
        self.assertLess(cat["rest_level"], 100.0)

    def test_overused_talk_is_not_recommended_or_bypassed(self) -> None:
        cat = old_cat(0)
        cat["boredom"] = 70
        cat["last_care_action"] = "talk"
        cat["same_action_streak"] = 4
        cat["last_care_at"] = datetime.utcnow().isoformat()
        cat["last_talk"] = datetime.utcnow().isoformat()
        self.assertFalse(can_bypass_action_cooldown(cat, "talk"))
        self.assertNotEqual(recommended_action(cat), "talk")

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

    def test_long_continuous_sleep_adds_boredom_after_ten_hours(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["boredom"] = 20
        cat["rest_level"] = 90
        cat["rest_updated_at"] = (now - timedelta(hours=2)).isoformat()
        cat["last_decay_at"] = (now - timedelta(hours=2)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=12)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=1)).isoformat()
        cat["slept_today_hours"] = 0.0
        apply_decay(cat)
        self.assertGreater(cat["boredom"], 20)

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
        self.assertGreaterEqual(hours, 3.0)
        self.assertLessEqual(hours, 7.5)

    def test_moderately_tired_cat_gets_nap(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 70
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        kind, hours = sleep_plan(cat)
        self.assertEqual(kind, "nap")
        self.assertGreaterEqual(hours, 10 / 60)
        self.assertLessEqual(hours, 25 / 60)

    def test_main_sleep_can_finish_when_rest_is_full(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["rest_level"] = 97
        cat["rest_updated_at"] = (now - timedelta(minutes=10)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(minutes=10)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=2)).isoformat()
        cat["sleep_planned_hours"] = 2.0
        cat["sleep_kind"] = "main"
        self.assertTrue(sleep_ready_to_finish(cat, now))

    def test_main_sleep_never_extends_past_planned_end(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["rest_level"] = 20
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now - timedelta(seconds=1)).isoformat()
        cat["sleep_planned_hours"] = 1.0
        cat["sleep_kind"] = "main"
        self.assertTrue(finish_sleep(cat, owner_present=True))
        self.assertIsNone(cat["sleep_until"])

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

    def test_main_sleep_wakes_early_when_rest_is_full(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["rest_level"] = 90
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now + timedelta(hours=2)).isoformat()
        cat["sleep_planned_hours"] = 3.0
        cat["sleep_kind"] = "main"
        self.assertTrue(finish_sleep(cat))
        self.assertIsNone(cat["sleep_until"])
        self.assertEqual(cat["wake_notice_kind"], "main")

    def test_nap_waits_for_its_real_end_time(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["rest_level"] = 95
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now + timedelta(minutes=30)).isoformat()
        cat["sleep_planned_hours"] = 1.5
        cat["sleep_kind"] = "nap"
        self.assertFalse(finish_sleep(cat))
        self.assertIsNotNone(cat["sleep_until"])

    def test_active_sleep_counts_only_hours_from_current_day(self) -> None:
        cat = old_cat(0)
        previous_day = datetime(2026, 1, 1, 23, 0, 0)
        current_day = datetime(2026, 1, 2, 2, 0, 0)
        cat["sleep_day"] = "2026-01-01"
        cat["slept_today_hours"] = 10.0
        cat["sleep_started_at"] = previous_day.isoformat()
        cat["sleep_until"] = datetime(2026, 1, 2, 3, 0, 0).isoformat()
        self.assertAlmostEqual(
            _effective_slept_today(cat, current_day),
            2.0,
            places=3,
        )

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

    def test_never_walked_cat_becomes_due_from_adoption_time(self) -> None:
        cat = old_cat(0)
        cat["last_walk"] = None
        cat["adopted_at"] = (
            datetime.utcnow() - timedelta(hours=15)
        ).isoformat()
        self.assertTrue(can_bypass_action_cooldown(cat, "walk"))
        self.assertIn("walk_due", collect_needs(cat))

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

    def test_physical_actions_yield_to_hunger_but_not_sleepiness(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 90
        self.assertEqual(action_block_reason(cat, "play"), "starving")
        self.assertEqual(action_block_reason(cat, "walk"), "starving")

        cat["hunger"] = 20
        cat["rest_level"] = 20
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        self.assertIsNone(action_block_reason(cat, "play"))
        self.assertIsNone(action_block_reason(cat, "walk"))

    def test_recommended_action_uses_real_priority(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 10
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        cat["hunger"] = 95
        self.assertEqual(recommended_action(cat), "feed")

        cat["hunger"] = 20
        self.assertEqual(recommended_action(cat), "sleep")

    def test_zero_love_marks_cat_as_fled_during_decay(self) -> None:
        cat = old_cat(0)
        cat["love_bar"] = 0
        apply_decay(cat)
        self.assertTrue(cat["is_fled"])
        self.assertIsNotNone(cat.get("fled_at"))

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

    def test_feed_at_seventy_percent_fullness_is_meaningful(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 30
        apply_care_effects(cat, "feed")
        self.assertTrue(cat["last_care_meaningful"])
        self.assertEqual(cat["hunger"], 0)
        self.assertGreater(care_reward_points(cat, "feed"), 0)

    def test_optional_care_without_real_need_has_no_reward(self) -> None:
        cat = old_cat(0)
        cat["happiness"] = 100
        cat["love_bar"] = 100
        cat["trust"] = 100
        cat["boredom"] = 0
        apply_care_effects(cat, "talk")
        self.assertFalse(cat["last_care_meaningful"])
        self.assertEqual(care_reward_points(cat, "talk"), 0)

    def test_bypass_icon_state_requires_a_live_cooldown(self) -> None:
        cat = old_cat(0)
        cat["hunger"] = 75
        cat["last_fed"] = (
            datetime.utcnow() - timedelta(minutes=5)
        ).isoformat()
        self.assertTrue(is_action_cooldown_bypassed(cat, "feed"))

        cat["last_fed"] = (
            datetime.utcnow() - timedelta(minutes=20)
        ).isoformat()
        self.assertFalse(is_action_cooldown_bypassed(cat, "feed"))

    def test_natural_wake_resets_old_need_notification_state(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["last_notified_state"] = "hungry"
        cat["last_notified_at"] = now.isoformat()
        cat["rest_level"] = 50
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now - timedelta(seconds=1)).isoformat()
        cat["sleep_planned_hours"] = 1.0
        cat["sleep_kind"] = "nap"
        self.assertTrue(finish_sleep(cat))
        self.assertIsNone(cat["last_notified_state"])
        self.assertIsNone(cat["last_notified_at"])

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


    def test_manual_sleep_and_wake_can_be_stubborn(self) -> None:
        cat = old_cat(0)
        self.assertTrue(stubbornly_refuses_sleep(cat, roll=0.0))
        self.assertFalse(stubbornly_refuses_sleep(cat, roll=0.99))

        now = datetime.utcnow()
        cat["sleep_started_at"] = now.isoformat()
        cat["sleep_until"] = (now + timedelta(hours=1)).isoformat()
        self.assertTrue(stubbornly_refuses_wake(cat, roll=0.0))
        self.assertFalse(stubbornly_refuses_wake(cat, roll=0.99))
        self.assertFalse(stubbornly_refuses_sleep(cat, roll=0.0))

    def test_owner_interaction_defers_auto_sleep(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 25
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        self.assertEqual(should_auto_sleep(cat), "main")
        self.assertTrue(defer_sleep_for_owner(cat))
        self.assertIsNone(should_auto_sleep(cat))

    def test_extreme_exhaustion_overrides_sleep_resistance(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 5
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        self.assertTrue(defer_sleep_for_owner(cat))
        self.assertEqual(should_auto_sleep(cat), "main")

    def test_auto_nap_is_short_and_has_cooldown(self) -> None:
        cat = old_cat(0)
        cat["rest_level"] = 50
        cat["rest_updated_at"] = datetime.utcnow().isoformat()
        self.assertEqual(should_auto_sleep(cat), "nap")
        minutes = start_sleep(cat, kind_override="nap")
        self.assertGreaterEqual(minutes, 10)
        self.assertLessEqual(minutes, 25)

    def test_play_and_walk_only_nudge_sleep_pressure(self) -> None:
        play_cat = old_cat(0)
        play_cat["rest_level"] = 80
        play_cat["rest_updated_at"] = datetime.utcnow().isoformat()
        play_cat["boredom"] = 60
        before_play = sleep_need_percent(play_cat)
        apply_care_effects(play_cat, "play")
        self.assertGreaterEqual(play_cat["rest_level"], before_play - 2)

        walk_cat = old_cat(0)
        walk_cat["rest_level"] = 80
        walk_cat["rest_updated_at"] = datetime.utcnow().isoformat()
        walk_cat["boredom"] = 60
        before_walk = sleep_need_percent(walk_cat)
        apply_care_effects(walk_cat, "walk")
        self.assertGreaterEqual(walk_cat["rest_level"], before_walk - 3)

    def test_natural_wake_solo_play_costs_only_a_little_love(self) -> None:
        cat = old_cat(0)
        now = datetime.utcnow()
        cat["love_bar"] = 80
        cat["boredom"] = 30
        cat["happiness"] = 70
        cat["rest_level"] = 90
        cat["rest_updated_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now - timedelta(seconds=1)).isoformat()
        cat["sleep_kind"] = "nap"
        self.assertTrue(finish_sleep(cat))
        self.assertEqual(cat["love_bar"], 79)
        self.assertLess(cat["boredom"], 30)
        self.assertGreater(cat["happiness"], 70)
        self.assertIsNotNone(cat.get("last_solo_play_at"))

if __name__ == "__main__":
    unittest.main()
