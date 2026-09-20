"""Offline checks for the checked-in JSON and Rich Message runtime."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from bot.services.cat_assets import (
    inspect_cat_asset_library,
    get_age_stage,
    media_key_candidates,
    normalize_cat_state,
)
from bot.services.rich_card import build_rich_card


class RuntimeTests(unittest.TestCase):
    def test_get_age_stage_boundaries(self) -> None:
        self.assertEqual(get_age_stage(0), "kitten")
        self.assertEqual(get_age_stage(6), "kitten")
        self.assertEqual(get_age_stage(7), "junior")
        self.assertEqual(get_age_stage(20), "junior")
        self.assertEqual(get_age_stage(21), "adult")
        self.assertEqual(get_age_stage(89), "adult")
        self.assertEqual(get_age_stage(90), "senior")
        self.assertEqual(get_age_stage(999), "senior")

    def test_legacy_state_mapping(self) -> None:
        self.assertEqual(normalize_cat_state("status"), "idle")
        self.assertEqual(normalize_cat_state("cat_angry_sleep"), "angry")
        self.assertEqual(normalize_cat_state("sleep"), "sleep")

    def test_media_key_precedence(self) -> None:
        keys = media_key_candidates("sleep", "siamese", "kitten")
        self.assertEqual(
            keys[:4],
            (
                "siamese:kitten:sleep",
                "siamese:adult:sleep",
                "siamese:sleep",
                "sleep",
            ),
        )

    def test_media_key_legacy_alias_candidates(self) -> None:
        keys = media_key_candidates("status", "siamese", "kitten")
        self.assertEqual(keys[0], "siamese:kitten:idle")
        self.assertIn("siamese:status", keys)
        self.assertIn("status", keys)
        self.assertIn("idle", keys)

        angry = media_key_candidates("cat_angry_sleep", "siamese", "kitten")
        self.assertEqual(angry[0], "siamese:kitten:angry")
        self.assertIn("siamese:cat_angry_sleep", angry)

    def test_rich_card_has_state_table_and_actions(self) -> None:
        cat = {
            "name": "Test",
            "breed": "black",
            "age_days": 5,
            "id_number": "123456",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 100,
            "slept_today_hours": 10,
        }
        card = asyncio.run(build_rich_card(None, cat, 42))
        self.assertIn("الشبع", card.html)
        self.assertIn("الراحة", card.html)
        self.assertIn("cat:feed", card.html)
        self.assertIn("cat:play", card.html)
        self.assertIn("cat:toy", card.html)
        self.assertIn("🧸 اعطها لعبة", card.html)
        self.assertIn("cat:relax", card.html)
        self.assertIn("<th>الحالة</th><th>النسبة</th><th>ملاحظة</th>", card.html)
        self.assertIn("شبعانة", card.html)
        self.assertIn("مرتاحة ومستانسة", card.html)
        self.assertNotIn("<td><b>ملاحظة</b></td>", card.html)
        self.assertIn("<details>", card.html)
        self.assertIn("<summary>شنو تعني النسب؟</summary>", card.html)
        self.assertIn("<ul>", card.html)
        self.assertIn("0 يعني جوعانة حيل، و100 يعني شبعانة حيل", card.html)
        self.assertIn("0 يعني مو ملانة أبد، و100 يعني عندها ملل قاتل", card.html)
        self.assertIn("0 يعني منهكة وما بيها حيل، و100 يعني مرتاحة حيل", card.html)

    def test_rich_card_binds_controls_to_cat_id(self) -> None:
        cat = {
            "cat_id": 77,
            "name": "Bound",
            "breed": "black",
            "age_days": 30,
            "id_number": "777777",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 100,
            "trust": 60,
            "boredom": 10,
            "rest_level": 100,
            "rest_updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            "last_fed": None,
            "last_played": None,
            "last_walk": None,
            "last_talk": None,
            "slept_today_hours": 0.0,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("cat:77:feed", card.html)
        self.assertIn("cat:77:play", card.html)
        self.assertIn("cat:77:toy", card.html)
        self.assertIn("cat:77:status", card.html)
        self.assertNotIn('data="cat:feed"', card.html)

    def test_rich_card_escapes_user_cat_name(self) -> None:
        cat = {
            "name": "<b>Test</b>",
            "breed": "black",
            "age_days": 30,
            "id_number": "123456",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 100,
            "trust": 60,
            "boredom": 10,
            "rest_level": 100,
            "slept_today_hours": 0,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("&lt;b&gt;Test&lt;/b&gt;", card.html)
        self.assertNotIn("<h2><b>Test</b></h2>", card.html)

    def test_state_note_describes_hunger_and_boredom(self) -> None:
        from datetime import datetime

        cat = {
            "name": "Mood",
            "breed": "black",
            "age_days": 30,
            "id_number": "222222",
            "hunger": 60,
            "happiness": 90,
            "love_bar": 100,
            "trust": 60,
            "boredom": 90,
            "rest_level": 100,
            "rest_updated_at": datetime.utcnow().isoformat(),
            "last_fed": None,
            "last_played": None,
            "last_walk": None,
            "last_talk": None,
            "last_relax": None,
            "slept_today_hours": 0.0,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("ملل قاتل", card.html)
        self.assertIn("جائعة شوي", card.html)

    def test_state_table_notes_cover_fullness_extremes(self) -> None:
        from datetime import datetime

        cat = {
            "name": "Notes",
            "breed": "black",
            "age_days": 30,
            "id_number": "232323",
            "hunger": 0,
            "happiness": 100,
            "love_bar": 100,
            "trust": 100,
            "boredom": 0,
            "rest_level": 100,
            "rest_updated_at": datetime.utcnow().isoformat(),
            "last_fed": None,
            "last_played": None,
            "last_walk": None,
            "last_talk": None,
            "last_relax": None,
            "slept_today_hours": 0.0,
        }

        full_card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("شبعانة حيل", full_card.html)
        self.assertIn("فرحانة حيل", full_card.html)
        self.assertIn("تحبك حيل", full_card.html)
        self.assertIn("واثقة بيك حيل", full_card.html)
        self.assertIn("مو ملانة أبد", full_card.html)
        self.assertIn("مرتاحة حيل", full_card.html)

        starving_card = asyncio.run(
            build_rich_card(None, dict(cat, hunger=100), 0)
        )
        self.assertIn("ميتة جوع", starving_card.html)

    def test_update_button_is_separate_and_colored(self) -> None:
        cat = {
            "name": "UI",
            "breed": "black",
            "age_days": 30,
            "id_number": "333333",
            "hunger": 20,
            "happiness": 90,
            "love_bar": 100,
            "trust": 60,
            "boredom": 10,
            "rest_level": 100,
            "last_fed": None,
            "last_played": None,
            "last_walk": None,
            "last_talk": None,
            "last_relax": None,
            "slept_today_hours": 0.0,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn('style="success" data="cat:status">🔄 تحديث', card.html)
        self.assertIn("🛋 استلقاء", card.html)
        self.assertIn("🧸 اعطها لعبة", card.html)

    def test_lightning_only_marks_live_cooldown_bypass(self) -> None:
        from datetime import datetime

        base = {
            "name": "Hungry",
            "breed": "black",
            "age_days": 30,
            "id_number": "121212",
            "hunger": 80,
            "happiness": 90,
            "love_bar": 100,
            "trust": 60,
            "boredom": 10,
            "rest_level": 100,
            "rest_updated_at": datetime.utcnow().isoformat(),
            "last_played": None,
            "last_walk": None,
            "last_talk": None,
            "slept_today_hours": 0.0,
        }

        ready_cat = dict(base, last_fed=None)
        ready_card = asyncio.run(build_rich_card(None, ready_cat, 0))
        self.assertIn("🎯 المطلوب هسه: 🍖 إطعام", ready_card.html)
        self.assertNotIn(">⚡ إطعام</tg-button>", ready_card.html)

        cooldown_cat = dict(base, last_fed=datetime.utcnow().isoformat())
        cooldown_card = asyncio.run(build_rich_card(None, cooldown_cat, 0))
        self.assertIn(">⚡ إطعام</tg-button>", cooldown_card.html)

    def test_sleeping_card_hides_care_actions(self) -> None:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        cat = {
            "name": "Sleepy",
            "breed": "siamese",
            "age_days": 30,
            "id_number": "999999",
            "hunger": 30,
            "happiness": 80,
            "love_bar": 90,
            "trust": 70,
            "boredom": 20,
            "rest_level": 60,
            "rest_updated_at": now.isoformat(),
            "sleep_started_at": now.isoformat(),
            "sleep_until": (now + timedelta(hours=1)).isoformat(),
            "sleep_kind": "nap",
            "sleep_planned_hours": 1.0,
            "slept_today_hours": 0.0,
            "sleep_day": now.date().isoformat(),
        }
        card = asyncio.run(build_rich_card(None, cat, 10, "sleep"))
        self.assertIn("cat:wake", card.html)
        self.assertIn("cat:status", card.html)
        self.assertNotIn("cat:feed", card.html)
        self.assertNotIn("cat:play", card.html)
        self.assertNotIn("cat:toy", card.html)
        self.assertNotIn("cat:walk", card.html)
        self.assertNotIn("cat:talk", card.html)

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
                        "age_days": 30,
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

    def test_json_backup_restores_cat_after_primary_corruption(self) -> None:
        from bot.config import settings
        from bot.services.local_store import create_cat, get_user_cat, now_iso, update_cat

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            data_path = Path(directory) / "catibot.json"
            settings.json_data_file = str(data_path)
            try:
                async def scenario() -> None:
                    stamp = now_iso()
                    cat = {
                        "owner_id": 991,
                        "name": "Protected",
                        "breed": "black",
                        "age_days": 30,
                        "id_number": "991991",
                        "hunger": 20,
                        "happiness": 90,
                        "love_bar": 100,
                        "trust": 60,
                        "boredom": 10,
                        "is_fled": False,
                        "last_fed": stamp,
                        "last_played": None,
                        "last_toy": None,
                        "last_walk": None,
                        "last_talk": None,
                        "last_relax": None,
                        "last_decay_at": stamp,
                    }
                    await create_cat(cat)
                    cat["happiness"] = 88
                    await update_cat(cat)

                    self.assertTrue(Path(str(data_path) + ".bak").exists())
                    data_path.write_text("{broken", encoding="utf-8")

                    restored = await get_user_cat(991)
                    self.assertIsNotNone(restored)
                    self.assertEqual(restored["name"], "Protected")
                    self.assertEqual(restored["happiness"], 88)

                asyncio.run(scenario())
            finally:
                settings.json_data_file = previous

    def test_media_lookup_fallback_chain_and_missing(self) -> None:
        from bot.config import settings
        from bot.services.local_store import get_media_file_id_sync

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            data_path = Path(directory) / "catibot.json"
            settings.json_data_file = str(data_path)
            data_path.write_text(
                json.dumps(
                    {
                        "media": {
                            "siamese:kitten:sleep": "exact",
                            "black:adult:sleep": "adult-fallback",
                            "calico:sleep": "legacy-fallback",
                            "hungry": "generic-fallback",
                            "siamese:kitten:idle": "idle-canonical",
                            "siamese:kitten:angry": "angry-canonical",
                        },
                        "media_types": {},
                    }
                ),
                encoding="utf-8",
            )
            try:
                self.assertEqual(
                    get_media_file_id_sync("sleep", "siamese", "kitten"),
                    "exact",
                )
                self.assertEqual(
                    get_media_file_id_sync("sleep", "black", "kitten"),
                    "adult-fallback",
                )
                self.assertEqual(
                    get_media_file_id_sync("sleep", "calico", "kitten"),
                    "legacy-fallback",
                )
                self.assertEqual(
                    get_media_file_id_sync("hungry", "white", "kitten"),
                    "generic-fallback",
                )
                self.assertEqual(
                    get_media_file_id_sync("status", "siamese", "kitten"),
                    "idle-canonical",
                )
                self.assertEqual(
                    get_media_file_id_sync("cat_angry_sleep", "siamese", "kitten"),
                    "angry-canonical",
                )
                self.assertEqual(
                    get_media_file_id_sync("sick", "white", "senior"),
                    "",
                )
            finally:
                settings.json_data_file = previous

    def test_set_media_file_writes_three_part_key(self) -> None:
        from bot.config import settings
        from bot.services.local_store import get_media_file_id_sync, set_media_file

        with tempfile.TemporaryDirectory() as directory:
            previous = settings.json_data_file
            settings.json_data_file = str(Path(directory) / "catibot.json")
            try:
                asyncio.run(
                    set_media_file(
                        "sleep",
                        "file-123",
                        "photo",
                        breed="white",
                        age_stage="senior",
                    )
                )
                self.assertEqual(
                    get_media_file_id_sync("sleep", "white", "senior"),
                    "file-123",
                )
            finally:
                settings.json_data_file = previous

    def test_asset_library_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            anchor = root / "siamese" / "kitten" / "idle.png"
            anchor.parent.mkdir(parents=True)
            anchor.touch()

            report = inspect_cat_asset_library(root)
            self.assertEqual(report.total_expected, 240)
            self.assertEqual(report.present, 1)
            self.assertEqual(report.missing_count, 239)
            self.assertNotIn("siamese/kitten/idle.png", report.missing)
            self.assertIn("siamese/kitten/sleep.png", report.missing)


if __name__ == "__main__":
    unittest.main()
