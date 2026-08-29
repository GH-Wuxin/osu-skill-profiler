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

from map_demand_v01 import model_v095 as v095  # noqa: E402
from map_demand_v01 import model_v096 as v096  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def row(
    index: int,
    *,
    dt: float = 120.0,
    distance: float = 160.0,
    radius: float = 36.5,
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
        for axis in v096.AXIS_ORDER
    }


def apply_precision(rows: list[dict], *, anchor: float = 8.0) -> float:
    components = {
        **v095._precision_components(rows),
        **v096._signed_precision_components(rows),
    }
    gates = v096._signed_gates(star_axes(anchor), components, set())
    support, counter, signals = gates["spatial_precision"]
    axes = star_axes(anchor)
    base, gain, cost, prominence, cap, reference_weight = v096._AXIS_SCALE["spatial_precision"]
    v096._set_signed_axis(
        axes,
        "spatial_precision",
        anchor=anchor,
        support=support,
        counter=counter,
        base_multiplier=base,
        support_gain=gain,
        counter_cost=cost,
        prominence_gain=prominence,
        cap=cap,
        reference_weight=reference_weight,
        signals=signals,
    )
    return axes["spatial_precision"]["demand_star_equivalent"]


class MapDemandV096Tests(unittest.TestCase):
    def test_v0953_replay_is_unchanged(self):
        calibration = mini_calibration()
        components = v07_components()
        before = v095.analyze_components(
            checksum="sha256:v095-before",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        v096.analyze_components(
            checksum="sha256:v096",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        after = v095.analyze_components(
            checksum="sha256:v095-after",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        before["identity"]["beatmap_checksum"] = "same"
        after["identity"]["beatmap_checksum"] = "same"
        self.assertEqual(before, after)

    def test_target_size_is_signed_not_additive_only(self):
        large = [row(i, distance=180.0, radius=45.5) for i in range(40)]
        neutral = [row(i, distance=180.0, radius=36.5) for i in range(40)]
        small = [row(i, distance=180.0, radius=18.5) for i in range(40)]
        large_value = apply_precision(large)
        neutral_value = apply_precision(neutral)
        small_value = apply_precision(small)
        self.assertLess(large_value, neutral_value - 0.5)
        self.assertGreater(small_value, neutral_value + 2.0)

    def test_high_sr_without_precision_evidence_does_not_get_precision_floor(self):
        ordinary = [row(i, distance=240.0, radius=36.5) for i in range(40)]
        self.assertLess(apply_precision(ordinary, anchor=9.0), 5.5)

    def test_micro_correction_can_survive_large_targets_but_does_not_erase_relief(self):
        plain_large = [row(i, distance=180.0, radius=45.5) for i in range(40)]
        correcting_large = [
            row(
                i,
                distance=280.0 if i % 2 == 0 else 30.0,
                radius=45.5,
                angle=0.0,
            )
            for i in range(40)
        ]
        self.assertGreater(
            apply_precision(correcting_large),
            apply_precision(plain_large) + 0.3,
        )

    def test_decisive_support_can_exceed_total_sr(self):
        axes = star_axes(8.0)
        v096._set_signed_axis(
            axes,
            "aim_control",
            anchor=8.0,
            support=1.0,
            counter=0.0,
            base_multiplier=0.40,
            support_gain=0.52,
            counter_cost=0.30,
            prominence_gain=0.20,
        )
        self.assertGreater(axes["aim_control"]["demand_star_equivalent"], 8.4)

    def test_counterevidence_can_lower_an_inherited_high_score(self):
        axes = star_axes(8.0)
        v096._set_signed_axis(
            axes,
            "raw_speed",
            anchor=8.0,
            support=0.0,
            counter=1.0,
            base_multiplier=0.38,
            support_gain=0.52,
            counter_cost=0.30,
            prominence_gain=0.18,
        )
        self.assertLess(axes["raw_speed"]["demand_star_equivalent"], 4.0)

    def test_compact_tapping_and_large_jump_cadence_separate_both_directions(self):
        compact_rows = [row(i, dt=95.0, distance=40.0, radius=32.0) for i in range(40)]
        jump_rows = [row(i, dt=95.0, distance=260.0, radius=32.0) for i in range(40)]
        compact = {
            **v095._compact_tapping_components(compact_rows),
            **v095._control_state_components(compact_rows),
            **v095._precision_components(compact_rows),
            **v096._signed_precision_components(compact_rows),
        }
        jumps = {
            **v095._compact_tapping_components(jump_rows),
            **v095._control_state_components(jump_rows),
            **v095._precision_components(jump_rows),
            **v096._signed_precision_components(jump_rows),
        }
        compact_gate = v096._signed_gates(star_axes(), compact, set())["raw_speed"]
        jump_gate = v096._signed_gates(star_axes(), jumps, set())["raw_speed"]
        self.assertGreater(compact_gate[0], jump_gate[0] + 0.65)
        self.assertLess(compact_gate[1], jump_gate[1] - 0.40)

    def test_broad_large_jump_share_counts_before_extreme_tail_activation(self):
        components = {
            "v092_jump_tail_activation": 0.0,
            "v092_jump_severity_gate": 0.65,
            "v092_jump_persistence_gate": 0.35,
            "v095_control_large_jump_share": 0.55,
            "v095_tapping_large_jump_pair_share": 0.05,
        }
        support, counter, _ = v096._signed_gates(
            star_axes(), components, set()
        )["jump_aim"]
        self.assertGreater(support, 0.70)
        self.assertLess(counter, 0.40)

    def test_raw_speed_requires_persistence_not_peak_rate_alone(self):
        short_rows = [row(i, dt=90.0, distance=40.0, radius=32.0) for i in range(8)]
        sustained_rows = [
            row(i, dt=90.0, distance=40.0, radius=32.0) for i in range(80)
        ]
        short_components = v095._compact_tapping_components(short_rows)
        sustained_components = v095._compact_tapping_components(sustained_rows)
        short_support = v096._signed_gates(
            star_axes(), short_components, set()
        )["raw_speed"][0]
        sustained_support = v096._signed_gates(
            star_axes(), sustained_components, set()
        )["raw_speed"][0]
        self.assertGreater(sustained_support, short_support + 0.25)

    def test_v096_identity(self):
        out = v096.analyze_components(
            checksum="sha256:v096",
            components=v07_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(out["identity"]["map_demand_version"], "0.9.6")
        self.assertEqual(out["schema_version"], "map_demand_v0.9.6")
        self.assertEqual(out["identity"]["algorithm_id"], "MAP_DEMAND_ATOMIC_V096")
        self.assertIn("v096_signed_axis_gates", out["diagnostics"])


if __name__ == "__main__":
    unittest.main()
