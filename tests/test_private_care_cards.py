"""Tests for private-chat care command Rich Cards."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.care import _send_private_care_card


class PrivateCareCardTests(unittest.TestCase):
    def test_private_care_command_renders_action_card_without_mutating_cat(self) -> None:
        bot = SimpleNamespace(send_rich_message=AsyncMock())
        message = SimpleNamespace(
            chat=SimpleNamespace(id=12345, type="private"),
            bot=bot,
        )
        cat = {
            "cat_id": 77,
            "name": "لوز",
            "breed": "siamese",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 90,
            "trust": 70,
            "boredom": 15,
            "rest_level": 80,
        }

        with (
            patch(
                "bot.handlers.care.get_user_points",
                new=AsyncMock(return_value=42),
            ) as get_points,
            patch(
                "bot.handlers.care.build_rich_card",
                new=AsyncMock(return_value="CARD"),
            ) as build_card,
        ):
            sent = asyncio.run(
                _send_private_care_card(
                    message,
                    9,
                    cat,
                    "play",
                    "🎾 انبسطت القطة باللعب!",
                )
            )

        self.assertTrue(sent)
        get_points.assert_awaited_once_with(9)
        build_card.assert_awaited_once()
        args = build_card.await_args.args
        kwargs = build_card.await_args.kwargs
        self.assertIs(args[0], bot)
        self.assertEqual(args[1]["action_notice"], "🎾 انبسطت القطة باللعب!")
        self.assertEqual(args[2], 42)
        self.assertEqual(args[3], "play")
        self.assertEqual(kwargs["upload_chat_id"], 12345)
        self.assertNotIn("action_notice", cat)
        bot.send_rich_message.assert_awaited_once_with(
            chat_id=12345,
            rich_message="CARD",
        )

    def test_non_private_care_command_keeps_legacy_response_path(self) -> None:
        bot = SimpleNamespace(send_rich_message=AsyncMock())
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100123, type="supergroup"),
            bot=bot,
        )
        cat = {"name": "لوز"}

        with patch(
            "bot.handlers.care.build_rich_card",
            new=AsyncMock(),
        ) as build_card:
            sent = asyncio.run(
                _send_private_care_card(
                    message,
                    9,
                    cat,
                    "feed",
                    "🍖 أكلت القطة.",
                    points=10,
                )
            )

        self.assertFalse(sent)
        build_card.assert_not_awaited()
        bot.send_rich_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
