from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_decoupled_v01 as decoupled  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def blank_components() -> dict:
    return {
        "v092_jump_severity_gate": 0.0,
        "v092_jump_extreme_gate": 0.0,
        "v092_jump_distance_raw_p99_px": 0.0,
        "v092_jump_velocity_raw_p99_px_per_ms": 0.0,
        "v092_jump_persistence_gate": 0.0,
        "v092_jump_tail_activation": 0.0,
        "v095_tapping_large_jump_pair_share": 0.0,
        "v095_control_large_jump_share": 0.0,
        "v091_flow_chain_share": 0.0,
        "v091_flow_chain_length_p90": 0.0,
        "v091_flow_chain_velocity_p90": 0.0,
        "v091_flow_chain_smoothness_mean": 0.0,
        "v095_control_index": 0.0,
        "v096_precision_small_target_gate": 0.0,
        "v096_precision_large_target_relief": 0.0,
        "v095_precision_micro_gate": 0.0,
        "v095_precision_settling_p90": 0.0,
        "v095_tapping_severity_gate": 0.0,
        "v095_tapping_longest_fast_chain_count": 0.0,
        "v095_tapping_longest_fast_chain_duration_ms": 0.0,
        "v095_tapping_fast_compact_pair_count": 0.0,
        "v095_tapping_rate_p90_per_s": 0.0,
        "v091_finger_fast_pair_count": 0.0,
        "v091_finger_nontrivial_change_share": 0.0,
        "v091_finger_novelty_p90": 0.0,
        "v092_pressure_coverage": 0.0,
        "v092_pressure_effective_duration_ms": 0.0,
        "v092_pressure_repeated_section_effective_ms": 0.0,
        "v092_pressure_longest_continuous_effective_ms": 0.0,
        "v092_pressure_recovery_ratio": 0.0,
        "reading_preempt_median_ms": 600.0,
        "v091_visible_overlap_load_p90": 0.0,
        "v091_visible_cluster_load_p90": 1.0,
        "v091_visible_overlap_pair_share": 0.0,
        "v091_visible_stack_object_share": 0.0,
        "reading_density": 0.0,
    }


class MapDemandDecoupledV01Tests(unittest.TestCase):
    def test_independent_sequence_extractor_keeps_spaced_long_chain(self):
        rows = [
            {
                "ls.object_type": "circle",
                "ls.adjusted_delta_time_ms": 80.0,
                "ls.jump_distance_raw_px": 96.0,
                "ls.radius_px": 32.0,
                "ls.slider_aware_angle_rad": math.pi,
            }
            for _ in range(10)
        ]
        components = decoupled._independent_sequence_components(rows)
        self.assertGreaterEqual(
            components["decoupled_tapping_longest_rapid_chain_notes"], 10
        )
        self.assertGreaterEqual(components["decoupled_flow_longest_chain_notes"], 10)
        self.assertGreater(components["decoupled_flow_distance_radii_p90"], 2.9)

    def test_jump_p99_extreme_survives_without_p95_or_persistence(self):
        components = blank_components()
        components["v092_jump_extreme_gate"] = 0.95
        support, counter, _ = decoupled.axis_evidence(components)["jump_aim"]
        self.assertGreaterEqual(support, 0.95)
        self.assertLess(counter, 0.1)

    def test_large_slow_jump_is_still_jump_evidence(self):
        components = blank_components()
        components.update(
            {
                "v092_jump_distance_raw_p99_px": 310.0,
                "v092_jump_velocity_raw_p99_px_per_ms": 0.70,
                "v095_control_large_jump_share": 0.20,
            }
        )
        support, _, signals = decoupled.axis_evidence(components)["jump_aim"]
        self.assertGreater(support, 0.68)
        self.assertGreater(signals["kinematic_peak"], 0.68)

    def test_jump_component_perturbation_changes_only_jump(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "v092_jump_severity_gate": 1.0,
                "v092_jump_tail_activation": 1.0,
                "v095_tapping_large_jump_pair_share": 0.8,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["jump_aim"], before["jump_aim"] + 7.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "jump_aim":
                self.assertEqual(before[axis], after[axis], axis)

    def test_flow_component_perturbation_changes_only_flow(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "v091_flow_chain_share": 0.55,
                "v091_flow_chain_length_p90": 24.0,
                "v091_flow_chain_velocity_p90": 2.2,
                "v091_flow_chain_smoothness_mean": 0.9,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["flow_aim"], before["flow_aim"] + 7.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "flow_aim":
                self.assertEqual(before[axis], after[axis], axis)

    def test_precision_component_perturbation_changes_only_precision(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "v095_precision_micro_gate": 0.82,
                "v095_precision_settling_p90": 0.65,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["spatial_precision"], before["spatial_precision"] + 4.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "spatial_precision":
                self.assertEqual(before[axis], after[axis], axis)

    def test_finger_component_perturbation_changes_only_finger(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "decoupled_finger_change_p90": 1.0,
                "decoupled_finger_change_share": 0.75,
                "decoupled_finger_complexity_p90": 0.55,
                "decoupled_finger_switch_count": 80,
                "decoupled_finger_longest_alternating_chain": 14,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["finger_control"], before["finger_control"] + 4.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "finger_control":
                self.assertEqual(before[axis], after[axis], axis)

    def test_control_component_perturbation_changes_only_control(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "v095_control_index": 0.75,
                "v095_control_shock_p95": 0.62,
                "v095_control_turn_change_p95": 0.85,
                "v095_control_speed_change_p95": 1.30,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["aim_control"], before["aim_control"] + 5.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "aim_control":
                self.assertEqual(before[axis], after[axis], axis)

    def test_short_burst_rate_perturbation_changes_raw_not_stamina(self):
        base = blank_components()
        base.update(
            {
                "decoupled_tapping_longest_rapid_chain_notes": 6.0,
                "decoupled_tapping_rapid_pair_count": 20.0,
                "decoupled_tapping_transition_count": 100.0,
            }
        )
        changed = copy.deepcopy(base)
        base["decoupled_tapping_rapid_rate_p90_per_s"] = 8.0
        changed["decoupled_tapping_rapid_rate_p90_per_s"] = 14.0
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["raw_speed"], before["raw_speed"] + 3.0)
        self.assertEqual(before["stamina"], 0.0)
        self.assertEqual(after["stamina"], 0.0)

    def test_endurance_pressure_perturbation_changes_only_endurance(self):
        base = blank_components()
        changed = copy.deepcopy(base)
        changed.update(
            {
                "v092_pressure_coverage": 0.90,
                "v092_pressure_effective_duration_ms": 240000.0,
                "v092_pressure_repeated_section_effective_ms": 180000.0,
                "v092_pressure_longest_continuous_effective_ms": 45000.0,
                "v092_pressure_p90": 1.10,
            }
        )
        before, _ = decoupled.decoupled_values(base, anchor=8.0)
        after, _ = decoupled.decoupled_values(changed, anchor=8.0)
        self.assertGreater(after["endurance"], before["endurance"] + 5.0)
        for axis in decoupled.AXIS_ORDER:
            if axis != "endurance":
                self.assertEqual(before[axis], after[axis], axis)

    def test_jump_and_flow_counterevidence_is_weak_when_peak_is_real(self):
        for axis in ("jump_aim", "flow_aim"):
            without_counter = decoupled._axis_value(axis, 8.0, 0.85, 0.0)
            with_counter = decoupled._axis_value(axis, 8.0, 0.85, 1.0)
            self.assertGreaterEqual(with_counter, without_counter * 0.98)

    def test_sparse_hard_jump_and_long_flow_chain_keep_high_support(self):
        jump = blank_components()
        jump.update(
            {
                "v092_jump_severity_gate": 1.0,
                "v092_jump_persistence_gate": 0.0,
                "v095_control_large_jump_share": 0.25,
            }
        )
        flow = blank_components()
        flow.update(
            {
                "v091_flow_chain_share": 0.03,
                "v091_flow_chain_length_p90": 30.0,
                "v091_flow_chain_velocity_p90": 2.4,
            }
        )
        self.assertGreater(decoupled.axis_evidence(jump)["jump_aim"][0], 0.95)
        self.assertGreater(decoupled.axis_evidence(flow)["flow_aim"][0], 0.95)

    def test_moderate_velocity_long_chain_is_not_vetoed_from_flow(self):
        flow = blank_components()
        flow.update(
            {
                "v091_flow_chain_share": 0.04,
                "v091_flow_chain_length_p90": 12.0,
                "v091_flow_chain_velocity_p90": 1.0,
                "v091_flow_chain_smoothness_mean": 0.8,
            }
        )
        self.assertGreater(decoupled.axis_evidence(flow)["flow_aim"][0], 0.80)

    def test_raw_speed_uses_actual_rate_not_saturated_legacy_severity(self):
        slower = blank_components()
        slower.update(
            {
                "v095_tapping_severity_gate": 1.0,
                "v095_tapping_rate_p90_per_s": 9.0,
                "v095_tapping_longest_fast_chain_count": 9.0,
                "v095_tapping_fast_compact_pair_count": 200.0,
            }
        )
        faster = copy.deepcopy(slower)
        faster["v095_tapping_rate_p90_per_s"] = 14.0
        slow_support = decoupled.axis_evidence(slower)["raw_speed"][0]
        fast_support = decoupled.axis_evidence(faster)["raw_speed"][0]
        self.assertLess(slow_support, 0.5)
        self.assertGreater(fast_support, slow_support + 0.40)

    def test_regular_large_jump_does_not_create_aim_control(self):
        components = blank_components()
        components.update(
            {
                "v095_control_index": 0.0,
                "v095_control_large_jump_share": 1.0,
                "v092_jump_tail_activation": 1.0,
            }
        )
        values, _ = decoupled.decoupled_values(components, anchor=8.0)
        self.assertGreater(values["jump_aim"], 7.0)
        self.assertLess(values["aim_control"], 0.5)

    def test_large_targets_reduce_precision_without_touching_control(self):
        neutral = blank_components()
        neutral["v095_precision_micro_gate"] = 0.55
        large = copy.deepcopy(neutral)
        large["v096_precision_large_target_relief"] = 1.0
        before, _ = decoupled.decoupled_values(neutral, anchor=8.0)
        after, _ = decoupled.decoupled_values(large, anchor=8.0)
        self.assertLess(after["spatial_precision"], before["spatial_precision"])
        self.assertEqual(after["aim_control"], before["aim_control"])
        self.assertEqual(after["jump_aim"], before["jump_aim"])

    def test_large_targets_reduce_but_do_not_erase_real_micro_precision(self):
        small = blank_components()
        small.update(
            {
                "v095_precision_micro_gate": 0.80,
                "v096_precision_small_target_gate": 0.45,
            }
        )
        large = copy.deepcopy(small)
        large["v096_precision_small_target_gate"] = 0.0
        large["v096_precision_large_target_relief"] = 1.0
        small_value = decoupled.decoupled_values(small, anchor=8.0)[0][
            "spatial_precision"
        ]
        large_value = decoupled.decoupled_values(large, anchor=8.0)[0][
            "spatial_precision"
        ]
        self.assertLess(large_value, small_value)
        self.assertGreater(large_value, 1.5)

    def test_stamina_starts_at_seven_and_does_not_change_raw_speed(self):
        six = blank_components()
        six.update(
            {
                "v095_tapping_rate_p90_per_s": 13.0,
                "v095_tapping_longest_fast_chain_count": 6.0,
                "v095_tapping_longest_fast_chain_duration_ms": 450.0,
                "v095_tapping_severity_gate": 0.9,
                "v095_tapping_fast_compact_pair_count": 6.0,
            }
        )
        seven = copy.deepcopy(six)
        seven["v095_tapping_longest_fast_chain_count"] = 7.0
        six_values, _ = decoupled.decoupled_values(six, anchor=8.0)
        seven_values, _ = decoupled.decoupled_values(seven, anchor=8.0)
        self.assertEqual(six_values["stamina"], 0.0)
        self.assertGreater(seven_values["stamina"], 0.0)
        self.assertEqual(six_values["raw_speed"], seven_values["raw_speed"])

    def test_reading_uses_raw_structure_not_axis_scores(self):
        simple_high_ar = blank_components()
        simple_high_ar["reading_preempt_median_ms"] = 300.0
        structured_high_ar = copy.deepcopy(simple_high_ar)
        structured_high_ar.update(
            {
                "v091_visible_overlap_load_p90": 1.8,
                "v091_visible_cluster_load_p90": 5.0,
                "v091_visible_overlap_pair_share": 0.42,
            }
        )
        simple = decoupled.decoupled_values(simple_high_ar, anchor=8.0)[0]["reading"]
        structured = decoupled.decoupled_values(structured_high_ar, anchor=8.0)[0]["reading"]
        self.assertLess(simple, 1.0)
        self.assertGreater(structured, simple + 2.5)

    def test_dense_relative_low_ar_and_hd_are_reading_peaks(self):
        dense = blank_components()
        dense.update(
            {
                "reading_preempt_median_ms": 750.0,
                "reading_density": 6.0,
                "v091_visible_overlap_load_p90": 0.7,
                "v091_visible_cluster_load_p90": 2.5,
                "v091_visible_overlap_pair_share": 0.22,
            }
        )
        nm = decoupled.decoupled_values(dense, anchor=7.0)[0]["reading"]
        hd = decoupled.decoupled_values(dense, mods={"HD"}, anchor=7.0)[0]["reading"]
        self.assertGreater(nm, 4.0)
        self.assertGreater(hd, 5.5)
        self.assertGreater(hd, nm + 1.0)

    def test_experimental_identity_is_distinct_and_explicit(self):
        output = decoupled.analyze_components(
            checksum="sha256:decoupled-v01",
            components=v07_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(output["identity"]["algorithm_id"], "MAP_DEMAND_DECOUPLED_V01_R2")
        self.assertEqual(output["identity"]["map_demand_version"], "0.9.6-decoupled.2")
        self.assertTrue(output["diagnostics"]["decoupled_no_axis_score_dependencies"])

    def test_fast_wide_jump_chain_is_not_full_flow_support(self):
        components = blank_components()
        components.update(
            {
                "decoupled_flow_longest_chain_notes": 16.0,
                "decoupled_flow_rate_p90_per_s": 13.5,
                "decoupled_flow_distance_radii_p90": 4.95,
                "v095_control_large_jump_share": 0.60,
            }
        )
        support, _, signals = decoupled.axis_evidence(components)["flow_aim"]
        self.assertLess(support, 0.70)
        self.assertGreater(signals["extreme_wide_jump"], 0.80)

    def test_long_compact_chain_remains_flow_support(self):
        components = blank_components()
        components.update(
            {
                "decoupled_flow_longest_chain_notes": 144.0,
                "decoupled_flow_rate_p90_per_s": 10.2,
                "decoupled_flow_distance_radii_p90": 1.2,
            }
        )
        support, _, _ = decoupled.axis_evidence(components)["flow_aim"]
        self.assertGreater(support, 0.85)

    def test_ordinary_followup_jump_is_not_micro_precision(self):
        rows = []
        for distance_radii in (5.0, 2.4) * 8:
            rows.append(
                {
                    "ls.object_type": "circle",
                    "ls.adjusted_delta_time_ms": 100.0,
                    "ls.jump_distance_raw_px": 32.0 * distance_radii,
                    "ls.radius_px": 32.0,
                    "ls.slider_aware_angle_rad": 0.0,
                }
            )
        components = decoupled._independent_sequence_components(rows)
        self.assertEqual(components["decoupled_precision_micro_gate"], 0.0)

    def test_true_tight_post_jump_correction_is_micro_precision(self):
        rows = []
        for distance_radii in (5.0, 0.8) * 8:
            rows.append(
                {
                    "ls.object_type": "circle",
                    "ls.adjusted_delta_time_ms": 90.0,
                    "ls.jump_distance_raw_px": 32.0 * distance_radii,
                    "ls.radius_px": 32.0,
                    "ls.slider_aware_angle_rad": 0.0,
                }
            )
        components = decoupled._independent_sequence_components(rows)
        self.assertGreater(components["decoupled_precision_micro_gate"], 0.25)

    def test_zero_support_has_no_total_sr_floor(self):
        self.assertEqual(decoupled._axis_value("reading", 12.0, 0.0, 0.0), 0.0)

    def test_proven_jump_recovers_full_map_scale(self):
        value = decoupled._axis_value("jump_aim", 11.75, 0.90, 0.0)
        self.assertGreater(value, 11.0)
        self.assertLessEqual(value, 11.75 * 1.08)


if __name__ == "__main__":
    unittest.main()
