from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import flow_cs_experiment_v01 as experiment  # noqa: E402
from map_demand_v01 import release  # noqa: E402


class FlowCsExperimentTests(unittest.TestCase):
    def test_cs4_is_exactly_neutral(self):
        for value in (0.0, 2.0, 4.0, 6.6, 10.0):
            with self.subTest(value=value):
                adjusted = experiment.adjust_flow_value(value, 4.0)
                self.assertAlmostEqual(adjusted["adjusted_value"], value)
                self.assertAlmostEqual(adjusted["size_load_factor"], 1.0)

    def test_reviewed_cs_is_strictly_monotonic_for_positive_flow(self):
        values = [
            experiment.adjust_flow_value(6.6, cs)["adjusted_value"]
            for cs in range(13)
        ]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_cs6_and_cs10_do_not_saturate_to_the_same_level(self):
        cs6 = experiment.adjust_flow_value(6.6, 6.0)["adjusted_value"]
        cs10 = experiment.adjust_flow_value(6.6, 10.0)["adjusted_value"]
        self.assertGreater(cs10 - cs6, 1.5)

    def test_common_cs_steps_remain_visible_at_public_precision(self):
        values = [
            experiment.adjust_flow_value(6.6, cs)["adjusted_value"]
            for cs in (4.0, 4.2, 4.5, 5.0)
        ]
        self.assertEqual(len({round(value, 1) for value in values}), 4)

    def test_zero_flow_cannot_be_created_by_circle_size(self):
        for cs in range(13):
            with self.subTest(cs=cs):
                self.assertEqual(
                    experiment.adjust_flow_value(0.0, cs)["adjusted_value"],
                    0.0,
                )

    def test_measure_copy_preserves_support_and_winner_identity(self):
        source = {
            "status": "FULL",
            "value": 6.6,
            "support": 0.4,
            "winning_section": {
                "segment": 2,
                "run": 1,
                "value": 6.6,
                "support": 0.4,
            },
            "signals": {"window_events": 48},
        }
        adjusted = experiment.adjust_flow_measure(source, 8.0)
        self.assertEqual(source["value"], 6.6)
        self.assertGreater(adjusted["value"], source["value"])
        self.assertEqual(adjusted["support"], source["support"])
        self.assertEqual(adjusted["winning_section"]["segment"], 2)
        self.assertEqual(adjusted["winning_section"]["run"], 1)
        self.assertEqual(adjusted["winning_section"]["support"], 0.4)
        self.assertFalse(
            adjusted["signals"]["target_size_hard_saturation"]
        )

    def test_insufficient_measure_stays_insufficient(self):
        source = {
            "status": "INSUFFICIENT",
            "value": None,
            "support": 0.0,
        }
        adjusted = experiment.adjust_flow_measure(source, 10.0)
        self.assertIsNone(adjusted["value"])
        self.assertIsNone(adjusted["experimental_adjustment"])

    def test_experiment_is_not_a_runtime_release(self):
        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertNotIn(
            "v010-beta9.1-flow-cs-exp1", release.RUNTIME_ALGORITHMS
        )

    def test_out_of_scope_cs_is_rejected(self):
        for cs in (-1.0, 12.1, 13.0):
            with self.subTest(cs=cs):
                with self.assertRaises(ValueError):
                    experiment.adjust_flow_value(4.0, cs)


if __name__ == "__main__":
    unittest.main()
