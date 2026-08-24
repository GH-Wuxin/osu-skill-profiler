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

from map_demand_v01 import model_v091 as v091  # noqa: E402
from map_demand_v01 import model_v092 as v092  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def row(
    index: int,
    *,
    dt: float = 120.0,
    distance: float = 160.0,
    angle: float = math.pi,
) -> dict:
    return {
        "ls.object_type": "circle",
        "ls.start_time_ms": index * dt,
        "ls.end_time_ms": index * dt,
        "ls.radius_px": 32.0,
        "ls.adjusted_delta_time_ms": dt,
        "ls.minimum_jump_time_ms": dt,
        "ls.jump_distance_raw_px": distance,
        "ls.slider_aware_angle_rad": angle,
    }


class MapDemandV092Tests(unittest.TestCase):
    def test_v091_replay_is_unchanged(self):
        calibration = mini_calibration()
        components = v07_components()
        before = v091.analyze_components(
            checksum="sha256:v091", components=copy.deepcopy(components), calibration=calibration
        )
        v092.analyze_components(
            checksum="sha256:v092", components=copy.deepcopy(components), calibration=calibration
        )
        after = v091.analyze_components(
            checksum="sha256:v091", components=copy.deepcopy(components), calibration=calibration
        )
        self.assertEqual(before, after)

    def test_spacing_separation_emerges_without_named_detector(self):
        stable = [row(i, distance=120.0) for i in range(24)]
        separated = [
            row(i, distance=(260.0 if i % 4 == 2 else 120.0)) for i in range(24)
        ]
        stable_c = v092._movement_control_components(stable)
        separated_c = v092._movement_control_components(separated)
        self.assertGreater(
            separated_c["v092_control_stable_cadence_spacing_p95"],
            stable_c["v092_control_stable_cadence_spacing_p95"] + 0.5,
        )
        self.assertGreater(separated_c["v092_control_index"], stable_c["v092_control_index"])

    def test_jump_tail_requires_persistent_distance_and_speed(self):
        isolated = [row(i, distance=(360.0 if i == 12 else 80.0)) for i in range(30)]
        sustained = [row(i, distance=(360.0 if 5 <= i <= 20 else 80.0)) for i in range(30)]
        isolated_c = v092._jump_movement_components(isolated)
        sustained_c = v092._jump_movement_components(sustained)
        self.assertLessEqual(isolated_c["v092_jump_longest_chain_count"], 1)
        self.assertGreaterEqual(sustained_c["v092_jump_longest_chain_count"], 12)
        self.assertGreater(sustained_c["v092_jump_tail_gate"], isolated_c["v092_jump_tail_gate"] + 0.4)

    def test_jump_tail_does_not_use_angle_change(self):
        straight = [row(i, distance=280.0, angle=math.pi) for i in range(24)]
        reversing = [row(i, distance=280.0, angle=0.0) for i in range(24)]
        self.assertEqual(
            v092._jump_movement_components(straight),
            v092._jump_movement_components(reversing),
        )

    def test_inactive_jump_tail_does_not_create_total_sr_floor(self):
        axes = {
            "jump_aim": {
                "status": "EMITTED",
                "score": 0.5,
                "demand_star_equivalent": 5.0,
                "evidence": [],
            },
            "aim_control": {"status": "EMITTED", "demand_star_equivalent": 6.0},
            "flow_aim": {"status": "EMITTED", "demand_star_equivalent": 6.0},
            "spatial_precision": {"status": "EMITTED", "demand_star_equivalent": 6.0},
            "raw_speed": {"status": "EMITTED", "demand_star_equivalent": 6.0},
        }
        components = {
            "v092_jump_transition_count": 100,
            "v092_jump_tail_gate": 0.2,
            "v092_jump_tail_activation": 0.0,
        }
        v092._apply_jump_movement_tail(axes, components, 8.0)
        self.assertEqual(axes["jump_aim"]["demand_star_equivalent"], 5.0)

    def test_repeated_large_turns_form_control_chain(self):
        straight = [row(i, angle=math.pi) for i in range(24)]
        turning = [row(i, angle=(math.pi / 4.0 if i >= 2 else math.pi)) for i in range(24)]
        straight_c = v092._movement_control_components(straight)
        turning_c = v092._movement_control_components(turning)
        self.assertGreater(turning_c["v092_control_turn_severity_p95"], 0.7)
        self.assertGreaterEqual(turning_c["v092_control_longest_chain_count"], 12)
        self.assertGreater(turning_c["v092_control_index"], straight_c["v092_control_index"] + 0.5)

    def test_uniform_pressure_has_more_sustain_than_fragmented_objects(self):
        uniform = [row(i, dt=100.0, distance=180.0) for i in range(80)]
        fragmented = []
        time_ms = 0.0
        for i in range(80):
            dt = 1000.0 if i % 8 == 0 else 100.0
            time_ms += dt
            item = row(i, dt=dt, distance=180.0)
            item["ls.start_time_ms"] = time_ms
            fragmented.append(item)
        uniform_c = v092._sustain_pressure_components(uniform)
        fragmented_c = v092._sustain_pressure_components(fragmented)
        self.assertGreater(
            uniform_c["v092_pressure_longest_continuous_effective_ms"],
            fragmented_c["v092_pressure_longest_continuous_effective_ms"] * 4,
        )
        self.assertGreater(
            uniform_c["v092_pressure_coverage"], fragmented_c["v092_pressure_coverage"]
        )
        self.assertGreater(
            uniform_c["v092_pressure_top3_segment_effective_ms"],
            fragmented_c["v092_pressure_top3_segment_effective_ms"],
        )

    def test_repeated_pressure_sections_are_retained_for_stamina(self):
        rows = []
        time_ms = 0.0
        for section in range(6):
            for i in range(18):
                time_ms += 100.0
                item = row(section * 18 + i, dt=100.0, distance=180.0)
                item["ls.start_time_ms"] = time_ms
                rows.append(item)
            time_ms += 1200.0
            recovery = row(1000 + section, dt=1200.0, distance=20.0)
            recovery["ls.start_time_ms"] = time_ms
            rows.append(recovery)
        components = v092._sustain_pressure_components(rows)
        self.assertGreaterEqual(components["v092_pressure_qualifying_segment_count"], 6)
        self.assertGreater(components["v092_pressure_repeated_section_effective_ms"], 8000.0)

    def test_duration_curve_has_nonzero_diminishing_returns(self):
        load = lambda minutes: v092._diminishing_duration_load(minutes * 60.0, 180.0)
        self.assertGreater(load(5) - load(3), load(7) - load(5))
        self.assertGreater(load(7) - load(5), load(25) - load(20))
        self.assertGreater(load(25) - load(20), 0.0)

    def test_high_star_without_sustain_no_longer_has_seventy_percent_floor(self):
        axes = {
            axis: {
                "status": "EMITTED",
                "score": 0.8,
                "demand_star_equivalent": 8.0,
                "evidence": [],
            }
            for axis in v092.AXIS_ORDER
        }
        components = {
            "v092_pressure_longest_continuous_effective_ms": 0.0,
            "v092_pressure_longest_circle_tapping_effective_ms": 0.0,
            "v092_pressure_effective_duration_ms": 0.0,
            "v092_pressure_repeated_section_effective_ms": 0.0,
            "v092_pressure_qualifying_segment_count": 0,
            "v092_pressure_coverage": 0.0,
            "v092_pressure_p90": 0.0,
        }
        v092._apply_stamina_timeline(axes, components)
        self.assertLess(axes["stamina"]["demand_star_equivalent"], 4.0)

    def test_endurance_rewards_uniform_pressure_not_song_length_alone(self):
        axes = {
            axis: {"status": "EMITTED", "demand_star_equivalent": 7.0}
            for axis in v092.AXIS_ORDER
        }
        common = {
            "v092_pressure_active_duration_ms": 300_000.0,
            "v092_pressure_segment_count": 10,
        }
        uniform = {
            **common,
            "v092_pressure_effective_duration_ms": 270_000.0,
            "v092_pressure_longest_continuous_effective_ms": 180_000.0,
            "v092_pressure_qualifying_segment_count": 1,
            "v092_pressure_repeated_section_effective_ms": 12_000.0,
            "v092_pressure_top3_segment_effective_ms": 180_000.0,
            "v092_pressure_high_duration_ms": 270_000.0,
            "v092_pressure_coverage": 0.90,
            "v092_pressure_recovery_ratio": 0.02,
        }
        sparse = {
            **common,
            "v092_pressure_effective_duration_ms": 45_000.0,
            "v092_pressure_longest_continuous_effective_ms": 5_000.0,
            "v092_pressure_qualifying_segment_count": 10,
            "v092_pressure_repeated_section_effective_ms": 45_000.0,
            "v092_pressure_top3_segment_effective_ms": 15_000.0,
            "v092_pressure_high_duration_ms": 20_000.0,
            "v092_pressure_coverage": 0.15,
            "v092_pressure_recovery_ratio": 0.60,
        }
        uniform_axis = v092._endurance_timeline_axis(axes, uniform)
        sparse_axis = v092._endurance_timeline_axis(axes, sparse)
        self.assertGreater(
            uniform_axis["demand_star_equivalent"],
            sparse_axis["demand_star_equivalent"] + 4.0,
        )

    def test_repeated_hard_sections_survive_recovery_without_becoming_uniform(self):
        axes = {
            axis: {"status": "EMITTED", "demand_star_equivalent": 8.0}
            for axis in v092.AXIS_ORDER
        }
        common = {
            "v092_pressure_active_duration_ms": 300_000.0,
            "v092_pressure_effective_duration_ms": 150_000.0,
            "v092_pressure_longest_continuous_effective_ms": 22_000.0,
            "v092_pressure_coverage": 0.50,
            "v092_pressure_segment_count": 12,
            "v092_pressure_qualifying_segment_count": 9,
            "v092_pressure_repeated_section_effective_ms": 86_000.0,
            "v092_pressure_top3_segment_effective_ms": 60_000.0,
            "v092_pressure_high_duration_ms": 145_000.0,
        }
        modest_recovery = v092._endurance_timeline_axis(
            axes, {**common, "v092_pressure_recovery_ratio": 0.18}
        )
        heavy_recovery = v092._endurance_timeline_axis(
            axes, {**common, "v092_pressure_recovery_ratio": 0.70}
        )
        self.assertGreater(modest_recovery["demand_star_equivalent"], 6.0)
        self.assertGreater(
            modest_recovery["demand_star_equivalent"],
            heavy_recovery["demand_star_equivalent"],
        )

    def test_rhythm_change_alone_is_not_aim_control(self):
        rows = []
        time_ms = 0.0
        for i, dt in enumerate([80.0, 160.0] * 12):
            time_ms += dt
            item = row(i, dt=dt, distance=100.0, angle=math.pi)
            item["ls.start_time_ms"] = time_ms
            rows.append(item)
        components = v092._movement_control_components(rows)
        self.assertGreater(components["v092_control_cadence_change_p95"], 0.5)
        self.assertLess(components["v092_control_index"], 0.35)

    def test_bounded_axes_do_not_compete_for_primary_dominance(self):
        axes = {}
        for axis in v092.AXIS_ORDER:
            value = 5.0
            if axis == "aim_control":
                value = 8.0
            if axis == "endurance":
                value = 10.0
            axes[axis] = {
                "status": "EMITTED",
                "score": value / 10.0,
                "demand_star_equivalent": value,
            }
        result = v092.classify_axes(axes)
        self.assertIn("aim_control", result["dominant_axes"])
        self.assertNotIn("endurance", result["dominant_axes"])
        self.assertEqual(result["auxiliary_traits"]["endurance"], 10.0)

    def test_movement_overlay_never_double_anchors_incoming_v091_value(self):
        axes = {
            "aim_control": {
                "status": "EMITTED",
                "score": 0.64,
                "demand_star_equivalent": 6.4,
                "evidence": [],
            },
            "jump_aim": {"status": "EMITTED", "demand_star_equivalent": 5.0},
            "flow_aim": {"status": "EMITTED", "demand_star_equivalent": 4.0},
            "spatial_precision": {"status": "EMITTED", "demand_star_equivalent": 4.5},
            "raw_speed": {"status": "EMITTED", "demand_star_equivalent": 4.5},
        }
        components = {
            "v092_control_transition_count": 100,
            "v092_control_index": 0.78,
            "v092_control_stable_cadence_spacing_p95": 0.4,
            "v092_control_high_transition_share": 0.2,
            "v092_jump_tail_activation": 0.0,
        }
        v092._apply_movement_control_state(axes, components, 5.0)
        self.assertEqual(axes["aim_control"]["demand_star_equivalent"], 6.4)

    def test_v092_identity_and_aim_control_evidence(self):
        components = v07_components()
        components.update(
            v091_nm_star_anchor=7.8,
            v092_control_transition_count=100,
            v092_control_shock_p95=0.75,
            v092_control_shock_top10_mean=0.70,
            v092_control_high_transition_share=0.30,
            v092_control_high_density_per_min=30.0,
            v092_control_longest_chain_count=12,
            v092_control_longest_chain_duration_ms=1800.0,
            v092_control_window_5s_load_p90=5.0,
            v092_control_turn_severity_p95=0.8,
            v092_control_velocity_change_p95=0.7,
            v092_control_spacing_change_p95=0.8,
            v092_control_stable_cadence_spacing_p95=0.7,
            v092_control_cadence_change_p95=0.2,
            v092_control_rhythm_movement_coupling_p95=0.2,
            v092_control_index=0.9,
        )
        out = v092.analyze_components(
            checksum="sha256:v092", components=components, calibration=mini_calibration()
        )
        self.assertEqual(out["identity"]["map_demand_version"], "0.9.2.2")
        self.assertEqual(out["schema_version"], "map_demand_v0.9.2.2")
        self.assertEqual(out["axes"]["aim_control"]["method"], "UNIFIED_MOVEMENT_CONTROL_STATE_V092")


if __name__ == "__main__":
    unittest.main()
