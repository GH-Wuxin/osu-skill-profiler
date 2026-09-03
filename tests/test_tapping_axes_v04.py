from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import tapping_axes_v03 as beta8_tapping  # noqa: E402
from map_demand_v01 import tapping_axes_v04 as beta9_tapping  # noqa: E402
from tests.test_tapping_axes_v03 import rows_for  # noqa: E402


def raw(module, intervals: list[float]) -> dict:
    return module.extract_tapping_measures(rows_for(intervals))["raw_speed"]


class Beta9RawSpeedTests(unittest.TestCase):
    def test_established_200_bpm_stream_uses_lower_rate_scale(self):
        beta8 = raw(beta8_tapping, [75.0] * 40)
        beta9 = raw(beta9_tapping, [75.0] * 40)

        self.assertAlmostEqual(beta8["value"], 7.681159420289856)
        self.assertAlmostEqual(beta9["value"], 6.410256410256411)
        self.assertEqual(beta9["value"], beta9["physical_peak"])
        self.assertEqual(beta9["establishment"]["support"], 1.0)

    def test_short_fast_burst_is_sublinear_but_peak_remains_visible(self):
        intervals = [1000.0 / 18.0] * 7
        beta8 = raw(beta8_tapping, intervals)
        beta9 = raw(beta9_tapping, intervals)

        self.assertAlmostEqual(
            beta8["establishment"]["support"],
            beta9["establishment"]["support"],
        )
        self.assertLess(beta9["value"], beta8["value"] * 0.75)
        self.assertLess(beta9["value"], beta9["physical_peak"] * 0.50)
        self.assertEqual(
            beta9["signals"]["partial_support_exponent"],
            beta9_tapping.RAW_PARTIAL_SUPPORT_EXPONENT,
        )

    def test_fully_established_legal_extreme_remains_unbounded(self):
        result = raw(beta9_tapping, [25.0] * 80)

        expected = (
            40.0 - beta9_tapping.RAW_RATE_BASELINE_PER_S
        ) / beta9_tapping.RAW_RATE_PER_STAR
        self.assertAlmostEqual(result["physical_peak"], expected)
        self.assertAlmostEqual(result["value"], expected)
        self.assertGreater(result["value"], 10.0)
        self.assertTrue(math.isfinite(result["value"]))

    def test_non_raw_tapping_axes_are_inherited_exactly(self):
        rows = rows_for([62.5] * 96)
        before = beta8_tapping.extract_tapping_measures(rows)
        after = beta9_tapping.extract_tapping_measures(rows)

        for axis in ("stamina", "finger_control", "endurance"):
            left = dict(before[axis])
            right = dict(after[axis])
            left.pop("schema_version", None)
            right.pop("schema_version", None)
            left.pop("implementation_basis_schema_version", None)
            right.pop("implementation_basis_schema_version", None)
            self.assertEqual(right, left)


if __name__ == "__main__":
    unittest.main()
