"""Default-deny target-leakage policy and declared-lineage validator.

The validator is deliberately small and deterministic. It does not infer
arbitrary mathematical equivalence: callers must declare known deterministic
lineage, after which source overlap is checked transitively.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from ..features.schema import FEATURE_SCHEMA_V01, FEATURE_SCHEMA_V02
from ..reference.ppy.contract import REFERENCE_SCHEMA
from ..signals.contract import SIGNAL_SCHEMA_V03

LEAKAGE_POLICY_VERSION = "0.1.0"


class SignalRole(str, Enum):
    OBSERVABLE_INPUT_CANDIDATE = "OBSERVABLE_INPUT_CANDIDATE"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    WEAK_LABEL_SOURCE = "WEAK_LABEL_SOURCE"
    HUMAN_LABEL = "HUMAN_LABEL"
    GROUND_TRUTH = "GROUND_TRUTH"
    PROVENANCE_ONLY = "PROVENANCE_ONLY"
    SPLIT_METADATA = "SPLIT_METADATA"
    CHALLENGE_SELECTION = "CHALLENGE_SELECTION"
    IDENTITY_ONLY = "IDENTITY_ONLY"
    DEPRECATED_FOR_NEW_MODELS = "DEPRECATED_FOR_NEW_MODELS"


@dataclass(frozen=True)
class LeakageViolation:
    code: str
    field: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "reason": self.reason}


@dataclass(frozen=True)
class LeakageAuditResult:
    policy_version: str
    status: str
    violations: tuple[LeakageViolation, ...]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "status": self.status,
            "violations": [violation.as_dict() for violation in self.violations],
        }


_IDENTITY_FIELDS = {
    "ls.original_index", "ls.time_sorted_index", "ref.original_index",
    "ref.time_sorted_index", "ref.start_time_ms", "ref.object_type",
    "map_key", "map_checksum", "sample_id", "beatmap_id", "beatmapset_id",
    "set_group_key", "mapper_group_key", "creator_id", "creator", "artist",
    "title", "version",
}

_SPLIT_FIELDS = {
    "split", "split_membership", "split_version", "set_disjoint_split",
    "mapper_disjoint_split", "strict_disjoint_split",
}

_CHALLENGE_FIELDS = {
    "challenge_selection", "challenge_flag", "reference_disagreement_flag",
    "reference_disagreement_challenge", "pathological_challenge",
    "legacy_format_ood",
}


def build_signal_role_registry() -> dict[str, SignalRole]:
    """Return the deterministic v0.1 field-role registry."""

    registry: dict[str, SignalRole] = {}
    for field in FEATURE_SCHEMA_V02:
        registry[field] = SignalRole.OBSERVABLE_INPUT_CANDIDATE
    for field in FEATURE_SCHEMA_V01:
        registry.setdefault(field, SignalRole.OBSERVABLE_INPUT_CANDIDATE)
    # RT-04: these names encode historical span counts and are never allowed
    # as new-model inputs despite remaining replayable in Feature v0.1.
    registry["slider.repeats_total"] = SignalRole.DEPRECATED_FOR_NEW_MODELS
    registry["slider.repeats_max"] = SignalRole.DEPRECATED_FOR_NEW_MODELS

    for field in SIGNAL_SCHEMA_V03:
        registry[field] = SignalRole.OBSERVABLE_INPUT_CANDIDATE
    registry["ls.provenance"] = SignalRole.PROVENANCE_ONLY

    for field, entry in REFERENCE_SCHEMA.items():
        if field == "ref.provenance":
            registry[field] = SignalRole.PROVENANCE_ONLY
        elif entry.get("classification") == "OFFICIAL_REFERENCE":
            registry[field] = SignalRole.REFERENCE_ONLY
        else:
            registry[field] = SignalRole.IDENTITY_ONLY

    for field in _IDENTITY_FIELDS:
        registry[field] = SignalRole.IDENTITY_ONLY
    for field in _SPLIT_FIELDS:
        registry[field] = SignalRole.SPLIT_METADATA
    for field in _CHALLENGE_FIELDS:
        registry[field] = SignalRole.CHALLENGE_SELECTION
    return registry


SIGNAL_ROLE_REGISTRY = build_signal_role_registry()


def _as_string_list(value: Any, field_name: str, violations: list[LeakageViolation]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        violations.append(LeakageViolation("INVALID_SCHEMA", field_name, f"{field_name} must be a list of non-empty strings"))
        return []
    return list(value)


def _declared_roles(value: Any, violations: list[LeakageViolation]) -> dict[str, SignalRole]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        violations.append(LeakageViolation("INVALID_SCHEMA", "field_roles", "field_roles must be an object"))
        return {}
    roles: dict[str, SignalRole] = {}
    for field, role_name in value.items():
        if not isinstance(field, str) or not isinstance(role_name, str):
            violations.append(LeakageViolation("INVALID_SCHEMA", "field_roles", "field_roles entries must be string:string"))
            continue
        try:
            roles[field] = SignalRole(role_name)
        except ValueError:
            violations.append(LeakageViolation("INVALID_ROLE", field, f"unknown signal role: {role_name}"))
    return roles


def _declared_lineage(value: Any, violations: list[LeakageViolation]) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        violations.append(LeakageViolation("INVALID_SCHEMA", "declared_lineage", "declared_lineage must be an object"))
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for field, sources in value.items():
        if not isinstance(field, str) or not isinstance(sources, list) or any(not isinstance(source, str) or not source for source in sources):
            violations.append(LeakageViolation("INVALID_LINEAGE", str(field), "each declared_lineage value must be a list of non-empty field names"))
            continue
        result[field] = tuple(sources)
    return result


def _lineage_closure(field: str, lineage: Mapping[str, Sequence[str]]) -> set[str]:
    closure: set[str] = set()
    pending = [field]
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        closure.add(current)
        pending.extend(lineage.get(current, ()))
    return closure


def audit_candidate_schema(candidate: Mapping[str, Any]) -> LeakageAuditResult:
    """Audit a dataset/model schema against the default-deny policy."""

    violations: list[LeakageViolation] = []
    if not isinstance(candidate, Mapping):
        violation = LeakageViolation("INVALID_SCHEMA", "$", "candidate schema must be a JSON object")
        return LeakageAuditResult(LEAKAGE_POLICY_VERSION, "FAIL", (violation,))

    inputs = _as_string_list(candidate.get("input_fields"), "input_fields", violations)
    targets = _as_string_list(candidate.get("target_fields"), "target_fields", violations)
    weak_sources = _as_string_list(candidate.get("weak_label_sources"), "weak_label_sources", violations)
    offline_eval = _as_string_list(candidate.get("offline_evaluation_fields"), "offline_evaluation_fields", violations)
    split_fields = _as_string_list(candidate.get("split_fields"), "split_fields", violations)
    provenance_fields = _as_string_list(candidate.get("provenance_fields"), "provenance_fields", violations)
    challenge_fields = _as_string_list(candidate.get("challenge_fields"), "challenge_fields", violations)
    roles = _declared_roles(candidate.get("field_roles"), violations)
    lineage = _declared_lineage(candidate.get("declared_lineage"), violations)

    registry = dict(SIGNAL_ROLE_REGISTRY)
    for field, declared_role in roles.items():
        existing_role = registry.get(field)
        if existing_role is not None and existing_role != declared_role:
            violations.append(
                LeakageViolation(
                    "ROLE_OVERRIDE_FORBIDDEN",
                    field,
                    f"candidate schema cannot override registry role {existing_role.value} with {declared_role.value}",
                )
            )
            continue
        registry[field] = declared_role
    for field in split_fields:
        registry[field] = SignalRole.SPLIT_METADATA
    for field in provenance_fields:
        registry[field] = SignalRole.PROVENANCE_ONLY
    for field in challenge_fields:
        registry[field] = SignalRole.CHALLENGE_SELECTION

    for field in inputs:
        role = registry.get(field)
        centrally_registered = field in SIGNAL_ROLE_REGISTRY
        declared_derivative = field in lineage and roles.get(field) == SignalRole.OBSERVABLE_INPUT_CANDIDATE
        if role is None or (not centrally_registered and not declared_derivative):
            violations.append(LeakageViolation("UNREGISTERED_INPUT", field, "unknown fields are denied as model inputs until explicitly registered by policy"))
        elif role != SignalRole.OBSERVABLE_INPUT_CANDIDATE:
            violations.append(LeakageViolation("FORBIDDEN_INPUT_ROLE", field, f"{field} has role {role.value}, not OBSERVABLE_INPUT_CANDIDATE"))

    allowed_target_roles = {SignalRole.WEAK_LABEL_SOURCE, SignalRole.HUMAN_LABEL, SignalRole.GROUND_TRUTH}
    for field in targets:
        role = registry.get(field)
        if role is None:
            violations.append(LeakageViolation("UNREGISTERED_TARGET", field, "target fields require an explicit HUMAN_LABEL, GROUND_TRUTH, or WEAK_LABEL_SOURCE role"))
        elif role not in allowed_target_roles:
            violations.append(LeakageViolation("INVALID_TARGET_ROLE", field, f"target has role {role.value}; expected an explicit label/ground-truth role"))

    known_fields = set(registry) | set(targets) | set(lineage)
    for derived, sources in lineage.items():
        if derived not in known_fields:
            violations.append(LeakageViolation("UNREGISTERED_LINEAGE_FIELD", derived, "derived lineage field is not registered"))
        for source in sources:
            if source not in registry and source not in lineage:
                violations.append(LeakageViolation("UNREGISTERED_LINEAGE_SOURCE", source, f"lineage source for {derived} is unknown; unknown lineage never passes silently"))

    input_set = set(inputs)
    for target in targets:
        protected = _lineage_closure(target, lineage)
        for input_field in inputs:
            overlap = protected & _lineage_closure(input_field, lineage)
            if overlap:
                violations.append(LeakageViolation("TARGET_LINEAGE_LEAKAGE", input_field, f"input and target {target} share protected lineage: {', '.join(sorted(overlap))}"))

    for field in set(targets) & input_set:
        violations.append(LeakageViolation("TARGET_IN_INPUTS", field, "target field is directly included in model inputs"))

    for field in weak_sources:
        if field not in registry and field not in lineage:
            violations.append(LeakageViolation("UNREGISTERED_WEAK_SOURCE", field, "weak-label source is unknown"))
            continue
        if targets and not any(field in _lineage_closure(target, lineage) for target in targets):
            violations.append(
                LeakageViolation(
                    "WEAK_SOURCE_NOT_IN_TARGET_LINEAGE",
                    field,
                    "every declared weak-label source must appear in the declared lineage of a target",
                )
            )

    for field in offline_eval:
        role = registry.get(field)
        if role != SignalRole.REFERENCE_ONLY:
            violations.append(LeakageViolation("INVALID_OFFLINE_EVALUATION_FIELD", field, "offline evaluation fields must be registered REFERENCE_ONLY signals"))

    unique = {(item.code, item.field, item.reason): item for item in violations}
    ordered = tuple(unique[key] for key in sorted(unique))
    return LeakageAuditResult(LEAKAGE_POLICY_VERSION, "PASS" if not ordered else "FAIL", ordered)


__all__ = [
    "LEAKAGE_POLICY_VERSION", "SignalRole", "LeakageViolation",
    "LeakageAuditResult", "SIGNAL_ROLE_REGISTRY", "build_signal_role_registry",
    "audit_candidate_schema",
]
