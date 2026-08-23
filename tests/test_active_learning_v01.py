from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from osu_skill_profiler.active_learning.batch_v01 import BatchConfig, build_batch, validate_duplicate_policy
from osu_skill_profiler.active_learning.contracts_v01 import (
    AnnotationEntity, AnnotationResponse, ConfidenceBand, ControlType,
    PairwiseAnswer, PresentationOrder, ResponseLedger, ScoreComponents,
    SelectionReason, TaskScope, build_task, canonical_answer,
    response_to_human_evidence,
)
from osu_skill_profiler.active_learning.metrics_v01 import annotation_metrics
from osu_skill_profiler.active_learning.presentation_v01 import blind_task_payload
from osu_skill_profiler.active_learning.selection_v01 import Candidate, CONTAINED_DEFECT_MAPS
from osu_skill_profiler.weak_supervision.contracts_v01 import EntityRef, EntityScope


ROOT = Path(__file__).resolve().parents[1]
UNAVAILABLE_TOOL = ROOT / "tools/active_learning_unavailable_v01.py"
SPEC = importlib.util.spec_from_file_location("active_learning_unavailable_v01", UNAVAILABLE_TOOL)
UNAVAILABLE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(UNAVAILABLE)


def checksum(index: int) -> str:
    return "sha256:" + f"{index:064x}"


def components(value: float = 0.5) -> ScoreComponents:
    return ScoreComponents(value, 0.0, value, value, value, value, 0.0, value)


def entity(index: int, scope: EntityScope = EntityScope.MAP, segment: int = 0, map_index: int | None = None) -> AnnotationEntity:
    map_id = index if map_index is None else map_index
    ref = EntityRef(scope, checksum(map_id)) if scope == EntityScope.MAP else EntityRef(
        scope, checksum(map_id), segment, segment * 5000.0, segment * 5000.0 + 5000.0,
    )
    return AnnotationEntity(ref, f"entity-{index}", f"set-{index % 20}", f"mapper-{index % 25}", {"object_count": 100 + index})


def candidate(index: int, proposition: str, scope: EntityScope, signal: float, map_index: int | None = None) -> Candidate:
    ent = entity(index, scope, segment=index, map_index=map_index)
    return Candidate(
        f"candidate-{index}-{scope.value.lower()}-{proposition[-4:]}", proposition, "0.1.0", ent,
        ("EMITTED",), ("POSITIVE",), f"sha256:{index:064x}", ("rule",), (),
        f"{scope.value.lower()}:{index % 8}", signal, components(0.5), 0.5, ("test",),
    )


def task(a: AnnotationEntity | None = None, b: AnnotationEntity | None = None, **overrides):
    a = a or entity(1)
    b = b or entity(2)
    values = dict(
        batch_id="batch-1", proposition_key="ws01.provisional.test", proposition_version="0.1.0",
        scope=TaskScope.MAP_PAIR if a.ref.scope == EntityScope.MAP else TaskScope.SEGMENT_PAIR,
        entity_a=a, entity_b=b, selection_reason=SelectionReason.INFORMATIVE_UNCERTAIN,
        selection_score_components=components(), acquisition_score=0.5,
        weak_evidence_snapshot={"sha256": "abc"}, provenance={"source": "synthetic"},
    )
    values.update(overrides)
    return build_task(**values)


def response(annotation_task, answer=PairwiseAnswer.A_SLIGHTLY_HIGHER, response_id="response-1", annotator="annotator-1"):
    return AnnotationResponse(
        response_id, annotation_task.task_id, annotation_task.task_version, annotation_task.batch_id,
        annotator, "session-1", answer, annotation_task.presentation_order, 1234,
        ConfidenceBand.MEDIUM, ("reason-visible",), {"client": "test"},
    )


class UnavailableClassificationTests(unittest.TestCase):
    @unittest.skipUnless(
        all(path.exists() for path in (
            UNAVAILABLE.DEFAULT_EVIDENCE,
            UNAVAILABLE.DEFAULT_FEATURE,
            UNAVAILABLE.DEFAULT_LOCAL,
            UNAVAILABLE.DEFAULT_REFERENCE,
        )),
        "requires local weak-supervision and QA datasets",
    )
    def test_real_pilot_classification_is_complete_and_stable(self):
        classified, summary = UNAVAILABLE.classify_all(
            UNAVAILABLE.DEFAULT_EVIDENCE, UNAVAILABLE.DEFAULT_FEATURE,
            UNAVAILABLE.DEFAULT_LOCAL, UNAVAILABLE.DEFAULT_REFERENCE,
        )
        self.assertEqual(len(classified), 42)
        self.assertEqual(summary["classification_counts"], {
            "legitimate_unavailable": 41, "unexpected_unavailable": 1, "unresolved": 0,
        })
        self.assertEqual(summary["active_learning_gate"], "PASS")
        self.assertEqual(summary["unexpected_defects"][0]["defect_id"], "ALV01-UNAVAILABLE-001")
        self.assertIn(checksum(int(next(iter(CONTAINED_DEFECT_MAPS))[7:], 16)), CONTAINED_DEFECT_MAPS)


class ContractTests(unittest.TestCase):
    def test_cross_scope_pair_rejected(self):
        with self.assertRaises(ValueError):
            task(entity(1), entity(2, EntityScope.SEGMENT, 2))

    def test_cannot_judge_is_abstention_not_equality(self):
        t = task()
        evidence = response_to_human_evidence(t, response(t, PairwiseAnswer.CANNOT_JUDGE))
        self.assertEqual(evidence.status.value, "ABSTAINED")
        self.assertIsNone(evidence.canonical_ordinal)
        self.assertEqual(evidence.raw_answer, PairwiseAnswer.CANNOT_JUDGE)

    def test_orientation_normalization(self):
        a, b = entity(5), entity(1)
        t = task(a, b, presentation_order=PresentationOrder.BA)
        self.assertEqual(canonical_answer(t, response(t, PairwiseAnswer.A_CLEARLY_HIGHER)), PairwiseAnswer.A_CLEARLY_HIGHER)

    def test_ledger_rejects_duplicate_unknown_task_and_annotator(self):
        t = task()
        with self.assertRaises(ValueError):
            ResponseLedger([t, t], ["annotator-1"])
        ledger = ResponseLedger([t], ["annotator-1"])
        row = response(t)
        ledger.add(row)
        with self.assertRaises(ValueError):
            ledger.add(row)
        with self.assertRaises(ValueError):
            ResponseLedger([t], ["annotator-2"]).add(response(t))
        unknown = task(entity(3), entity(4))
        with self.assertRaises(ValueError):
            ResponseLedger([t], ["annotator-1"]).add(response(unknown))

    def test_contradictory_human_annotations_are_preserved(self):
        t = task()
        ledger = ResponseLedger([t], ["annotator-1", "annotator-2"])
        first = ledger.add(response(t, PairwiseAnswer.A_CLEARLY_HIGHER, "response-a", "annotator-1"))
        second = ledger.add(response(t, PairwiseAnswer.B_CLEARLY_HIGHER, "response-b", "annotator-2"))
        self.assertEqual((first.canonical_ordinal, second.canonical_ordinal), (2, -2))

    def test_blind_payload_hides_internal_metadata(self):
        t = task(
            proposition_key="ws01.provisional.movement_demand_high",
            weak_evidence_snapshot={"secret": "weak"},
            provenance={"challenge_categories": ["pathological"], "split": "test"},
            control_type=ControlType.EASY_ANCHOR,
        )
        payload = blind_task_payload(t)
        text = json.dumps(payload, sort_keys=True)
        for forbidden in ("weak", "challenge", "pathological", "control", "split", "sampling_groups"):
            self.assertNotIn(forbidden, text.lower())
        self.assertIn("cursor movement", payload["proposition"]["question"])


class BatchTests(unittest.TestCase):
    def _pool(self):
        props = ["ws01.provisional.movement_demand_high", "ws01.provisional.dense_timing_pressure_high", "ws01.provisional.slider_tracking_travel_high"]
        rows = []
        for scope in (EntityScope.MAP, EntityScope.SEGMENT):
            for p_index, proposition in enumerate(props):
                if scope == EntityScope.MAP and "slider_tracking" in proposition:
                    continue
                for index in range(1, 101):
                    rows.append(candidate(index + p_index * 200 + (1000 if scope == EntityScope.SEGMENT else 0), proposition, scope, (index % 20) / 20.0))
        return rows

    def test_deterministic_batch_and_controls(self):
        config = BatchConfig(map_tasks=5, segment_tasks=10, exact_repeats=2, inversions=2, max_ordinary_per_map=4)
        first, _ = build_batch(self._pool(), config)
        second, _ = build_batch(list(reversed(self._pool())), config)
        self.assertEqual([row.as_dict() for row in first], [row.as_dict() for row in second])
        self.assertEqual(sum(row.control_type == ControlType.EXACT_REPEAT for row in first), 2)
        self.assertEqual(sum(row.control_type == ControlType.AB_INVERSION for row in first), 2)

    def test_accidental_duplicate_rejected_and_explicit_repeat_accepted(self):
        base = task()
        duplicate = task()
        with self.assertRaises(ValueError):
            validate_duplicate_policy([base, duplicate])
        repeat = task(
            control_type=ControlType.EXACT_REPEAT, selection_reason=SelectionReason.EXACT_REPEAT,
            source_task_id=base.task_id, control_group_id="control-1",
        )
        validate_duplicate_policy([base, repeat])

    def test_inversion_control_normalizes_to_source_orientation(self):
        rows = self._pool()
        tasks, _ = build_batch(rows, BatchConfig(map_tasks=3, segment_tasks=3, exact_repeats=1, inversions=1, max_ordinary_per_map=4))
        inversion = next(row for row in tasks if row.control_type == ControlType.AB_INVERSION)
        source = next(row for row in tasks if row.task_id == inversion.source_task_id)
        source_answer = PairwiseAnswer.A_SLIGHTLY_HIGHER
        inversion_answer = PairwiseAnswer.B_SLIGHTLY_HIGHER
        self.assertEqual(
            canonical_answer(source, response(source, source_answer, "source-response")),
            canonical_answer(inversion, response(inversion, inversion_answer, "inversion-response")),
        )

    def test_all_scores_equal_and_one_map_dominates_are_bounded(self):
        rows = [candidate(index, "ws01.provisional.movement_demand_high", EntityScope.MAP, 0.5) for index in range(1, 50)]
        tasks, diagnostics = build_batch(rows, BatchConfig(map_tasks=5, segment_tasks=0, exact_repeats=0, inversions=0, max_ordinary_per_map=2))
        self.assertEqual(len(tasks), 5)
        self.assertLessEqual(diagnostics["diversity"]["max_ordinary_tasks_per_map"], 2)
        dominated = [candidate(index, "ws01.provisional.slider_tracking_travel_high", EntityScope.SEGMENT, 0.5, map_index=1) for index in range(1, 20)]
        with self.assertRaises(ValueError):
            build_batch(dominated, BatchConfig(map_tasks=0, segment_tasks=5, exact_repeats=0, inversions=0, max_ordinary_per_map=2))

    def test_insufficient_candidates_and_missing_weak_evidence_fail(self):
        with self.assertRaises(ValueError):
            build_batch([], BatchConfig(map_tasks=1, segment_tasks=0, exact_repeats=0, inversions=0))
        with self.assertRaises(ValueError):
            Candidate("candidate-x", "p", "0.1.0", entity(1), ("UNAVAILABLE",), (), checksum(9), ("rule",), (), "b", 0.5, components(), 0.5, ())
        with self.assertRaises(ValueError):
            Candidate("candidate-y", "p", "0.1.0", entity(1), (), (), checksum(9), (), (), "b", 0.5, components(), 0.5, ())


class MetricTests(unittest.TestCase):
    def test_position_repeat_inversion_and_abstention_metrics(self):
        base = task(control_type=ControlType.EASY_ANCHOR, diagnostic_expected_canonical_sign=1)
        repeat = task(
            control_type=ControlType.EXACT_REPEAT, selection_reason=SelectionReason.EXACT_REPEAT,
            source_task_id=base.task_id, control_group_id="control-r",
        )
        inversion = task(
            base.entity_a, base.entity_b, control_type=ControlType.AB_INVERSION,
            selection_reason=SelectionReason.AB_INVERSION, source_task_id=base.task_id,
            control_group_id="control-i", presentation_order=PresentationOrder.BA,
        )
        responses = [
            response(base, PairwiseAnswer.A_CLEARLY_HIGHER, "r1"),
            response(repeat, PairwiseAnswer.A_SLIGHTLY_HIGHER, "r2"),
            response(inversion, PairwiseAnswer.A_SLIGHTLY_HIGHER, "r3"),
            response(base, PairwiseAnswer.CANNOT_JUDGE, "r4", "annotator-2"),
        ]
        metrics = annotation_metrics([base, repeat, inversion], responses)
        self.assertEqual(metrics["abstention_count"], 1)
        self.assertIsNotNone(metrics["position_bias"]["first_presented_direction_rate"])
        self.assertGreaterEqual(metrics["intra_annotator_consistency"]["comparable_controls"], 1)
        self.assertIn("strict_ordinal_rate", metrics["intra_annotator_consistency"])
        self.assertIn("directional_rate", metrics["intra_annotator_consistency"])
        self.assertIn("mean_ordinal_distance", metrics["intra_annotator_consistency"])
        self.assertGreaterEqual(metrics["inversion_consistency"]["comparable_controls"], 1)


if __name__ == "__main__":
    unittest.main()
