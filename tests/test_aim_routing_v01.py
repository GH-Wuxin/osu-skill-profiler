from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import aim_routing_v01 as routing


def measure(rows: list[dict]) -> dict:
    return routing.aim_routing_measure(
        rows,
        source_local_signal_version=routing.LOCAL_SIGNAL_VERSION,
    )


def row(
    *,
    kind: str = "circle",
    raw: float = 100.0,
    adjusted: float = 100.0,
    minimum_raw: float | None = 100.0,
    minimum_time: float = 100.0,
    lazy_jump_raw: float | None = None,
    travel_raw: float | None = 0.0,
    travel_time: float | None = 0.0,
    angle: float = math.pi,
    cs_scale: float = routing.REFERENCE_CS_SCALE,
) -> dict:
    lazy_jump_raw = raw if lazy_jump_raw is None else lazy_jump_raw
    return {
        "ls.object_type": kind,
        "ls.cs_scale": cs_scale,
        "ls.adjusted_delta_time_ms": adjusted,
        "ls.minimum_jump_time_ms": minimum_time,
        "ls.jump_distance_raw_px": raw,
        "ls.minimum_jump_distance_cs_normalised": (
            None if minimum_raw is None else minimum_raw * cs_scale
        ),
        "ls.lazy_jump_distance_cs_normalised": (
            None if lazy_jump_raw is None else lazy_jump_raw * cs_scale
        ),
        "ls.lazy_travel_distance_cs_normalised": (
            None if travel_raw is None else travel_raw * cs_scale
        ),
        "ls.lazy_travel_time_ms": travel_time,
        "ls.slider_aware_angle_rad": angle,
    }


class AimRoutingPairingTests(unittest.TestCase):
    def test_primary_is_minimum_distance_over_minimum_time_not_raw_over_minimum(self):
        first = row()
        candidate = row(
            raw=400.0,
            adjusted=200.0,
            minimum_raw=80.0,
            minimum_time=50.0,
            lazy_jump_raw=80.0,
        )
        jump = measure([first, candidate])["jump"]

        self.assertEqual(jump["minimum_minimum_pair_count"], 1)
        self.assertEqual(jump["head_full_fallback_pair_count"], 0)
        self.assertAlmostEqual(jump["distance_raw_p99_px"], 80.0)
        self.assertAlmostEqual(jump["velocity_raw_p99_px_per_ms"], 1.6)
        self.assertNotEqual(jump["velocity_raw_p99_px_per_ms"], 400.0 / 50.0)

        changed_raw = measure(
            [
                first,
                row(
                    raw=800.0,
                    adjusted=200.0,
                    minimum_raw=80.0,
                    minimum_time=50.0,
                    lazy_jump_raw=80.0,
                ),
            ]
        )["jump"]
        self.assertEqual(changed_raw, jump)

    def test_fallback_is_head_distance_over_full_time_and_ignores_minimum_time(self):
        first = row()
        a = measure(
            [first, row(raw=400.0, adjusted=200.0, minimum_raw=None, minimum_time=25.0)]
        )["jump"]
        b = measure(
            [first, row(raw=400.0, adjusted=200.0, minimum_raw=None, minimum_time=5.0)]
        )["jump"]

        self.assertEqual(a["minimum_minimum_pair_count"], 0)
        self.assertEqual(a["head_full_fallback_pair_count"], 1)
        self.assertAlmostEqual(a["velocity_raw_p99_px_per_ms"], 2.0)
        self.assertNotEqual(a["velocity_raw_p99_px_per_ms"], 400.0 / 25.0)
        self.assertEqual(a, b)

    def test_lazy_full_channel_never_uses_minimum_time(self):
        jump = measure(
            [
                row(),
                row(
                    raw=400.0,
                    adjusted=200.0,
                    minimum_raw=80.0,
                    minimum_time=50.0,
                    lazy_jump_raw=250.0,
                ),
            ]
        )["jump"]

        self.assertEqual(jump["lazy_full_pair_count"], 1)
        self.assertAlmostEqual(jump["lazy_full_distance_raw_p99_px"], 250.0)
        self.assertAlmostEqual(
            jump["lazy_full_velocity_raw_p99_px_per_ms"], 250.0 / 200.0
        )
        self.assertNotEqual(
            jump["lazy_full_velocity_raw_p99_px_per_ms"], 250.0 / 50.0
        )

    def test_distance_and_velocity_tails_cannot_borrow_across_transitions(self):
        slow_large = row(
            raw=320.0,
            adjusted=1000.0,
            minimum_raw=320.0,
            minimum_time=1000.0,
            lazy_jump_raw=320.0,
        )
        fast_small = row(
            raw=80.0,
            adjusted=25.0,
            minimum_raw=80.0,
            minimum_time=25.0,
            lazy_jump_raw=80.0,
        )
        slow = measure([row(), slow_large])["jump"]
        fast = measure([row(), fast_small])["jump"]
        combined = measure([row(), slow_large, fast_small])["jump"]

        self.assertEqual(combined["joint_load_p99"], 0.0)
        self.assertGreater(combined["distance_raw_p99_px"], 300.0)
        self.assertGreater(combined["velocity_raw_p99_px_per_ms"], 3.0)
        self.assertLessEqual(
            combined["kinematic_joint_p99"],
            max(slow["kinematic_joint_p99"], fast["kinematic_joint_p99"]),
        )
        self.assertLessEqual(combined["support"], max(slow["support"], fast["support"]))

    def test_missing_jump_pairs_attenuate_support(self):
        hard = row(
            raw=300.0,
            adjusted=100.0,
            minimum_raw=300.0,
            minimum_time=100.0,
            lazy_jump_raw=300.0,
        )
        complete = measure([row(), hard])["jump"]
        invalid = [row() for _ in range(100)]
        for item in invalid:
            item["ls.minimum_jump_distance_cs_normalised"] = None
            item["ls.jump_distance_raw_px"] = None
            item["ls.lazy_jump_distance_cs_normalised"] = None
        partial = measure([row(), *invalid, hard])["jump"]

        self.assertEqual(complete["valid_pair_coverage"], 1.0)
        self.assertLess(partial["valid_pair_coverage"], 0.01)
        self.assertLess(partial["support"], complete["support"])

    def test_corrected_circle_pairs_retain_spatial_jump_evidence(self):
        distance = 4.0 * routing.REFERENCE_RADIUS_PX
        circles = [
            row(raw=distance, minimum_raw=distance, minimum_time=200.0)
            for _ in range(8)
        ]
        sliders = [
            row(
                kind="slider",
                raw=distance,
                minimum_raw=distance,
                minimum_time=200.0,
            )
            for _ in range(8)
        ]
        circle_jump = measure(circles)["jump"]
        slider_jump = measure(sliders)["jump"]

        self.assertEqual(circle_jump["circle_pair_count"], 7)
        self.assertEqual(circle_jump["circle_large_pair_count"], 7)
        self.assertEqual(circle_jump["circle_large_pair_share"], 1.0)
        self.assertEqual(slider_jump["circle_pair_count"], 0)
        self.assertGreater(circle_jump["support"], slider_jump["support"])

    def test_slow_circle_spacing_is_not_large_jump_presence(self):
        distance = 4.0 * routing.REFERENCE_RADIUS_PX
        jump = measure(
            [
                row(raw=distance, minimum_raw=distance, minimum_time=400.0)
                for _ in range(8)
            ]
        )["jump"]

        self.assertEqual(jump["circle_pair_count"], 7)
        self.assertEqual(jump["circle_large_pair_count"], 0)
        self.assertEqual(jump["circle_large_presence"], 0.0)

    def test_sparse_circle_events_cannot_prove_map_level_jump(self):
        easy_sliders = [
            row(
                kind="slider",
                raw=20.0,
                minimum_raw=20.0,
                minimum_time=200.0,
                lazy_jump_raw=20.0,
            )
            for _ in range(1002)
        ]
        large = 4.0 * routing.REFERENCE_RADIUS_PX

        def with_large_circle_pairs(count: int) -> dict:
            circles = [
                row(
                    kind="circle",
                    raw=20.0,
                    minimum_raw=20.0,
                    minimum_time=200.0,
                    lazy_jump_raw=20.0,
                )
            ]
            circles.extend(
                row(
                    kind="circle",
                    raw=large,
                    minimum_raw=large,
                    minimum_time=200.0,
                    lazy_jump_raw=large,
                )
                for _ in range(count)
            )
            return measure([*easy_sliders, *circles])["jump"]

        singleton = with_large_circle_pairs(1)
        pair = with_large_circle_pairs(2)
        self.assertEqual(singleton["circle_large_pair_share"], 1.0)
        self.assertLess(singleton["circle_large_valid_pair_share"], 0.002)
        self.assertEqual(singleton["circle_large_presence"], 0.0)
        self.assertLess(singleton["support"], 0.10)
        self.assertLess(pair["circle_large_presence"], 0.30)
        self.assertLess(pair["support"], 0.30)

    def test_six_of_eight_large_circle_pairs_are_strong_local_jump_evidence(self):
        large = 4.0 * routing.REFERENCE_RADIUS_PX
        rows = [row(kind="circle")]
        rows.extend(row(kind="circle", raw=20.0, minimum_raw=20.0) for _ in range(2))
        rows.extend(
            row(kind="circle", raw=large, minimum_raw=large, minimum_time=200.0)
            for _ in range(6)
        )
        jump = measure(rows)["jump"]

        self.assertEqual(jump["valid_pair_count"], 8)
        self.assertEqual(jump["circle_large_pair_count"], 6)
        self.assertEqual(jump["circle_large_local_window_size"], 8)
        self.assertEqual(jump["circle_large_local_window_count"], 6)
        self.assertEqual(jump["circle_large_local_window_share"], 0.75)
        self.assertEqual(jump["longest_circle_large_chain_pairs"], 6)
        self.assertEqual(jump["circle_large_presence"], 0.80)

    def test_short_local_jump_section_survives_a_long_easy_map(self):
        large = 4.0 * routing.REFERENCE_RADIUS_PX
        rows = [
            row(kind="slider", raw=20.0, minimum_raw=20.0, minimum_time=200.0)
            for _ in range(1002)
        ]
        rows.append(row(kind="circle", raw=20.0, minimum_raw=20.0))
        rows.extend(
            row(kind="circle", raw=large, minimum_raw=large, minimum_time=200.0)
            for _ in range(6)
        )
        jump = measure(rows)["jump"]

        self.assertLess(jump["circle_large_valid_pair_share"], 0.01)
        self.assertEqual(jump["circle_large_local_window_count"], 6)
        self.assertEqual(jump["longest_circle_large_chain_pairs"], 6)
        self.assertEqual(jump["circle_large_presence"], 0.80)
        self.assertGreaterEqual(jump["support"], 0.80)

    def test_circle_evidence_is_continuous_at_time_boundary(self):
        distance = 4.0 * routing.REFERENCE_RADIUS_PX

        def circle_chain(delta: float) -> dict:
            return measure(
                [
                    row(
                        raw=distance,
                        minimum_raw=distance,
                        minimum_time=delta,
                    )
                    for _ in range(8)
                ]
            )["jump"]

        at_boundary = circle_chain(250.0)
        just_after = circle_chain(250.001)

        self.assertEqual(at_boundary["circle_large_pair_count"], 7)
        self.assertEqual(just_after["circle_large_pair_count"], 0)
        self.assertLess(
            abs(at_boundary["support"] - just_after["support"]),
            1e-3,
        )

    def test_circle_evidence_is_continuous_at_distance_boundary(self):
        radius = routing.REFERENCE_RADIUS_PX

        def circle_chain(distance: float) -> dict:
            return measure(
                [
                    row(
                        raw=distance,
                        minimum_raw=distance,
                        minimum_time=200.0,
                    )
                    for _ in range(8)
                ]
            )["jump"]

        at_boundary = circle_chain(3.75 * radius)
        just_below = circle_chain((3.75 - 1e-6) * radius)

        self.assertEqual(at_boundary["circle_large_pair_count"], 7)
        self.assertEqual(just_below["circle_large_pair_count"], 0)
        self.assertLess(
            abs(at_boundary["support"] - just_below["support"]),
            1e-3,
        )

    def test_high_load_persistence_is_continuous_at_time_boundary(self):
        def high_chain(delta: float) -> dict:
            return measure(
                [
                    row(
                        raw=350.0,
                        adjusted=delta,
                        minimum_raw=350.0,
                        minimum_time=delta,
                        lazy_jump_raw=350.0,
                    )
                    for _ in range(32)
                ]
            )["jump"]

        at_boundary = high_chain(250.0)
        just_after = high_chain(250.001)

        self.assertEqual(at_boundary["high_pair_count"], 31)
        self.assertEqual(just_after["high_pair_count"], 0)
        self.assertLess(
            abs(at_boundary["support"] - just_after["support"]),
            1e-3,
        )


class AimRoutingFlowTests(unittest.TestCase):
    def test_slider_travel_increases_flow_without_changing_jump(self):
        without_travel = [row()]
        without_travel.extend(
            row(
                kind="slider",
                raw=70.0,
                adjusted=200.0,
                minimum_raw=70.0,
                minimum_time=200.0,
                lazy_jump_raw=70.0,
                travel_raw=0.0,
                travel_time=100.0,
            )
            for _ in range(5)
        )
        with_travel = copy.deepcopy(without_travel)
        for item in with_travel[1:]:
            item["ls.lazy_travel_distance_cs_normalised"] = (
                160.0 * routing.REFERENCE_CS_SCALE
            )
        before = measure(without_travel)
        after = measure(with_travel)

        self.assertEqual(after["jump"], before["jump"])
        self.assertEqual(after["flow"]["slider_travel_valid_count"], 5)
        self.assertGreater(
            after["flow"]["slider_travel_velocity_raw_p90_px_per_ms"],
            before["flow"]["slider_travel_velocity_raw_p90_px_per_ms"],
        )
        self.assertGreater(after["flow"]["support"], before["flow"]["support"])

    def test_slider_travel_without_directional_chain_cannot_create_flow(self):
        flow = measure(
            [
                row(),
                row(
                    kind="slider",
                    raw=70.0,
                    minimum_raw=70.0,
                    lazy_jump_raw=70.0,
                    travel_raw=220.0,
                    travel_time=80.0,
                ),
            ]
        )["flow"]

        self.assertEqual(flow["coherence_gate"], 0.0)
        self.assertEqual(flow["slider_peak"], 0.0)
        self.assertEqual(flow["support"], 0.0)

    def test_unrelated_fast_slider_cannot_borrow_a_chain_elsewhere(self):
        chain = [row(raw=90.0, adjusted=180.0) for _ in range(5)]
        baseline = measure(chain)["flow"]
        separated = [
            *chain,
            row(kind="spinner"),
            row(
                kind="slider",
                raw=20.0,
                minimum_raw=20.0,
                travel_raw=300.0,
                travel_time=50.0,
            ),
        ]
        with_unrelated_slider = measure(separated)["flow"]

        self.assertGreater(
            with_unrelated_slider["slider_peak"], baseline["slider_peak"]
        )
        self.assertAlmostEqual(with_unrelated_slider["support"], baseline["support"])

    def test_broad_chain_has_no_six_radius_upper_cutoff(self):
        distance = 7.0 * routing.REFERENCE_RADIUS_PX
        rows = [row(raw=distance) for _ in range(8)]
        flow = measure(rows)["flow"]

        self.assertEqual(flow["broad_pair_count"], 6)
        self.assertEqual(flow["broad_longest_chain_notes"], 8)
        self.assertGreater(flow["broad_full_path_ref_radii_p90"], 6.0)

    def test_hr_changes_physical_flow_only_through_mild_size_load(self):
        physical_distance = 2.0 * routing.REFERENCE_RADIUS_PX
        nm_scale = routing.REFERENCE_CS_SCALE
        hr_scale = nm_scale * 1.30
        nm_rows = [
            row(raw=physical_distance, minimum_raw=physical_distance, cs_scale=nm_scale)
            for _ in range(10)
        ]
        hr_rows = [
            row(raw=physical_distance, minimum_raw=physical_distance, cs_scale=hr_scale)
            for _ in range(10)
        ]
        nm = measure(nm_rows)["flow"]
        hr = measure(hr_rows)["flow"]

        invariant = {
            "transition_candidate_count",
            "full_path_pair_count",
            "full_path_pair_coverage",
            "morphology_opportunity_count",
            "directional_pair_count",
            "directional_pair_coverage",
            "full_path_distance_raw_p95_px",
            "full_path_distance_raw_p99_px",
            "full_path_velocity_raw_p95_px_per_ms",
            "full_path_velocity_raw_p99_px_per_ms",
            "strict_pair_count",
            "strict_pair_coverage",
            "strict_chain_length_p90_notes",
            "strict_smoothness_mean",
            "broad_pair_count",
            "broad_pair_coverage",
            "broad_longest_chain_notes",
            "broad_rate_p90_per_s",
            "broad_full_path_ref_radii_p90",
            "morphology_pair_count",
            "morphology_full_path_ref_radii_p90",
            "head_dominance_weight_sum",
            "wide_head_dominance_weight_sum",
            "wide_head_dominance_share",
        }
        for key in invariant:
            self.assertEqual(hr[key], nm[key], key)
        self.assertGreater(hr["size_factor_p50"], nm["size_factor_p50"])
        self.assertGreater(
            hr["strict_velocity_load_p90_px_per_ms"],
            nm["strict_velocity_load_p90_px_per_ms"],
        )
        self.assertGreaterEqual(hr["support"], nm["support"])

    def test_only_head_dominated_paths_contribute_wide_jump_shape(self):
        distance = 5.0 * routing.REFERENCE_RADIUS_PX
        rows = [
            row(kind="circle", raw=distance),
            row(kind="slider", raw=distance, travel_raw=distance, travel_time=100.0),
            row(kind="circle", raw=distance),
            row(kind="circle", raw=distance),
        ]
        flow = measure(rows)["flow"]

        self.assertEqual(flow["broad_pair_count"], 2)
        self.assertEqual(flow["head_dominance_weight_sum"], 1.5)
        self.assertEqual(flow["wide_head_dominance_weight_sum"], 1.5)
        self.assertAlmostEqual(
            flow["wide_head_dominance_share"], 1.5 / 2.0
        )

        sliders_only = [
            row(kind="slider", raw=distance, travel_raw=distance, travel_time=100.0)
            for _ in range(4)
        ]
        slider_flow = measure(sliders_only)["flow"]
        self.assertAlmostEqual(slider_flow["head_dominance_weight_sum"], 1.0)
        self.assertAlmostEqual(
            slider_flow["wide_head_dominance_weight_sum"], 1.0
        )
        self.assertAlmostEqual(slider_flow["wide_head_dominance_share"], 0.5)

        zero_travel_sliders = [
            row(kind="slider", raw=distance, travel_raw=0.0, travel_time=100.0)
            for _ in range(4)
        ]
        zero_travel_flow = measure(zero_travel_sliders)["flow"]
        self.assertEqual(zero_travel_flow["head_dominance_weight_sum"], 2.0)
        self.assertEqual(zero_travel_flow["wide_head_dominance_weight_sum"], 2.0)
        self.assertEqual(
            zero_travel_flow["wide_head_dominance_share"], 1.0
        )

        epsilon_travel_sliders = copy.deepcopy(zero_travel_sliders)
        for item in epsilon_travel_sliders:
            item["ls.lazy_travel_distance_cs_normalised"] = 1e-9
        epsilon_flow = measure(epsilon_travel_sliders)["flow"]
        self.assertAlmostEqual(
            epsilon_flow["wide_head_dominance_share"],
            zero_travel_flow["wide_head_dominance_share"],
        )
        self.assertAlmostEqual(epsilon_flow["support"], zero_travel_flow["support"])

    def test_wide_head_dominated_jump_chain_does_not_saturate_flow(self):
        rows = [
            row(raw=300.0, adjusted=200.0, minimum_raw=300.0)
            for _ in range(20)
        ]
        flow = measure(rows)["flow"]

        self.assertEqual(flow["wide_head_dominance_share"], 1.0)
        self.assertLess(flow["support"], 0.70)

    def test_wide_jump_countershape_survives_broad_time_boundary(self):
        at_boundary = measure(
            [row(raw=300.0, adjusted=220.0, minimum_raw=300.0) for _ in range(20)]
        )["flow"]
        just_after = measure(
            [
                row(raw=300.0, adjusted=220.001, minimum_raw=300.0)
                for _ in range(20)
            ]
        )["flow"]

        self.assertEqual(at_boundary["wide_head_dominance_share"], 1.0)
        self.assertEqual(just_after["wide_head_dominance_share"], 1.0)
        self.assertLess(at_boundary["support"], 0.70)
        self.assertLess(just_after["support"], 0.70)
        self.assertLess(abs(at_boundary["support"] - just_after["support"]), 0.05)

    def test_flow_support_is_continuous_at_time_window_boundaries(self):
        def chain(*, angle: float, delta: float) -> dict:
            return measure(
                [
                    row(
                        raw=90.0,
                        adjusted=delta,
                        minimum_raw=90.0,
                        minimum_time=delta,
                        angle=angle,
                    )
                    for _ in range(20)
                ]
            )["flow"]

        broad_at = chain(angle=2.0, delta=220.0)
        broad_after = chain(angle=2.0, delta=220.001)
        strict_at = chain(angle=math.pi, delta=300.0)
        strict_after = chain(angle=math.pi, delta=300.001)

        self.assertLess(abs(broad_at["support"] - broad_after["support"]), 1e-3)
        self.assertLess(abs(strict_at["support"] - strict_after["support"]), 1e-3)

    def test_small_slow_chain_length_alone_does_not_saturate_flow(self):
        rows = [
            row(
                raw=21.0,
                adjusted=220.0,
                minimum_raw=21.0,
                minimum_time=220.0,
            )
            for _ in range(14)
        ]
        flow = measure(rows)["flow"]

        self.assertEqual(flow["broad_longest_chain_notes"], 14)
        self.assertLess(flow["support"], 0.25)

    def test_missing_full_paths_attenuate_flow_support(self):
        complete = [row(raw=90.0, adjusted=180.0) for _ in range(5)]
        partial = copy.deepcopy(complete)
        partial.extend(row(raw=90.0, adjusted=180.0) for _ in range(15))
        for item in partial[5:]:
            item["ls.lazy_jump_distance_cs_normalised"] = None

        complete_flow = measure(complete)["flow"]
        partial_flow = measure(partial)["flow"]

        self.assertEqual(complete_flow["full_path_pair_coverage"], 1.0)
        self.assertLess(partial_flow["full_path_pair_coverage"], 0.25)
        self.assertLess(partial_flow["support"], complete_flow["support"])

    def test_missing_directional_geometry_attenuates_flow_support(self):
        complete = [row(raw=90.0, adjusted=180.0) for _ in range(10)]
        partial = copy.deepcopy(complete)
        for item in partial[5:]:
            item["ls.slider_aware_angle_rad"] = None

        complete_flow = measure(complete)["flow"]
        partial_flow = measure(partial)["flow"]

        self.assertEqual(complete_flow["directional_pair_coverage"], 1.0)
        self.assertLess(partial_flow["directional_pair_coverage"], 0.50)
        self.assertLess(partial_flow["support"], complete_flow["support"])

    def test_sections_cannot_borrow_length_and_rate(self):
        slow_long = [
            row(raw=21.0, adjusted=250.0, angle=2.0)
            for _ in range(30)
        ]
        fast_short_sections: list[dict] = []
        for _ in range(4):
            if fast_short_sections:
                fast_short_sections.append(row(kind="spinner"))
            fast_short_sections.extend(
                row(raw=160.0, adjusted=80.0, angle=2.0)
                for _ in range(3)
            )

        slow = measure(slow_long)["flow"]
        fast = measure(fast_short_sections)["flow"]
        combined = measure(
            [*slow_long, row(kind="spinner"), *fast_short_sections]
        )["flow"]

        self.assertGreater(combined["broad_longest_chain_notes"], 15.0)
        self.assertGreater(combined["broad_rate_p90_per_s"], 10.0)
        self.assertLessEqual(
            combined["support"],
            max(slow["support"], fast["support"]),
        )

    def test_partial_broad_chain_does_not_activate_an_unqualified_route(self):
        partial = [
            row(raw=90.0, adjusted=200.0, angle=2.0),
            row(raw=90.0, adjusted=285.33336, angle=2.0),
            row(raw=90.0, adjusted=200.0, angle=2.0),
            row(raw=90.0, adjusted=200.0, angle=2.0),
        ]
        complete = [row(raw=90.0, adjusted=200.0, angle=2.0) for _ in range(4)]

        partial_flow = measure(partial)["flow"]
        complete_flow = measure(complete)["flow"]

        self.assertLess(partial_flow["broad_longest_chain_notes"], 3.5)
        self.assertEqual(partial_flow["broad_joint_peak_raw"], 0.0)
        self.assertEqual(partial_flow["routing_activation"], 0.0)
        self.assertEqual(partial_flow["support"], 0.0)
        self.assertEqual(complete_flow["routing_activation"], 1.0)
        self.assertGreater(complete_flow["support"], 0.0)

    def test_isolated_strict_turn_is_not_a_flow_chain(self):
        isolated = measure(
            [
                row(raw=200.0, adjusted=142.667, angle=0.0),
                row(raw=200.0, adjusted=142.667, angle=0.4206),
                row(raw=200.0, adjusted=286.0, angle=2.5268),
            ]
        )["flow"]

        self.assertEqual(isolated["strict_pair_count"], 1)
        self.assertEqual(isolated["strict_chain_length_p90_notes"], 3.0)
        self.assertEqual(isolated["strict_joint_peak_raw"], 0.0)
        self.assertEqual(isolated["morphology_joint_peak_raw"], 0.0)
        self.assertEqual(isolated["routing_activation"], 0.0)
        self.assertEqual(isolated["support"], 0.0)

    def test_missing_middle_angle_splits_runs_without_crashing(self):
        rows = [row(raw=200.0, adjusted=180.0, angle=math.pi) for _ in range(5)]
        rows[3]["ls.slider_aware_angle_rad"] = None

        flow = measure(rows)["flow"]

        self.assertEqual(flow["full_path_pair_count"], 4)
        self.assertEqual(flow["morphology_opportunity_count"], 3)
        self.assertEqual(flow["directional_pair_count"], 2)
        self.assertEqual(flow["strict_joint_peak_raw"], 0.0)
        self.assertEqual(flow["routing_activation"], 0.0)
        self.assertEqual(flow["support"], 0.0)


class AimRoutingValidationTests(unittest.TestCase):
    def setUp(self):
        self.measure = measure([row(), row()])

    def test_exact_schema_rejects_missing_and_extra_fields(self):
        missing = copy.deepcopy(self.measure)
        missing["jump"].pop("support")
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            routing.validate_measure(missing)

        extra = copy.deepcopy(self.measure)
        extra["flow"]["legacy_velocity"] = 1.0
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            routing.validate_measure(extra)

    def test_nonfinite_and_inconsistent_derived_values_are_rejected(self):
        nonfinite = copy.deepcopy(self.measure)
        nonfinite["flow"]["support"] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            routing.validate_measure(nonfinite)

        inconsistent = copy.deepcopy(self.measure)
        inconsistent["jump"]["support"] = min(
            1.0, inconsistent["jump"]["support"] + 0.1
        )
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            routing.validate_measure(inconsistent)

    def test_measure_and_axis_evidence_do_not_mutate_inputs(self):
        rows = [row(), row()]
        saved_rows = copy.deepcopy(rows)
        measured = measure(rows)
        saved_measure = copy.deepcopy(measured)
        evidence = routing.axis_evidence(measured)

        self.assertEqual(rows, saved_rows)
        self.assertEqual(measured, saved_measure)
        self.assertEqual(evidence["jump_aim"][0], measured["jump"]["support"])
        self.assertEqual(evidence["flow_aim"][1], measured["flow"]["counterevidence"])

    def test_measure_requires_explicit_local04_provenance(self):
        rows = [row(), row()]
        with self.assertRaises(TypeError):
            routing.aim_routing_measure(rows)
        with self.assertRaisesRegex(ValueError, "requires Local Signal 0.4.0"):
            routing.aim_routing_measure(
                rows,
                source_local_signal_version="0.3.0",
            )


if __name__ == "__main__":
    unittest.main()
