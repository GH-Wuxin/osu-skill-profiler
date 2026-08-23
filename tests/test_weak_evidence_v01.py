from __future__ import annotations

from dataclasses import replace
import json
import math
import unittest

from osu_skill_profiler.weak_supervision.audit_v01 import audit_evidence
from osu_skill_profiler.weak_supervision.contracts_v01 import (
    AbstentionReason,
    ConfidenceBand,
    EntityRef,
    EntityScope,
    EvidenceDirection,
    EvidenceStatus,
    EvidenceValue,
    PropositionStatus,
    RuleContext,
    RuleOutcome,
    SourceFamily,
    WeakEvidenceRecord,
)
from osu_skill_profiler.weak_supervision.leakage_v01 import audit_evidence_for_model_inputs
from osu_skill_profiler.weak_supervision.pilot_v01 import (
    ObservableMovementTailRule,
    PILOT_PROPOSITIONS,
    PILOT_RULE_REGISTRY,
    PILOT_RULES,
    PILOT_SOURCES,
    ReferenceSnapTailRule,
)
from osu_skill_profiler.weak_supervision.registry_v01 import (
    PropositionDefinition,
    PropositionRegistry,
    RuleRegistry,
    SourceDefinition,
    SourceRegistry,
)
from osu_skill_profiler.weak_supervision.runtime_v01 import canonical_json, execute_rules, serialize_records

CHECKSUM = "sha256:" + "1" * 64


def _context(**values) -> RuleContext:
    return RuleContext(EntityRef(EntityScope.MAP, CHECKSUM), values)


def _execute(context: RuleContext, rules=PILOT_RULES):
    return execute_rules(context, rules, PILOT_PROPOSITIONS, PILOT_SOURCES, PILOT_RULE_REGISTRY)


def _record(
    *,
    rule_id: str,
    source_id: str,
    family: SourceFamily,
    group: str,
    lineage: tuple[str, ...],
    direction: EvidenceDirection,
    proposition: str = "ws01.provisional.movement_demand_high",
) -> WeakEvidenceRecord:
    return WeakEvidenceRecord(
        entity=EntityRef(EntityScope.MAP, CHECKSUM),
        proposition_key=proposition,
        proposition_version="0.1.0",
        status=EvidenceStatus.EMITTED,
        source_id=source_id,
        source_version="0.1.0",
        source_family=family,
        rule_id=rule_id,
        rule_version="0.1.0",
        input_dependencies=lineage,
        semantic_lineage=lineage,
        independence_group=group,
        value=EvidenceValue(direction),
        strength=0.5,
        confidence_band=ConfidenceBand.MEDIUM,
    )


class RegistryTests(unittest.TestCase):
    def test_pilot_registries_are_valid_and_provisional(self):
        payload = PILOT_PROPOSITIONS.as_dict()
        self.assertTrue(payload["propositions"])
        self.assertEqual({item["status"] for item in payload["propositions"]}, {"PROVISIONAL"})
        self.assertTrue(PILOT_SOURCES.as_dict()["sources"])

    def test_duplicate_and_unknown_proposition_rejected(self):
        item = PropositionDefinition(
            "p", "1", PropositionStatus.PROVISIONAL, "x", (EntityScope.MAP,), ("POSITIVE",)
        )
        with self.assertRaises(ValueError):
            PropositionRegistry("1", (item, item))
        with self.assertRaises(KeyError):
            PILOT_PROPOSITIONS.require("unknown", "0.1.0")

    def test_duplicate_unknown_and_version_mismatched_source_rejected(self):
        source = PILOT_SOURCES.require("ws01.source.observable.movement_tail", "0.1.0")
        with self.assertRaises(ValueError):
            SourceRegistry("1", (source, source))
        with self.assertRaises(KeyError):
            PILOT_SOURCES.require("unknown", "0.1.0")
        with self.assertRaises(KeyError):
            PILOT_SOURCES.require(source.source_id, "9.9.9")

    def test_unknown_lineage_root_and_dependency_rejected(self):
        valid = PILOT_SOURCES.require("ws01.source.observable.movement_tail", "0.1.0")
        with self.assertRaisesRegex(ValueError, "unknown lineage root"):
            SourceRegistry("1", (replace(valid, source_id="bad", lineage_roots=("unknown.root",)),))
        with self.assertRaisesRegex(ValueError, "unknown source dependency"):
            SourceRegistry("1", (replace(valid, source_id="bad", source_dependencies=("missing",)),))

    def test_direct_transitive_shared_lineage_and_cycle(self):
        root = PILOT_SOURCES.require("ws01.source.observable.movement_tail", "0.1.0")
        derived = SourceDefinition(
            "derived", "0.1.0", SourceFamily.DETERMINISTIC_RELATION, (), (root.source_id,),
            True, True, False, "same", True, "derived", "contract",
        )
        twice = SourceDefinition(
            "twice", "0.1.0", SourceFamily.DETERMINISTIC_RELATION, (), (derived.source_id,),
            True, True, False, "same", True, "derived twice", "contract",
        )
        registry = SourceRegistry("1", (root, derived, twice))
        self.assertEqual(registry.lineage_closure("derived", "0.1.0"), tuple(sorted(root.lineage_roots)))
        self.assertEqual(registry.lineage_closure("twice", "0.1.0"), tuple(sorted(root.lineage_roots)))
        self.assertEqual(registry.shared_lineage((root.source_id, root.version), ("twice", "0.1.0")), tuple(sorted(root.lineage_roots)))
        first = replace(derived, source_id="first", source_dependencies=("second",))
        second = replace(derived, source_id="second", source_dependencies=("first",))
        with self.assertRaisesRegex(ValueError, "cycle"):
            SourceRegistry("1", (first, second))


class RuleAndContractTests(unittest.TestCase):
    def test_positive_negative_abstain_and_missing(self):
        rule = ObservableMovementTailRule()
        positive = rule.evaluate(_context(**{"spatial.distance_norm_p95": .7, "spatial.velocity_norm_per_s_p95": 7}))
        negative = rule.evaluate(_context(**{"spatial.distance_norm_p95": .05, "spatial.velocity_norm_per_s_p95": .2}))
        abstain = rule.evaluate(_context(**{"spatial.distance_norm_p95": .3, "spatial.velocity_norm_per_s_p95": 1.2}))
        missing = rule.evaluate(_context(**{"spatial.distance_norm_p95": .7}))
        self.assertEqual(positive.value.direction, EvidenceDirection.POSITIVE)
        self.assertEqual(negative.value.direction, EvidenceDirection.NEGATIVE)
        self.assertEqual(abstain.status, EvidenceStatus.ABSTAINED)
        self.assertEqual(missing.status, EvidenceStatus.UNAVAILABLE)

    def test_geometry_blocked_reference_is_unavailable(self):
        context = RuleContext(EntityRef(EntityScope.MAP, CHECKSUM), {"ref.ppy.snap_include_sliders": 2.0}, {"geometry_blocked": True})
        outcome = ReferenceSnapTailRule().evaluate(context)
        self.assertEqual(outcome.status, EvidenceStatus.UNAVAILABLE)
        self.assertEqual(outcome.reason, AbstentionReason.GEOMETRY_BLOCKED)

    def test_zero_is_evidence_and_absent_is_unavailable(self):
        no_sliders = _context(**{"slider.slider_ratio": 0.0, "slider.duration_ms_p90": None, "slider.repeat_count_total": 0.0})
        missing = _context(**{"slider.slider_ratio": None, "slider.duration_ms_p90": None, "slider.repeat_count_total": None})
        slider_rule = PILOT_RULES[-2]
        self.assertEqual(slider_rule.evaluate(no_sliders).status, EvidenceStatus.EMITTED)
        self.assertEqual(slider_rule.evaluate(missing).status, EvidenceStatus.UNAVAILABLE)

    def test_all_rules_abstain_or_unavailable_is_preserved(self):
        records = _execute(_context())
        self.assertEqual(len(records), len([rule for rule in PILOT_RULES if EntityScope.MAP in rule.definition.applicable_scopes]))
        self.assertTrue(all(record.status != EvidenceStatus.EMITTED for record in records))

    def test_all_applicable_map_rules_can_abstain_explicitly(self):
        records = _execute(_context(**{
            "spatial.distance_norm_p95": .30,
            "spatial.velocity_norm_per_s_p95": 1.2,
            "ref.ppy.snap_include_sliders": 1.0,
            "temporal.object_rate_max_1s": 6.0,
            "temporal.burst_longest_duration_ms_125ms": 200.0,
            "slider.slider_ratio": .30,
            "slider.duration_ms_p90": 500.0,
            "slider.repeat_count_total": 0.0,
        }))
        self.assertTrue(records)
        self.assertEqual({record.status for record in records}, {EvidenceStatus.ABSTAINED})

    def test_missing_local_and_canonical_segment_rule(self):
        rule = PILOT_RULES[-1]
        entity = EntityRef(EntityScope.SEGMENT, CHECKSUM, 0, 0.0, 5000.0)
        missing = rule.evaluate(RuleContext(entity, {}))
        positive = rule.evaluate(RuleContext(entity, {"ls.lazy_travel_distance_cs_normalised": 180.0}, {"source_segment_max": 240.0}))
        self.assertEqual(missing.status, EvidenceStatus.UNAVAILABLE)
        self.assertEqual(positive.value.direction, EvidenceDirection.POSITIVE)

    def test_deterministic_replay_and_duplicate_emission(self):
        context = _context(**{
            "spatial.distance_norm_p95": .7,
            "spatial.velocity_norm_per_s_p95": 7,
            "ref.ppy.snap_include_sliders": 2.2,
            "temporal.object_rate_max_1s": 12,
            "temporal.burst_longest_duration_ms_125ms": 1500,
            "slider.slider_ratio": .7,
            "slider.duration_ms_p90": 1200,
            "slider.repeat_count_total": 4,
        })
        first = _execute(context)
        second = _execute(context)
        self.assertEqual(serialize_records(first), serialize_records(second))
        with self.assertRaisesRegex(ValueError, "duplicate evidence"):
            _execute(context, (PILOT_RULES[0], PILOT_RULES[0]))

    def test_pairwise_schema_extension_and_segment_identity(self):
        segment = EntityRef(EntityScope.SEGMENT, CHECKSUM, 2, 10.0, 20.0)
        self.assertIn(":segment:2", segment.stable_key)
        value = EvidenceValue(EvidenceDirection.PAIRWISE, pair_preference="A_HIGHER")
        self.assertEqual(value.as_dict()["pair_preference"], "A_HIGHER")
        scalar = EvidenceValue(EvidenceDirection.SCALAR, scalar=0.0)
        self.assertEqual(scalar.as_dict(), {"direction": "SCALAR", "scalar": 0.0})

    def test_nonfinite_and_invalid_outcome_fail_closed(self):
        with self.assertRaises(ValueError):
            EvidenceValue(EvidenceDirection.SCALAR, scalar=math.inf)
        with self.assertRaises(ValueError):
            RuleOutcome(EvidenceStatus.ABSTAINED)
        with self.assertRaises(ValueError):
            canonical_json({"x": math.nan})


class LeakageAndAuditTests(unittest.TestCase):
    def test_valid_independent_and_direct_reference_leakage(self):
        context = _context(**{
            "spatial.distance_norm_p95": .7,
            "spatial.velocity_norm_per_s_p95": 7,
            "ref.ppy.snap_include_sliders": 2.2,
        })
        records = _execute(context, PILOT_RULES[:2])
        independent = audit_evidence_for_model_inputs(records, ["temporal.object_rate_max_1s"])
        leaked = audit_evidence_for_model_inputs(records, ["ref.ppy.snap_include_sliders"])
        self.assertTrue(independent.passed, independent.as_dict())
        self.assertFalse(leaked.passed)
        self.assertIn("TARGET_LINEAGE_LEAKAGE", {item.code for item in leaked.violations})

    def test_transitive_reference_leakage(self):
        record = _record(
            rule_id="transitive", source_id="derived", family=SourceFamily.DETERMINISTIC_RELATION,
            group="reference.ppy.snap_policy", lineage=("ref.ppy.snap_include_sliders",),
            direction=EvidenceDirection.POSITIVE,
        )
        result = audit_evidence_for_model_inputs([record], ["ref.ppy.snap_include_sliders"])
        self.assertFalse(result.passed)

    def test_split_challenge_qa_unknown_and_reference_inputs_fail_closed(self):
        record = _record(
            rule_id="target", source_id="target", family=SourceFamily.OBSERVABLE,
            group="target", lineage=("spatial.distance_norm_p95",),
            direction=EvidenceDirection.POSITIVE,
        )
        for field in ("split", "reference_disagreement_challenge", "qa.failure_reason", "ref.ppy.speed"):
            result = audit_evidence_for_model_inputs([record], [field])
            self.assertFalse(result.passed, (field, result.as_dict()))

    def test_target_as_input_fails_for_weak_evidence_target(self):
        record = _record(
            rule_id="target", source_id="target", family=SourceFamily.OBSERVABLE,
            group="target", lineage=("spatial.distance_norm_p95",),
            direction=EvidenceDirection.POSITIVE,
        )
        target = "weak_evidence:ws01.provisional.movement_demand_high@0.1.0"
        result = audit_evidence_for_model_inputs([record], [target])
        self.assertFalse(result.passed)
        self.assertIn("TARGET_IN_INPUTS", {item.code for item in result.violations})

    def test_correlated_rules_do_not_count_twice(self):
        first = _record(rule_id="a", source_id="a", family=SourceFamily.OBSERVABLE, group="g", lineage=("spatial.distance_norm_p95",), direction=EvidenceDirection.POSITIVE)
        second = _record(rule_id="b", source_id="b", family=SourceFamily.DETERMINISTIC_RELATION, group="g", lineage=("spatial.distance_norm_p95",), direction=EvidenceDirection.POSITIVE)
        audit = audit_evidence([first, second])
        self.assertEqual(audit["effective_independent_support_histogram"], {"1": 1})
        self.assertEqual(audit["correlated_group_count"], 1)
        self.assertEqual(audit["agreement_case_count"], 0)

    def test_independent_agreement_and_conflict_preserved(self):
        observable = _record(rule_id="obs", source_id="obs", family=SourceFamily.OBSERVABLE, group="obs", lineage=("spatial.distance_norm_p95",), direction=EvidenceDirection.POSITIVE)
        reference = _record(rule_id="ref", source_id="ref", family=SourceFamily.REFERENCE_PPY, group="ref", lineage=("ref.ppy.snap_include_sliders",), direction=EvidenceDirection.POSITIVE)
        agreement = audit_evidence([observable, reference])
        self.assertEqual(agreement["agreement_case_count"], 1)
        conflicting = replace(reference, value=EvidenceValue(EvidenceDirection.NEGATIVE))
        conflict = audit_evidence([observable, conflicting])
        self.assertEqual(conflict["disagreement_case_count"], 1)
        self.assertEqual(conflict["strongest_disagreement"][0]["directions"], ["NEGATIVE", "POSITIVE"])

    def test_serialization_round_trip_and_stable_order(self):
        a = _record(rule_id="a", source_id="a", family=SourceFamily.OBSERVABLE, group="a", lineage=("spatial.distance_norm_p95",), direction=EvidenceDirection.POSITIVE)
        b = _record(rule_id="b", source_id="b", family=SourceFamily.REFERENCE_PPY, group="b", lineage=("ref.ppy.snap_include_sliders",), direction=EvidenceDirection.NEGATIVE)
        first = serialize_records([b, a])
        second = serialize_records([a, b])
        self.assertEqual(first, second)
        rows = [json.loads(line) for line in first.decode().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["schema_version"] == "0.1.0" for row in rows))


if __name__ == "__main__":
    unittest.main()
