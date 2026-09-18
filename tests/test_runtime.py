"""Offline checks for the checked-in JSON and Rich Message runtime."""
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from bot.services.rich_card import build_rich_card


def _cat(stamp: str) -> dict:
    return {
        "owner_id": 777,
        "name": "Test",
        "breed": "black",
        "id_number": "777777",
        "hunger": 20,
        "happiness": 90,
        "love_bar": 100,
        "is_fled": False,
        "last_fed": stamp,
        "last_played": stamp,
        "last_walk": stamp,
        "last_talked": stamp,
        "last_decay_at": stamp,
        "last_wake_at": stamp,
        "sleep_until": None,
        "slept_today_hours": 10.0,
    }


class RuntimeTests(unittest.TestCase):
    def test_rich_card_has_state_table_and_actions(self) -> None:
        stamp = datetime.utcnow().isoformat()
        card = build_rich_card(_cat(stamp), 42)
        self.assertIn("الشبع", card.html)
        self.assertIn("الراحة والنوم", card.html)
        self.assertIn("cat:777:feed", card.html)
        self.assertIn("cat:777:play", card.html)

    def test_local_store_creates_and_updates_json(self) -> None:
        from bot.config import settings
        from bot.services.local_store import create_cat, get_user_cat, now_iso, update_cat

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            settings.json_data_file = str(Path(directory) / "catibot.json")
            try:
                async def scenario() -> None:
                    cat = _cat(now_iso())
                    await create_cat(cat)
                    saved = await get_user_cat(777)
                    self.assertIsNotNone(saved)
                    saved["happiness"] = 80
                    await update_cat(saved)
                    self.assertEqual((await get_user_cat(777))["happiness"], 80)

                asyncio.run(scenario())
            finally:
                settings.json_data_file = previous

    def test_create_cat_recovers_from_duplicate_id_number(self) -> None:
        from bot.config import settings
        from bot.services.local_store import create_cat, now_iso

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            settings.json_data_file = str(Path(directory) / "catibot.json")
            try:
                async def scenario() -> None:
                    first = _cat(now_iso())
                    first["owner_id"] = 1
                    first["id_number"] = "111111"
                    second = _cat(now_iso())
                    second["owner_id"] = 2
                    second["id_number"] = "111111"
                    await create_cat(first)
                    await create_cat(second)
                    self.assertNotEqual(first["id_number"], second["id_number"])

                asyncio.run(scenario())
            finally:
                settings.json_data_file = previous

    def test_fractional_decay_survives_frequent_sweeps(self) -> None:
        from bot.services.local_store import apply_decay

        stamp = (datetime.utcnow() - timedelta(minutes=15, seconds=5)).isoformat()
        cat = _cat(stamp)
        apply_decay(cat)
        self.assertEqual(cat["hunger"], 21)
        self.assertEqual(cat["happiness"], 90)
        self.assertGreater(cat.get("happiness_decay_carry", 0), 0.7)

        cat["last_decay_at"] = (datetime.utcnow() - timedelta(minutes=15, seconds=5)).isoformat()
        apply_decay(cat)
        self.assertEqual(cat["hunger"], 22)
        self.assertEqual(cat["happiness"], 89)

    def test_sleep_need_drops_every_five_minutes_by_default(self) -> None:
        from bot.config import settings
        from bot.services.local_store import sleep_need_percent

        old_interval = settings.sleep_need_drop_interval_minutes
        old_drop = settings.sleep_need_drop_per_interval
        settings.sleep_need_drop_interval_minutes = 5
        settings.sleep_need_drop_per_interval = 1
        try:
            cat = _cat(datetime.utcnow().isoformat())
            cat["last_wake_at"] = (datetime.utcnow() - timedelta(minutes=26)).isoformat()
            self.assertEqual(sleep_need_percent(cat), 95)
        finally:
            settings.sleep_need_drop_interval_minutes = old_interval
            settings.sleep_need_drop_per_interval = old_drop

    def test_sleep_freezes_decay_and_auto_wake_uses_planned_time(self) -> None:
        from bot.services.local_store import apply_decay, finish_sleep

        now = datetime.utcnow()
        cat = _cat((now - timedelta(hours=2)).isoformat())
        cat["sleep_started_at"] = (now - timedelta(hours=1)).isoformat()
        cat["sleep_until"] = (now + timedelta(minutes=30)).isoformat()
        cat["sleep_planned_hours"] = 1.5

        before = (cat["hunger"], cat["happiness"], cat["love_bar"])
        apply_decay(cat)
        self.assertEqual((cat["hunger"], cat["happiness"], cat["love_bar"]), before)

        scheduled = datetime.utcnow() - timedelta(minutes=10)
        cat["sleep_until"] = scheduled.isoformat()
        cat["sleep_started_at"] = (scheduled - timedelta(hours=1)).isoformat()
        cat["sleep_planned_hours"] = 1.0
        self.assertTrue(finish_sleep(cat))
        self.assertEqual(cat["last_wake_at"], scheduled.isoformat())
        self.assertEqual(cat["last_decay_at"], scheduled.isoformat())

    def test_notice_token_prevents_stale_task_from_clearing_new_notice(self) -> None:
        from bot.services.local_store import clear_action_notice, set_action_notice

        cat = {}
        old = set_action_notice(cat, "old")
        new = set_action_notice(cat, "new")
        self.assertFalse(clear_action_notice(cat, expected_token=old))
        self.assertEqual(cat["action_notice"], "new")
        self.assertTrue(clear_action_notice(cat, expected_token=new))
        self.assertNotIn("action_notice", cat)


if __name__ == "__main__":
    unittest.main()
