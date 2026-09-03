from __future__ import annotations

from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import spatial_axes_v03 as beta8_spatial  # noqa: E402
from map_demand_v01 import spatial_axes_v04 as beta9_spatial  # noqa: E402
from tests.test_spatial_axes_v03 import RADIUS, rows_from_steps  # noqa: E402


def precision(module, rows: list[dict]) -> dict:
    return module.extract_spatial_measures(rows)["spatial_precision"]


class Beta9PrecisionTests(unittest.TestCase):
    def test_only_same_position_repeats_still_measure_zero(self):
        rows = rows_from_steps(
            [(0.0, 100.0, 0.0)] * 16,
            minimum_distances=[0.0] * 16,
        )
        result = precision(beta9_spatial, rows)

        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["winning_section"]["mean_micro_correction"], 0.0)
        self.assertFalse(result["signals"]["same_position_repeat_is_micro_correction"])

    def test_genuine_small_correction_recovers_without_repeat_loophole(self):
        minimum = [300.0, 12.0] * 8
        rows = rows_from_steps(
            [(300.0, 100.0, 0.0)] * len(minimum),
            minimum_distances=minimum,
        )
        before = precision(beta8_spatial, rows)
        after = precision(beta9_spatial, rows)

        self.assertGreater(after["value"], before["value"] * 1.30)
        self.assertGreater(
            after["winning_section"]["mean_micro_displacement_presence"],
            before["winning_section"]["mean_micro_displacement_presence"],
        )

    def test_cs4_target_acquisition_has_bounded_nonzero_precision(self):
        rows = rows_from_steps([(220.0, 100.0, 0.0)] * 16)
        before = precision(beta8_spatial, rows)
        after = precision(beta9_spatial, rows)

        self.assertLess(before["value"], 0.01)
        self.assertGreater(after["value"], 1.0)
        self.assertLess(after["value"], 3.5)
        self.assertLessEqual(
            after["winning_section"]["mean_neutral_target_effort"],
            beta9_spatial.NEUTRAL_TARGET_EFFORT_CAP,
        )

    def test_small_targets_keep_their_high_cs_tail(self):
        rows = rows_from_steps(
            [(220.0, 100.0, 0.0)] * 16,
            radius=RADIUS / 2.0,
        )
        before = precision(beta8_spatial, rows)
        after = precision(beta9_spatial, rows)

        self.assertGreater(after["value"], before["value"])
        self.assertGreater(after["value"], 5.0)
        self.assertEqual(
            after["signals"]["target_tightness_dimensions"],
            2.0,
        )

    def test_small_circle_gain_does_not_raise_cs4_floor(self):
        ordinary = rows_from_steps([(220.0, 100.0, 0.0)] * 16)
        small = rows_from_steps(
            [(220.0, 100.0, 0.0)] * 16,
            radius=RADIUS * 0.80,
        )

        ordinary_result = precision(beta9_spatial, ordinary)
        small_result = precision(beta9_spatial, small)

        self.assertLess(ordinary_result["value"], 3.5)
        self.assertGreater(small_result["value"], ordinary_result["value"] + 2.0)

    def test_other_spatial_axes_are_inherited_exactly(self):
        rows = rows_from_steps([(180.0, 140.0, 3.14159)] * 24)
        before = beta8_spatial.extract_spatial_measures(rows)
        after = beta9_spatial.extract_spatial_measures(rows)

        for axis in ("jump_aim", "flow_aim", "aim_control"):
            self.assertEqual(after[axis], before[axis])


if __name__ == "__main__":
    unittest.main()
