"""Deterministic pair construction and bounded dry-run batch building v0.1."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
from typing import Any, Iterable

from osu_skill_profiler.weak_supervision.contracts_v01 import EntityScope

from .contracts_v01 import (
    AnnotationTask,
    ControlType,
    PresentationOrder,
    ScoreComponents,
    SelectionReason,
    TaskScope,
    build_task,
    stable_id,
)
from .selection_v01 import Candidate


BATCH_BUILDER_VERSION = "0.1.0"


@dataclass(frozen=True)
class BatchConfig:
    batch_id: str = "al01-dry-run"
    seed: str = "osu-skill-profiler-active-learning-v01"
    map_tasks: int = 20
    segment_tasks: int = 65
    exact_repeats: int = 4
    inversions: int = 4
    max_ordinary_per_map: int = 3
    max_ordinary_per_set: int = 5
    max_ordinary_per_mapper: int = 5
    max_ordinary_per_bucket: int = 24

    @property
    def target_total(self) -> int:
        return self.map_tasks + self.segment_tasks + self.exact_repeats + self.inversions

    def __post_init__(self) -> None:
        if self.target_total > 200:
            raise ValueError("Active Learning v0.1 dry run may not exceed 200 tasks")
        if min(self.map_tasks, self.segment_tasks, self.exact_repeats, self.inversions) < 0:
            raise ValueError("task counts must be non-negative")


def _rank(seed: str, *parts: str) -> str:
    return hashlib.sha256((seed + "\n" + "\n".join(parts)).encode("utf-8")).hexdigest()


def _pair_components(a: Candidate, b: Candidate) -> tuple[ScoreComponents, float, float]:
    proximity = 1.0 - abs(a.signal_position - b.signal_position)
    values_a = a.score_components.as_dict()
    values_b = b.score_components.as_dict()
    values = {
        key: round((values_a[key] + values_b[key]) / 2.0, 6)
        for key in values_a
    }
    values["pair_proximity"] = round(proximity, 6)
    components = ScoreComponents(**values)
    total = round(min(1.0, (a.acquisition_score + b.acquisition_score) / 2.0 * 0.8 + proximity * 0.2), 6)
    return components, total, proximity


def _reason(a: Candidate, b: Candidate, proximity: float) -> tuple[SelectionReason, ControlType, int | None]:
    signal_delta = a.signal_position - b.signal_position
    if a.map_checksum == b.map_checksum and a.scope == EntityScope.SEGMENT:
        return SelectionReason.WITHIN_MAP_SEGMENT, ControlType.WITHIN_MAP_SEGMENT, None
    if abs(signal_delta) >= 0.65:
        return SelectionReason.EASY_ANCHOR, ControlType.EASY_ANCHOR, 1 if signal_delta > 0 else -1
    if a.challenge_categories or b.challenge_categories:
        return SelectionReason.CHALLENGE_AUDIT, ControlType.NONE, None
    if all(status == "ABSTAINED" for status in (*a.statuses, *b.statuses)):
        return SelectionReason.AMBIGUOUS_CONTROL, ControlType.AMBIGUOUS_CONTROL, 0
    if a.score_components.abstention_pressure + b.score_components.abstention_pressure >= 1.0:
        return SelectionReason.ABSTENTION_HEAVY, ControlType.NONE, None
    if proximity >= 0.85:
        return SelectionReason.BOUNDARY_ADJACENT, ControlType.NONE, None
    return SelectionReason.INFORMATIVE_UNCERTAIN, ControlType.NONE, None


def _make_task(
    config: BatchConfig,
    a: Candidate,
    b: Candidate,
    ordinal: int,
) -> AnnotationTask:
    if a.proposition_key != b.proposition_key or a.scope != b.scope:
        raise ValueError("pair candidates must have matching proposition and scope")
    if a.entity.stable_key == b.entity.stable_key:
        raise ValueError("ordinary pair cannot contain the same entity twice")
    components, total, proximity = _pair_components(a, b)
    reason, control_type, expected = _reason(a, b, proximity)
    order = PresentationOrder.AB if int(_rank(config.seed + ":order", a.candidate_id, b.candidate_id), 16) % 2 == 0 else PresentationOrder.BA
    scope = TaskScope.MAP_PAIR if a.scope == EntityScope.MAP else TaskScope.SEGMENT_PAIR
    return build_task(
        batch_id=config.batch_id,
        proposition_key=a.proposition_key,
        proposition_version=a.proposition_version,
        scope=scope,
        entity_a=a.entity,
        entity_b=b.entity,
        selection_reason=reason,
        selection_score_components=components,
        acquisition_score=total,
        weak_evidence_snapshot={
            "candidate_a": a.evidence_snapshot_hash,
            "candidate_b": b.evidence_snapshot_hash,
            "weak_evidence_is_ground_truth": False,
        },
        provenance={
            "builder_version": BATCH_BUILDER_VERSION,
            "seed": config.seed,
            "candidate_ids": [a.candidate_id, b.candidate_id],
            "challenge_categories": sorted(set(a.challenge_categories + b.challenge_categories)),
            "evidence_buckets": [a.evidence_bucket, b.evidence_bucket],
            "ordinal": ordinal,
        },
        control_type=control_type,
        presentation_order=order,
        diagnostic_expected_canonical_sign=expected,
    )


def _candidate_pairs(candidates: list[Candidate], seed: str) -> list[tuple[Candidate, Candidate]]:
    by_group: dict[tuple[str, EntityScope], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_group[(candidate.proposition_key, candidate.scope)].append(candidate)
    pairs: list[tuple[Candidate, Candidate]] = []
    for (proposition, scope), members in sorted(by_group.items(), key=lambda item: (item[0][0], item[0][1].value)):
        ordered = sorted(members, key=lambda item: (item.signal_position, _rank(seed, item.candidate_id), item.candidate_id))
        if len(ordered) < 2:
            continue
        # Near-neighbour pairs exercise uncertainty; offset pairs supply anchors
        # and challenge diversity.  This is bounded and deterministic.
        for index, left in enumerate(ordered):
            for offset in (1, 2, max(1, len(ordered) // 2), len(ordered) - 1):
                right = ordered[(index + offset) % len(ordered)]
                if left.entity.stable_key == right.entity.stable_key:
                    continue
                a, b = sorted((left, right), key=lambda item: item.entity.stable_key)
                pairs.append((a, b))
        # Deliberately expose bounded low/high contrasts so easy-anchor
        # controls exist even when most candidates cluster near a boundary.
        anchor_width = min(24, len(ordered) // 2)
        for index in range(anchor_width):
            left, right = ordered[index], ordered[-1 - index]
            if left.entity.stable_key != right.entity.stable_key:
                a, b = sorted((left, right), key=lambda item: item.entity.stable_key)
                pairs.append((a, b))
        # Same-map segment pairs are explicit diagnostic controls.  They are
        # still distinct canonical segments and never bypass entity identity.
        if scope == EntityScope.SEGMENT:
            by_map: dict[str, list[Candidate]] = defaultdict(list)
            for member in ordered:
                by_map[member.map_checksum].append(member)
            for map_checksum, map_members in sorted(by_map.items()):
                local = sorted(map_members, key=lambda item: (item.signal_position, item.entity.stable_key))
                if len(local) >= 2:
                    a, b = sorted((local[0], local[-1]), key=lambda item: item.entity.stable_key)
                    if a.entity.stable_key != b.entity.stable_key:
                        pairs.append((a, b))
    unique: dict[tuple[str, str, str], tuple[Candidate, Candidate]] = {}
    for a, b in pairs:
        key = (a.proposition_key, a.entity.stable_key, b.entity.stable_key)
        unique.setdefault(key, (a, b))
    return sorted(unique.values(), key=lambda pair: (_rank(seed + ":pairs", pair[0].candidate_id, pair[1].candidate_id), pair[0].candidate_id, pair[1].candidate_id))


def _select_scope(
    candidates: list[Candidate],
    scope: EntityScope,
    count: int,
    config: BatchConfig,
    selected_pairs: set[tuple[str, str, str]],
    counters: dict[str, Counter[str]],
    start_ordinal: int,
) -> list[AnnotationTask]:
    tasks: list[AnnotationTask] = []
    raw_pairs = _candidate_pairs([row for row in candidates if row.scope == scope], config.seed + ":" + scope.value)
    ranked: dict[SelectionReason, list[tuple[Candidate, Candidate]]] = defaultdict(list)
    for a, b in raw_pairs:
        _, _, proximity = _pair_components(a, b)
        reason, _, _ = _reason(a, b, proximity)
        ranked[reason].append((a, b))
    for reason in ranked:
        ranked[reason].sort(key=lambda pair: (_rank(config.seed + ":reason:" + reason.value, pair[0].candidate_id, pair[1].candidate_id), pair[0].candidate_id, pair[1].candidate_id))

    quotas = (
        {
            SelectionReason.EASY_ANCHOR: 2,
            SelectionReason.AMBIGUOUS_CONTROL: 2,
            SelectionReason.CHALLENGE_AUDIT: 3,
        }
        if scope == EntityScope.MAP
        else {
            SelectionReason.EASY_ANCHOR: 2,
            SelectionReason.AMBIGUOUS_CONTROL: 2,
            SelectionReason.WITHIN_MAP_SEGMENT: 4,
            SelectionReason.CHALLENGE_AUDIT: 7,
        }
    )
    ordered_pairs: list[tuple[Candidate, Candidate]] = []
    consumed: set[tuple[str, str, str]] = set()
    for reason, quota in quotas.items():
        for pair in ranked.get(reason, ())[:quota]:
            key = (pair[0].proposition_key, pair[0].entity.stable_key, pair[1].entity.stable_key)
            if key not in consumed:
                consumed.add(key)
                ordered_pairs.append(pair)
    ordinary_reasons = (
        SelectionReason.BOUNDARY_ADJACENT,
        SelectionReason.INFORMATIVE_UNCERTAIN,
        SelectionReason.ABSTENTION_HEAVY,
    )
    fill = [pair for reason in ordinary_reasons for pair in ranked.get(reason, ())]
    fill.sort(key=lambda pair: (_rank(config.seed + ":ordinary-fill", pair[0].candidate_id, pair[1].candidate_id), pair[0].candidate_id, pair[1].candidate_id))
    for pair in fill:
        key = (pair[0].proposition_key, pair[0].entity.stable_key, pair[1].entity.stable_key)
        if key not in consumed:
            consumed.add(key)
            ordered_pairs.append(pair)
    # Only if ordinary pools cannot meet the target, consume additional
    # already-categorised pairs without silently changing their reason.
    remainder = [pair for pairs in ranked.values() for pair in pairs]
    remainder.sort(key=lambda pair: (_rank(config.seed + ":bounded-remainder", pair[0].candidate_id, pair[1].candidate_id), pair[0].candidate_id, pair[1].candidate_id))
    for pair in remainder:
        key = (pair[0].proposition_key, pair[0].entity.stable_key, pair[1].entity.stable_key)
        if key not in consumed:
            consumed.add(key)
            ordered_pairs.append(pair)

    for a, b in ordered_pairs:
        key = (a.proposition_key, *sorted((a.entity.stable_key, b.entity.stable_key)))
        if key in selected_pairs:
            continue
        proposed = {
            "map": Counter({name: 1 for name in (a.map_checksum, b.map_checksum)}),
            "set": Counter({name: 1 for name in (a.entity.set_group_key, b.entity.set_group_key)}),
            "mapper": Counter({name: 1 for name in (a.entity.mapper_group_key, b.entity.mapper_group_key)}),
            "bucket": Counter({name: 1 for name in (a.evidence_bucket, b.evidence_bucket)}),
        }
        limits = {
            "map": config.max_ordinary_per_map,
            "set": config.max_ordinary_per_set,
            "mapper": config.max_ordinary_per_mapper,
            "bucket": config.max_ordinary_per_bucket,
        }
        if any(counters[kind][name] + amount > limits[kind] for kind, values in proposed.items() for name, amount in values.items()):
            continue
        task = _make_task(config, a, b, start_ordinal + len(tasks))
        tasks.append(task)
        selected_pairs.add(key)
        for kind, values in proposed.items():
            counters[kind].update(values)
        if len(tasks) == count:
            break
    if len(tasks) != count:
        raise ValueError(f"insufficient diverse {scope.value} pairs: requested {count}, selected {len(tasks)}")
    return tasks


def _clone_control(source: AnnotationTask, config: BatchConfig, control_type: ControlType, ordinal: int) -> AnnotationTask:
    if control_type not in (ControlType.EXACT_REPEAT, ControlType.AB_INVERSION):
        raise ValueError("only exact repeat and inversion clone an existing task")
    inverted = control_type == ControlType.AB_INVERSION
    group_id = stable_id("control-", {"source": source.task_id, "type": control_type.value})
    kwargs: dict[str, Any] = {
        "batch_id": source.batch_id,
        "proposition_key": source.proposition_key,
        "proposition_version": source.proposition_version,
        "scope": source.scope,
        "entity_a": source.entity_a,
        "entity_b": source.entity_b,
        "selection_reason": SelectionReason.AB_INVERSION if inverted else SelectionReason.EXACT_REPEAT,
        "selection_score_components": source.selection_score_components,
        "acquisition_score": source.acquisition_score,
        "weak_evidence_snapshot": dict(source.weak_evidence_snapshot),
        "provenance": {**dict(source.provenance), "ordinal": ordinal, "control_source": source.task_id},
        "control_type": control_type,
        "control_group_id": group_id,
        "source_task_id": source.task_id,
        "presentation_order": (
            PresentationOrder.BA if inverted and source.presentation_order == PresentationOrder.AB
            else PresentationOrder.AB if inverted else source.presentation_order
        ),
        "diagnostic_expected_canonical_sign": source.diagnostic_expected_canonical_sign,
    }
    return build_task(**kwargs)


def validate_duplicate_policy(tasks: Iterable[AnnotationTask]) -> None:
    seen: dict[tuple[str, str, str], AnnotationTask] = {}
    ids: set[str] = set()
    for task in tasks:
        if task.task_id in ids:
            raise ValueError("duplicate task_id")
        ids.add(task.task_id)
        prior = seen.get(task.unordered_pair_key)
        if prior is not None:
            explicit = task.control_type in (ControlType.EXACT_REPEAT, ControlType.AB_INVERSION) and task.source_task_id == prior.task_id
            if not explicit:
                raise ValueError("accidental duplicate unordered pair")
        else:
            seen[task.unordered_pair_key] = task


def build_batch(candidates: Iterable[Candidate], config: BatchConfig = BatchConfig()) -> tuple[list[AnnotationTask], dict[str, Any]]:
    rows = list(candidates)
    selected_pairs: set[tuple[str, str, str]] = set()
    counters = {name: Counter() for name in ("map", "set", "mapper", "bucket")}
    ordinary: list[AnnotationTask] = []
    ordinary.extend(_select_scope(rows, EntityScope.MAP, config.map_tasks, config, selected_pairs, counters, 0))
    ordinary.extend(_select_scope(rows, EntityScope.SEGMENT, config.segment_tasks, config, selected_pairs, counters, len(ordinary)))
    ranked_sources = sorted(ordinary, key=lambda task: (_rank(config.seed + ":controls", task.task_id), task.task_id))
    controls: list[AnnotationTask] = []
    for source in ranked_sources[: config.exact_repeats]:
        controls.append(_clone_control(source, config, ControlType.EXACT_REPEAT, len(ordinary) + len(controls)))
    inversion_sources = ranked_sources[config.exact_repeats : config.exact_repeats + config.inversions]
    for source in inversion_sources:
        controls.append(_clone_control(source, config, ControlType.AB_INVERSION, len(ordinary) + len(controls)))
    tasks = ordinary + controls
    validate_duplicate_policy(tasks)
    if len(tasks) != config.target_total:
        raise AssertionError("batch size mismatch")
    diagnostics = {
        "builder_version": BATCH_BUILDER_VERSION,
        "batch_id": config.batch_id,
        "seed": config.seed,
        "task_count": len(tasks),
        "source_pair_count_before_repeat_inversion_controls": len(ordinary),
        "non_control_task_count": sum(task.control_type == ControlType.NONE for task in tasks),
        "control_task_count": len(controls) + sum(task.control_type not in (ControlType.NONE,) for task in ordinary),
        "by_scope": dict(sorted(Counter(task.scope.value for task in tasks).items())),
        "by_proposition": dict(sorted(Counter(task.proposition_key for task in tasks).items())),
        "by_selection_reason": dict(sorted(Counter(task.selection_reason.value for task in tasks).items())),
        "by_control_type": dict(sorted(Counter(task.control_type.value for task in tasks).items())),
        "unique_entities": len({key for task in tasks for key in (task.entity_a.stable_key, task.entity_b.stable_key)}),
        "diversity": {
            "maps": len(counters["map"]),
            "sets": len(counters["set"]),
            "mappers": len(counters["mapper"]),
            "max_ordinary_tasks_per_map": max(counters["map"].values(), default=0),
            "max_ordinary_tasks_per_set": max(counters["set"].values(), default=0),
            "max_ordinary_tasks_per_mapper": max(counters["mapper"].values(), default=0),
            "limits": {
                "map": config.max_ordinary_per_map,
                "set": config.max_ordinary_per_set,
                "mapper": config.max_ordinary_per_mapper,
                "evidence_bucket": config.max_ordinary_per_bucket,
            },
        },
        "no_taxonomy_frozen": True,
        "no_model_trained": True,
    }
    return tasks, diagnostics


__all__ = [
    "BATCH_BUILDER_VERSION", "BatchConfig", "build_batch",
    "validate_duplicate_policy",
]
