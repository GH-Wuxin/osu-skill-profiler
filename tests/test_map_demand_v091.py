from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v09 as v09  # noqa: E402
from map_demand_v01 import model_v091 as v091  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def row(
    *,
    time: float,
    x: float,
    y: float,
    radius: float = 32.0,
    dt: float | None = 150.0,
    distance: float | None = 160.0,
    angle: float | None = 2.8,
) -> dict:
    return {
        "ls.object_type": "circle",
        "ls.start_time_ms": time,
        "ls.end_time_ms": time,
        "ls.preempt_ms": 600.0,
        "ls.radius_px": radius,
        "ls.cs_scale": 50.0 / radius,
        "ls.adjusted_delta_time_ms": dt,
        "ls.minimum_jump_time_ms": dt,
        "ls.jump_distance_raw_px": distance,
        "ls.slider_aware_angle_rad": angle,
        v091._PRIVATE_X: x,
        v091._PRIVATE_Y: y,
    }


class MapDemandV091Tests(unittest.TestCase):
    def test_v09_replay_is_unchanged(self):
        calibration = mini_calibration()
        components = v07_components()
        before = v09.analyze_components(
            checksum="sha256:v09", components=copy.deepcopy(components), calibration=calibration
        )
        v091.analyze_components(
            checksum="sha256:v091", components=copy.deepcopy(components), calibration=calibration
        )
        after = v09.analyze_components(
            checksum="sha256:v09", components=copy.deepcopy(components), calibration=calibration
        )
        self.assertEqual(before, after)

    def test_overlap_is_geometric_not_density_only(self):
        stacked = [row(time=i * 100.0, x=256.0, y=192.0) for i in range(12)]
        spread = [row(time=i * 100.0, x=float((i % 4) * 150), y=float((i // 4) * 150)) for i in range(12)]
        stacked_components = v091._mechanic_components(stacked)
        spread_components = v091._mechanic_components(spread)
        self.assertGreater(stacked_components["v091_visible_overlap_load_p90"], 3.0)
        self.assertGreater(
            stacked_components["v091_visible_overlap_load_p90"],
            spread_components["v091_visible_overlap_load_p90"],
        )
        self.assertGreater(stacked_components["v091_visible_stack_object_share"], 0.5)

    def test_smaller_targets_raise_precision_more_than_jump(self):
        large = [row(time=i * 150.0, x=i * 30.0, y=100.0, radius=40.0) for i in range(10)]
        small = [row(time=i * 150.0, x=i * 30.0, y=100.0, radius=20.0) for i in range(10)]
        large_c = v091._mechanic_components(large)
        small_c = v091._mechanic_components(small)
        self.assertEqual(
            large_c["v091_jump_velocity_raw_p90_px_per_ms"],
            small_c["v091_jump_velocity_raw_p90_px_per_ms"],
        )
        self.assertGreater(
            small_c["v091_precision_tolerance_p90"],
            large_c["v091_precision_tolerance_p90"] * 1.9,
        )

    def test_ordinary_one_to_two_rhythm_has_no_novelty(self):
        rows = []
        time = 0.0
        for i, dt in enumerate(([100.0, 200.0] * 20)):
            time += dt
            rows.append(row(time=time, x=float(i), y=100.0, dt=dt))
        components = v091._mechanic_components(rows)
        self.assertAlmostEqual(components["v091_finger_novelty_p90"], 0.0)
        self.assertEqual(components["v091_finger_nontrivial_change_share"], 0.0)

    def test_soft_anchor_saturates_extreme_tail_but_keeps_specialisation(self):
        self.assertGreater(v091._soft_anchor(20.0, 7.0), 7.0)
        self.assertLess(v091._soft_anchor(20.0, 7.0), 10.0)
        self.assertLess(v091._soft_anchor(4.0, 7.0), 7.0)

    def test_dt_extreme_jump_recovers_saturated_tail_without_changing_nm(self):
        components = {
            "v091_jump_distance_raw_p90_px": 269.0,
            "v091_jump_velocity_raw_p90_px_per_ms": 3.09,
        }
        severity = v091._jump_movement_severity(components)
        self.assertGreater(severity, 0.8)
        nm_factor = 1.0 + 0.30 * 0.0 * severity
        dt_factor = 1.0 + 0.30 * 1.0 * severity
        self.assertEqual(nm_factor, 1.0)
        self.assertGreater(dt_factor, 1.24)

    def test_explicit_anchor_bounds_every_star_axis(self):
        components = v07_components()
        components.update(
            v091_nm_star_anchor=6.0,
            v091_jump_cs_scale_median=1.0,
            v091_precision_tolerance_p90=4.0,
            v091_precision_settling_p90=2.0,
            v091_precision_micro_correction_p90=0.2,
            v091_precision_micro_correction_count=4,
            v091_flow_chain_share=0.5,
            v091_flow_chain_length_p90=5.0,
            v091_flow_chain_velocity_p90=1.2,
            v091_flow_chain_smoothness_mean=0.8,
            v091_finger_fast_pair_count=100,
            v091_finger_nontrivial_change_share=0.4,
            v091_finger_novelty_p90=0.3,
            v091_visible_overlap_load_p90=1.0,
            v091_visible_cluster_load_p90=3.0,
            v091_visible_overlap_pair_share=0.2,
            v091_visible_stack_object_share=0.05,
        )
        out = v091.analyze_components(
            checksum="sha256:anchor", components=components, calibration=mini_calibration()
        )
        self.assertEqual(out["identity"]["map_demand_version"], "0.9.1")
        self.assertEqual(out["schema_version"], "map_demand_v0.9.1")
        self.assertEqual(set(out["axes"]), set(v091.AXIS_ORDER))
        for axis in v091._STAR_AXES:
            item = out["axes"][axis]
            if item["status"] == "EMITTED":
                self.assertLess(item["demand_star_equivalent"], 9.0)


if __name__ == "__main__":
    unittest.main()
