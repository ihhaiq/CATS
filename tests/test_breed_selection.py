"""Checks for temporary breed selection UI and rules."""
import unittest

from bot.handlers.adopt import _adopted_card, _breed_keyboard
from bot.services.economy import ACTIVE_BREEDS


class BreedSelectionTests(unittest.TestCase):
    def test_only_siamese_and_black_are_active(self) -> None:
        self.assertEqual(ACTIVE_BREEDS, ("siamese", "black"))

    def test_adoption_keyboard_offers_both_active_breeds(self) -> None:
        keyboard = _breed_keyboard()
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertEqual(
            callbacks,
            {"adopt:breed:siamese", "adopt:breed:black"},
        )

    def test_disabled_breed_notice_offers_both_choices(self) -> None:
        cat = {
            "cat_id": 7,
            "name": "قديم",
            "breed": "calico",
            "id_number": "123456",
        }
        card = _adopted_card(
            cat,
            newly_adopted=False,
            show_breed_notice=True,
        )
        self.assertIn('data="cat:breed:siamese"', card.html)
        self.assertIn('data="cat:breed:black"', card.html)
        self.assertIn("معطلة مؤقتًا", card.html)

    def test_active_breed_does_not_show_disabled_notice(self) -> None:
        for breed in ACTIVE_BREEDS:
            with self.subTest(breed=breed):
                cat = {
                    "cat_id": 8,
                    "name": "فعالة",
                    "breed": breed,
                    "id_number": "654321",
                }
                card = _adopted_card(
                    cat,
                    newly_adopted=False,
                    show_breed_notice=True,
                )
                self.assertNotIn("cat:breed:siamese", card.html)
                self.assertNotIn("cat:breed:black", card.html)


if __name__ == "__main__":
    unittest.main()
