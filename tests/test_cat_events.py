"""Tests for spontaneous cat-life events."""
import unittest
from datetime import datetime, timedelta

from bot.services.cat_events import (
    active_boredom_escape,
    active_boredom_host_busy,
    active_cat_request,
    active_hiding,
    boredom_escape_remaining_minutes,
    boredom_host_busy_remaining_minutes,
    can_start_boredom_escape,
    call_hidden_cat,
    can_start_hiding,
    can_start_request,
    finish_boredom_escape_if_ready,
    finish_boredom_host_busy_if_ready,
    fulfill_cat_request,
    ignore_cat_request,
    search_hidden_cat,
    start_boredom_escape,
    start_cat_request,
    start_hiding,
    visit_eligible,
)


def base_cat() -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "cat_id": 1,
        "owner_id": 10,
        "name": "لوز",
        "breed": "black",
        "id_number": "123456",
        "hunger": 20,
        "happiness": 80,
        "love_bar": 80,
        "trust": 70,
        "boredom": 20,
        "rest_level": 80,
        "rest_updated_at": now,
        "last_walk": now,
        "last_social_at": now,
        "last_played": now,
        "created_at": now,
        "last_fed": now,
        "sleep_until": None,
        "is_fled": False,
    }


class CatEventTests(unittest.TestCase):
    def test_hidden_cat_requires_correct_search_place(self) -> None:
        cat = base_cat()
        start_hiding(cat, spot="box")
        self.assertTrue(active_hiding(cat))

        self.assertFalse(search_hidden_cat(cat, "bed"))
        self.assertTrue(active_hiding(cat))
        self.assertEqual(cat["hidden_attempts"], 1)

        self.assertTrue(search_hidden_cat(cat, "box"))
        self.assertFalse(active_hiding(cat))
        self.assertNotIn("hidden_spot", cat)
        self.assertGreater(cat["happiness"], 80)

    def test_calling_hidden_cat_uses_relationship_chance(self) -> None:
        cat = base_cat()
        start_hiding(cat, spot="curtain")
        self.assertTrue(call_hidden_cat(cat, roll=0.0))
        self.assertFalse(active_hiding(cat))

    def test_hiding_has_cooldown_and_skips_emergencies(self) -> None:
        cat = base_cat()
        self.assertTrue(can_start_hiding(cat))

        cat["last_hidden_at"] = datetime.utcnow().isoformat()
        self.assertFalse(can_start_hiding(cat))

        cat = base_cat()
        cat["hunger"] = 95
        self.assertFalse(can_start_hiding(cat))

    def test_request_can_be_fulfilled_by_requested_action(self) -> None:
        cat = base_cat()
        action = start_cat_request(cat, action="play")
        self.assertEqual(action, "play")
        self.assertEqual(active_cat_request(cat), "play")

        self.assertFalse(fulfill_cat_request(cat, "feed"))
        self.assertTrue(fulfill_cat_request(cat, "play"))
        self.assertIsNone(active_cat_request(cat))
        self.assertGreater(cat["love_bar"], 80)

    def test_ignoring_request_has_small_relationship_cost(self) -> None:
        cat = base_cat()
        start_cat_request(cat, action="talk")
        happiness = cat["happiness"]
        love = cat["love_bar"]

        ignored = ignore_cat_request(cat)
        self.assertEqual(ignored, "talk")
        self.assertIsNone(active_cat_request(cat))
        self.assertEqual(cat["happiness"], happiness - 2)
        self.assertEqual(cat["love_bar"], love - 1)

    def test_requests_do_not_start_while_hidden(self) -> None:
        cat = base_cat()
        self.assertTrue(can_start_request(cat))
        start_hiding(cat, spot="bed")
        self.assertFalse(can_start_request(cat))

    def test_extreme_boredom_can_start_temporary_escape(self) -> None:
        cat = base_cat()
        cat["boredom"] = 89
        self.assertFalse(can_start_boredom_escape(cat))

        cat["boredom"] = 93
        self.assertTrue(can_start_boredom_escape(cat))

    def test_boredom_escape_stays_away_then_returns_relaxed(self) -> None:
        now = datetime.utcnow()
        cat = base_cat()
        cat["boredom"] = 93

        duration = start_boredom_escape(
            cat,
            peer_cat_id=2,
            peer_owner_id=22,
            moment=now,
            duration_minutes=120,
        )

        self.assertEqual(duration, 120)
        self.assertTrue(
            active_boredom_escape(cat, now + timedelta(minutes=30))
        )
        self.assertEqual(
            boredom_escape_remaining_minutes(
                cat,
                now + timedelta(minutes=30),
            ),
            90,
        )
        self.assertFalse(
            finish_boredom_escape_if_ready(
                cat,
                now + timedelta(minutes=119),
            )
        )
        self.assertTrue(
            finish_boredom_escape_if_ready(
                cat,
                now + timedelta(minutes=121),
            )
        )
        self.assertFalse(
            active_boredom_escape(cat, now + timedelta(minutes=121))
        )
        self.assertEqual(cat["boredom"], 33)
        self.assertEqual(cat["last_boredom_escape_peer_cat_id"], 2)
        self.assertEqual(cat["last_boredom_escape_peer_owner_id"], 22)

    def test_host_cat_is_busy_until_escape_visit_ends(self) -> None:
        now = datetime.utcnow()
        cat = base_cat()
        cat["boredom_host_busy_started_at"] = now.isoformat()
        cat["boredom_host_busy_until"] = (
            now + timedelta(minutes=120)
        ).isoformat()
        cat["boredom_host_peer_cat_id"] = 2
        cat["boredom_host_peer_owner_id"] = 22
        cat["boredom_host_peer_cat_name"] = "سمسم"

        self.assertTrue(
            active_boredom_host_busy(cat, now + timedelta(minutes=30))
        )
        self.assertEqual(
            boredom_host_busy_remaining_minutes(
                cat,
                now + timedelta(minutes=30),
            ),
            90,
        )
        self.assertFalse(
            can_start_boredom_escape(cat, now + timedelta(minutes=30))
        )
        self.assertFalse(
            visit_eligible(cat, now + timedelta(minutes=30))
        )
        self.assertFalse(
            finish_boredom_host_busy_if_ready(
                cat,
                now + timedelta(minutes=119),
            )
        )
        self.assertTrue(
            finish_boredom_host_busy_if_ready(
                cat,
                now + timedelta(minutes=121),
            )
        )
        self.assertFalse(
            active_boredom_host_busy(cat, now + timedelta(minutes=121))
        )
        self.assertEqual(cat["last_boredom_host_peer_cat_name"], "سمسم")

    def test_visit_eligibility_respects_both_visit_directions(self) -> None:
        cat = base_cat()
        self.assertTrue(visit_eligible(cat))

        cat["last_visit_at"] = datetime.utcnow().isoformat()
        self.assertFalse(visit_eligible(cat))

        cat = base_cat()
        cat["last_visitor_at"] = datetime.utcnow().isoformat()
        self.assertFalse(visit_eligible(cat))

        cat["last_visitor_at"] = (
            datetime.utcnow() - timedelta(hours=19)
        ).isoformat()
        self.assertTrue(visit_eligible(cat))



    def test_away_cat_uses_shorter_visit_cooldown(self) -> None:
        now = datetime.utcnow()

        normal = base_cat()
        normal["last_visit_at"] = (now - timedelta(hours=5)).isoformat()
        self.assertFalse(visit_eligible(normal, now))

        away = base_cat()
        old = (now - timedelta(hours=5)).isoformat()
        for key in ("last_fed", "last_played", "last_walk", "created_at"):
            away[key] = old
        away["last_visit_at"] = old
        self.assertTrue(visit_eligible(away, now))

if __name__ == "__main__":
    unittest.main()
