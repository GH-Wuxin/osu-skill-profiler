from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for path in (TOOLS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01.bid_review_ui_v01 import BidReviewError  # noqa: E402
from map_demand_v01.type_annotation_ui_v01 import (  # noqa: E402
    ANNOTATION_SCHEMA_VERSION,
    TypeAnnotationWorkbench,
)
from map_demand_v01.type_classifier_v01 import suggest_sections  # noqa: E402
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402


class TypeAnnotationWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.songs = self.root / "Songs"
        folder = self.songs / "2000001 fixture"
        folder.mkdir(parents=True)
        self.map_path = folder / "fixture.osu"
        shutil.copy2(ROOT / "tests" / "fixtures" / "minimal.osu", self.map_path)
        (folder / "audio.mp3").write_bytes(b"fixture-audio")
        self.manifest = self.root / "manifest.jsonl"
        self.manifest.write_text(
            json.dumps(
                {
                    "beatmap_id": 1000001,
                    "beatmapset_id": 2000001,
                    "relative_path": "2000001 fixture/fixture.osu",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.responses = self.root / "responses.jsonl"
        self.workbench = TypeAnnotationWorkbench(
            manifest_path=self.manifest,
            songs_root=self.songs,
            responses_path=self.responses,
            reviewer_id="tester",
            cache_root=self.root / "cache",
            allow_downloads=False,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_analysis_contains_playable_objects_sections_and_mod_clock(self):
        result = self.workbench.analyze_bid(1000001, "HDDT")
        self.assertEqual(result["mod_context"]["requested_mods"], ["HD", "DT"])
        self.assertEqual(result["preview"]["clock_rate"], 1.5)
        self.assertTrue(result["preview"]["audio_available"])
        self.assertEqual(len(result["preview"]["objects"]), 5)
        self.assertGreater(len(result["preview"]["objects"][2]["slider_path"]), 2)
        self.assertLess(result["preview"]["objects"][0]["start_ms"], 1000)
        self.assertGreaterEqual(len(result["suggested_sections"]), 1)
        self.assertIn("machine_proposal", result["suggested_sections"][0])
        self.assertIn("machine_summary", result)
        self.assertEqual(result["map_demand"]["status"], "UNAVAILABLE")
        media = self.workbench.media_path(result["analysis_id"], "audio")
        self.assertEqual(media, self.map_path.parent / "audio.mp3")

    def test_gimmick_subtype_is_required_and_valid_annotation_is_appended(self):
        result = self.workbench.analyze_bid(1000001, [])
        section = {
            "section_id": "s1",
            "start_ms": result["preview"]["start_ms"],
            "end_ms": result["preview"]["end_ms"],
            "primary_type": "GIMMICK",
            "secondary_types": [],
            "gimmick_subtype": None,
            "structural_tags": ["DIFFICULTY_SPIKE"],
            "contribution": "DECISIVE",
            "notes": "fixture",
        }
        summary = {
            "primary_type": "GIMMICK",
            "secondary_types": [],
            "gimmick_subtype": "ODD_RHYTHM",
            "composition_types": ["JUMP"],
        }
        with self.assertRaises(BidReviewError) as missing:
            self.workbench.save(
                {"analysis_id": result["analysis_id"], "sections": [section], "summary": summary}
            )
        self.assertEqual(missing.exception.code, "GIMMICK_SUBTYPE_REQUIRED")
        section["gimmick_subtype"] = "ODD_RHYTHM"
        saved = self.workbench.save(
            {"analysis_id": result["analysis_id"], "sections": [section], "summary": summary}
        )
        self.assertEqual(saved["status"], "SAVED")
        payload = json.loads(self.responses.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], ANNOTATION_SCHEMA_VERSION)
        self.assertEqual(payload["identity"]["beatmap_id"], 1000001)
        self.assertEqual(payload["sections"][0]["contribution"], "DECISIVE")
        self.assertIn("machine_proposal", payload["sections"][0])
        self.assertTrue(payload["sections"][0]["human_changed_machine_proposal"])
        self.assertIn("machine_proposal", payload["summary"])

    def test_section_suggestions_are_deterministic(self):
        objects = normalize(parse_osu_file(ROOT / "tests" / "fixtures" / "sliders.osu")).objects
        self.assertEqual(suggest_sections(objects), suggest_sections(objects))
        sections = suggest_sections(objects)
        self.assertEqual(sections[0]["object_start"], 0)
        self.assertEqual(sections[-1]["object_end"], len(objects))
        self.assertLessEqual(len(sections), 8)

    def test_ui_distinguishes_unlabeled_and_defaults_audio_to_thirty_percent(self):
        html = (ROOT / "tools" / "map_demand_v01" / "type_annotation_ui_v01.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("UNLABELED:'未标注'", html)
        self.assertIn("NONE:'人工确认无明显主类型'", html)
        self.assertIn('id="musicVolume" type="range" min="0" max="1" step="0.01" value="0.3"', html)
        self.assertIn('id="hitVolume" type="range" min="0" max="1" step="0.01" value="0.3"', html)
        self.assertIn('id="axes" class="axis-grid"', html)


if __name__ == "__main__":
    unittest.main()
