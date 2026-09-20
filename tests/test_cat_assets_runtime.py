"""Tests for filesystem-first Catibot media resolution."""
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from bot.services.cat_assets import (
    CAT_ASSETS_ROOT,
    get_age_stage,
    resolve_cat_visual_state,
    resolve_local_asset,
    resolve_media_value,
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
        await asyncio.sleep(0.01)
        self.uploads += 1
        return FakeMessage(f"uploaded-{self.uploads}", self.uploads)

    async def delete_message(self, **kwargs):
        return True


class CatAssetRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.media: dict[str, str] = {}
        self.media_types: dict[str, str] = {}
        self.cache: dict[str, dict] = {}
        self.overrides: dict[str, dict] = {}

        async def get_media_file_id(kind, breed=None, age_stage=None):
            value, _ = resolve_media_value(
                self.media,
                kind,
                breed,
                age_stage,
            )
            return value

        async def get_media_type(kind, breed=None, age_stage=None):
            value, _ = resolve_media_value(
                self.media_types,
                kind,
                breed,
                age_stage,
                default="photo",
            )
            return value or "photo"

        async def get_media_cache_entry(cache_key):
            value = self.cache.get(cache_key)
            return dict(value) if value else None

        async def set_media_cache_entry(
            cache_key,
            *,
            file_id,
            file_hash,
            media_type,
            path,
        ):
            self.cache[cache_key] = {
                "file_id": file_id,
                "file_hash": file_hash,
                "media_type": media_type,
                "path": path,
            }

        async def get_media_override(kind, breed, age_stage):
            state = resolve_cat_visual_state(
                {"hunger": 0},
                kind,
            )
            value = self.overrides.get(f"{breed}:{age_stage}:{state}")
            return dict(value) if value else None

        self._patchers = [
            patch(
                "bot.services.media_runtime.get_media_file_id",
                new=get_media_file_id,
            ),
            patch(
                "bot.services.media_runtime.get_media_type",
                new=get_media_type,
            ),
            patch(
                "bot.services.media_runtime.get_media_cache_entry",
                new=get_media_cache_entry,
            ),
            patch(
                "bot.services.media_runtime.set_media_cache_entry",
                new=set_media_cache_entry,
            ),
            patch(
                "bot.services.media_runtime.get_media_override",
                new=get_media_override,
            ),
        ]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()

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
                "siamese",
                "kitten",
                "sleep",
                root=root,
            )
            self.assertEqual(result.path, exact)

            exact.unlink()
            result = resolve_local_asset(
                "siamese",
                "kitten",
                "sleep",
                root=root,
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

            old_chat = settings.media_cache_chat_id
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
                settings.media_cache_chat_id = old_chat

    def test_database_fallback_when_local_missing(self) -> None:
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            self.media["siamese:sleep"] = "db-sleep"
            self.media_types["siamese:sleep"] = "photo"
            cat = {
                "breed": "siamese",
                "age_days": 5,
                "hunger": 20,
                "sleep_until": None,
            }
            result = asyncio.run(
                resolve_cat_media(
                    None,
                    cat,
                    "sleep",
                    assets_root=root,
                )
            )
            self.assertEqual(result.source, "database_fallback")
            self.assertEqual(result.file_id, "db-sleep")

    def test_missing_local_without_database_fallback_returns_none(self) -> None:
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            cat = {
                "breed": "white",
                "age_days": 100,
                "hunger": 20,
                "sleep_until": None,
            }
            result = asyncio.run(
                resolve_cat_media(
                    None,
                    cat,
                    "sick",
                    assets_root=root,
                )
            )
            self.assertIsNone(result)

    def test_concurrent_requests_upload_once(self) -> None:
        from bot.config import settings
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            asset = root / "siamese" / "adult" / "idle.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"concurrent")

            old_chat = settings.media_cache_chat_id
            settings.media_cache_chat_id = 0
            bot = FakeBot()
            cat = {
                "breed": "siamese",
                "age_days": 30,
                "hunger": 20,
                "sleep_until": None,
            }

            async def scenario():
                return await asyncio.gather(
                    resolve_cat_media(
                        bot,
                        cat,
                        "status",
                        upload_chat_id=123,
                        assets_root=root,
                    ),
                    resolve_cat_media(
                        bot,
                        cat,
                        "status",
                        upload_chat_id=123,
                        assets_root=root,
                    ),
                )

            try:
                first, second = asyncio.run(scenario())
                self.assertEqual(bot.uploads, 1)
                self.assertEqual(first.file_id, second.file_id)
                self.assertEqual(
                    {first.source, second.source},
                    {"local_upload", "local_cache"},
                )
            finally:
                settings.media_cache_chat_id = old_chat

    def test_literal_legacy_status_and_angry_keys_still_work(self) -> None:
        from bot.services.media_runtime import resolve_cat_media

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            self.media["siamese:status"] = "legacy-status"
            self.media["siamese:cat_angry_sleep"] = "legacy-angry"
            cat = {
                "breed": "siamese",
                "age_days": 30,
                "hunger": 20,
                "sleep_until": None,
            }

            status_media = asyncio.run(
                resolve_cat_media(
                    None,
                    cat,
                    "status",
                    assets_root=root,
                )
            )
            angry_media = asyncio.run(
                resolve_cat_media(
                    None,
                    cat,
                    "cat_angry_sleep",
                    assets_root=root,
                )
            )
            self.assertEqual(status_media.file_id, "legacy-status")
            self.assertEqual(angry_media.file_id, "legacy-angry")


if __name__ == "__main__":
    unittest.main()
