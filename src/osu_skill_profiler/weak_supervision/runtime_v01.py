"""Deterministic weak-evidence rule runtime and strict serialization."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .contracts_v01 import RuleContext, WeakEvidenceRecord
from .pilot_v01 import ExecutableWeakRule
from .registry_v01 import PropositionRegistry, RuleRegistry, SourceRegistry


def _assert_strict_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_strict_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_strict_finite(item, f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    _assert_strict_finite(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def execute_rules(
    context: RuleContext,
    rules: Iterable[ExecutableWeakRule],
    propositions: PropositionRegistry,
    sources: SourceRegistry,
    rule_registry: RuleRegistry,
) -> list[WeakEvidenceRecord]:
    records: list[WeakEvidenceRecord] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for rule in sorted(rules, key=lambda item: (item.definition.rule_id, item.definition.version)):
        definition = rule_registry.require(rule.definition.rule_id, rule.definition.version)
        proposition = propositions.require(definition.proposition_key, definition.proposition_version)
        source = sources.require(definition.source_id, definition.source_version)
        if context.entity.scope not in definition.applicable_scopes:
            continue
        outcome = rule.evaluate(context)
        record = WeakEvidenceRecord(
            entity=context.entity,
            proposition_key=proposition.key,
            proposition_version=proposition.version,
            status=outcome.status,
            source_id=source.source_id,
            source_version=source.version,
            source_family=source.family,
            rule_id=definition.rule_id,
            rule_version=definition.version,
            input_dependencies=definition.input_dependencies,
            semantic_lineage=sources.lineage_closure(source.source_id, source.version),
            independence_group=source.independence_group,
            value=outcome.value,
            strength=outcome.strength,
            confidence_band=outcome.confidence_band,
            abstention_reason=outcome.reason,
            diagnostics=outcome.diagnostics,
            provenance=context.provenance,
        )
        if record.stable_key in seen:
            raise ValueError(f"duplicate evidence emission: {record.stable_key}")
        seen.add(record.stable_key)
        records.append(record)
    return records


def serialize_records(records: Iterable[WeakEvidenceRecord]) -> bytes:
    ordered = sorted(records, key=lambda record: record.stable_key)
    return ("\n".join(canonical_json(record.as_dict()) for record in ordered) + ("\n" if ordered else "")).encode("utf-8")


def write_records(records: Iterable[WeakEvidenceRecord], path: str | Path) -> dict[str, Any]:
    payload = serialize_records(records)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {"path": destination.as_posix(), "bytes": len(payload), "sha256": "sha256:" + hashlib.sha256(payload).hexdigest()}
