import unittest
from pathlib import Path

from osu_skill_profiler.models.baseline import DeterministicBaselineProfiler
from osu_skill_profiler.schema.output_schema import OUTPUT_SCHEMA
from osu_skill_profiler.schema.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"


class ModelInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.profiler = DeterministicBaselineProfiler()

    def test_analyze_map_returns_schema_valid_profile(self):
        profile = self.profiler.analyze_map(str(FIXTURES / "sliders.osu"))
        self.assertEqual(validate(profile, OUTPUT_SCHEMA), [])
        self.assertEqual(profile["model_kind"], "baseline")
        self.assertEqual(profile["status"], "not_inferred")
        self.assertIn("BASELINE / NOT TRAINED / NOT GROUND TRUTH", profile["disclaimer"])
        for skill in profile["skills"].values():
            self.assertIsNone(skill["score"])
            self.assertIsNone(skill["confidence"])
            self.assertEqual(skill["status"], "not_inferred")
        self.assertGreater(len(profile["segments"]), 0)
        self.assertIn("temporal.object_count_mean", profile["features"])

    def test_analyze_segments(self):
        segments = self.profiler.analyze_segments(str(FIXTURES / "minimal.osu"))
        self.assertEqual(len(segments), 1)
        for segment in segments:
            self.assertIn("start_ms", segment)
            self.assertIn("end_ms", segment)
            self.assertIn("features", segment)

    def test_deterministic_output(self):
        first = self.profiler.analyze_map(str(FIXTURES / "unusual_sv.osu"))
        second = self.profiler.analyze_map(str(FIXTURES / "unusual_sv.osu"))
        self.assertEqual(first, second)

    def test_invalid_strategy_rejected(self):
        with self.assertRaises(ValueError):
            DeterministicBaselineProfiler(segment_strategy="bogus")


if __name__ == "__main__":
    unittest.main()

