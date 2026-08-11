import math
import unittest

from osu_skill_profiler.features.stats import describe
from osu_skill_profiler.segments.aggregator import aggregate_features
from osu_skill_profiler.segments.base import Segment


class StatsTests(unittest.TestCase):
    def test_describe_survives_huge_opposite_sign_values(self):
        result = describe([1e308, -1e308, 1.0, 2.0])
        for value in result.values():
            self.assertIsNotNone(value)
            self.assertTrue(math.isfinite(value))

    def test_aggregate_features_survives_huge_opposite_sign_values(self):
        huge = 1.79769313486231e308
        segments = [
            Segment(0, 1000, 0, 2, {"slider.length_px_min": -huge}),
            Segment(1000, 2000, 2, 4, {"slider.length_px_min": -huge}),
            Segment(2000, 3000, 4, 6, {"slider.length_px_min": 379.0}),
        ]
        aggregated = aggregate_features(segments)
        self.assertTrue(aggregated["slider.length_px_min_mean"] < 0)
        for value in (
            aggregated["slider.length_px_min_mean"],
            aggregated["slider.length_px_min_std"],
            aggregated["slider.length_px_min_max"],
            aggregated["slider.length_px_min_p90"],
        ):
            self.assertTrue(math.isfinite(value))


if __name__ == "__main__":
    unittest.main()
