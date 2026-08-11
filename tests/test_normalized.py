import unittest
from pathlib import Path

from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.parser.model import Beatmap
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import OsuParseError, parse_osu, parse_osu_file

FIXTURES = Path(__file__).parent / "fixtures"


class NormalizedTests(unittest.TestCase):
    def setUp(self):
        self.nmap = normalize(parse_osu_file(FIXTURES / "minimal.osu"))

    def test_object_count_and_times(self):
        self.assertEqual(len(self.nmap.objects), 5)
        self.assertEqual([obj.time_ms for obj in self.nmap.objects], [1000, 1500, 2000, 3500, 4500])

    def test_normalized_coordinates_in_range(self):
        for obj in self.nmap.objects:
            self.assertGreaterEqual(obj.x_norm, 0.0)
            self.assertLessEqual(obj.x_norm, 1.0)
            self.assertGreaterEqual(obj.y_norm, 0.0)
            self.assertLessEqual(obj.y_norm, 1.0)

    def test_deltas(self):
        deltas = [obj.delta_time_ms for obj in self.nmap.objects[1:]]
        self.assertEqual(deltas, [500.0, 500.0, 1500.0, 1000.0])

    def test_slider_duration_formula(self):
        slider = self.nmap.objects[2]
        self.assertAlmostEqual(slider.slider_duration_ms, 500.0, places=6)

    def test_local_context(self):
        self.assertEqual(self.nmap.objects[0].local_bpm, 120.0)
        self.assertEqual(self.nmap.objects[0].local_sv, 1.0)
        self.assertGreater(self.nmap.objects[0].local_density_per_s, 0.0)
        self.assertIsNotNone(self.nmap.objects[2].angle_deg)

    def test_non_standard_mode_rejected(self):
        beatmap = parse_osu_file(FIXTURES / "minimal.osu")
        wrong = Beatmap(
            format_version=beatmap.format_version,
            mode=3,
            metadata=beatmap.metadata,
            difficulty=beatmap.difficulty,
            timing_points=beatmap.timing_points,
            hit_objects=beatmap.hit_objects,
        )
        with self.assertRaises(OsuParseError):
            normalize(wrong)

    def test_slice_preserves_timing_context(self):
        sliced = self.nmap.slice(1, 4)
        self.assertEqual(len(sliced.objects), 3)
        self.assertEqual(sliced.beatmap, self.nmap.beatmap)

    def test_huge_coordinates_do_not_overflow(self):
        text = (
            "osu file format v14\n"
            "[TimingPoints]\n"
            "1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "1e160,1e160,1000,1,0\n"
            "1e160,1e160,1500,1,0\n"
            "1e160,1e160,2000,1,0\n"
        )
        nmap = normalize(parse_osu(text))
        self.assertEqual(len(nmap.objects), 3)
        self.assertIsNone(nmap.objects[1].angle_deg)
        features = FeatureExtractor().extract(nmap)
        floats = [v for v in features.values() if isinstance(v, float)]
        self.assertFalse(any(v != v for v in floats))


if __name__ == "__main__":
    unittest.main()
