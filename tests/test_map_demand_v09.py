from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v08 as v08  # noqa: E402
from map_demand_v01 import model_v09 as v09  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


def emitted(stars: float) -> dict:
    return {
        "status": "EMITTED",
        "demand_star_equivalent": stars,
        "score": stars / 10.0,
        "percentile_rank": 0.5,
        "scale_method": "fixture",
        "method": "fixture",
        "evidence": [],
    }


class MapDemandV09Tests(unittest.TestCase):
    def test_v08_replay_is_stable_and_v09_has_distinct_identity(self):
        calibration = mini_calibration()
        components = v07_components()
        old_before = v08.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        new = v09.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        old_after = v08.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        self.assertEqual(old_before, old_after)
        self.assertEqual(new["identity"]["map_demand_version"], "0.9.0")
        self.assertEqual(new["identity"]["algorithm_id"], v09.ALGORITHM_ID)
        self.assertEqual(new["schema_version"], "map_demand_v0.9.0")
        self.assertEqual(set(new["axes"]), set(v09.AXIS_ORDER))
        self.assertNotEqual(old_before["identity"], new["identity"])

    def test_fast_passage_features_ignore_slow_transition_changes(self):
        rows = [
            {"ls.object_type": "circle", "ls.adjusted_delta_time_ms": value}
            for value in (100.0, 200.0, 100.0, 800.0, 100.0)
        ]
        components, _ = v09.extract_components(rows)
        # Only the 100/200 and 200/100 pairs are eligible.  Transitions around
        # the 800 ms break must not inflate local Finger Control.
        self.assertEqual(components["v09_fast_interval_pair_count"], 2)
        self.assertAlmostEqual(components["v09_fast_interval_change_mean"], 1.0)
        self.assertAlmostEqual(components["v09_fast_interval_change_p75"], 1.0)

    def test_irregular_fast_pattern_recovers_finger_control_without_global_floor(self):
        regular_axes = {
            "finger_control": emitted(2.5),
            "raw_speed": emitted(4.6),
        }
        irregular_axes = copy.deepcopy(regular_axes)
        common = {
            "v09_fast_interval_pair_count": 100.0,
            "v07_burst_longest_duration_ms_250ms": 5000.0,
            "v07_map_duration_ms": 120000.0,
            "reading_density": 8.0,
        }
        regular = dict(
            common,
            v09_fast_interval_change_mean=0.02,
            v09_fast_interval_change_p75=0.0,
        )
        irregular = dict(
            common,
            v09_fast_interval_change_mean=0.35,
            v09_fast_interval_change_p75=1.0,
        )
        v09._finger_overlay(regular_axes, regular)
        v09._finger_overlay(irregular_axes, irregular)
        self.assertAlmostEqual(
            regular_axes["finger_control"]["demand_star_equivalent"], 2.5
        )
        self.assertGreater(
            irregular_axes["finger_control"]["demand_star_equivalent"], 5.5
        )

    def test_hd_dense_structure_bonus_is_conditional(self):
        base_axes = {
            "jump_aim": emitted(6.0),
            "flow_aim": emitted(7.0),
            "aim_control": emitted(6.0),
            "spatial_precision": emitted(6.0),
            "raw_speed": emitted(6.5),
            "stamina": emitted(6.5),
            "reading": emitted(4.8),
        }
        sparse = {
            "reading_preempt_median_ms": 500.0,
            "reading_density": 7.0,
            "reading_hidden_pressure": 0.5,
        }
        dense = dict(sparse, reading_density=12.0)
        sparse_axes = copy.deepcopy(base_axes)
        dense_axes = copy.deepcopy(base_axes)
        v09._reading_overlay(sparse_axes, sparse, {"HD"})
        v09._reading_overlay(dense_axes, dense, {"HD"})
        self.assertAlmostEqual(
            sparse_axes["reading"]["demand_star_equivalent"], 4.8
        )
        self.assertGreater(
            dense_axes["reading"]["demand_star_equivalent"], 6.0
        )

    def test_dense_stamina_correction_is_bounded_and_ignores_map_length(self):
        axes = {"stamina": emitted(9.8)}
        v09._stamina_overlay(
            axes,
            {
                "reading_density": 20.0,
                "v07_map_duration_ms": 600000.0,
            },
        )
        self.assertLessEqual(axes["stamina"]["demand_star_equivalent"], 10.0)
        # The correction intentionally has no effect once Stamina is already
        # above the validated dense-intensity region.
        self.assertEqual(axes["stamina"]["demand_star_equivalent"], 9.8)
        evidence = axes["stamina"]["evidence"][-1]
        self.assertNotIn("v07_map_duration_ms", evidence)


if __name__ == "__main__":
    unittest.main()
