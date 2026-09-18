"""Tests for filesystem-first Catibot media resolution."""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from bot.services.cat_assets import (
    CAT_ASSETS_ROOT,
    get_age_stage,
    resolve_cat_visual_state,
    resolve_local_asset,
)


class FakePhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class FakeMessage:
    def __init__(self, file_id: str, message_id: int) -> None:
        self.photo = [FakePhoto(file_id)]
        self.message_id = message_id


class FakeBot:
    def __init__(self) -> None:
        self.uploads = 0

    async def send_photo(self, **kwargs):
        self.uploads += 1
        return FakeMessage(f"uploaded-{self.uploads}", self.uploads)

    async def delete_message(self, **kwargs):
        return True


class CatAssetRuntimeTests(unittest.TestCase):
    def test_age_boundaries(self) -> None:
        self.assertEqual(get_age_stage(6), "kitten")
        self.assertEqual(get_age_stage(7), "junior")
        self.assertEqual(get_age_stage(21), "adult")
        self.assertEqual(get_age_stage(90), "senior")

    def test_status_idle_hungry_sleep_and_angry_precedence(self) -> None:
        cat = {"hunger": 20, "sleep_until": None}
        self.assertEqual(resolve_cat_visual_state(cat, "status"), "idle")

        cat["hunger"] = 70
        self.assertEqual(resolve_cat_visual_state(cat, "status"), "hungry")

        cat["sleep_until"] = (
            datetime.utcnow() + timedelta(hours=1)
        ).isoformat()
        self.assertEqual(resolve_cat_visual_state(cat, "status"), "sleep")

        cat["sleep_until"] = None
        cat["action_refusal_until"] = (
            datetime.utcnow() + timedelta(minutes=5)
        ).timestamp()
        self.assertEqual(resolve_cat_visual_state(cat, "status"), "angry")
        self.assertEqual(
            resolve_cat_visual_state(cat, "cat_angry_sleep"),
            "angry",
        )

    def test_explicit_action_wins(self) -> None:
        cat = {
            "hunger": 100,
            "sleep_until": (
                datetime.utcnow() + timedelta(hours=1)
            ).isoformat(),
        }
        self.assertEqual(resolve_cat_visual_state(cat, "feed"), "feed")
        self.assertEqual(resolve_cat_visual_state(cat, "sleep"), "sleep")

    def test_local_exact_then_adult_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "siamese" / "kitten" / "sleep.png"
            adult = root / "siamese" / "adult" / "sleep.png"
            exact.parent.mkdir(parents=True)
            adult.parent.mkdir(parents=True)
            exact.write_bytes(b"exact")
            adult.write_bytes(b"adult")

            result = resolve_local_asset(
                "siamese", "kitten", "sleep", root=root
            )
            self.assertEqual(result.path, exact)

            exact.unlink()
            result = resolve_local_asset(
                "siamese", "kitten", "sleep", root=root
            )
            self.assertEqual(result.path, adult)
            self.assertEqual(result.age_stage, "adult")

    def test_checked_in_siamese_assets_exist(self) -> None:
        for state in ("idle", "hungry", "sleep", "angry"):
            path = (
                CAT_ASSETS_ROOT
                / "siamese"
                / "adult"
                / f"{state}.png"
            )
            self.assertTrue(path.is_file(), path)

    def test_local_precedence_cache_reuse_and_invalidation(self) -> None:
        from bot.config import settings
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            asset = root / "siamese" / "adult" / "idle.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"version-one")

            data_path = Path(directory) / "catibot.json"
            data_path.write_text(
                json.dumps(
                    {
                        "media": {
                            "siamese:idle": "legacy-id"
                        },
                        "media_types": {
                            "siamese:idle": "photo"
                        },
                    }
                ),
                encoding="utf-8",
            )

            old_data = settings.json_data_file
            old_chat = settings.media_cache_chat_id
            settings.json_data_file = str(data_path)
            settings.media_cache_chat_id = 0
            bot = FakeBot()
            cat = {
                "breed": "siamese",
                "age_days": 30,
                "hunger": 20,
                "sleep_until": None,
            }
            try:
                first = asyncio.run(
                    resolve_cat_media(
                        bot,
                        cat,
                        "status",
                        upload_chat_id=123,
                        assets_root=root,
                    )
                )
                second = asyncio.run(
                    resolve_cat_media(
                        bot,
                        cat,
                        "status",
                        upload_chat_id=123,
                        assets_root=root,
                    )
                )
                self.assertEqual(first.source, "local_upload")
                self.assertEqual(second.source, "local_cache")
                self.assertEqual(bot.uploads, 1)

                asset.write_bytes(b"version-two")
                third = asyncio.run(
                    resolve_cat_media(
                        bot,
                        cat,
                        "status",
                        upload_chat_id=123,
                        assets_root=root,
                    )
                )
                self.assertEqual(third.source, "local_upload")
                self.assertEqual(third.file_id, "uploaded-2")
                self.assertEqual(bot.uploads, 2)
            finally:
                settings.json_data_file = old_data
                settings.media_cache_chat_id = old_chat

    def test_legacy_fallback_when_local_missing(self) -> None:
        from bot.config import settings
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            data_path = Path(directory) / "catibot.json"
            data_path.write_text(
                json.dumps(
                    {
                        "media": {
                            "siamese:sleep": "legacy-sleep"
                        },
                        "media_types": {
                            "siamese:sleep": "photo"
                        },
                    }
                ),
                encoding="utf-8",
            )
            old_data = settings.json_data_file
            settings.json_data_file = str(data_path)
            cat = {
                "breed": "siamese",
                "age_days": 5,
                "hunger": 20,
                "sleep_until": None,
            }
            try:
                result = asyncio.run(
                    resolve_cat_media(
                        None,
                        cat,
                        "sleep",
                        assets_root=root,
                    )
                )
                self.assertEqual(result.source, "legacy_json")
                self.assertEqual(result.file_id, "legacy-sleep")
            finally:
                settings.json_data_file = old_data

    def test_missing_local_without_legacy_returns_none(self) -> None:
        from bot.config import settings
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            data_path = Path(directory) / "catibot.json"
            old_data = settings.json_data_file
            settings.json_data_file = str(data_path)
            cat = {
                "breed": "white",
                "age_days": 100,
                "hunger": 20,
                "sleep_until": None,
            }
            try:
                result = asyncio.run(
                    resolve_cat_media(
                        None,
                        cat,
                        "sick",
                        assets_root=root,
                    )
                )
                self.assertIsNone(result)
            finally:
                settings.json_data_file = old_data


if __name__ == "__main__":
    unittest.main()
