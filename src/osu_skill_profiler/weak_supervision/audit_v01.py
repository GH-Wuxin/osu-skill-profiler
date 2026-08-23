"""Lineage-aware agreement, conflict, and coverage audit."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .contracts_v01 import EvidenceDirection, EvidenceStatus, WeakEvidenceRecord


def _correlation_components(records: list[WeakEvidenceRecord]) -> list[list[WeakEvidenceRecord]]:
    """Group evidence sharing a declared group or any semantic ancestor."""

    components: list[list[WeakEvidenceRecord]] = []
    for record in records:
        matches: list[int] = []
        roots = set(record.semantic_lineage)
        for index, component in enumerate(components):
            if any(
                member.independence_group == record.independence_group
                or roots.intersection(member.semantic_lineage)
                for member in component
            ):
                matches.append(index)
        if not matches:
            components.append([record])
            continue
        merged = [record]
        for index in reversed(matches):
            merged.extend(components.pop(index))
        components.append(sorted(merged, key=lambda item: item.stable_key))
    return sorted(components, key=lambda group: group[0].stable_key)


def audit_evidence(records: Iterable[WeakEvidenceRecord]) -> dict:
    ordered = sorted(records, key=lambda record: record.stable_key)
    status_counts = Counter({status.value: 0 for status in EvidenceStatus})
    status_counts.update(record.status.value for record in ordered)
    by_rule = Counter(record.rule_id for record in ordered)
    by_source = Counter(record.source_id for record in ordered)
    by_family = Counter(record.source_family.value for record in ordered)
    by_proposition = Counter(record.proposition_key for record in ordered)
    by_scope = Counter(record.entity.scope.value for record in ordered)
    per_rule_status: dict[str, Counter[str]] = defaultdict(Counter)
    missing_source_patterns: Counter[str] = Counter()
    for record in ordered:
        per_rule_status[record.rule_id][record.status.value] += 1
        if record.status in (EvidenceStatus.UNAVAILABLE, EvidenceStatus.INVALID):
            reason = record.abstention_reason.value if record.abstention_reason else "UNKNOWN"
            missing_source_patterns[f"{record.source_id}:{reason}"] += 1
    abstention_reasons = Counter(
        record.abstention_reason.value
        for record in ordered
        if record.abstention_reason is not None
    )

    grouped: dict[tuple[str, str], list[WeakEvidenceRecord]] = defaultdict(list)
    for record in ordered:
        if record.status == EvidenceStatus.EMITTED:
            grouped[(record.entity.stable_key, record.proposition_key)].append(record)

    agreement_cases: list[dict] = []
    conflict_cases: list[dict] = []
    correlated_groups: list[dict] = []
    independent_support_histogram: Counter[int] = Counter()
    family_combinations: Counter[str] = Counter()
    for (entity_key, proposition), members in sorted(grouped.items()):
        components = _correlation_components(members)
        independent_support_histogram[len(components)] += 1
        directions = sorted({member.value.direction.value for member in members if member.value is not None})
        combination = "+".join(sorted({member.source_family.value for member in members}))
        family_combinations[combination] += 1
        summary = {
            "entity": entity_key,
            "proposition": proposition,
            "record_count": len(members),
            "effective_independent_support": len(components),
            "directions": directions,
            "rules": sorted(member.rule_id for member in members),
        }
        if EvidenceDirection.POSITIVE.value in directions and EvidenceDirection.NEGATIVE.value in directions:
            conflict_cases.append(summary)
        elif len(directions) == 1 and len(components) >= 2:
            agreement_cases.append(summary)
        for component in components:
            if len(component) > 1:
                correlated_groups.append({
                    "entity": entity_key,
                    "proposition": proposition,
                    "independence_groups": sorted({member.independence_group for member in component}),
                    "shared_lineage": sorted(set.intersection(*(set(member.semantic_lineage) for member in component))),
                    "rules": sorted(member.rule_id for member in component),
                })

    agreement_cases.sort(key=lambda item: (-item["effective_independent_support"], item["entity"], item["proposition"]))
    conflict_cases.sort(key=lambda item: (-item["effective_independent_support"], item["entity"], item["proposition"]))
    per_rule_coverage = {}
    for rule_id, counts in sorted(per_rule_status.items()):
        total = sum(counts.values())
        per_rule_coverage[rule_id] = {
            "total": total,
            "status_counts": dict(sorted(counts.items())),
            "emission_rate": counts[EvidenceStatus.EMITTED.value] / total if total else 0.0,
            "abstention_rate": counts[EvidenceStatus.ABSTAINED.value] / total if total else 0.0,
            "unavailable_rate": counts[EvidenceStatus.UNAVAILABLE.value] / total if total else 0.0,
            "invalid_rate": counts[EvidenceStatus.INVALID.value] / total if total else 0.0,
        }
    considered = len(agreement_cases) + len(conflict_cases)
    return {
        "schema_version": "0.1.0",
        "total_records": len(ordered),
        "status_counts": dict(sorted(status_counts.items())),
        "records_by_rule": dict(sorted(by_rule.items())),
        "records_by_source": dict(sorted(by_source.items())),
        "records_by_source_family": dict(sorted(by_family.items())),
        "records_by_proposition": dict(sorted(by_proposition.items())),
        "records_by_scope": dict(sorted(by_scope.items())),
        "abstention_reasons": dict(sorted(abstention_reasons.items())),
        "per_rule_coverage": per_rule_coverage,
        "missing_source_patterns": dict(sorted(missing_source_patterns.items())),
        "effective_independent_support_histogram": {str(key): value for key, value in sorted(independent_support_histogram.items())},
        "source_family_combinations": dict(sorted(family_combinations.items())),
        "correlated_group_count": len(correlated_groups),
        "correlated_groups": correlated_groups[:100],
        "agreement_case_count": len(agreement_cases),
        "disagreement_case_count": len(conflict_cases),
        "agreement_rate_among_multi_source_cases": len(agreement_cases) / considered if considered else 0.0,
        "disagreement_rate_among_multi_source_cases": len(conflict_cases) / considered if considered else 0.0,
        "strongest_independent_agreement": agreement_cases[:25],
        "strongest_disagreement": conflict_cases[:25],
    }
