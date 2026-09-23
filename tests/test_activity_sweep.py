"""Tests for spontaneous activity notifications."""
import unittest
from unittest.mock import AsyncMock, patch

from bot.services.activity_sweep import _send_visit_notifications


class ActivitySweepTests(unittest.IsolatedAsyncioTestCase):
    async def test_visit_sends_notifications_to_both_owners(self) -> None:
        bot = AsyncMock()
        visitor = {
            "owner_id": 11,
            "cat_id": 1,
            "name": "لوز",
        }
        host = {
            "owner_id": 22,
            "cat_id": 2,
            "name": "سمسم",
        }

        with patch(
            "bot.services.activity_sweep._display_name",
            new=AsyncMock(side_effect=["حسين", "علي"]),
        ):
            await _send_visit_notifications(bot, visitor, host)

        self.assertEqual(bot.send_message.await_count, 2)
        first = bot.send_message.await_args_list[0]
        second = bot.send_message.await_args_list[1]

        self.assertEqual(first.args[0], 11)
        self.assertIn("قطتك", first.args[1])
        self.assertIn("علي", first.args[1])
        self.assertIn("سمسم", first.args[1])

        self.assertEqual(second.args[0], 22)
        self.assertIn("قطة", second.args[1])
        self.assertIn("حسين", second.args[1])
        self.assertIn("زارتكم", second.args[1])
        self.assertIn("لوز", second.args[1])


if __name__ == "__main__":
    unittest.main()
