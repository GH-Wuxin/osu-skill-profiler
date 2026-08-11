import unittest
from pathlib import Path

from osu_skill_profiler.models.baseline import DeterministicBaselineProfiler
from osu_skill_profiler.parser.osu_parser import parse_osu_file

FIXTURES = Path(__file__).parent / "fixtures"


class DeterminismTests(unittest.TestCase):
    def test_all_fixtures_reproduce_identical_profiles(self):
        profiler = DeterministicBaselineProfiler()
        for fixture in FIXTURES.glob("*.osu"):
            first = profiler.analyze_map(str(fixture))
            second = profiler.analyze_map(str(fixture))
            self.assertEqual(first, second, f"nondeterministic profile for {fixture.name}")

    def test_parse_twice_is_identical(self):
        for fixture in FIXTURES.glob("*.osu"):
            beatmap = parse_osu_file(fixture)
            self.assertEqual(beatmap, parse_osu_file(fixture), f"nondeterministic parse for {fixture.name}")


if __name__ == "__main__":
    unittest.main()
