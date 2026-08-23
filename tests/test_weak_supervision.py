import json
import tempfile
import unittest
from pathlib import Path

from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.segments.fixed_time import FixedTimeWindowStrategy
from osu_skill_profiler.weak_supervision.engine import (
    apply_weak_rules,
    canonical_json,
    checksum_normalized,
    save_weak_labels,
)
from osu_skill_profiler.weak_supervision.rules import CONSERVATIVE_RULES


def _stream_map():
    lines = ["osu file format v14", "[General]", "Mode: 0", "[Metadata]", "Creator:fixture-mapper", "Version:X",
             "[Difficulty]", "CircleSize:4", "OverallDifficulty:8", "ApproachRate:9", "SliderMultiplier:1.4",
             "[TimingPoints]", "1000,300,4,2,1,60,1,0", "[HitObjects]"]
    for index in range(51):
        lines.append(f"256,192,{1000 + index * 100},1,0,0:0:0:0:")
    return "\n".join(lines)


def _jump_map():
    lines = ["osu file format v14", "[General]", "Mode: 0", "[Metadata]", "Creator:fixture-mapper", "Version:X",
             "[Difficulty]", "CircleSize:4", "OverallDifficulty:8", "ApproachRate:9", "SliderMultiplier:1.4",
             "[TimingPoints]", "1000,300,4,2,1,60,1,0", "[HitObjects]"]
    corners = [(64, 64), (448, 320), (64, 320), (448, 64)]
    for index in range(20):
        x, y = corners[index % 4]
        lines.append(f"{x},{y},{1000 + index * 80},1,0,0:0:0:0:")
    return "\n".join(lines)


class WeakSupervisionTests(unittest.TestCase):
    def _run(self, text):
        nmap = normalize(parse_osu(text))
        extractor = FeatureExtractor()
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, extractor)
        features = extractor.extract(nmap)
        return apply_weak_rules(features, segments, CONSERVATIVE_RULES, checksum_normalized(nmap))

    def test_conservative_rules_fire_on_obvious_patterns(self):
        dense = self._run(_stream_map())
        skills = {record.skill for record in dense}
        self.assertIn("stream", skills)
        jumps = self._run(_jump_map())
        self.assertIn("jump_aim", {record.skill for record in jumps})

    def test_rules_do_not_fire_on_quiet_map(self):
        quiet = Path(__file__).parent / "fixtures" / "minimal.osu"
        nmap = normalize(parse_osu(quiet.read_text(encoding="utf-8")))
        extractor = FeatureExtractor()
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, extractor)
        records = apply_weak_rules(extractor.extract(nmap), segments, CONSERVATIVE_RULES, checksum_normalized(nmap))
        self.assertEqual(records, [])

    def test_provenance_and_confidence(self):
        records = self._run(_stream_map())
        self.assertTrue(records)
        for record in records:
            self.assertTrue(record.rule_id.startswith("wsp"))
            self.assertLessEqual(record.confidence, 0.35)
            self.assertTrue(record.evidence)
            self.assertIn("WEAK LABEL != GROUND TRUTH", record.disclaimer)
            self.assertRegex(record.input_checksum, r"^sha256:[0-9a-f]{64}$")

    def test_deterministic(self):
        first = self._run(_stream_map())
        second = self._run(_stream_map())
        self.assertEqual([record.as_dict() for record in first], [record.as_dict() for record in second])

    def test_canonical_json_rejects_nonfinite(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                canonical_json({"value": value})

    def test_save_load_roundtrip(self):
        records = self._run(_stream_map())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weak_labels.json"
            save_weak_labels(records, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "weak_labels")
            self.assertEqual(len(payload["records"]), len(records))
            self.assertEqual(payload["records"][0]["rule_id"], records[0].rule_id)


if __name__ == "__main__":
    unittest.main()

