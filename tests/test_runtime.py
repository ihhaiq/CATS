"""Offline checks for the PostgreSQL/Rich Message runtime."""
import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from bot.services.cat_assets import (
    inspect_cat_asset_library,
    get_age_stage,
    media_key_candidates,
    normalize_cat_state,
)
from bot.services.rich_card import build_rich_card


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._media_patchers = [
            patch(
                "bot.services.media_runtime.get_media_override",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.media_runtime.get_media_cache_entry",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.media_runtime.set_media_cache_entry",
                new=AsyncMock(),
            ),
            patch(
                "bot.services.media_runtime.get_media_file_id",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "bot.services.media_runtime.get_media_type",
                new=AsyncMock(return_value="photo"),
            ),
        ]
        for patcher in self._media_patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self._media_patchers):
            patcher.stop()

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
        self.assertIn("<h1>Test</h1>", card.html)
        self.assertIn("😋 الشبع", card.html)
        self.assertIn("الراحة", card.html)
        self.assertIn("<footer>🐈 السلالة: black | #123456</footer>", card.html)
        self.assertIn("cat:feed", card.html)
        self.assertIn("cat:play", card.html)
        self.assertIn("cat:toy", card.html)
        self.assertIn("🧸 اعطها لعبة", card.html)
        self.assertIn("cat:relax", card.html)
        self.assertIn("🍖 إطعام", card.html)
        self.assertIn("🎾 لعب", card.html)
        self.assertIn("🌿 نزهة", card.html)
        self.assertIn("💬 تحدث", card.html)
        self.assertIn("😴 نوم", card.html)
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
        self.assertIn("<h1>&lt;b&gt;Test&lt;/b&gt;</h1>", card.html)
        self.assertNotIn("<h1><b>Test</b></h1>", card.html)

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
        self.assertIn("☀️ إيقاظ", card.html)
        self.assertIn("cat:status", card.html)
        self.assertNotIn("cat:feed", card.html)
        self.assertNotIn("cat:play", card.html)
        self.assertNotIn("cat:toy", card.html)
        self.assertNotIn("cat:walk", card.html)
        self.assertNotIn("cat:talk", card.html)

    def test_hidden_card_replaces_stats_with_search_controls(self) -> None:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        cat = {
            "cat_id": 91,
            "name": "لوز",
            "breed": "black",
            "id_number": "919191",
            "hunger": 20,
            "happiness": 80,
            "love_bar": 80,
            "trust": 70,
            "boredom": 20,
            "rest_level": 80,
            "rest_updated_at": now.isoformat(),
            "hidden_spot": "box",
            "hidden_started_at": now.isoformat(),
            "hidden_until": (now + timedelta(hours=1)).isoformat(),
            "sleep_until": None,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("<h1>لوز</h1>", card.html)
        self.assertIn("اختفت بالبيت", card.html)
        self.assertIn("cat:91:hide_bed", card.html)
        self.assertIn("cat:91:hide_box", card.html)
        self.assertIn("cat:91:hide_curtain", card.html)
        self.assertIn("cat:91:hide_call", card.html)
        self.assertIn("📣 نادي لوز", card.html)
        self.assertNotIn("<table", card.html)
        self.assertNotIn("cat:91:feed", card.html)
        self.assertNotIn("cat:91:play", card.html)

    def test_active_cat_request_adds_direct_action_and_ignore(self) -> None:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        cat = {
            "cat_id": 92,
            "name": "لوز",
            "breed": "black",
            "age_days": 30,
            "id_number": "929292",
            "hunger": 20,
            "happiness": 80,
            "love_bar": 80,
            "trust": 70,
            "boredom": 20,
            "rest_level": 80,
            "rest_updated_at": now.isoformat(),
            "last_fed": now.isoformat(),
            "last_played": now.isoformat(),
            "last_walk": now.isoformat(),
            "last_talk": now.isoformat(),
            "last_relax": now.isoformat(),
            "last_social_at": now.isoformat(),
            "active_request_action": "play",
            "active_request_started_at": now.isoformat(),
            "active_request_until": (now + timedelta(hours=1)).isoformat(),
            "sleep_until": None,
            "slept_today_hours": 0.0,
        }
        card = asyncio.run(build_rich_card(None, cat, 0))
        self.assertIn("جابت لعبتها", card.html)
        self.assertIn('data="cat:92:play"', card.html)
        self.assertIn('data="cat:92:request_ignore"', card.html)
        self.assertIn("🙈 طنش", card.html)
        self.assertIn("<table", card.html)

    def test_postgres_runtime_state_sections(self) -> None:
        from bot.database.models import default_runtime_state

        state = default_runtime_state()
        self.assertEqual(
            set(state),
            {
                "users",
                "cats",
                "items",
                "user_inventory",
                "points_log",
                "media",
                "media_types",
                "media_cache",
                "media_overrides",
            },
        )
        self.assertEqual(state["users"], {})
        self.assertEqual(state["cats"], [])

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
