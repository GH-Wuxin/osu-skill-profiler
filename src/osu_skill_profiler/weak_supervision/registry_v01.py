"""Fail-closed proposition, source, rule, and lineage registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..dataset.leakage import SIGNAL_ROLE_REGISTRY
from .contracts_v01 import (
    ConfidenceBand,
    EntityScope,
    PropositionStatus,
    SourceFamily,
)


@dataclass(frozen=True)
class PropositionDefinition:
    key: str
    version: str
    status: PropositionStatus
    description: str
    allowed_scopes: tuple[EntityScope, ...]
    allowed_directions: tuple[str, ...]


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    version: str
    family: SourceFamily
    lineage_roots: tuple[str, ...]
    source_dependencies: tuple[str, ...]
    model_input_safe: bool
    target_safe: bool
    reference_only: bool
    independence_group: str
    deterministic: bool
    description: str
    contract_reference: str
    active: bool = True


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    version: str
    source_id: str
    source_version: str
    proposition_key: str
    proposition_version: str
    applicable_scopes: tuple[EntityScope, ...]
    input_dependencies: tuple[str, ...]
    confidence_semantics: str
    confidence_band: ConfidenceBand
    abstention_conditions: tuple[str, ...]
    rationale: str
    discriminator: str
    failure_modes: tuple[str, ...]


class PropositionRegistry:
    def __init__(self, version: str, definitions: Iterable[PropositionDefinition]) -> None:
        self.version = version
        self._items: dict[tuple[str, str], PropositionDefinition] = {}
        for item in definitions:
            key = (item.key, item.version)
            if key in self._items:
                raise ValueError(f"duplicate proposition: {item.key}@{item.version}")
            if item.status is not PropositionStatus.PROVISIONAL:
                raise ValueError("v0.1 proposition registry accepts PROVISIONAL entries only")
            self._items[key] = item

    def require(self, key: str, version: str) -> PropositionDefinition:
        try:
            return self._items[(key, version)]
        except KeyError as exc:
            raise KeyError(f"unknown proposition: {key}@{version}") from exc

    def as_dict(self) -> dict:
        items = []
        for item in sorted(self._items.values(), key=lambda value: (value.key, value.version)):
            items.append({
                "key": item.key,
                "version": item.version,
                "status": item.status.value,
                "description": item.description,
                "allowed_scopes": [scope.value for scope in item.allowed_scopes],
                "allowed_directions": list(item.allowed_directions),
            })
        return {"registry_version": self.version, "propositions": items}


class SourceRegistry:
    def __init__(self, version: str, definitions: Iterable[SourceDefinition]) -> None:
        self.version = version
        self._items: dict[tuple[str, str], SourceDefinition] = {}
        for item in definitions:
            key = (item.source_id, item.version)
            if key in self._items:
                raise ValueError(f"duplicate source: {item.source_id}@{item.version}")
            if not item.independence_group:
                raise ValueError(f"source {item.source_id} has no independence group")
            self._items[key] = item
        self._validate_graph()

    def require(self, source_id: str, version: str) -> SourceDefinition:
        try:
            item = self._items[(source_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown source: {source_id}@{version}") from exc
        if not item.active:
            raise ValueError(f"source is schema-supported but inactive: {source_id}@{version}")
        return item

    def _validate_graph(self) -> None:
        by_id: dict[str, SourceDefinition] = {}
        for item in self._items.values():
            if item.source_id in by_id:
                raise ValueError(f"multiple versions for source ID require an explicit versioned dependency: {item.source_id}")
            by_id[item.source_id] = item
            for root in item.lineage_roots:
                if root not in SIGNAL_ROLE_REGISTRY:
                    raise ValueError(f"unknown lineage root for {item.source_id}: {root}")
        for item in self._items.values():
            for dependency in item.source_dependencies:
                if dependency not in by_id:
                    raise ValueError(f"unknown source dependency for {item.source_id}: {dependency}")

        state: dict[str, int] = {}
        def visit(source_id: str) -> None:
            marker = state.get(source_id, 0)
            if marker == 1:
                raise ValueError(f"source lineage cycle at {source_id}")
            if marker == 2:
                return
            state[source_id] = 1
            for dependency in by_id[source_id].source_dependencies:
                visit(dependency)
            state[source_id] = 2
        for source_id in sorted(by_id):
            visit(source_id)

    def lineage_closure(self, source_id: str, version: str) -> tuple[str, ...]:
        item = self.require(source_id, version)
        by_id = {value.source_id: value for value in self._items.values()}
        roots: set[str] = set()
        pending = [item]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current.source_id in visited:
                continue
            visited.add(current.source_id)
            roots.update(current.lineage_roots)
            pending.extend(by_id[dependency] for dependency in current.source_dependencies)
        return tuple(sorted(roots))

    def shared_lineage(self, first: tuple[str, str], second: tuple[str, str]) -> tuple[str, ...]:
        return tuple(sorted(set(self.lineage_closure(*first)) & set(self.lineage_closure(*second))))

    def as_dict(self) -> dict:
        items = []
        for item in sorted(self._items.values(), key=lambda value: (value.source_id, value.version)):
            items.append({
                "source_id": item.source_id,
                "version": item.version,
                "family": item.family.value,
                "lineage_roots": list(item.lineage_roots),
                "source_dependencies": list(item.source_dependencies),
                "lineage_closure": list(self.lineage_closure(item.source_id, item.version)) if item.active else [],
                "model_input_safe": item.model_input_safe,
                "target_safe": item.target_safe,
                "reference_only": item.reference_only,
                "independence_group": item.independence_group,
                "deterministic": item.deterministic,
                "active": item.active,
                "description": item.description,
                "contract_reference": item.contract_reference,
            })
        return {"registry_version": self.version, "sources": items}


class RuleRegistry:
    def __init__(
        self,
        definitions: Iterable[RuleDefinition],
        propositions: PropositionRegistry,
        sources: SourceRegistry,
    ) -> None:
        self._items: dict[tuple[str, str], RuleDefinition] = {}
        for item in definitions:
            key = (item.rule_id, item.version)
            if key in self._items:
                raise ValueError(f"duplicate rule: {item.rule_id}@{item.version}")
            proposition = propositions.require(item.proposition_key, item.proposition_version)
            source = sources.require(item.source_id, item.source_version)
            if not set(item.applicable_scopes).issubset(proposition.allowed_scopes):
                raise ValueError(f"rule scope is not allowed by {item.proposition_key}")
            closure = set(sources.lineage_closure(source.source_id, source.version))
            if not set(item.input_dependencies).issubset(closure):
                raise ValueError(f"rule {item.rule_id} has dependencies outside declared source lineage")
            self._items[key] = item

    def require(self, rule_id: str, version: str) -> RuleDefinition:
        try:
            return self._items[(rule_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown rule: {rule_id}@{version}") from exc

    def definitions(self) -> tuple[RuleDefinition, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: (item.rule_id, item.version)))
