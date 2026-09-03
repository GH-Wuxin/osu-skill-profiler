from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import profile_semantics_v02 as semantics  # noqa: E402


def supported_measure(*, confidence: float = 0.2, established: float = 8.5):
    return {
        "status": "FULL",
        "eligible_count": 20,
        "physical_peak": {"star": 12.75, "source": "atomic"},
        "evidence_confidence": {"value": confidence, "coverage": 1.0},
        "establishment": {"frontier_star": established, "event_mass": 12.0},
        "sustain": {"frontier_star": 7.25, "duration_ms": 1800.0},
        "recurrence": {"frontier_star": 6.75, "episode_count": 3},
        "public_frontier": {
            "frontier_star": established,
            "selected_component": "establishment",
            "eligible_components": ["establishment", "recurrence"],
            "policy_id": "TEST_MAX_ER",
            "selection_method": "MAX_SUPPORT_QUALIFIED_FRONTIER",
            "confidence_affects_selection": False,
            "physical_peak_is_candidate": False,
        },
    }


class ProfileSemanticsV02Tests(unittest.TestCase):
    def apply(self, raw):
        return semantics.apply_supported_axis_measure(
            {},
            raw,
            method="TEST_SUPPORT_FRONTIER",
            scale_method="TEST_UNBOUNDED_SCALE",
            component="test_axis",
            evidence_tag="TEST_EVIDENCE",
        )

    def test_public_value_is_the_explicitly_selected_frontier(self):
        output = self.apply(supported_measure())
        self.assertEqual(output["stars"], 8.5)
        self.assertEqual(output["demand_star_equivalent"], 8.5)
        self.assertEqual(output["score"], 0.85)
        self.assertEqual(output["establishment"]["frontier_star"], 8.5)
        self.assertEqual(output["physical_peak"]["star"], 12.75)
        self.assertEqual(
            output["public_value_semantics"],
            semantics.PUBLIC_VALUE_SEMANTICS,
        )
        self.assertEqual(
            output["public_frontier"]["selected_component"],
            "establishment",
        )

    def test_recurrence_can_be_selected_without_confidence_or_peak_blending(self):
        raw = supported_measure()
        raw["recurrence"]["frontier_star"] = 11.25
        raw["public_frontier"].update(
            frontier_star=11.25,
            selected_component="recurrence",
        )
        output = self.apply(raw)

        self.assertEqual(output["stars"], 11.25)
        self.assertEqual(output["physical_peak"]["star"], 12.75)
        self.assertEqual(
            output["public_frontier"]["selected_component"], "recurrence"
        )

    def test_confidence_never_attenuates_any_demand_value(self):
        low = self.apply(supported_measure(confidence=0.05))
        high = self.apply(supported_measure(confidence=0.95))
        for key in ("stars", "demand_star_equivalent", "physical_peak"):
            self.assertEqual(low[key], high[key])
        self.assertNotEqual(
            low["evidence_confidence"], high["evidence_confidence"]
        )

    def test_unbounded_values_are_not_clipped(self):
        raw = supported_measure(established=14.25)
        raw["physical_peak"]["star"] = 31.5
        raw["sustain"]["frontier_star"] = 12.0
        raw["recurrence"]["frontier_star"] = 11.0
        output = self.apply(raw)
        self.assertEqual(output["stars"], 14.25)
        self.assertEqual(output["physical_peak"]["star"], 31.5)

    def test_missing_support_is_not_an_observed_zero(self):
        output = self.apply(
            {
                "status": "INSUFFICIENT",
                "reason": "NO_VALID_EVENTS",
                "eligible_count": 0,
            }
        )
        self.assertEqual(output["status"], semantics.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(output["stars"])
        self.assertIsNone(output["demand_star_equivalent"])
        self.assertIsNone(output["physical_peak"])

    def test_inherited_axes_are_marked_without_inventing_frontiers(self):
        output = semantics.annotate_legacy_axis(
            {
                "status": semantics.AXIS_EMITTED,
                "demand_star_equivalent": 6.25,
                "score": 0.625,
            },
            source_contract="beta7_local_axis_value_v01",
        )
        self.assertEqual(output["stars"], 6.25)
        self.assertFalse(output["support_frontiers_available"])
        self.assertNotIn("physical_peak", output)


if __name__ == "__main__":
    unittest.main()
