import unittest
from pathlib import Path

from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.features.schema import FEATURE_SCHEMA
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu, parse_osu_file

FIXTURES = Path(__file__).parent / "fixtures"


class FeatureTests(unittest.TestCase):
    def _features(self, name):
        nmap = normalize(parse_osu_file(FIXTURES / name))
        return FeatureExtractor().extract(nmap)

    def test_minimal_features_are_known_and_numeric(self):
        features = self._features("minimal.osu")
        self.assertIn("temporal.object_count", features)
        self.assertEqual(features["temporal.object_count"], 5.0)
        for key, value in features.items():
            self.assertIn(key, FEATURE_SCHEMA, f"unknown feature {key}")
            self.assertTrue(value is None or isinstance(value, (int, float)), f"{key} -> {value!r}")

    def test_slider_features(self):
        features = self._features("sliders.osu")
        self.assertAlmostEqual(features["slider.slider_ratio"], 10.0 / 12.0)
        self.assertGreater(features["slider.repeats_total"], 0.0)
        self.assertGreater(features["slider.duration_ms_mean"], 0.0)

    def test_unusual_sv_rhythm_and_bursts(self):
        features = self._features("unusual_sv.osu")
        self.assertGreater(features["temporal.rhythm_entropy_bits"], 0.0)
        self.assertGreaterEqual(features["temporal.burst_count_125ms"], 1.0)
        self.assertEqual(features["temporal.bpm_max"], 300.0)

    def test_timing_changes_bpm_range(self):
        features = self._features("timing_changes.osu")
        self.assertEqual(features["temporal.bpm_min"], 120.0)
        self.assertEqual(features["temporal.bpm_max"], 240.0)

    def test_extraction_is_deterministic(self):
        first = self._features("unusual_sv.osu")
        second = self._features("unusual_sv.osu")
        self.assertEqual(first, second)

    def test_absurd_timestamp_does_not_create_unbounded_windows(self):
        text = (
            "osu file format v14\n"
            "[TimingPoints]\n"
            "1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "192,192,1e12,1,0\n"
        )
        features = FeatureExtractor().extract(normalize(parse_osu(text)))
        self.assertLessEqual(features["section.window_count"], 2.0)
        self.assertLessEqual(features["temporal.object_count"], 2.0)

    def test_difficulty_context_features_are_populated(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\n"
            "HPDrainRate:5\n"
            "CircleSize:4\n"
            "OverallDifficulty:8\n"
            "ApproachRate:9\n"
            "SliderMultiplier:1.4\n"
            "SliderTickRate:2\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
        )
        features = FeatureExtractor().extract(normalize(parse_osu(text)))
        self.assertEqual(features["difficulty.AR"], 9.0)
        self.assertEqual(features["difficulty.OD"], 8.0)
        self.assertEqual(features["difficulty.CS"], 4.0)
        self.assertEqual(features["difficulty.HP"], 5.0)
        self.assertEqual(features["difficulty.SliderMultiplier"], 1.4)
        self.assertEqual(features["difficulty.SliderTickRate"], 2.0)


if __name__ == "__main__":
    unittest.main()
