"""Conservative diagnostics for ordinal pairwise HUMAN evidence v0.1."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Mapping

from .contracts_v01 import AnnotationResponse, AnnotationTask, PairwiseAnswer, canonical_answer


METRICS_VERSION = "0.1.0"


def _direction(answer: PairwiseAnswer) -> int | None:
    if answer == PairwiseAnswer.CANNOT_JUDGE:
        return None
    if answer in (PairwiseAnswer.A_CLEARLY_HIGHER, PairwiseAnswer.A_SLIGHTLY_HIGHER):
        return 1
    if answer in (PairwiseAnswer.B_CLEARLY_HIGHER, PairwiseAnswer.B_SLIGHTLY_HIGHER):
        return -1
    return 0


def _ordinal(answer: PairwiseAnswer) -> int | None:
    return {
        PairwiseAnswer.B_CLEARLY_HIGHER: -2,
        PairwiseAnswer.B_SLIGHTLY_HIGHER: -1,
        PairwiseAnswer.APPROX_EQUAL: 0,
        PairwiseAnswer.A_SLIGHTLY_HIGHER: 1,
        PairwiseAnswer.A_CLEARLY_HIGHER: 2,
        PairwiseAnswer.CANNOT_JUDGE: None,
    }[answer]


def annotation_metrics(
    tasks: Iterable[AnnotationTask],
    responses: Iterable[AnnotationResponse],
) -> dict:
    task_by_id = {task.task_id: task for task in tasks}
    response_rows = list(responses)
    canonical: list[tuple[AnnotationResponse, AnnotationTask, PairwiseAnswer]] = []
    for response in response_rows:
        task = task_by_id.get(response.task_id)
        if task is None:
            raise ValueError("metrics received response for unknown task")
        canonical.append((response, task, canonical_answer(task, response)))

    answer_counts = Counter(answer.value for _, _, answer in canonical)
    abstentions = answer_counts[PairwiseAnswer.CANNOT_JUDGE.value]
    non_abstain = [(response, task, answer) for response, task, answer in canonical if _direction(answer) is not None]

    by_pair_annotator: dict[tuple[str, str, str, str], list[tuple[AnnotationTask, PairwiseAnswer]]] = defaultdict(list)
    for response, task, answer in canonical:
        by_pair_annotator[(response.annotator_id, *task.unordered_pair_key)].append((task, answer))
    repeat_total = repeat_consistent = inversion_total = inversion_consistent = 0
    repeat_strict = inversion_strict = 0
    repeat_ordinal_distance = inversion_ordinal_distance = 0.0
    for rows in by_pair_annotator.values():
        if len(rows) < 2:
            continue
        base_task, base_answer = rows[0]
        base_direction = _direction(base_answer)
        for task, answer in rows[1:]:
            direction = _direction(answer)
            if task.control_type.value == "AB_INVERSION":
                inversion_total += base_direction is not None and direction is not None
                inversion_consistent += base_direction is not None and direction is not None and base_direction == direction
                if base_direction is not None and direction is not None:
                    inversion_strict += base_answer == answer
                    base_ordinal, ordinal = _ordinal(base_answer), _ordinal(answer)
                    assert base_ordinal is not None and ordinal is not None
                    inversion_ordinal_distance += abs(base_ordinal - ordinal)
            else:
                repeat_total += base_direction is not None and direction is not None
                repeat_consistent += base_direction is not None and direction is not None and base_direction == direction
                if base_direction is not None and direction is not None:
                    repeat_strict += base_answer == answer
                    base_ordinal, ordinal = _ordinal(base_answer), _ordinal(answer)
                    assert base_ordinal is not None and ordinal is not None
                    repeat_ordinal_distance += abs(base_ordinal - ordinal)

    by_task: dict[str, list[int]] = defaultdict(list)
    ordinal_by_task: dict[str, list[int]] = defaultdict(list)
    for _, task, answer in non_abstain:
        direction = _direction(answer)
        ordinal = _ordinal(answer)
        assert direction is not None and ordinal is not None
        by_task[task.task_id].append(direction)
        ordinal_by_task[task.task_id].append(ordinal)
    pairwise_comparisons = pairwise_agreements = 0
    weighted_distance_sum = 0.0
    weighted_pairs = 0
    for task_id in sorted(by_task):
        directions = by_task[task_id]
        ordinals = ordinal_by_task[task_id]
        for left in range(len(directions)):
            for right in range(left + 1, len(directions)):
                pairwise_comparisons += 1
                pairwise_agreements += directions[left] == directions[right]
                weighted_distance_sum += abs(ordinals[left] - ordinals[right]) / 4.0
                weighted_pairs += 1

    # Position bias is about the displayed first/second side, so use the raw
    # A/B response before canonical entity-orientation normalization.
    first_side = sum(
        1 for response, _, _ in non_abstain
        if response.answer in (PairwiseAnswer.A_CLEARLY_HIGHER, PairwiseAnswer.A_SLIGHTLY_HIGHER)
    )
    second_side = sum(
        1 for response, _, _ in non_abstain
        if response.answer in (PairwiseAnswer.B_CLEARLY_HIGHER, PairwiseAnswer.B_SLIGHTLY_HIGHER)
    )
    directional_count = first_side + second_side

    anchor_total = anchor_agree = 0
    for _, task, answer in non_abstain:
        if task.control_type.value != "EASY_ANCHOR" or task.diagnostic_expected_canonical_sign is None:
            continue
        anchor_total += 1
        anchor_agree += _direction(answer) == task.diagnostic_expected_canonical_sign

    # Diagnostic transitivity is only evaluated on strict directional edges
    # within one annotator and proposition. Equality/abstention is excluded.
    edges: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for response, task, answer in non_abstain:
        direction = _direction(answer)
        if direction == 0:
            continue
        a, b = task.entity_a.stable_key, task.entity_b.stable_key
        winner, loser = (a, b) if direction == 1 else (b, a)
        edges[(response.annotator_id, task.proposition_key)].add((winner, loser))
    transitive_checks = transitive_violations = 0
    for group_edges in edges.values():
        for a, b in group_edges:
            for b2, c in group_edges:
                if b != b2 or a == c:
                    continue
                transitive_checks += 1
                transitive_violations += (c, a) in group_edges

    return {
        "metrics_version": METRICS_VERSION,
        "response_count": len(response_rows),
        "response_distribution": dict(sorted(answer_counts.items())),
        "abstention_rate": abstentions / len(response_rows) if response_rows else 0.0,
        "abstention_count": abstentions,
        "ordinal_direction_excluded_count": abstentions,
        "intra_annotator_consistency": {
            "rate": repeat_consistent / repeat_total if repeat_total else None,
            "strict_ordinal_rate": repeat_strict / repeat_total if repeat_total else None,
            "directional_rate": repeat_consistent / repeat_total if repeat_total else None,
            "mean_ordinal_distance": repeat_ordinal_distance / repeat_total if repeat_total else None,
            "comparable_controls": repeat_total,
        },
        "inversion_consistency": {
            "rate": inversion_consistent / inversion_total if inversion_total else None,
            "strict_ordinal_rate": inversion_strict / inversion_total if inversion_total else None,
            "directional_rate": inversion_consistent / inversion_total if inversion_total else None,
            "mean_ordinal_distance": inversion_ordinal_distance / inversion_total if inversion_total else None,
            "comparable_controls": inversion_total,
        },
        "position_bias": {
            "first_presented_direction_rate": first_side / directional_count if directional_count else None,
            "directional_responses": directional_count,
            "interpretation": "diagnostic only; equality and CANNOT_JUDGE excluded",
        },
        "anchor_agreement": {
            "rate": anchor_agree / anchor_total if anchor_total else None,
            "comparable_responses": anchor_total,
            "interpretation": "diagnostic against deliberately easy controls, not annotator accuracy",
        },
        "directional_inter_annotator_agreement": {
            "rate": pairwise_agreements / pairwise_comparisons if pairwise_comparisons else None,
            "annotator_pairs": pairwise_comparisons,
        },
        "weighted_ordinal_disagreement": {
            "mean_normalized_distance": weighted_distance_sum / weighted_pairs if weighted_pairs else None,
            "annotator_pairs": weighted_pairs,
        },
        "pairwise_transitivity": {
            "violation_rate": transitive_violations / transitive_checks if transitive_checks else None,
            "ordered_two_edge_checks": transitive_checks,
            "interpretation": "diagnostic only; subjective multidimensional phenomena need not be transitive",
        },
        "human_evidence_is_ground_truth": False,
    }


__all__ = ["METRICS_VERSION", "annotation_metrics"]
