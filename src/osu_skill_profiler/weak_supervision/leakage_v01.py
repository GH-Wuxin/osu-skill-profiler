"""Bridge weak-evidence lineage into the authoritative leakage gate."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ..dataset.leakage import SignalRole, audit_candidate_schema
from .contracts_v01 import WeakEvidenceRecord


def audit_evidence_for_model_inputs(
    records: Iterable[WeakEvidenceRecord],
    input_fields: Iterable[str],
):
    """Conservatively audit proposed inputs against every evidence target.

    Multiple rules for one proposition contribute the union of their roots.
    This intentionally fails if an input overlaps *any* way that proposition
    was constructed; it does not infer arbitrary algebra beyond declared
    lineage.
    """

    roots_by_target: dict[str, set[str]] = defaultdict(set)
    weak_sources: set[str] = set()
    roles: dict[str, str] = {}
    for record in records:
        target = f"weak_evidence:{record.proposition_key}@{record.proposition_version}"
        roots_by_target[target].update(record.semantic_lineage)
        weak_sources.update(record.semantic_lineage)
        roles[target] = SignalRole.WEAK_LABEL_SOURCE.value
    targets = sorted(roots_by_target)
    candidate = {
        "schema_version": "0.1.0",
        "input_fields": sorted(set(input_fields)),
        "target_fields": targets,
        "weak_label_sources": sorted(weak_sources),
        "offline_evaluation_fields": [],
        "split_fields": [],
        "provenance_fields": [],
        "challenge_fields": [],
        "field_roles": roles,
        "declared_lineage": {target: sorted(roots) for target, roots in sorted(roots_by_target.items())},
    }
    return audit_candidate_schema(candidate)
