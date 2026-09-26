"""Tests for Railway-backed compact cat image previews."""
import unittest
from datetime import datetime, timedelta

from bot.services.cat_preview import cat_preview_url


class CatPreviewUrlTests(unittest.TestCase):
    def test_status_preview_uses_existing_png_asset(self) -> None:
        cat = {
            "breed": "siamese",
            "age_days": 30,
            "hunger": 10,
        }

        url = cat_preview_url(
            cat,
            "status",
            base_url="https://cat.example.up.railway.app/",
        )

        self.assertEqual(
            url,
            "https://cat.example.up.railway.app/cat-assets/siamese/adult/idle.png",
        )

    def test_visual_state_is_reflected_in_preview_url(self) -> None:
        cat = {
            "breed": "siamese",
            "age_days": 30,
            "hunger": 90,
        }

        url = cat_preview_url(
            cat,
            "status",
            base_url="https://cat.example.up.railway.app",
        )

        self.assertTrue(url.endswith("/siamese/adult/hungry.png"))


    def test_treat_uses_feed_asset(self) -> None:
        cat = {
            "breed": "siamese",
            "age_days": 30,
            "hunger": 10,
        }

        url = cat_preview_url(
            cat,
            "treat",
            base_url="https://cat.example.up.railway.app",
        )

        self.assertTrue(url.endswith("/siamese/adult/feed.png"))

    def test_toy_uses_play_asset(self) -> None:
        cat = {
            "breed": "siamese",
            "age_days": 30,
            "hunger": 10,
        }

        url = cat_preview_url(
            cat,
            "toy",
            base_url="https://cat.example.up.railway.app",
        )

        self.assertTrue(url.endswith("/siamese/adult/play.png"))

    def test_hidden_cat_has_no_preview(self) -> None:
        cat = {
            "breed": "siamese",
            "age_days": 30,
            "hunger": 10,
            "hidden_spot": "bed",
            "hidden_until": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }

        self.assertEqual(
            cat_preview_url(
                cat,
                "status",
                base_url="https://cat.example.up.railway.app",
            ),
            "",
        )

    def test_black_preview_stays_disabled(self) -> None:
        cat = {
            "breed": "black",
            "age_days": 30,
            "hunger": 10,
        }

        self.assertEqual(
            cat_preview_url(
                cat,
                "status",
                base_url="https://cat.example.up.railway.app",
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
