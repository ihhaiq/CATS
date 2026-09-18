"""Offline checks for the checked-in JSON and Rich Message runtime."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from bot.services.rich_card import build_rich_card


class RuntimeTests(unittest.TestCase):
    def test_rich_card_has_state_table_and_actions(self) -> None:
        cat = {
            "name": "Test",
            "breed": "black",
            "id_number": "123456",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 100,
            "slept_today_hours": 10,
        }
        card = build_rich_card(cat, 42)
        self.assertIn("الشبع", card.html)
        self.assertIn("الحاجة للنوم", card.html)
        self.assertIn("cat:feed", card.html)
        self.assertIn("cat:play", card.html)

    def test_local_store_creates_and_updates_json(self) -> None:
        from bot.config import settings
        from bot.services.local_store import create_cat, get_user_cat, now_iso, update_cat

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            settings.json_data_file = str(Path(directory) / "catibot.json")
            try:
                async def scenario() -> None:
                    stamp = now_iso()
                    cat = {
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
                        "last_decay_at": stamp,
                    }
                    await create_cat(cat)
                    saved = await get_user_cat(777)
                    self.assertIsNotNone(saved)
                    saved["happiness"] = 80
                    await update_cat(saved)
                    self.assertEqual((await get_user_cat(777))["happiness"], 80)

                asyncio.run(scenario())
            finally:
                settings.json_data_file = previous


if __name__ == "__main__":
    unittest.main()
