"""Regression coverage for corrected corpus-QA infrastructure."""

from __future__ import annotations

import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import feature_qa  # noqa: E402
import foundation_remediation_qa  # noqa: E402
import local_signal_qa  # noqa: E402
from osu_skill_profiler.features.schema import FEATURE_SCHEMA, FEATURE_VERSION  # noqa: E402


class ScaleSafeStatisticsTests(unittest.TestCase):
    def test_extreme_finite_moments_remain_strict_json(self):
        accumulator = feature_qa._StreamAccumulator(exact=True, rng=random.Random(1))
        for value in (1.0e308, -1.0e308, 1.0, -1.0):
            accumulator.update(value)
        result = accumulator.finish()
        self.assertTrue(math.isfinite(result["mean"]))
        self.assertTrue(math.isfinite(result["std"]))
        json.dumps(result, allow_nan=False)

    def test_merged_scaled_summary_matches_direct_moments(self):
        rows = [{"ls.delta_time_ms": value} for value in (1.0e300, -1.0e300, 25.0, 50.0)]
        summary = local_signal_qa._map_signal_summaries(rows, seed=7)["ls.delta_time_ms"]
        merged = local_signal_qa._LocalSignalAccumulator(exact=False, rng=random.Random(7))
        merged.merge_map_summary(summary)
        direct = feature_qa._StreamAccumulator(exact=True, rng=random.Random(7))
        for row in rows:
            direct.update(row["ls.delta_time_ms"])
        merged_result = merged.finish()
        direct_result = direct.finish()
        self.assertEqual(merged_result["count"], direct_result["count"])
        self.assertAlmostEqual(merged_result["mean"] / 1.0e300, direct_result["mean"] / 1.0e300, places=12)
        self.assertAlmostEqual(merged_result["std"] / 1.0e300, direct_result["std"] / 1.0e300, places=12)
        json.dumps(summary, allow_nan=False)
        json.dumps(merged_result, allow_nan=False)

    def test_extreme_scale_pearson_is_finite(self):
        xs = [float(index) * 1.0e300 for index in range(1, 40)]
        ys = [value * 0.5 for value in xs]
        result = feature_qa._pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertTrue(math.isfinite(result))
        self.assertAlmostEqual(result, 1.0, places=12)


class ResumeCompletenessTests(unittest.TestCase):
    @staticmethod
    def _complete_record(sample_id: str) -> dict:
        return {
            "sample_id": sample_id,
            "ok": True,
            "feature_version": FEATURE_VERSION,
            "feature_count": len(FEATURE_SCHEMA),
            "features": {key: 0.0 for key in FEATURE_SCHEMA},
            "segment_count": 1,
            "index_span_consistent": True,
            "segment_nonfinite_count": 0,
            "agg_nonfinite_count": 0,
            "agg_serializable": True,
        }

    def test_resume_retries_failed_partial_stale_and_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.jsonl"
            valid = self._complete_record("valid")
            failed = {"sample_id": "failed", "ok": False}
            partial = {"sample_id": "partial", "ok": True}
            stale = {**self._complete_record("stale"), "feature_version": "0.1.0"}
            path.write_text(
                "\n".join(
                    [
                        json.dumps(valid, sort_keys=True),
                        json.dumps(failed, sort_keys=True),
                        json.dumps(partial, sort_keys=True),
                        json.dumps(stale, sort_keys=True),
                        json.dumps(valid, sort_keys=True),
                        "{truncated",
                    ]
                ),
                encoding="utf-8",
            )
            done = feature_qa._prepare_resume_records(path, True, feature_qa._resume_record_complete)
            self.assertEqual(done, {"valid"})
            retained = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["sample_id"] for row in retained], ["valid"])
            first_bytes = path.read_bytes()
            done_again = feature_qa._prepare_resume_records(path, True, feature_qa._resume_record_complete)
            self.assertEqual(done_again, {"valid"})
            self.assertEqual(path.read_bytes(), first_bytes)


class FoundationDeltaQaInfrastructureTests(unittest.TestCase):
    @staticmethod
    def _complete_delta_record(sample_id: str, checksum: str) -> dict:
        return {
            "sample_id": sample_id,
            "checksum": checksum,
            "status": "PASS",
            "qa_version": foundation_remediation_qa.QA_VERSION,
            "versions": foundation_remediation_qa.EXPECTED_VERSIONS,
            "object_count": 1,
            "slider_count": 0,
            "repeat_slider_count": 0,
            "feature_delta": {},
            "local_delta": {},
            "reference_delta": {},
            "feature_changed_field_count": 0,
            "local_changed_object_count": 0,
            "reference_changed_object_count": 0,
            "reference_reading_only_object_count": 0,
            "local_geometry_blocked_old": 0,
            "local_geometry_blocked_new": 0,
            "reference_geometry_blocked_old": 0,
            "reference_geometry_blocked_new": 0,
            "timing_ms": {
                "feature_both": 1.0,
                "local_old": 1.0,
                "local_new": 1.0,
                "reference_old": 1.0,
                "reference_new": 1.0,
                "total": 5.0,
            },
        }

    def test_resume_retries_failed_partial_stale_duplicate_and_nonfinite_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delta.jsonl"
            valid = self._complete_delta_record("valid", "sha256:valid")
            duplicate = self._complete_delta_record("duplicate", "sha256:duplicate")
            failed = {
                **self._complete_delta_record("failed", "sha256:failed"),
                "status": "FAIL",
            }
            partial = {
                "sample_id": "partial",
                "checksum": "sha256:partial",
                "status": "PASS",
            }
            stale = {
                **self._complete_delta_record("stale", "sha256:stale"),
                "qa_version": "0.1.0",
            }
            records = [
                {"sample_id": name, "checksum": f"sha256:{name}"}
                for name in ("valid", "duplicate", "failed", "partial", "stale", "nonfinite")
            ]
            path.write_text(
                "\n".join(
                    [
                        json.dumps(valid, sort_keys=True, allow_nan=False),
                        json.dumps(duplicate, sort_keys=True, allow_nan=False),
                        json.dumps(failed, sort_keys=True, allow_nan=False),
                        json.dumps(partial, sort_keys=True, allow_nan=False),
                        json.dumps(stale, sort_keys=True, allow_nan=False),
                        json.dumps(duplicate, sort_keys=True, allow_nan=False),
                        '{"sample_id":"nonfinite","status":"PASS","timing_ms":{"total":NaN}}',
                        "{truncated",
                    ]
                ),
                encoding="utf-8",
            )
            done = foundation_remediation_qa._prepare_resume_rows(path, True, records)
            self.assertEqual(set(done), {"valid"})
            retained = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["sample_id"] for row in retained], ["valid"])
            first_bytes = path.read_bytes()
            done_again = foundation_remediation_qa._prepare_resume_rows(path, True, records)
            self.assertEqual(set(done_again), {"valid"})
            self.assertEqual(path.read_bytes(), first_bytes)

    def test_extreme_finite_delta_has_strict_scaled_representation(self):
        delta = foundation_remediation_qa._field_delta(
            [{"signal": -1.0e308}],
            [{"signal": 1.0e308}],
        )
        stats = delta["signal"]
        self.assertIsNone(stats["abs_delta_sum"])
        self.assertTrue(stats["abs_delta_sum_overflow"])
        self.assertIsNone(stats["abs_delta_max"])
        self.assertTrue(stats["abs_delta_max_overflow"])
        self.assertTrue(math.isfinite(stats["abs_delta_sum_scale"]))
        self.assertTrue(math.isfinite(stats["abs_delta_sum_scaled"]))
        self.assertEqual(stats["magnitude_bins"], [0, 0, 0, 0, 0, 1])

        merged: dict[str, dict] = {}
        foundation_remediation_qa._merge_field_delta(merged, delta)
        foundation_remediation_qa._merge_field_delta(merged, delta)
        self.assertIsNone(merged["signal"]["abs_delta_sum"])
        self.assertTrue(merged["signal"]["abs_delta_sum_overflow"])
        json.dumps(merged, allow_nan=False)

    def test_large_operands_preserve_exact_magnitude_bin_boundary(self):
        left = 1.0e4
        right = left + 1000.0
        self.assertEqual(abs(right - left), 1000.0)
        delta = foundation_remediation_qa._field_delta(
            [{"signal": left}],
            [{"signal": right}],
        )
        stats = delta["signal"]
        self.assertEqual(stats["abs_delta_sum"], 1000.0)
        self.assertEqual(stats["abs_delta_max"], 1000.0)
        self.assertEqual(stats["magnitude_bins"], [0, 0, 0, 0, 1, 0])

    def test_new_missing_value_fails_bounded_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            selection = Path(tmp) / "selection.jsonl"
            selection.write_text('{}\n', encoding="utf-8")
            stats = foundation_remediation_qa._empty_field_delta()
            stats["changed"] = 1
            stats["missing_introduced"] = 1
            row = self._complete_delta_record("missing", "sha256:missing")
            row["feature_delta"] = {"signal": stats}
            row["feature_changed_field_count"] = 1
            summary = foundation_remediation_qa._summarize(
                [row],
                selection=selection,
                workers=1,
                wall_seconds=0.0,
            )
            self.assertEqual(summary["status"], "FAIL")
            self.assertEqual(summary["new_missing_count"], 1)
            json.dumps(summary, allow_nan=False)

    def test_nonfinite_introduced_and_resolved_counted_independently(self):
        delta = foundation_remediation_qa._field_delta(
            [{"signal": float("nan"), "other": 1.0}],
            [{"signal": 1.0, "other": float("nan")}],
        )
        resolved = delta["signal"]
        self.assertEqual(resolved["nonfinite_old"], 1)
        self.assertEqual(resolved["nonfinite_new"], 0)
        self.assertEqual(resolved["nonfinite_resolved"], 1)
        self.assertEqual(resolved["nonfinite_introduced"], 0)

        introduced = delta["other"]
        self.assertEqual(introduced["nonfinite_old"], 0)
        self.assertEqual(introduced["nonfinite_new"], 1)
        self.assertEqual(introduced["nonfinite_resolved"], 0)
        self.assertEqual(introduced["nonfinite_introduced"], 1)

    def test_merge_keeps_introduced_and_resolved_independent(self):
        target: dict[str, dict] = {}
        resolved = foundation_remediation_qa._field_delta(
            [{"signal": float("nan")}],
            [{"signal": 1.0}],
        )
        introduced = foundation_remediation_qa._field_delta(
            [{"signal": 1.0}],
            [{"signal": float("nan")}],
        )
        foundation_remediation_qa._merge_field_delta(target, resolved)
        foundation_remediation_qa._merge_field_delta(target, introduced)
        stats = target["signal"]
        self.assertEqual(stats["nonfinite_resolved"], 1)
        self.assertEqual(stats["nonfinite_introduced"], 1)
        self.assertEqual(stats["nonfinite_old"], 1)
        self.assertEqual(stats["nonfinite_new"], 1)

    def test_summary_reports_resolved_and_introduced_nonfinite_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            selection = Path(tmp) / "selection.jsonl"
            selection.write_text('{}\n', encoding="utf-8")

            resolved_row = self._complete_delta_record("resolved", "sha256:resolved")
            resolved_stats = foundation_remediation_qa._field_delta(
                [{"signal": float("nan")}],
                [{"signal": 1.0}],
            )
            resolved_row["feature_delta"] = resolved_stats
            resolved_row["feature_changed_field_count"] = len(resolved_stats)
            resolved_summary = foundation_remediation_qa._summarize(
                [resolved_row],
                selection=selection,
                workers=1,
                wall_seconds=0.0,
            )
            self.assertEqual(resolved_summary["status"], "PASS")
            self.assertEqual(resolved_summary["resolved_nonfinite_count"], 1)
            self.assertEqual(resolved_summary["new_nonfinite_count"], 0)

            introduced_row = self._complete_delta_record("introduced", "sha256:introduced")
            introduced_stats = foundation_remediation_qa._field_delta(
                [{"signal": 1.0}],
                [{"signal": float("nan")}],
            )
            introduced_row["feature_delta"] = introduced_stats
            introduced_row["feature_changed_field_count"] = len(introduced_stats)
            introduced_summary = foundation_remediation_qa._summarize(
                [introduced_row],
                selection=selection,
                workers=1,
                wall_seconds=0.0,
            )
            self.assertEqual(introduced_summary["status"], "FAIL")
            self.assertEqual(introduced_summary["resolved_nonfinite_count"], 0)
            self.assertEqual(introduced_summary["new_nonfinite_count"], 1)

    def test_resume_rejects_field_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delta.jsonl"
            row = self._complete_delta_record("mismatch", "sha256:mismatch")
            row["feature_changed_field_count"] = 1
            path.write_text(
                json.dumps(row, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            records = [{"sample_id": "mismatch", "checksum": "sha256:mismatch"}]
            done = foundation_remediation_qa._prepare_resume_rows(path, True, records)
            self.assertEqual(done, {})
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_resume_rejects_internal_bounds_violations(self):
        mutations = [
            {"object_count": 0, "slider_count": 1},
            {"repeat_slider_count": 1},
            {"local_changed_object_count": 2},
            {"reference_changed_object_count": 2},
            {"reference_reading_only_object_count": 1},
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "delta.jsonl"
                    row = self._complete_delta_record(f"bad{index}", f"sha256:bad{index}")
                    row.update(mutation)
                    path.write_text(
                        json.dumps(row, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8",
                    )
                    records = [{"sample_id": f"bad{index}", "checksum": f"sha256:bad{index}"}]
                    done = foundation_remediation_qa._prepare_resume_rows(path, True, records)
                    self.assertEqual(done, {})
                    self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_resume_rejects_unknown_layer_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delta.jsonl"
            row = self._complete_delta_record("unknown", "sha256:unknown")
            row["local_delta"] = {
                "ls.not_a_real_signal": foundation_remediation_qa._empty_field_delta(),
            }
            path.write_text(
                json.dumps(row, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            records = [{"sample_id": "unknown", "checksum": "sha256:unknown"}]
            done = foundation_remediation_qa._prepare_resume_rows(path, True, records)
            self.assertEqual(done, {})
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_resume_rejects_stale_qa_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delta.jsonl"
            row = self._complete_delta_record("stale", "sha256:stale")
            row["qa_version"] = "0.2.0"
            path.write_text(
                json.dumps(row, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            records = [{"sample_id": "stale", "checksum": "sha256:stale"}]
            done = foundation_remediation_qa._prepare_resume_rows(path, True, records)
            self.assertEqual(done, {})
            self.assertEqual(path.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
