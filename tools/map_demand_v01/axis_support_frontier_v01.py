"""Versioned, axis-agnostic support-frontier extraction.

This module deliberately keeps five concepts separate:

* ``physical_peak`` is the largest finite absolute-difficulty observation;
* ``evidence_confidence`` describes the reliability of the supplied evidence;
* ``establishment`` describes how much same-episode evidence supports a level;
* ``sustain`` describes how much active time supports a level; and
* ``recurrence`` describes whether support reappears in separate episodes or
  sections.

Confidence is metadata.  It never scales a difficulty, a support value, or a
frontier.  Per-sample ``weight`` is instead intrinsic mechanism exposure (for
example, a transition's non-double-tap share), and therefore may contribute to
support without changing ``physical_peak``.

Frontiers are found by scanning every observed difficulty threshold.  Partial
support is linearly interpolated from the zero-difficulty origin to that
threshold, so the result has no fixed star ceiling and remains continuous while
evidence accumulates.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "axis_support_frontier_v01"


@dataclass(frozen=True)
class SupportSample:
    """One absolute-difficulty observation used by a support frontier.

    ``episode_id`` should identify one uninterrupted hard run.  A separated
    repetition should receive a different episode id.  ``section_id`` is a
    coarser map region and can be selected as the recurrence unit by policy.
    ``duration_ms`` is active exposure time, not wall-clock time to the next
    observation.  Point observations receive the policy's ``point_duration_ms``.
    """

    difficulty: float
    time_ms: float
    duration_ms: float = 0.0
    episode_id: Any = 0
    section_id: Any = 0
    weight: float = 1.0


@dataclass(frozen=True)
class SupportPolicy:
    """Configuration for converting observations into independent frontiers."""

    name: str = "generic"
    establishment_target_weight: float = 12.0
    sustain_target_ms: float = 1200.0
    recurrence_target_episodes: float = 2.0
    recurrence_min_episode_weight: float = 2.0
    point_duration_ms: float = 75.0
    frontier_support_target: float = 0.8
    establishment_mix: float = 0.55
    sustain_mix: float = 0.30
    recurrence_mix: float = 0.15
    recurrence_scope: str = "episode"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("SupportPolicy.name must be a non-empty string")
        for field_name in (
            "establishment_target_weight",
            "sustain_target_ms",
            "recurrence_target_episodes",
            "recurrence_min_episode_weight",
            "frontier_support_target",
        ):
            value = _finite_float(getattr(self, field_name))
            if value is None or value <= 0.0:
                raise ValueError(f"SupportPolicy.{field_name} must be finite and positive")
            object.__setattr__(self, field_name, value)
        point_duration_ms = _finite_float(self.point_duration_ms)
        if point_duration_ms is None or point_duration_ms < 0.0:
            raise ValueError("SupportPolicy.point_duration_ms must be finite and non-negative")
        object.__setattr__(self, "point_duration_ms", point_duration_ms)
        if self.frontier_support_target > 1.0:
            raise ValueError("SupportPolicy.frontier_support_target must be at most 1")
        mix_names = ("establishment_mix", "sustain_mix", "recurrence_mix")
        mixes = tuple(_finite_float(getattr(self, field_name)) for field_name in mix_names)
        if any(value is None or value < 0.0 for value in mixes):
            raise ValueError("SupportPolicy mix weights must be finite and non-negative")
        if sum(value for value in mixes if value is not None) <= 0.0:
            raise ValueError("SupportPolicy requires at least one positive mix weight")
        for field_name, value in zip(mix_names, mixes):
            object.__setattr__(self, field_name, value)
        if self.recurrence_scope not in {"episode", "section", "episode_section"}:
            raise ValueError(
                "SupportPolicy.recurrence_scope must be episode, section, or episode_section"
            )

    @classmethod
    def jump(cls) -> "SupportPolicy":
        """A persistence-forward preset for spatial jump observations."""

        return cls(
            name="jump",
            establishment_target_weight=16.0,
            sustain_target_ms=1600.0,
            recurrence_target_episodes=2.0,
            recurrence_min_episode_weight=3.0,
            point_duration_ms=80.0,
            frontier_support_target=0.8,
            establishment_mix=0.60,
            sustain_mix=0.25,
            recurrence_mix=0.15,
            recurrence_scope="episode",
        )

    @classmethod
    def raw_speed(cls) -> "SupportPolicy":
        """A shorter-window preset for raw-speed burst observations."""

        return cls(
            name="raw_speed",
            # Six pairs are a real burst, but not yet the same evidence as an
            # established speed passage.  Sixteen effective pairs retain a
            # roughly one-second high-rate response without letting one
            # isolated burst claim a full speed-map rating.
            establishment_target_weight=16.0,
            sustain_target_ms=1200.0,
            recurrence_target_episodes=2.0,
            recurrence_min_episode_weight=2.0,
            point_duration_ms=50.0,
            frontier_support_target=0.8,
            establishment_mix=0.62,
            sustain_mix=0.23,
            recurrence_mix=0.15,
            recurrence_scope="episode",
        )


@dataclass
class _NormalSample:
    difficulty: float
    time_ms: float
    duration_ms: float
    episode_id: Any
    section_id: Any
    weight: float


@dataclass
class _GroupState:
    weight: float = 0.0
    active_ms: float = 0.0
    sample_count: int = 0
    start_ms: float | None = None
    end_ms: float | None = None
    episode_id: Any = None
    section_id: Any = None

    def add(self, sample: _NormalSample, point_duration_ms: float) -> None:
        self.weight += sample.weight
        active_ms = max(sample.duration_ms, point_duration_ms) * sample.weight
        self.active_ms += active_ms
        self.sample_count += 1
        start_ms = sample.time_ms
        end_ms = sample.time_ms + max(sample.duration_ms, point_duration_ms)
        self.start_ms = start_ms if self.start_ms is None else min(self.start_ms, start_ms)
        self.end_ms = end_ms if self.end_ms is None else max(self.end_ms, end_ms)
        self.episode_id = sample.episode_id
        self.section_id = sample.section_id


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _finite_float(value: object) -> float | None:
    if not _is_finite_number(value):
        return None
    return float(value)


def _safe_identifier(value: Any) -> Any:
    try:
        hash(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


def _coerce_sample(value: SupportSample | Mapping[str, Any]) -> _NormalSample | None:
    if isinstance(value, SupportSample):
        difficulty = _finite_float(value.difficulty)
        time_ms = _finite_float(value.time_ms)
        duration_ms = _finite_float(value.duration_ms)
        weight = _finite_float(value.weight)
        episode_id = value.episode_id
        section_id = value.section_id
    elif isinstance(value, Mapping):
        difficulty = _finite_float(value.get("difficulty"))
        time_ms = _finite_float(value.get("time_ms"))
        duration_ms = _finite_float(value.get("duration_ms", 0.0))
        weight = _finite_float(value.get("weight", 1.0))
        episode_id = value.get("episode_id", 0)
        section_id = value.get("section_id", 0)
    else:
        return None
    if difficulty is None or time_ms is None or duration_ms is None or weight is None:
        return None
    if duration_ms < 0.0 or weight < 0.0:
        return None
    return _NormalSample(
        difficulty=max(0.0, difficulty),
        time_ms=time_ms,
        duration_ms=duration_ms,
        episode_id=_safe_identifier(episode_id),
        section_id=_safe_identifier(section_id),
        weight=weight,
    )


def _confidence(value: object) -> float:
    numeric = _finite_float(value)
    if numeric is None:
        return 0.0
    return min(1.0, max(0.0, numeric))


def _frontier_star(threshold: float, support: float, target: float) -> float:
    """Interpolate partial support linearly without imposing an upper bound."""

    return threshold * min(1.0, max(0.0, support) / target)


def select_public_frontier(
    frontier: Mapping[str, Any],
    *,
    components: Iterable[str],
    policy_id: str,
) -> dict[str, Any]:
    """Select an explicit public frontier without blending unlike evidence.

    The caller decides which support meanings are allowed for its mechanic.
    Selection is a deterministic maximum over already support-qualified
    frontiers; physical peak and evidence confidence are never candidates.
    Earlier component names win exact ties.
    """

    if not isinstance(frontier, Mapping):
        raise TypeError("frontier must be a mapping")
    if frontier.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("support frontier schema mismatch")
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise ValueError("policy_id must be a non-empty string")
    allowed = tuple(components)
    if not allowed:
        raise ValueError("at least one public frontier component is required")
    unknown = [
        component
        for component in allowed
        if component not in {"establishment", "sustain", "recurrence"}
    ]
    if unknown:
        raise ValueError(f"unknown public frontier components: {unknown!r}")

    selected_component: str | None = None
    selected_star: float | None = None
    component_frontiers: dict[str, float | None] = {}
    for component in allowed:
        payload = frontier.get(component)
        if not isinstance(payload, Mapping):
            raise ValueError(f"support frontier missing {component}")
        candidate = _finite_float(payload.get("frontier_star"))
        if candidate is not None and candidate < 0.0:
            raise ValueError(f"{component}.frontier_star must be non-negative")
        component_frontiers[component] = candidate
        if candidate is not None and (
            selected_star is None or candidate > selected_star
        ):
            selected_component = component
            selected_star = candidate

    physical_peak = _finite_float(frontier.get("physical_peak"))
    if (
        selected_star is not None
        and physical_peak is not None
        and selected_star > physical_peak + 1e-12
    ):
        raise ValueError("selected public frontier exceeds physical peak")
    return {
        "frontier_star": selected_star,
        "selected_component": selected_component,
        "eligible_components": list(allowed),
        "component_frontiers": component_frontiers,
        "policy_id": policy_id,
        "selection_method": "MAX_SUPPORT_QUALIFIED_FRONTIER",
        "confidence_affects_selection": False,
        "physical_peak_is_candidate": False,
    }


def _episode_key(sample: _NormalSample) -> tuple[Any, Any]:
    # Section is included to avoid accidental collisions when callers reuse
    # local episode ordinals in every section.
    return sample.section_id, sample.episode_id


def _merge_group_states(left: _GroupState, right: _GroupState) -> _GroupState:
    """Merge adjacent active runs belonging to one caller episode."""

    return _GroupState(
        weight=left.weight + right.weight,
        active_ms=left.active_ms + right.active_ms,
        sample_count=left.sample_count + right.sample_count,
        start_ms=(
            right.start_ms
            if left.start_ms is None
            else left.start_ms
            if right.start_ms is None
            else min(left.start_ms, right.start_ms)
        ),
        end_ms=(
            right.end_ms
            if left.end_ms is None
            else left.end_ms
            if right.end_ms is None
            else max(left.end_ms, right.end_ms)
        ),
        episode_id=left.episode_id,
        section_id=left.section_id,
    )


def _recurrence_key(sample: _NormalSample, scope: str) -> Any:
    if scope == "section":
        return sample.section_id
    if scope == "episode_section":
        return sample.episode_id, sample.section_id
    return _episode_key(sample)


def _component_result(
    *,
    frontier_star: float,
    threshold: float,
    support: float,
    qualifying_sample_count: int,
    qualifying_weight: float,
    episode_count: int,
    section_count: int,
    group: _GroupState | None = None,
    recurrence_units: float | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "frontier_star": frontier_star,
        "support": support,
        "winning_threshold_star": threshold,
        "qualifying_sample_count": qualifying_sample_count,
        "qualifying_weight": qualifying_weight,
        "episode_count": episode_count,
        "section_count": section_count,
    }
    if group is not None:
        result.update(
            {
                "winning_episode_id": group.episode_id,
                "winning_section_id": group.section_id,
                "winning_episode_weight": group.weight,
                "winning_episode_active_ms": group.active_ms,
                "winning_episode_sample_count": group.sample_count,
                "winning_episode_start_ms": group.start_ms,
                "winning_episode_end_ms": group.end_ms,
            }
        )
    if recurrence_units is not None:
        result["recurrence_units"] = recurrence_units
    return result


def _empty_result(policy: SupportPolicy, evidence_confidence: object, ignored: int) -> dict[str, Any]:
    empty_component = {
        "frontier_star": None,
        "support": 0.0,
        "winning_threshold_star": None,
        "qualifying_sample_count": 0,
        "qualifying_weight": 0.0,
        "episode_count": 0,
        "section_count": 0,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "INSUFFICIENT_EVIDENCE",
        "policy": policy.name,
        "physical_peak": None,
        "evidence_confidence": _confidence(evidence_confidence),
        "establishment": dict(empty_component),
        "sustain": dict(empty_component),
        "recurrence": dict(empty_component, recurrence_units=0.0),
        "combined_frontier_star": None,
        "combined_support": 0.0,
        "valid_sample_count": 0,
        "positive_weight_sample_count": 0,
        "ignored_sample_count": ignored,
        "threshold_count": 0,
        "diagnostics": {
            "confidence_affects_frontier": False,
            "threshold_scan": "ALL_OBSERVED_UNBOUNDED_LINEAR_PARTIAL_SUPPORT",
        },
    }


def evaluate_support_frontier(
    samples: Iterable[SupportSample | Mapping[str, Any]],
    policy: SupportPolicy | None = None,
    evidence_confidence: float = 1.0,
) -> dict[str, Any]:
    """Evaluate independent support frontiers for absolute-difficulty samples.

    Every distinct observed difficulty is scanned as a threshold.  At a
    threshold, only samples at or above it may establish, sustain, or recur.
    This prevents slower filler below an existing frontier from lending support
    to the harder mode.  The function is deterministic and has no difficulty
    clipping or fixed upper bound.
    """

    if policy is None:
        policy = DEFAULT_SUPPORT_POLICY
    if not isinstance(policy, SupportPolicy):
        raise TypeError("policy must be a SupportPolicy")

    normal: list[_NormalSample] = []
    ignored = 0
    try:
        iterator = iter(samples)
    except TypeError:
        return _empty_result(policy, evidence_confidence, 1)
    for value in iterator:
        sample = _coerce_sample(value)
        if sample is None:
            ignored += 1
        else:
            normal.append(sample)
    if not normal:
        return _empty_result(policy, evidence_confidence, ignored)

    physical_peak = max(item.difficulty for item in normal)

    # Build caller-episode adjacency in time order.  At every scanned
    # difficulty threshold an inactive (below-threshold or zero-weight) sample
    # is a real boundary.  This is the crucial distinction between one
    # contiguous burst and fast intervals scattered across an otherwise
    # ordinary map.
    neighbours: list[list[int]] = [[] for _ in normal]
    members_by_episode: dict[tuple[Any, Any], list[int]] = {}
    for sample_index, sample in enumerate(normal):
        members_by_episode.setdefault(_episode_key(sample), []).append(sample_index)
    for members in members_by_episode.values():
        members.sort(key=lambda member: (normal[member].time_ms, member))
        for left, right in zip(members, members[1:]):
            neighbours[left].append(right)
            neighbours[right].append(left)

    order = sorted(
        range(len(normal)),
        key=lambda sample_index: normal[sample_index].difficulty,
        reverse=True,
    )
    parent = list(range(len(normal)))
    component_size = [1] * len(normal)
    active = [False] * len(normal)
    active_states: dict[int, _GroupState] = {}
    state_revisions = [0] * len(normal)
    weight_heap: list[tuple[float, int, int, int]] = []
    active_ms_heap: list[tuple[float, int, int, int]] = []
    heap_sequence = 0
    recurrence_weights: dict[Any, float] = {}
    sections: set[Any] = set()
    qualifying_count = 0
    qualifying_weight = 0.0
    positive_weight_count = 0
    dynamic_recurrence_units = 0.0

    def find(sample_index: int) -> int:
        while parent[sample_index] != sample_index:
            parent[sample_index] = parent[parent[sample_index]]
            sample_index = parent[sample_index]
        return sample_index

    def recurrence_contribution(state: _GroupState) -> float:
        return min(1.0, state.weight / policy.recurrence_min_episode_weight)

    def push_state(root: int) -> None:
        """Publish a component state to lazy heaps in O(log n)."""

        nonlocal heap_sequence
        state = active_states[root]
        revision = state_revisions[root]
        heapq.heappush(
            weight_heap,
            (-state.weight, heap_sequence, root, revision),
        )
        heapq.heappush(
            active_ms_heap,
            (-state.active_ms, heap_sequence, root, revision),
        )
        heap_sequence += 1

    def best_state(
        heap: list[tuple[float, int, int, int]],
    ) -> _GroupState | None:
        """Return the current maximum while discarding superseded entries."""

        while heap:
            _negative_metric, _sequence, root, revision = heap[0]
            if root in active_states and state_revisions[root] == revision:
                return active_states[root]
            heapq.heappop(heap)
        return None

    def join(left_index: int, right_index: int) -> None:
        nonlocal dynamic_recurrence_units
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root == right_root:
            return
        if component_size[left_root] < component_size[right_root]:
            left_root, right_root = right_root, left_root
        left_state = active_states[left_root]
        right_state = active_states[right_root]
        if policy.recurrence_scope == "episode":
            dynamic_recurrence_units -= recurrence_contribution(left_state)
            dynamic_recurrence_units -= recurrence_contribution(right_state)
        parent[right_root] = left_root
        component_size[left_root] += component_size[right_root]
        merged = _merge_group_states(left_state, right_state)
        active_states[left_root] = merged
        del active_states[right_root]
        state_revisions[left_root] += 1
        push_state(left_root)
        if policy.recurrence_scope == "episode":
            dynamic_recurrence_units += recurrence_contribution(merged)

    def activate(sample_index: int) -> None:
        nonlocal dynamic_recurrence_units
        sample = normal[sample_index]
        if sample.weight <= 0.0:
            return
        state = _GroupState()
        state.add(sample, policy.point_duration_ms)
        active[sample_index] = True
        active_states[sample_index] = state
        state_revisions[sample_index] += 1
        push_state(sample_index)
        if policy.recurrence_scope == "episode":
            dynamic_recurrence_units += recurrence_contribution(state)
        else:
            recurrence_key = _recurrence_key(sample, policy.recurrence_scope)
            recurrence_weights[recurrence_key] = (
                recurrence_weights.get(recurrence_key, 0.0) + sample.weight
            )
        for neighbour in neighbours[sample_index]:
            if active[neighbour]:
                join(sample_index, neighbour)

    winners: dict[str, dict[str, Any] | None] = {
        "establishment": None,
        "sustain": None,
        "recurrence": None,
        "combined": None,
    }
    threshold_count = 0
    mix_total = policy.establishment_mix + policy.sustain_mix + policy.recurrence_mix

    index = 0
    while index < len(order):
        threshold = normal[order[index]].difficulty
        bucket_end = index
        while (
            bucket_end < len(order)
            and normal[order[bucket_end]].difficulty == threshold
        ):
            sample_index = order[bucket_end]
            sample = normal[sample_index]
            qualifying_count += 1
            qualifying_weight += sample.weight
            if sample.weight > 0.0:
                positive_weight_count += 1
            sections.add(sample.section_id)
            activate(sample_index)
            bucket_end += 1

        threshold_count += 1
        best_establishment_group = best_state(weight_heap)
        best_sustain_group = best_state(active_ms_heap)
        establishment_support = min(
            1.0,
            (
                0.0
                if best_establishment_group is None
                else best_establishment_group.weight
                / policy.establishment_target_weight
            ),
        )
        sustain_support = min(
            1.0,
            (
                0.0
                if best_sustain_group is None
                else best_sustain_group.active_ms / policy.sustain_target_ms
            ),
        )
        established_recurrence_units = (
            dynamic_recurrence_units
            if policy.recurrence_scope == "episode"
            else sum(
                min(1.0, weight / policy.recurrence_min_episode_weight)
                for weight in recurrence_weights.values()
            )
        )
        repeated_units = max(0.0, established_recurrence_units - 1.0)
        recurrence_support = min(1.0, repeated_units / policy.recurrence_target_episodes)
        combined_support = (
            policy.establishment_mix * establishment_support
            + policy.sustain_mix * sustain_support
            + policy.recurrence_mix * recurrence_support
        ) / mix_total

        common = {
            "threshold": threshold,
            "qualifying_sample_count": qualifying_count,
            "qualifying_weight": qualifying_weight,
            "episode_count": len(active_states),
            "section_count": len(sections),
        }
        candidates = {
            "establishment": {
                **common,
                "frontier_star": _frontier_star(
                    threshold, establishment_support, policy.frontier_support_target
                ),
                "support": establishment_support,
                "group": best_establishment_group,
            },
            "sustain": {
                **common,
                "frontier_star": _frontier_star(
                    threshold, sustain_support, policy.frontier_support_target
                ),
                "support": sustain_support,
                "group": best_sustain_group,
            },
            "recurrence": {
                **common,
                "frontier_star": _frontier_star(
                    threshold, recurrence_support, policy.frontier_support_target
                ),
                "support": recurrence_support,
                "recurrence_units": repeated_units,
            },
            "combined": {
                **common,
                "frontier_star": _frontier_star(
                    threshold, combined_support, policy.frontier_support_target
                ),
                "support": combined_support,
            },
        }
        for component, candidate in candidates.items():
            winner = winners[component]
            if winner is None or candidate["frontier_star"] > winner["frontier_star"]:
                winners[component] = candidate
        index = bucket_end

    establishment_winner = winners["establishment"]
    sustain_winner = winners["sustain"]
    recurrence_winner = winners["recurrence"]
    combined_winner = winners["combined"]
    assert establishment_winner is not None
    assert sustain_winner is not None
    assert recurrence_winner is not None
    assert combined_winner is not None

    def component(name: str, winner: dict[str, Any]) -> dict[str, Any]:
        return _component_result(
            frontier_star=winner["frontier_star"],
            threshold=winner["threshold"],
            support=winner["support"],
            qualifying_sample_count=winner["qualifying_sample_count"],
            qualifying_weight=winner["qualifying_weight"],
            episode_count=winner["episode_count"],
            section_count=winner["section_count"],
            group=winner.get("group"),
            recurrence_units=(winner.get("recurrence_units") if name == "recurrence" else None),
        )

    status = "FULL" if positive_weight_count > 0 else "INSUFFICIENT_EVIDENCE"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "policy": policy.name,
        "physical_peak": physical_peak,
        "evidence_confidence": _confidence(evidence_confidence),
        "establishment": component("establishment", establishment_winner),
        "sustain": component("sustain", sustain_winner),
        "recurrence": component("recurrence", recurrence_winner),
        "combined_frontier_star": combined_winner["frontier_star"],
        "combined_support": combined_winner["support"],
        "combined_winning_threshold_star": combined_winner["threshold"],
        "valid_sample_count": len(normal),
        "positive_weight_sample_count": positive_weight_count,
        "ignored_sample_count": ignored,
        "threshold_count": threshold_count,
        "diagnostics": {
            "confidence_affects_frontier": False,
            "threshold_scan": "ALL_OBSERVED_UNBOUNDED_LINEAR_PARTIAL_SUPPORT",
            "recurrence_scope": policy.recurrence_scope,
            "sample_weight_semantics": "INTRINSIC_MECHANISM_EXPOSURE",
        },
    }


DEFAULT_SUPPORT_POLICY = SupportPolicy()
JUMP_SUPPORT_POLICY = SupportPolicy.jump()
RAW_SPEED_SUPPORT_POLICY = SupportPolicy.raw_speed()


__all__ = [
    "DEFAULT_SUPPORT_POLICY",
    "JUMP_SUPPORT_POLICY",
    "RAW_SPEED_SUPPORT_POLICY",
    "SCHEMA_VERSION",
    "SupportPolicy",
    "SupportSample",
    "evaluate_support_frontier",
    "select_public_frontier",
]
