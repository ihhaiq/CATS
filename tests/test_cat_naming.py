"""Checks for explicit cat naming and rename controls."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.adopt import AdoptFlow, _adopted_card, cmd_adopt


class CatNamingTests(unittest.TestCase):
    def test_start_card_can_offer_rich_rename_control(self) -> None:
        cat = {
            "cat_id": 17,
            "name": "لوز",
            "breed": "black",
            "id_number": "171717",
        }

        card = _adopted_card(
            cat,
            newly_adopted=False,
            show_rename=True,
        )

        self.assertIn('data="cat:name:change"', card.html)
        self.assertIn(">تغيير اسم القطة</tg-button>", card.html)

    def test_rename_control_is_opt_in_for_start_card_only(self) -> None:
        cat = {
            "cat_id": 18,
            "name": "لوز",
            "breed": "black",
            "id_number": "181818",
        }

        card = _adopted_card(cat, newly_adopted=False)

        self.assertNotIn("cat:name:change", card.html)
        self.assertNotIn("تغيير اسم القطة", card.html)

    def test_adopt_command_without_name_does_not_assign_default_name(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            text="/adopt",
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            clear=AsyncMock(),
            update_data=AsyncMock(),
            set_state=AsyncMock(),
        )

        async def run() -> None:
            with (
                patch(
                    "bot.handlers.adopt.ensure_user",
                    new=AsyncMock(),
                ),
                patch(
                    "bot.handlers.adopt.get_user_cat",
                    new=AsyncMock(return_value=None),
                ),
            ):
                await cmd_adopt(message, state)

        asyncio.run(run())

        state.clear.assert_awaited_once()
        state.update_data.assert_awaited_once_with(pending_name="")
        state.set_state.assert_awaited_once_with(AdoptFlow.waiting_breed)
        message.answer.assert_awaited_once()
        self.assertNotIn("لوز", message.answer.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
