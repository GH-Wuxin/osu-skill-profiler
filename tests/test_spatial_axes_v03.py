from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import paired_transition_geometry_v01 as paired
from map_demand_v01 import spatial_axes_v02 as beta7_spatial
from map_demand_v01 import spatial_axes_v03 as beta8_spatial


RADIUS = beta8_spatial.REFERENCE_RADIUS_PX


def rows_from_steps(
    steps: list[tuple[float, float, float]],
    *,
    radius: float = RADIUS,
    minimum_distances: list[float | None] | None = None,
) -> list[dict]:
    """Return one initial circle followed by the supplied transitions."""
    scale = 50.0 / radius
    result: list[dict] = []
    time = 0.0
    x = 256.0
    direction = 1.0
    for index in range(len(steps) + 1):
        if index == 0:
            distance = None
            interval = None
            angle = None
            minimum = None
        else:
            distance, interval, angle = steps[index - 1]
            time += interval
            direction *= -1.0
            x += direction * min(distance, 500.0)
            minimum = (
                distance
                if minimum_distances is None
                else minimum_distances[index - 1]
            )
        result.append(
            {
                "ls.original_index": index,
                "ls.object_type": "circle",
                "ls.start_time_ms": time,
                "ls.end_time_ms": time,
                "ls.preempt_ms": 750.0,
                "ls.radius_px": radius,
                "ls.cs_scale": scale,
                "ls.adjusted_delta_time_ms": interval,
                "ls.minimum_jump_time_ms": interval,
                "ls.jump_distance_raw_px": distance,
                "ls.minimum_jump_distance_cs_normalised": (
                    None if minimum is None else minimum * scale
                ),
                "ls.lazy_jump_distance_cs_normalised": (
                    None if distance is None else distance * scale
                ),
                "ls.lazy_travel_distance_cs_normalised": 0.0,
                "ls.lazy_travel_time_ms": 0.0,
                "ls.slider_aware_angle_rad": None if index < 2 else angle,
                "v091.start_x_px": x,
                "v091.start_y_px": 192.0,
            }
        )
    return result


def regular_rows(
    transitions: int,
    *,
    distance: float = 300.0,
    interval: float = 100.0,
    angle: float = 0.0,
) -> list[dict]:
    return rows_from_steps([(distance, interval, angle)] * transitions)


def jump(rows: list[dict]) -> dict:
    return beta8_spatial.extract_spatial_measures(rows)["jump_aim"]


class JumpEnvelopeTests(unittest.TestCase):
    def test_no_spatial_opportunity_is_insufficient_not_observed_zero(self):
        result = jump(regular_rows(0))

        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIsNone(result["value"])
        self.assertIsNone(result["physical_peak"])
        self.assertIsNone(result["establishment"]["frontier_star"])

    def test_midscale_large_jump_is_materially_lower_than_beta7(self):
        rows = regular_rows(8, distance=300.0, interval=100.0)
        before = beta7_spatial.extract_spatial_measures(rows)["jump_aim"]
        after = jump(rows)

        self.assertEqual(after["status"], "FULL")
        self.assertLess(after["value"], before["value"] * 0.85)
        self.assertGreater(after["physical_peak"], after["value"])
        self.assertEqual(
            after["signals"]["public_value_semantics"],
            "SELECTED_SUPPORT_FRONTIER_STAR",
        )

    def test_slow_fillers_cannot_change_a_hard_jump_frontier(self):
        hard = [(300.0, 100.0, 0.0)] * 8
        baseline = jump(rows_from_steps(hard))
        filled = jump(
            rows_from_steps(hard + [(5.0, 300.0, 0.0)] * 1000)
        )

        self.assertAlmostEqual(
            filled["physical_peak"],
            baseline["physical_peak"],
            places=12,
        )
        self.assertAlmostEqual(filled["value"], baseline["value"], places=10)
        self.assertAlmostEqual(
            filled["establishment"]["frontier_star"],
            baseline["establishment"]["frontier_star"],
            places=10,
        )

    def test_sixteen_transitions_add_establishment_and_sustain_beyond_eight(self):
        eight = jump(regular_rows(8, distance=360.0, interval=80.0))
        sixteen = jump(regular_rows(16, distance=360.0, interval=80.0))

        self.assertAlmostEqual(
            sixteen["physical_peak"],
            eight["physical_peak"],
            places=12,
        )
        self.assertGreater(sixteen["value"], eight["value"])
        self.assertGreater(
            sixteen["establishment"]["support"],
            eight["establishment"]["support"],
        )
        self.assertGreater(
            sixteen["sustain"]["support"],
            eight["sustain"]["support"],
        )
        self.assertIsNone(eight["signals"]["fixed_max_window_events"])
        self.assertEqual(eight["eligible_count"], 8)
        self.assertEqual(sixteen["eligible_count"], 16)

    def test_independent_repeat_can_publish_recurrence_without_faking_sustain(self):
        hard = [(340.0, 90.0, 0.0)] * 8
        one = jump(rows_from_steps(hard))
        repeated = jump(
            rows_from_steps(hard + [(0.0, 11000.0, 0.0)] + hard)
        )

        self.assertAlmostEqual(
            repeated["physical_peak"],
            one["physical_peak"],
            places=12,
        )
        self.assertGreater(repeated["value"], one["value"])
        self.assertGreater(
            repeated["recurrence"]["support"], one["recurrence"]["support"]
        )
        self.assertEqual(
            repeated["public_frontier"]["selected_component"],
            "recurrence",
        )
        self.assertAlmostEqual(
            repeated["sustain"]["frontier_star"],
            one["sustain"]["frontier_star"],
            places=10,
        )
        self.assertGreaterEqual(
            repeated["recurrence"].get("episode_count", 0), 2
        )

    def test_confidence_changes_do_not_attenuate_physical_or_public_value(self):
        full = jump(regular_rows(8, distance=320.0, interval=90.0))
        degraded_rows = regular_rows(10, distance=320.0, interval=90.0)
        for row in degraded_rows[-2:]:
            row["ls.minimum_jump_distance_cs_normalised"] = None
            row["ls.jump_distance_raw_px"] = None
        degraded = jump(degraded_rows)

        self.assertEqual(full["status"], "FULL")
        self.assertEqual(degraded["status"], "DEGRADED")
        self.assertLess(
            degraded["evidence_confidence"],
            full["evidence_confidence"],
        )
        self.assertAlmostEqual(
            degraded["physical_peak"],
            full["physical_peak"],
            places=12,
        )
        self.assertAlmostEqual(degraded["value"], full["value"], places=10)

    def test_extreme_physical_peak_is_unbounded_and_remains_visible(self):
        extreme = jump(regular_rows(8, distance=500.0, interval=50.0))
        faster = jump(regular_rows(8, distance=500.0, interval=40.0))

        self.assertGreater(extreme["physical_peak"], 10.0)
        self.assertGreater(faster["physical_peak"], 10.0)
        self.assertGreater(
            faster["physical_peak"],
            extreme["physical_peak"],
        )
        self.assertGreater(faster["value"], extreme["value"])

    def test_jump_keeps_minimum_minimum_slider_aware_phase_pairing(self):
        rows = rows_from_steps(
            [(400.0, 200.0, 0.0)] * 8,
            minimum_distances=[80.0] * 8,
        )
        for row in rows[1:]:
            row["ls.minimum_jump_time_ms"] = 50.0
        result = jump(rows)
        expected_load = math.sqrt(
            80.0 / (4.0 * beta8_spatial.REFERENCE_RADIUS_PX)
        ) * ((80.0 / 50.0) / 1.15)

        self.assertAlmostEqual(
            result["physical_peak_details"]["raw_load"], expected_load, places=12
        )
        self.assertEqual(
            result["winning_section"]["channel"], paired.MINIMUM_MINIMUM
        )

    def test_concurrent_active_sliders_are_not_scored_as_single_cursor_jump(self):
        rows = regular_rows(20, distance=360.0, interval=50.0)
        for row in rows:
            row["ls.object_type"] = "slider"
            row["ls.end_time_ms"] = row["ls.start_time_ms"] + 5000.0

        result = jump(rows)
        alternative = result["signals"]["alternative_mechanism"]
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertEqual(
            result["reason"],
            "CONCURRENT_ACTIVE_SLIDER_ALTERNATIVE_MECHANISM",
        )
        self.assertGreater(alternative["excluded_transition_count"], 0)
        self.assertGreater(alternative["max_concurrent_active_sliders"], 2)
        self.assertEqual(
            alternative["routing"], "EXCLUDED_FROM_SINGLE_CURSOR_JUMP"
        )

    def test_non_overlapping_slider_timing_remains_eligible(self):
        rows = regular_rows(20, distance=360.0, interval=80.0)
        for row in rows:
            row["ls.object_type"] = "slider"
            row["ls.end_time_ms"] = row["ls.start_time_ms"] + 80.0

        result = jump(rows)
        alternative = result["signals"]["alternative_mechanism"]
        self.assertEqual(result["status"], "FULL")
        self.assertEqual(alternative["excluded_transition_count"], 0)
        self.assertEqual(alternative["max_concurrent_active_sliders"], 1)

    def test_material_alternative_mechanism_forces_map_level_abstention(self):
        abstain, share = beta8_spatial._alternative_mechanism_abstention(
            excluded_transition_count=15,
            candidate_transition_count=100,
            max_concurrent_active_sliders=2,
        )
        clustered, clustered_share = (
            beta8_spatial._alternative_mechanism_abstention(
                excluded_transition_count=5,
                candidate_transition_count=100,
                max_concurrent_active_sliders=8,
            )
        )

        self.assertTrue(abstain)
        self.assertEqual(share, 0.15)
        self.assertTrue(clustered)
        self.assertEqual(clustered_share, 0.05)

    def test_implausible_phase_distance_is_excluded_not_star_capped(self):
        minimum = [120.0] * 20
        minimum[9] = 10000.0
        result = jump(
            rows_from_steps(
                [(120.0, 100.0, 0.0)] * 20,
                minimum_distances=minimum,
            )
        )
        alternative = result["signals"]["alternative_mechanism"]

        self.assertEqual(result["status"], "FULL")
        self.assertEqual(
            alternative["invalid_single_cursor_geometry_count"], 1
        )
        self.assertGreater(alternative["max_invalid_geometry_distance_px"], 4096.0)
        self.assertLess(result["physical_peak"], 100.0)


class PrecisionCorrectionTests(unittest.TestCase):
    def test_same_position_repeat_is_not_a_micro_correction(self):
        minimum = [300.0, 0.0] * 8
        rows = rows_from_steps(
            [(300.0, 100.0, 0.0)] * len(minimum),
            minimum_distances=minimum,
        )
        before = beta7_spatial.extract_spatial_measures(rows)[
            "spatial_precision"
        ]
        after = beta8_spatial.extract_spatial_measures(rows)[
            "spatial_precision"
        ]

        self.assertGreater(before["value"], 3.0)
        self.assertEqual(after["value"], 0.0)
        self.assertGreater(after["signals"]["same_position_repeat_count"], 0)
        self.assertFalse(
            after["signals"]["same_position_repeat_is_micro_correction"]
        )

    def test_small_nonzero_landing_retains_micro_correction_evidence(self):
        minimum = [300.0, 12.0] * 8
        rows = rows_from_steps(
            [(300.0, 100.0, 0.0)] * len(minimum),
            minimum_distances=minimum,
        )
        result = beta8_spatial.extract_spatial_measures(rows)[
            "spatial_precision"
        ]

        self.assertGreater(result["value"], 0.0)
        self.assertGreater(
            result["winning_section"]["mean_micro_correction"], 0.0
        )


class DelegationTests(unittest.TestCase):
    def test_flow_and_control_are_exactly_delegated_to_v02(self):
        rows = regular_rows(24, distance=180.0, interval=140.0, angle=math.pi)
        before = beta7_spatial.extract_spatial_measures(rows, effective_mods=("HD",))
        after = beta8_spatial.extract_spatial_measures(rows, effective_mods=("HD",))

        self.assertEqual(beta8_spatial.SCHEMA_VERSION, "spatial_axes_v0.4.0")
        for axis in ("flow_aim", "aim_control"):
            self.assertEqual(after[axis], before[axis])
        self.assertEqual(
            after["spatial_precision"]["scale"],
            beta8_spatial.PRECISION_SCALE,
        )
        self.assertEqual(after["geometry"], before["geometry"])


if __name__ == "__main__":
    unittest.main()
