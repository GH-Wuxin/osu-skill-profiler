from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import profile_semantics_v01 as semantics  # noqa: E402


def emitted_axis(value: float, *, confidence: str = "HIGH") -> dict:
    measure = semantics.AxisMeasure.observed(value, eligible_count=8)
    return semantics.apply_axis_measure(
        {},
        measure,
        method="TEST_MEASURE",
        scale_method="TEST_SCALE",
        component="test_component",
        evidence_tag="TEST",
        confidence=confidence,
    )


def complete_axes(
    *, auxiliary_value: float = 3.0, confidence: str = "HIGH"
) -> dict[str, dict]:
    stars = {
        "jump_aim": 9.0,
        "flow_aim": 5.5,
        "aim_control": 5.0,
        "spatial_precision": 4.5,
        "raw_speed": 4.0,
        "finger_control": 3.5,
        "reading": 3.0,
    }
    axes = {
        axis: emitted_axis(value, confidence=confidence)
        for axis, value in stars.items()
    }
    axes.update(
        stamina=emitted_axis(auxiliary_value, confidence=confidence),
        endurance=emitted_axis(auxiliary_value, confidence=confidence),
    )
    return axes


class ProfileSemanticsV01Tests(unittest.TestCase):
    def test_schema_and_policy_identify_confidence_aware_descriptor_semantics(self):
        result = semantics.classify_star_archetype(complete_axes())
        self.assertEqual(semantics.SCHEMA_VERSION, "profile_semantics_v0.2.0")
        self.assertEqual(
            result["schema_version"],
            "profile_archetype_v0.2.0",
        )
        self.assertEqual(
            result["policy_id"],
            "SEVEN_STAR_AXIS_DOMINANCE_WITH_BOUNDED_AUXILIARY_V02",
        )

    def test_missing_measure_is_not_observed_zero(self):
        missing = semantics.AxisMeasure.insufficient(
            reason="missing required input",
            missing_required_fields=("ls.required",),
        )
        output = semantics.apply_axis_measure(
            {"status": "EMITTED", "demand_star_equivalent": 7.0, "score": 0.7},
            missing,
            method="TEST_MEASURE",
            scale_method="TEST_SCALE",
            component="test_component",
            evidence_tag="TEST",
        )
        self.assertEqual(output["status"], semantics.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(output["demand_star_equivalent"])
        self.assertIsNone(output["score"])
        self.assertFalse(output["evidence"][0]["measure"]["evidence"]["observed_zero"])

        observed_zero = semantics.AxisMeasure.observed(0.0, eligible_count=4)
        zero_output = semantics.apply_axis_measure(
            {},
            observed_zero,
            method="TEST_MEASURE",
            scale_method="TEST_SCALE",
            component="test_component",
            evidence_tag="TEST",
        )
        self.assertEqual(zero_output["status"], semantics.AXIS_EMITTED)
        self.assertEqual(zero_output["demand_star_equivalent"], 0.0)
        self.assertEqual(zero_output["score"], 0.0)
        self.assertEqual(
            zero_output["score_semantics"],
            "VALUE_DIV_10_DISPLAY_RATIO_NOT_PROBABILITY",
        )
        self.assertTrue(
            zero_output["evidence"][0]["measure"]["evidence"]["observed_zero"]
        )

    def test_invalid_measure_and_axis_value_score_combinations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "observed_zero"):
            semantics.validate_axis_measure(
                semantics.AxisMeasure(
                    status=semantics.MEASURE_OK,
                    value=0.0,
                    evidence=semantics.EvidenceEnvelope(
                        eligible_count=1,
                        observed_zero=False,
                    ),
                )
            )
        with self.assertRaisesRegex(ValueError, "missing required"):
            semantics.validate_axis_measure(
                semantics.AxisMeasure(
                    status=semantics.MEASURE_OK,
                    value=1.0,
                    evidence=semantics.EvidenceEnvelope(
                        eligible_count=1,
                        missing_required_fields=("x",),
                    ),
                )
            )
        with self.assertRaisesRegex(ValueError, "value / 10"):
            semantics.validate_axis_output(
                {
                    "status": semantics.AXIS_EMITTED,
                    "demand_star_equivalent": 5.0,
                    "score": 0.6,
                }
            )

    def test_same_unit_summaries_and_missingness_propagate(self):
        axes = complete_axes(auxiliary_value=6.0)
        summaries = semantics.derive_profile_summaries(axes)
        self.assertEqual(summaries["aim_star_summary"]["value"], 6.0)
        self.assertEqual(summaries["tapping_star_summary"]["value"], 3.75)
        self.assertEqual(
            summaries["tapping_star_summary"]["source_axes"],
            ["raw_speed", "finger_control"],
        )
        self.assertEqual(summaries["bounded_sustain_summary"]["value"], 6.0)
        self.assertEqual(summaries["primary_star_summary"]["confidence"], "HIGH")
        self.assertEqual(
            summaries["overall_demand"]["status"],
            semantics.NOT_PUBLISHED_MIXED_UNITS,
        )
        self.assertIsNone(summaries["overall_demand"]["score"])
        for name in (
            "aim_star_summary",
            "tapping_star_summary",
            "primary_star_summary",
        ):
            self.assertEqual(
                summaries[name]["interpretation"],
                semantics.STAR_SUMMARY_INTERPRETATION,
            )
        self.assertEqual(
            summaries["bounded_sustain_summary"]["interpretation"],
            semantics.BOUNDED_SUMMARY_INTERPRETATION,
        )
        self.assertIn(
            "DIFFERENT_UNITS",
            summaries["overall_demand"]["interpretation"],
        )

        low_confidence_axes = complete_axes(confidence="HIGH")
        low_confidence_axes["reading"] = emitted_axis(3.0, confidence="LOW")
        low_confidence = semantics.derive_profile_summaries(low_confidence_axes)
        self.assertEqual(
            low_confidence["primary_star_summary"]["confidence"],
            "LOW",
        )
        self.assertEqual(
            low_confidence["aim_star_summary"]["confidence"],
            "HIGH",
        )

        axes["raw_speed"] = semantics.apply_axis_measure(
            axes["raw_speed"],
            semantics.AxisMeasure.insufficient(
                reason="missing cadence", missing_required_fields=("cadence",)
            ),
            method="TEST_MEASURE",
            scale_method="TEST_SCALE",
            component="test_component",
            evidence_tag="TEST",
        )
        missing = semantics.derive_profile_summaries(axes)
        self.assertEqual(missing["aim_star_summary"]["status"], semantics.AXIS_EMITTED)
        self.assertEqual(
            missing["tapping_star_summary"]["status"],
            semantics.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(missing["tapping_star_summary"]["missing_axes"], ["raw_speed"])
        self.assertEqual(
            missing["primary_star_summary"]["status"],
            semantics.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(missing["primary_star_summary"]["confidence"], "NONE")

    def test_auxiliary_axes_do_not_change_primary_archetype(self):
        low_aux = semantics.classify_star_archetype(complete_axes(auxiliary_value=0.0))
        high_aux = semantics.classify_star_archetype(complete_axes(auxiliary_value=10.0))
        primary_fields = (
            "status",
            "primary_type",
            "secondary_types",
            "dominant_axes",
            "confidence",
            "uncertainty_score",
            "demand_tier",
            "axis_scores",
            "missing_axes",
            "completeness",
            "decision_evidence",
        )
        for field in primary_fields:
            self.assertEqual(low_aux[field], high_aux[field], field)
        self.assertNotEqual(low_aux["auxiliary_traits"], high_aux["auxiliary_traits"])
        self.assertEqual(low_aux["missing_axes"], [])
        self.assertEqual(low_aux["completeness"], 1.0)

    def test_seven_of_seven_can_receive_high_confidence(self):
        result = semantics.classify_star_archetype(complete_axes())
        self.assertEqual(result["status"], "CLASSIFIED")
        self.assertEqual(result["primary_type"], "JUMP_AIM_DOMINANT")
        self.assertEqual(result["emitted_competition_axis_count"], 7)
        self.assertEqual(result["competition_axis_count"], 7)
        self.assertEqual(result["confidence"], "HIGH")

    def test_axis_confidence_caps_archetype_confidence(self):
        axes = complete_axes(confidence="HIGH")
        axes["reading"] = emitted_axis(3.0, confidence="LOW")
        result = semantics.classify_star_archetype(axes)

        self.assertEqual(result["status"], "CLASSIFIED")
        self.assertEqual(result["primary_type"], "JUMP_AIM_DOMINANT")
        self.assertEqual(result["confidence"], "LOW")
        self.assertEqual(result["input_confidence_cap"], "LOW")
        self.assertEqual(
            result["decision_evidence"][0]["structural_confidence"],
            "HIGH",
        )
        self.assertGreaterEqual(result["uncertainty_score"], 0.5)

    def test_archetype_declares_peak_descriptor_not_map_style_truth(self):
        result = semantics.classify_star_archetype(complete_axes())
        self.assertEqual(
            result["descriptor_semantics"],
            semantics.DESCRIPTOR_SEMANTICS,
        )
        self.assertIn("PEAK_LOCAL_DEMAND", result["descriptor_semantics"])
        self.assertIn("NOT_PREDOMINANT_MAP_STYLE", result["descriptor_semantics"])

    def test_six_of_seven_is_classified_at_low_confidence(self):
        axes = complete_axes()
        axes["reading"] = semantics.apply_axis_measure(
            axes["reading"],
            semantics.AxisMeasure.insufficient(reason="missing visibility"),
            method="TEST_MEASURE",
            scale_method="TEST_SCALE",
            component="test_component",
            evidence_tag="TEST",
        )
        result = semantics.classify_star_archetype(axes)
        self.assertEqual(result["status"], "CLASSIFIED")
        self.assertEqual(result["emitted_competition_axis_count"], 6)
        self.assertEqual(result["missing_axes"], ["reading"])
        self.assertEqual(result["confidence"], "LOW")

    def test_five_or_fewer_star_axes_abstain(self):
        axes = complete_axes()
        for axis in ("reading", "finger_control"):
            axes[axis] = semantics.apply_axis_measure(
                axes[axis],
                semantics.AxisMeasure.insufficient(reason=f"missing {axis}"),
                method="TEST_MEASURE",
                scale_method="TEST_SCALE",
                component="test_component",
                evidence_tag="TEST",
            )
        result = semantics.classify_star_archetype(axes)
        self.assertEqual(result["status"], semantics.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result["emitted_competition_axis_count"], 5)
        self.assertEqual(result["confidence"], "NONE")
        self.assertIsNone(result["primary_type"])

    def test_finite_extreme_values_are_not_clipped(self):
        extreme = emitted_axis(42.75)
        self.assertEqual(extreme["demand_star_equivalent"], 42.75)
        self.assertEqual(extreme["score"], 4.275)
        self.assertTrue(math.isfinite(extreme["score"]))

        axes = complete_axes()
        axes["jump_aim"] = extreme
        summaries = semantics.derive_profile_summaries(axes)
        expected = (42.75 + 5.5 + 5.0 + 4.5 + 4.0 + 3.5 + 3.0) / 7.0
        self.assertEqual(summaries["primary_star_summary"]["value"], expected)
        result = semantics.classify_star_archetype(axes)
        self.assertEqual(result["axis_scores"]["jump_aim"], 4.275)
        self.assertEqual(result["primary_type"], "JUMP_AIM_DOMINANT")


if __name__ == "__main__":
    unittest.main()
