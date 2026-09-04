from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import flow_target_size_v01 as target_size  # noqa: E402
from map_demand_v01 import spatial_axes_v05 as spatial  # noqa: E402


class SpatialAxesV05Tests(unittest.TestCase):
    def test_cs4_is_neutral_and_winner_identity_is_preserved(self):
        source = {
            "status": "FULL",
            "value": 6.6,
            "support": 0.42,
            "scale": "OLD",
            "eligible_count": 48,
            "winning_section": {
                "segment": 3,
                "run": 2,
                "value": 6.6,
                "support": 0.42,
            },
            "signals": {"window_events": 48},
        }
        result = spatial.apply_flow_target_size(source, 4.0)

        self.assertEqual(source["scale"], "OLD")
        self.assertAlmostEqual(result["value"], 6.6)
        self.assertEqual(result["support"], source["support"])
        self.assertEqual(result["winning_section"]["segment"], 3)
        self.assertEqual(result["winning_section"]["run"], 2)
        self.assertEqual(result["winning_section"]["support"], 0.42)
        self.assertEqual(result["scale"], spatial.FLOW_SCALE)
        self.assertNotIn("experimental_algorithm_id", result)
        self.assertNotIn("runtime_release_registered", result["signals"])

    def test_continuous_common_cs_steps_and_unbounded_reviewed_tail(self):
        values = {
            cs: spatial.apply_flow_target_size(
                {"status": "FULL", "value": 6.6}, cs
            )["value"]
            for cs in (4.0, 4.2, 4.5, 5.0, 6.0, 7.0, 10.0)
        }
        ordered = list(values.values())
        self.assertTrue(all(a < b for a, b in zip(ordered, ordered[1:])))
        self.assertEqual(
            len({round(values[cs], 1) for cs in (4.0, 4.2, 4.5, 5.0)}),
            4,
        )
        self.assertGreater(values[10.0] - values[7.0], 2.0)

    def test_zero_flow_is_not_created(self):
        for cs in range(13):
            with self.subTest(cs=cs):
                result = spatial.apply_flow_target_size(
                    {"status": "FULL", "value": 0.0}, cs
                )
                self.assertEqual(result["value"], 0.0)

    def test_out_of_review_range_abstains_only_flow(self):
        result = spatial.apply_flow_target_size(
            {
                "status": "FULL",
                "value": 6.6,
                "eligible_count": 48,
                "winning_section": {"value": 6.6},
            },
            12.1,
        )
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIsNone(result["value"])
        self.assertIsNone(result["winning_section"])
        self.assertIn(
            "effective_circle_size", result["missing_required_fields"]
        )

    def test_formula_is_shared_with_reviewed_experiment(self):
        result = spatial.apply_flow_target_size(
            {"status": "FULL", "value": 6.6}, 8.0
        )
        expected = target_size.adjust_flow_value(6.6, 8.0)
        self.assertAlmostEqual(result["value"], expected["adjusted_value"])
        self.assertEqual(
            result["signals"]["target_size_adjustment"], expected
        )


if __name__ == "__main__":
    unittest.main()
