"""Synthetic hard-gate tests for target leakage enforcement v0.1."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from osu_skill_profiler.dataset.leakage import (
    LEAKAGE_POLICY_VERSION,
    SignalRole,
    audit_candidate_schema,
)

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "target_leakage_audit.py"


def _candidate(**overrides):
    payload = {
        "schema_version": "0.1.0",
        "input_fields": ["ls.adjusted_delta_time_ms", "ls.jump_distance_cs_normalised"],
        "target_fields": ["label.future_human_flow"],
        "weak_label_sources": [],
        "declared_lineage": {},
        "field_roles": {"label.future_human_flow": SignalRole.HUMAN_LABEL.value},
        "split_fields": ["split"],
        "provenance_fields": ["ls.provenance"],
        "challenge_fields": ["reference_disagreement_flag"],
        "offline_evaluation_fields": [],
    }
    payload.update(overrides)
    return payload


class LeakagePolicyTests(unittest.TestCase):
    def assert_fails_with(self, candidate, code):
        result = audit_candidate_schema(candidate)
        self.assertFalse(result.passed, result.as_dict())
        self.assertIn(code, {violation.code for violation in result.violations})

    def test_observable_to_independent_future_label_passes(self):
        result = audit_candidate_schema(_candidate())
        self.assertTrue(result.passed, result.as_dict())
        self.assertEqual(result.policy_version, LEAKAGE_POLICY_VERSION)

    def test_reference_input_to_reference_derived_target_fails(self):
        self.assert_fails_with(
            _candidate(
                input_fields=["ref.ppy.flow_include_sliders"],
                target_fields=["label.derived_ref_flow"],
                declared_lineage={"label.derived_ref_flow": ["ref.ppy.flow_include_sliders"]},
                field_roles={"label.derived_ref_flow": SignalRole.WEAK_LABEL_SOURCE.value},
                weak_label_sources=["ref.ppy.flow_include_sliders"],
            ),
            "TARGET_LINEAGE_LEAKAGE",
        )

    def test_deterministic_derivative_of_reference_target_fails(self):
        self.assert_fails_with(
            _candidate(
                input_fields=["derived.ref_speed_zscore"],
                target_fields=["label.derived_ref_speed"],
                declared_lineage={
                    "derived.ref_speed_zscore": ["ref.ppy.speed"],
                    "label.derived_ref_speed": ["ref.ppy.speed"],
                },
                field_roles={
                    "derived.ref_speed_zscore": SignalRole.OBSERVABLE_INPUT_CANDIDATE.value,
                    "label.derived_ref_speed": SignalRole.WEAK_LABEL_SOURCE.value,
                },
                weak_label_sources=["ref.ppy.speed"],
            ),
            "TARGET_LINEAGE_LEAKAGE",
        )

    def test_split_membership_input_fails(self):
        self.assert_fails_with(_candidate(input_fields=["split"]), "FORBIDDEN_INPUT_ROLE")

    def test_challenge_flag_input_fails(self):
        self.assert_fails_with(_candidate(input_fields=["reference_disagreement_flag"]), "FORBIDDEN_INPUT_ROLE")

    def test_target_directly_in_features_fails(self):
        self.assert_fails_with(_candidate(input_fields=["label.future_human_flow"]), "TARGET_IN_INPUTS")

    def test_reference_offline_evaluation_only_passes(self):
        result = audit_candidate_schema(_candidate(offline_evaluation_fields=["ref.ppy.flow_include_sliders"]))
        self.assertTrue(result.passed, result.as_dict())

    def test_unknown_input_is_default_denied(self):
        self.assert_fails_with(_candidate(input_fields=["mystery.feature"]), "UNREGISTERED_INPUT")

    def test_unknown_input_cannot_self_promote_without_lineage(self):
        self.assert_fails_with(
            _candidate(
                input_fields=["mystery.feature"],
                field_roles={
                    "mystery.feature": SignalRole.OBSERVABLE_INPUT_CANDIDATE.value,
                    "label.future_human_flow": SignalRole.HUMAN_LABEL.value,
                },
            ),
            "UNREGISTERED_INPUT",
        )

    def test_reference_role_cannot_be_overridden(self):
        self.assert_fails_with(
            _candidate(
                input_fields=["ref.ppy.speed"],
                field_roles={
                    "ref.ppy.speed": SignalRole.OBSERVABLE_INPUT_CANDIDATE.value,
                    "label.future_human_flow": SignalRole.HUMAN_LABEL.value,
                },
            ),
            "ROLE_OVERRIDE_FORBIDDEN",
        )

    def test_unknown_lineage_source_fails(self):
        self.assert_fails_with(
            _candidate(declared_lineage={"label.future_human_flow": ["mystery.source"]}),
            "UNREGISTERED_LINEAGE_SOURCE",
        )

    def test_legacy_misnamed_repeat_field_is_forbidden(self):
        self.assert_fails_with(_candidate(input_fields=["slider.repeats_total"]), "FORBIDDEN_INPUT_ROLE")


class LeakageCliTests(unittest.TestCase):
    def test_cli_exit_codes_and_exact_status(self):
        with tempfile.TemporaryDirectory(prefix="leakage-audit-") as temp_dir:
            path = Path(temp_dir) / "candidate.json"
            path.write_text(json.dumps(_candidate()), encoding="utf-8")
            passed = subprocess.run(
                [sys.executable, str(TOOL), str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(json.loads(passed.stdout)["status"], "PASS")

            path.write_text(json.dumps(_candidate(input_fields=["split"])), encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, str(TOOL), str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1, failed.stderr)
            payload = json.loads(failed.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(payload["violations"])


if __name__ == "__main__":
    unittest.main()
