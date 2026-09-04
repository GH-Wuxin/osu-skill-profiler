from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import tapping_axes_v04 as beta9  # noqa: E402
from map_demand_v01 import tapping_axes_v05 as beta91  # noqa: E402
from tests.test_tapping_axes_v03 import rows_for  # noqa: E402


def raw(module, intervals: list[float]) -> dict:
    return module.extract_tapping_measures(rows_for(intervals))["raw_speed"]


class Beta91RawSpeedTests(unittest.TestCase):
    def test_mixed_rates_reselect_powered_establishment_winner(self):
        high_interval = 1000.0 / (5.0 + 15.0 * 1.30)
        lower_interval = 1000.0 / (5.0 + 6.6 * 1.30)
        intervals = [high_interval] * 5 + [lower_interval] * 6

        old = raw(beta9, intervals)
        repaired = raw(beta91, intervals)

        self.assertAlmostEqual(
            old["establishment"]["winning_threshold_star"],
            15.0,
        )
        self.assertAlmostEqual(
            repaired["establishment"]["winning_threshold_star"],
            6.6,
        )
        self.assertAlmostEqual(
            repaired["establishment"]["frontier_star"],
            5.2579688492494645,
        )
        self.assertEqual(
            repaired["public_frontier"]["selected_component"],
            "establishment",
        )
        self.assertAlmostEqual(repaired["value"], 5.2579688492494645)
        self.assertGreater(repaired["value"], old["value"])

    def test_constant_established_stream_preserves_beta9_value(self):
        old = raw(beta9, [75.0] * 40)
        repaired = raw(beta91, [75.0] * 40)

        self.assertEqual(repaired["value"], old["value"])
        self.assertAlmostEqual(repaired["value"], 6.410256410256411)
        self.assertEqual(repaired["physical_peak"], old["physical_peak"])

    def test_short_burst_remains_sublinear(self):
        result = raw(beta91, [1000.0 / 18.0] * 7)

        self.assertLess(result["value"], result["physical_peak"] * 0.50)
        self.assertEqual(
            result["signals"]["partial_support_exponent"],
            beta91.RAW_PARTIAL_SUPPORT_EXPONENT,
        )
        self.assertEqual(
            result["signals"]["frontier_engine"],
            "axis_support_frontier_v02",
        )

    def test_25ms_established_extreme_is_finite_and_not_clipped_at_ten(self):
        result = raw(beta91, [25.0] * 80)
        expected = (
            40.0 - beta91.RAW_RATE_BASELINE_PER_S
        ) / beta91.RAW_RATE_PER_STAR

        self.assertAlmostEqual(result["physical_peak"], expected)
        self.assertAlmostEqual(result["value"], expected)
        self.assertGreater(result["value"], 10.0)
        self.assertTrue(math.isfinite(result["value"]))

    def test_non_raw_tapping_axes_match_beta9_payloads(self):
        rows = rows_for([62.5] * 96)
        old = beta9.extract_tapping_measures(rows)
        repaired = beta91.extract_tapping_measures(rows)

        for axis in ("stamina", "finger_control", "endurance"):
            with self.subTest(axis=axis):
                left = dict(old[axis])
                right = dict(repaired[axis])
                left.pop("schema_version", None)
                right.pop("schema_version", None)
                self.assertEqual(right, left)

    def test_frontier_schema_mismatch_fails_closed(self):
        with mock.patch.object(
            beta91.powered_frontier,
            "evaluate_support_frontier",
            return_value={"schema_version": "wrong"},
        ):
            with self.assertRaisesRegex(ValueError, "schema mismatch"):
                raw(beta91, [75.0] * 40)


if __name__ == "__main__":
    unittest.main()
