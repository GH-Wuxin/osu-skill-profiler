import unittest
from pathlib import Path

from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu, parse_osu_file
from osu_skill_profiler.segments.base import Segment
from osu_skill_profiler.segments.aggregator import aggregate_features
from osu_skill_profiler.segments.fixed_count import FixedObjectCountStrategy
from osu_skill_profiler.segments.fixed_time import FixedTimeWindowStrategy

FIXTURES = Path(__file__).parent / "fixtures"


class SegmentTests(unittest.TestCase):
    def _nmap(self, name):
        return normalize(parse_osu_file(FIXTURES / name))

    def test_fixed_time_windows(self):
        nmap = self._nmap("sliders.osu")
        extractor = FeatureExtractor()
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, extractor)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].start_ms, 1000.0)
        self.assertEqual(segments[0].end_ms, 6000.0)
        self.assertEqual(segments[0].start_idx, 0)
        for segment in segments:
            self.assertGreater(segment.end_idx, segment.start_idx)
            self.assertIn("temporal.object_count", segment.features)

    def test_fixed_count_chunks(self):
        nmap = self._nmap("sliders.osu")
        extractor = FeatureExtractor()
        segments = FixedObjectCountStrategy(chunk_size=5).segment(nmap, extractor)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[-1].end_idx, len(nmap.objects))

    def test_aggregation_is_deterministic(self):
        nmap = self._nmap("unusual_sv.osu")
        extractor = FeatureExtractor()
        segments = FixedTimeWindowStrategy(window_ms=3000.0).segment(nmap, extractor)
        first = aggregate_features(segments)
        second = aggregate_features(segments)
        self.assertEqual(first, second)
        self.assertEqual(first["segment_count"], len(segments))
        self.assertIn("temporal.object_count_mean", first)

    def test_fixed_time_single_window_on_short_map(self):
        nmap = self._nmap("minimal.osu")
        extractor = FeatureExtractor()
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, extractor)
        self.assertEqual(len(segments), 1)

    def test_aggregation_survives_huge_values(self):
        huge = 1e200
        segments = [
            Segment(0, 1000, 0, 2, {"m": huge}),
            Segment(1000, 2000, 2, 4, {"m": huge + 1.0}),
        ]
        aggregated = aggregate_features(segments)
        self.assertTrue(aggregated["m_std"] >= 0)
        self.assertTrue(aggregated["m_std"] < 1.0)

    def test_fixed_time_survives_absurd_timestamps(self):
        text = (
            "osu file format v14\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "192,192,1e12,1,0\n"
        )
        nmap = normalize(parse_osu(text))
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, FeatureExtractor())
        self.assertLessEqual(len(segments), 2)

    def test_fixed_time_partitions_out_of_order_times(self):
        text = (
            "osu file format v14\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "192,192,50000,1,0\n"
            "128,128,2000,1,0\n"
            "256,256,3000,1,0\n"
        )
        nmap = normalize(parse_osu(text))
        segments = FixedTimeWindowStrategy(window_ms=5000.0).segment(nmap, FeatureExtractor())
        spans = [seg.end_idx - seg.start_idx for seg in segments]
        self.assertEqual(sum(spans), len(nmap.objects))
        self.assertTrue(all(span > 0 for span in spans))
        prev_end = None
        for seg in segments:
            if prev_end is not None:
                self.assertGreaterEqual(seg.start_idx, prev_end)
            prev_end = seg.end_idx


if __name__ == "__main__":
    unittest.main()
