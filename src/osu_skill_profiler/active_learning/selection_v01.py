"""Deterministic, interpretable candidate extraction for Active Learning v0.1.

The score is an acquisition priority, not a probability or confidence.  It
operates only on the bounded Weak Supervision pilot and preserves all source
statuses.  The known ALV01-UNAVAILABLE-001 map is excluded explicitly rather
than repairing or reinterpreting the historical pilot artifact.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from osu_skill_profiler.weak_supervision.contracts_v01 import EntityRef, EntityScope

from .contracts_v01 import AnnotationEntity, ScoreComponents, canonical_json


SELECTION_VERSION = "0.1.0"
SELECTED_PROPOSITIONS = (
    "ws01.provisional.movement_demand_high",
    "ws01.provisional.dense_timing_pressure_high",
    "ws01.provisional.slider_tracking_travel_high",
)
EXCLUDED_PROPOSITIONS = {
    "ws01.provisional.slider_control_load_high": (
        "not selected for v0.1: a short deterministic presentation does not yet "
        "make the combined duration/repeat control-load hypothesis reliably judgeable"
    )
}
CONTAINED_DEFECT_MAPS = {
    "sha256:996be2f8004d76234b3749e982006e59837fe0547b09d4146cefd75be41480c3":
        "ALV01-UNAVAILABLE-001"
}


def _bounded(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("candidate score must be finite")
    return round(min(1.0, max(0.0, value)), 6)


def _entity_ref(payload: Mapping[str, Any]) -> EntityRef:
    scope = EntityScope(str(payload["scope"]))
    return EntityRef(
        scope=scope,
        map_checksum=str(payload["map_checksum"]),
        segment_index=payload.get("segment_index"),
        segment_start_ms=payload.get("segment_start_ms"),
        segment_end_ms=payload.get("segment_end_ms"),
    )


def _snapshot_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    ordered = sorted((dict(row) for row in rows), key=canonical_json)
    return "sha256:" + hashlib.sha256(canonical_json(ordered).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    proposition_key: str
    proposition_version: str
    entity: AnnotationEntity
    statuses: tuple[str, ...]
    directions: tuple[str, ...]
    evidence_snapshot_hash: str
    source_rule_ids: tuple[str, ...]
    challenge_categories: tuple[str, ...]
    evidence_bucket: str
    signal_position: float
    score_components: ScoreComponents
    acquisition_score: float
    selection_notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evidence_snapshot_hash.startswith("sha256:") or len(self.evidence_snapshot_hash) != 71:
            raise ValueError("candidate requires a complete sha256 weak-evidence snapshot")
        if not self.statuses or not self.source_rule_ids:
            raise ValueError("candidate requires explicit weak-evidence status and source rules")
        if any(status in ("UNAVAILABLE", "INVALID") for status in self.statuses):
            raise ValueError("unavailable/invalid weak evidence is ineligible for candidate construction")
        if not 0.0 <= self.signal_position <= 1.0 or not math.isfinite(self.signal_position):
            raise ValueError("signal_position must be finite and bounded")
        if not 0.0 <= self.acquisition_score <= 1.0 or not math.isfinite(self.acquisition_score):
            raise ValueError("acquisition_score must be finite and bounded")

    @property
    def scope(self) -> EntityScope:
        return self.entity.ref.scope

    @property
    def map_checksum(self) -> str:
        return self.entity.ref.map_checksum

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "proposition": {"key": self.proposition_key, "version": self.proposition_version},
            "entity": self.entity.as_dict(),
            "statuses": list(self.statuses),
            "directions": list(self.directions),
            "evidence_snapshot_hash": self.evidence_snapshot_hash,
            "source_rule_ids": list(self.source_rule_ids),
            "challenge_categories": list(self.challenge_categories),
            "evidence_bucket": self.evidence_bucket,
            "signal_position": self.signal_position,
            "score_components": self.score_components.as_dict(),
            "acquisition_score": self.acquisition_score,
            "selection_notes": list(self.selection_notes),
        }


def _base_components(rows: list[Mapping[str, Any]], challenge: bool) -> tuple[ScoreComponents, float, str, tuple[str, ...]]:
    emitted = [row for row in rows if row.get("status") == "EMITTED"]
    abstained = [row for row in rows if row.get("status") == "ABSTAINED"]
    unavailable = [row for row in rows if row.get("status") in ("UNAVAILABLE", "INVALID")]
    if unavailable:
        raise ValueError("unavailable/invalid evidence must be excluded before candidate scoring")

    strengths = [float(row["strength"]) for row in emitted]
    uncertainty = 1.0 if not strengths else sum(1.0 - value for value in strengths) / len(strengths)
    abstention_pressure = len(abstained) / len(rows)
    groups = {str(row["independence_group"]) for row in emitted}
    directions = {str(row["value"]["direction"]) for row in emitted}
    independent_disagreement = 1.0 if {"POSITIVE", "NEGATIVE"}.issubset(directions) and len(groups) >= 2 else 0.0
    low_support = 1.0 - min(1.0, len(groups) / 2.0)
    boundary = uncertainty if emitted else 1.0

    if "POSITIVE" in directions and "NEGATIVE" not in directions:
        signal = 0.75 + (sum(strengths) / len(strengths)) * 0.25
        direction_bucket = "positive"
    elif "NEGATIVE" in directions and "POSITIVE" not in directions:
        signal = 0.25 - (sum(strengths) / len(strengths)) * 0.25
        direction_bucket = "negative"
    else:
        signal = 0.5
        direction_bucket = "abstained" if abstained else "mixed"
    components = ScoreComponents(
        uncertainty=_bounded(uncertainty),
        independent_disagreement=_bounded(independent_disagreement),
        abstention_pressure=_bounded(abstention_pressure),
        boundary_proximity=_bounded(boundary),
        low_effective_support=_bounded(low_support),
        novelty_underrepresentation=0.0,
        challenge_audit_bonus=0.35 if challenge else 0.0,
        pair_proximity=0.0,
    )
    notes = (
        "real pilot directional disagreement is retained and not fabricated",
        "component values are deterministic acquisition heuristics, not probabilities",
    )
    return components, _bounded(signal), direction_bucket, notes


def extract_candidates(
    evidence_rows: Iterable[Mapping[str, Any]],
    split_rows: Mapping[str, Mapping[str, Any]],
    feature_rows: Mapping[str, Mapping[str, Any]],
    challenge_by_map: Mapping[str, tuple[str, ...]],
) -> list[Candidate]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        proposition = str(row["proposition"]["key"])
        if proposition not in SELECTED_PROPOSITIONS:
            continue
        entity = _entity_ref(row["entity"])
        if entity.map_checksum in CONTAINED_DEFECT_MAPS:
            continue
        grouped[(entity.stable_key, proposition, str(row["proposition"]["version"]))].append(row)

    prelim: list[Candidate] = []
    for (_, proposition, proposition_version), rows in sorted(grouped.items()):
        if any(row.get("status") in ("UNAVAILABLE", "INVALID") for row in rows):
            continue
        ref = _entity_ref(rows[0]["entity"])
        split = split_rows.get(ref.map_checksum)
        feature = feature_rows.get(ref.map_checksum)
        if split is None or feature is None:
            continue
        challenges = tuple(sorted(challenge_by_map.get(ref.map_checksum, ())))
        components, signal, direction_bucket, notes = _base_components(rows, bool(challenges))
        display = "entity-" + hashlib.sha256(ref.stable_key.encode("utf-8")).hexdigest()[:12]
        neutral = {
            "duration_ms": feature.get("duration_ms"),
            "object_count": feature.get("object_count"),
            "bpm_max": feature.get("bpm_max"),
        }
        neutral = {key: value for key, value in neutral.items() if isinstance(value, (int, float)) and math.isfinite(float(value))}
        entity = AnnotationEntity(
            ref=ref,
            anonymous_display_id=display,
            set_group_key=str(split["set_group_key"]),
            mapper_group_key=str(split["mapper_group_key"]),
            neutral_metadata=neutral,
        )
        snapshot = _snapshot_hash(rows)
        candidate_id = "candidate-" + hashlib.sha256(
            f"{proposition}\n{ref.stable_key}\n{snapshot}".encode("utf-8")
        ).hexdigest()[:24]
        statuses = tuple(sorted(str(row["status"]) for row in rows))
        directions = tuple(sorted({str(row["value"]["direction"]) for row in rows if row.get("value")}))
        bucket = f"{ref.scope.value.lower()}:{direction_bucket}:{'challenge' if challenges else 'ordinary'}"
        prelim.append(Candidate(
            candidate_id=candidate_id,
            proposition_key=proposition,
            proposition_version=proposition_version,
            entity=entity,
            statuses=statuses,
            directions=directions,
            evidence_snapshot_hash=snapshot,
            source_rule_ids=tuple(sorted(str(row["rule"]["id"]) for row in rows)),
            challenge_categories=challenges,
            evidence_bucket=bucket,
            signal_position=signal,
            score_components=components,
            acquisition_score=0.0,
            selection_notes=notes,
        ))

    bucket_counts = Counter(candidate.evidence_bucket for candidate in prelim)
    max_count = max(bucket_counts.values(), default=1)
    output: list[Candidate] = []
    for candidate in prelim:
        novelty = 1.0 - (bucket_counts[candidate.evidence_bucket] - 1) / max_count
        components = replace(candidate.score_components, novelty_underrepresentation=_bounded(novelty))
        weights = {
            "uncertainty": 0.18,
            "independent_disagreement": 0.18,
            "abstention_pressure": 0.18,
            "boundary_proximity": 0.14,
            "low_effective_support": 0.12,
            "novelty_underrepresentation": 0.10,
            "challenge_audit_bonus": 0.10,
        }
        values = components.as_dict()
        total = sum(weights[key] * values[key] for key in weights)
        output.append(replace(candidate, score_components=components, acquisition_score=_bounded(total)))
    return sorted(output, key=lambda item: (item.proposition_key, item.entity.stable_key))


def candidate_diagnostics(candidates: Iterable[Candidate]) -> dict[str, Any]:
    rows = list(candidates)
    return {
        "selection_version": SELECTION_VERSION,
        "total_eligible": len(rows),
        "by_proposition": dict(sorted(Counter(row.proposition_key for row in rows).items())),
        "by_scope": dict(sorted(Counter(row.scope.value for row in rows).items())),
        "by_evidence_bucket": dict(sorted(Counter(row.evidence_bucket for row in rows).items())),
        "contained_defect_maps_excluded": dict(sorted(CONTAINED_DEFECT_MAPS.items())),
        "selected_propositions": list(SELECTED_PROPOSITIONS),
        "excluded_propositions": dict(sorted(EXCLUDED_PROPOSITIONS.items())),
        "score_semantics": "bounded deterministic acquisition priority; not probability or confidence",
    }


__all__ = [
    "SELECTION_VERSION", "SELECTED_PROPOSITIONS", "EXCLUDED_PROPOSITIONS",
    "CONTAINED_DEFECT_MAPS", "Candidate", "extract_candidates", "candidate_diagnostics",
]
