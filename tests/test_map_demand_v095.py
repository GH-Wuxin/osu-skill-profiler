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

from map_demand_v01 import model_v092 as v092  # noqa: E402
from map_demand_v01 import model_v095 as v095  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def row(
    index: int,
    *,
    dt: float = 120.0,
    distance: float = 160.0,
    radius: float = 32.0,
    angle: float = math.pi,
) -> dict:
    return {
        "ls.object_type": "circle",
        "ls.start_time_ms": index * dt,
        "ls.end_time_ms": index * dt,
        "ls.radius_px": radius,
        "ls.adjusted_delta_time_ms": dt,
        "ls.minimum_jump_time_ms": dt,
        "ls.jump_distance_raw_px": distance,
        "ls.slider_aware_angle_rad": angle,
    }


def star_axes(value: float = 8.0) -> dict:
    return {
        axis: {
            "status": "EMITTED",
            "score": value / 10.0,
            "demand_star_equivalent": value,
            "evidence": [],
        }
        for axis in v095.AXIS_ORDER
    }


class MapDemandV095Tests(unittest.TestCase):
    def test_v0922_replay_is_unchanged(self):
        calibration = mini_calibration()
        components = v07_components()
        before = v092.analyze_components(
            checksum="sha256:v092", components=copy.deepcopy(components), calibration=calibration
        )
        v095.analyze_components(
            checksum="sha256:v095", components=copy.deepcopy(components), calibration=calibration
        )
        after = v092.analyze_components(
            checksum="sha256:v092", components=copy.deepcopy(components), calibration=calibration
        )
        self.assertEqual(before, after)

    def test_large_jump_cadence_is_not_compact_raw_speed(self):
        compact = [row(i, dt=100.0, distance=45.0) for i in range(30)]
        jumps = [row(i, dt=100.0, distance=240.0) for i in range(30)]
        compact_c = v095._compact_tapping_components(compact)
        jump_c = v095._compact_tapping_components(jumps)
        self.assertGreater(compact_c["v095_tapping_evidence_gate"], 0.65)
        self.assertLess(jump_c["v095_tapping_evidence_gate"], 0.10)

        compact_axes = star_axes()
        jump_axes = star_axes()
        v095._apply_raw_speed(compact_axes, compact_c)
        v095._apply_raw_speed(jump_axes, jump_c)
        self.assertGreater(
            compact_axes["raw_speed"]["demand_star_equivalent"],
            jump_axes["raw_speed"]["demand_star_equivalent"] + 1.0,
        )

    def test_stable_large_jumps_route_to_jump_not_control(self):
        stable_jump = [
            row(i, distance=260.0, angle=math.pi / 4.0) for i in range(30)
        ]
        technical = [
            row(
                i,
                distance=260.0 if i % 3 == 1 else 75.0,
                angle=math.pi / 8.0 if i % 2 else math.pi,
            )
            for i in range(30)
        ]
        jump_c = v095._control_state_components(stable_jump)
        tech_c = v095._control_state_components(technical)
        self.assertGreater(
            tech_c["v095_control_index"], jump_c["v095_control_index"] + 0.40
        )

        jump_c["v092_jump_tail_activation"] = 1.0
        tech_c["v092_jump_tail_activation"] = 0.0
        jump_axes = star_axes()
        tech_axes = star_axes()
        v095._apply_aim_control(jump_axes, jump_c, 8.0)
        v095._apply_aim_control(tech_axes, tech_c, 8.0)
        self.assertGreater(
            tech_axes["aim_control"]["demand_star_equivalent"],
            jump_axes["aim_control"]["demand_star_equivalent"] + 1.0,
        )

    def test_precision_requires_small_targets_or_micro_correction(self):
        ordinary_jump = [
            row(i, distance=240.0, radius=36.5, angle=math.pi / 4.0)
            for i in range(30)
        ]
        micro = [
            row(
                i,
                distance=230.0 if i % 2 == 0 else 25.0,
                radius=22.0,
                angle=0.0,
            )
            for i in range(30)
        ]
        ordinary_c = v095._precision_components(ordinary_jump)
        micro_c = v095._precision_components(micro)
        self.assertLess(ordinary_c["v095_precision_index"], 0.15)
        self.assertGreater(micro_c["v095_precision_index"], 0.65)

        ordinary_axes = star_axes()
        micro_axes = star_axes()
        v095._apply_spatial_precision(ordinary_axes, ordinary_c, 8.0)
        v095._apply_spatial_precision(micro_axes, micro_c, 8.0)
        self.assertGreater(
            micro_axes["spatial_precision"]["demand_star_equivalent"],
            ordinary_axes["spatial_precision"]["demand_star_equivalent"] + 0.3,
        )

    def test_high_ar_alone_does_not_create_reading_demand(self):
        high_ar_axes = star_axes()
        low_ar_axes = star_axes()
        common = {
            "v091_visible_overlap_load_p90": 0.0,
            "v091_visible_cluster_load_p90": 1.0,
            "v091_visible_stack_object_share": 0.0,
        }
        v095._apply_reading(
            high_ar_axes, {**common, "reading_preempt_median_ms": 300.0}, set()
        )
        v095._apply_reading(
            low_ar_axes, {**common, "reading_preempt_median_ms": 900.0}, set()
        )
        high = high_ar_axes["reading"]["demand_star_equivalent"]
        low = low_ar_axes["reading"]["demand_star_equivalent"]
        self.assertLess(high, 7.0)
        self.assertGreater(low, high + 1.0)

    def test_v095_identity(self):
        out = v095.analyze_components(
            checksum="sha256:v095",
            components=v07_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(out["identity"]["map_demand_version"], "0.9.5.0")
        self.assertEqual(out["schema_version"], "map_demand_v0.9.5.0")
        self.assertEqual(out["identity"]["algorithm_id"], "MAP_DEMAND_ATOMIC_V095")


if __name__ == "__main__":
    unittest.main()
