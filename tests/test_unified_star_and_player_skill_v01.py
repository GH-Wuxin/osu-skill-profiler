from __future__ import annotations

import copy
import sys
import unittest


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01.player_skill_rating_v01 import (  # noqa: E402
    DEMONSTRATED,
    NOT_DEMONSTRATED,
    estimate_player_skill_profile,
    make_evidence_record,
)
from map_demand_v01.unified_star_scale_v01 import (  # noqa: E402
    apply_unified_star_scale,
    fit_calibration,
    map_axis_value,
)
from osu_skill_profiler.formal_release import AXES  # noqa: E402


def _calibration():
    records = []
    for index in range(8):
        records.append(
            {
                "map_id": f"map-{index}",
                "ppy_nm_star": float(index + 1),
                "stratum": f"family-{index % 2}",
                "axes": {axis: float(index) for axis in AXES},
            }
        )
    return fit_calibration(
        records,
        [float(index) for index in range(8)],
        source_scope="unit-test",
        min_formal_maps=8,
        min_formal_axis_samples=8,
        min_formal_strata=2,
    )


class UnifiedStarScaleTests(unittest.TestCase):
    def test_equivalent_empirical_rank_maps_to_the_same_reference_star(self):
        calibration = _calibration()
        left = map_axis_value(calibration, "jump_aim", 3.0)
        right = map_axis_value(calibration, "raw_speed", 3.0)
        self.assertEqual(left["status"], "ADMITTED")
        self.assertEqual(left["value"], right["value"])

    def test_out_of_support_is_not_silently_low(self):
        calibration = _calibration()
        result = map_axis_value(calibration, "jump_aim", 99.0)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "raw_value_outside_calibration_support")

    def test_overlay_keeps_frozen_fields_and_adds_new_fields(self):
        calibration = _calibration()
        output = {
            "identity": {"algorithm_id": "FORMAL_MAP_DEMAND_V040"},
            "axes": {
                axis: {
                    "status": "EMITTED",
                    "demand_star_equivalent": 3.0,
                    "unit": "star_equivalent",
                }
                for axis in AXES
            },
        }
        before = copy.deepcopy(output)
        result = apply_unified_star_scale(output, calibration)
        self.assertEqual(output, before)
        self.assertEqual(
            result["axes"]["jump_aim"]["demand_star_equivalent"],
            before["axes"]["jump_aim"]["demand_star_equivalent"],
        )
        self.assertIn("unified_star_equivalent", result["axes"]["jump_aim"])
        self.assertEqual(
            result["identity"]["algorithm_id"], "FORMAL_MAP_DEMAND_V040"
        )
        self.assertEqual(result["unified_star_scale"]["status"], "ADMITTED")


class PlayerSkillRatingTests(unittest.TestCase):
    def _record(self, map_id, timestamp, demand, status):
        return make_evidence_record(
            player_id="player-1",
            map_id=map_id,
            timestamp=timestamp,
            source="normalized_score_fixture",
            map_demand={
                "jump_aim": {
                    "unified_star_equivalent": demand,
                    "unified_star_status": "ADMITTED",
                }
            },
            axis_outcomes={
                "jump_aim": {
                    "status": status,
                    "evidence_count": 1,
                    "source_detail": "fixture",
                }
            },
            normalization_id="score-normalization-v1",
        )

    def test_player_rating_is_an_interval_from_multiple_maps_and_times(self):
        records = [
            self._record("a", "2026-01-01T00:00:00Z", 3.0, DEMONSTRATED),
            self._record("b", "2026-01-02T00:00:00Z", 4.5, DEMONSTRATED),
            self._record("c", "2026-01-03T00:00:00Z", 6.0, NOT_DEMONSTRATED),
        ]
        result = estimate_player_skill_profile(
            records,
            normalization_id="score-normalization-v1",
            reference_range=(0.0, 10.0),
        )
        axis = result["axes"]["jump_aim"]
        self.assertEqual(axis["status"], "ADMITTED")
        self.assertEqual(axis["uncertainty"], {"lower": 4.5, "upper": 6.0})
        self.assertEqual(axis["rating"], 5.25)
        self.assertEqual(result["overall"]["status"], "NOT_EMITTED")

    def test_failures_alone_do_not_become_low_skill(self):
        records = [
            self._record("a", "2026-01-01T00:00:00Z", 3.0, NOT_DEMONSTRATED),
            self._record("b", "2026-01-02T00:00:00Z", 4.0, NOT_DEMONSTRATED),
            self._record("c", "2026-01-03T00:00:00Z", 5.0, NOT_DEMONSTRATED),
        ]
        result = estimate_player_skill_profile(records)
        axis = result["axes"]["jump_aim"]
        self.assertEqual(axis["status"], "UNKNOWN")
        self.assertIsNone(axis["rating"])
        self.assertEqual(axis["reason"], "no_demonstrated_capacity_evidence")

    def test_candidate_map_scale_cannot_become_admitted_player_rating(self):
        records = []
        for index, status in enumerate(
            (DEMONSTRATED, DEMONSTRATED, NOT_DEMONSTRATED)
        ):
            records.append(
                make_evidence_record(
                    player_id="player-1",
                    map_id=f"candidate-{index}",
                    timestamp=f"2026-02-0{index + 1}T00:00:00Z",
                    source="normalized_score_fixture",
                    map_demand={
                        "jump_aim": {
                            "unified_star_equivalent": 3.0 + index,
                            "unified_star_status": "CANDIDATE",
                        }
                    },
                    axis_outcomes={"jump_aim": {"status": status}},
                    normalization_id="score-normalization-v1",
                )
            )
        result = estimate_player_skill_profile(records)
        self.assertEqual(result["axes"]["jump_aim"]["status"], "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
