"""Safe Slider evidence contract for the default Skill Profiler runtime.

The runtime exposes ppy-aligned Slider geometry and an explicit semantic
ownership map.  It deliberately does not turn map geometry, leaderboard rank,
or a lossy ``.osr`` cursor trace into a player score.  Per-object head/tick/
repeat/tail/break judgements become ``PROVEN`` only when an independent,
integrity-checked ppy judgement trace is supplied.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


SLIDER_RUNTIME_SCHEMA_VERSION = "ppy_slider_runtime_v0.1.0"
SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION = "ppy_slider_judgement_trace_v0.1.0"
SLIDER_SCORE_OBSERVATION_SCHEMA_VERSION = "ppy_slider_score_observation_v0.1.0"

SLIDER_PHASES = ("head", "tick", "repeat", "tail", "break")
SLIDER_JUDGEMENT_SEMANTICS = (
    "stable_legacy",
    "lazer_default",
    "lazer_classic",
    "unverified",
)
_RESULTS = frozenset({"300", "100", "50", "miss", "hit", "break", "unverified"})

# Runtime traces may use either the compact contract values or ppy's
# HitResult names. Keep the raw result in the evidence while validating its
# semantic class here.
_RESULT_ALIASES = {
    "great": "300",
    "ok": "100",
    "meh": "50",
    "miss": "miss",
    "hit": "hit",
    "break": "break",
    "largetickhit": "hit",
    "largetickmiss": "miss",
    "smalltickhit": "hit",
    "smalltickmiss": "miss",
    "slidertailhit": "hit",
    "ignorehit": "hit",
    "ignoremiss": "miss",
}

_INDEPENDENT_TRACE_SOURCES = {
    "ppy_stable_judgement_trace": "stable_legacy",
    "ppy_lazer_default_judgement_trace": "lazer_default",
    "ppy_lazer_classic_judgement_trace": "lazer_classic",
}

# These are score-level fields emitted by modern ppy score serializers.  They
# are useful aggregate observations, but they still do not identify the map
# object that produced a result.  Keep aliases here because API payloads and
# internal ppy names use different casing/pluralisation.
_MODERN_SCORE_ALIASES: dict[str, tuple[str, ...]] = {
    "slider_tail_hit": ("slider_tail_hit", "slider_tail_hits", "SliderTailHit"),
    "large_tick_hit": ("large_tick_hit", "large_tick_hits", "LargeTickHit"),
    "large_tick_miss": ("large_tick_miss", "large_tick_misses", "LargeTickMiss"),
    "small_tick_hit": ("small_tick_hit", "small_tick_hits", "SmallTickHit"),
    "small_tick_miss": ("small_tick_miss", "small_tick_misses", "SmallTickMiss"),
}
_LEGACY_SCORE_ALIASES: dict[str, tuple[str, ...]] = {
    "count_300": ("count_300", "great", "Great"),
    "count_100": ("count_100", "ok", "Ok"),
    "count_50": ("count_50", "meh", "Meh"),
    "count_miss": ("count_miss", "miss", "Miss"),
}

SLIDER_JUDGEMENT_CONTRACT = {
    "schema_version": SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION,
    "phase_order": list(SLIDER_PHASES),
    "required_event_fields": ["event_id", "object_id", "phase", "result", "offset_ms"],
    "result_values": sorted(_RESULTS),
    "result_aliases": sorted(_RESULT_ALIASES),
    "judgement_semantics": list(SLIDER_JUDGEMENT_SEMANTICS),
    "independent_source_kinds": sorted(_INDEPENDENT_TRACE_SOURCES),
    "provenance_requirement": (
        "source_kind in {ppy_stable_judgement_trace, ppy_lazer_default_judgement_trace, "
        "ppy_lazer_classic_judgement_trace} and integrity=verified"
    ),
    "replay_boundary": (
        "stable .osr exposes cursor frames and aggregate header counts but does not identify "
        "which Slider head/tick/repeat/tail event produced each count"
    ),
}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _first_finite(features: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite(features.get(key))
        if value is not None:
            return value
    return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _first_int(features: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _nonnegative_int(features.get(key))
        if value is not None:
            return value
    return None


def _statistics_mapping(score: Mapping[str, Any]) -> Mapping[str, Any]:
    statistics = score.get("statistics")
    return statistics if isinstance(statistics, Mapping) else score


def build_slider_score_observation(
    score: Mapping[str, Any] | None = None,
    *,
    map_geometry: Mapping[str, Any] | None = None,
    ppy_estimates: Mapping[str, Any] | None = None,
    source_kind: str | None = None,
    integrity: str | None = None,
) -> dict[str, Any]:
    """Normalize score-level Slider statistics without fabricating events.

    Modern ppy statistics (for example ``SliderTailHit`` and
    ``LargeTickMiss``) are exact *aggregate* categories when the caller marks
    the payload as verified.  Legacy stable score headers only expose total
    300/100/50/miss counts, so they stay ``AGGREGATE_ONLY``.  Neither form can
    be routed to a per-object judgement or a formal player axis.
    """

    score = score if isinstance(score, Mapping) else {}
    stats = _statistics_mapping(score)
    geometry = {str(key): _nonnegative_int(value) for key, value in (map_geometry or {}).items()}
    geometry = {key: value for key, value in geometry.items() if value is not None}
    observed_modern: dict[str, int] = {}
    observed_legacy: dict[str, int] = {}
    invalid_fields: list[str] = []

    for canonical, aliases in _MODERN_SCORE_ALIASES.items():
        for alias in aliases:
            if alias in stats:
                parsed = _nonnegative_int(stats.get(alias))
                if parsed is None:
                    invalid_fields.append(canonical)
                else:
                    observed_modern[canonical] = parsed
                break
    for canonical, aliases in _LEGACY_SCORE_ALIASES.items():
        for alias in aliases:
            if alias in stats:
                parsed = _nonnegative_int(stats.get(alias))
                if parsed is None:
                    invalid_fields.append(canonical)
                else:
                    observed_legacy[canonical] = parsed
                break

    source = str(source_kind or score.get("source_kind") or "unverified")
    integrity_value = str(integrity or score.get("integrity") or "unverified")
    semantics = str(score.get("score_semantics") or score.get("mode") or "unverified")
    estimates: dict[str, float] = {}
    for key, value in (ppy_estimates or score.get("ppy_estimates") or {}).items():
        number = _finite(value)
        if number is not None and number >= 0:
            estimates[str(key)] = number

    if invalid_fields:
        status = "INVALID"
        reason = "score_statistics_contain_negative_or_non_numeric_values"
    elif observed_modern and integrity_value == "verified":
        status = "EXACT_AGGREGATE"
        reason = "verified_ppy_score_statistics_do_not_identify_object_identity"
    elif observed_modern:
        status = "AGGREGATE_ONLY"
        reason = "modern_slider_statistics_present_but_source_integrity_is_unverified"
    elif observed_legacy:
        status = "AGGREGATE_ONLY"
        reason = "legacy_score_header_has_total_judgement_counts_only"
    elif estimates:
        status = "AGGREGATE_ESTIMATE"
        reason = "ppy_slider_break_estimates_are_model_outputs_not_judgements"
    else:
        status = "UNVERIFIED"
        reason = "no_slider_score_statistics_or_ppy_estimate"

    phase_evidence = {
        phase: {
            "status": "UNVERIFIED",
            "reason": "score_level_aggregate_has_no_event_identity",
            "event_count": 0,
        }
        for phase in SLIDER_PHASES
    }
    return {
        "schema_version": SLIDER_SCORE_OBSERVATION_SCHEMA_VERSION,
        "status": status,
        "source_kind": source,
        "integrity": integrity_value,
        "score_semantics": semantics,
        "modern_statistics": observed_modern or None,
        "legacy_statistics": observed_legacy or None,
        "ppy_estimates": estimates or None,
        "map_geometry": geometry or None,
        "phase_evidence": phase_evidence,
        "per_event_identity": False,
        "formal_axis_admission": "NOT_ADMITTED",
        "player_skill_score_admitted": False,
        "admission_reason": reason,
    }


def _unverified_phase(reason: str) -> dict[str, Any]:
    return {"status": "UNVERIFIED", "reason": reason, "event_count": 0}


def _normalise_semantics(value: Any) -> str:
    """Return one of the explicit Stable/Lazer judgement semantic labels."""

    token = str(value or "").strip().lower().replace("+", "_").replace("-", "_")
    aliases = {
        "stable": "stable_legacy",
        "legacy": "stable_legacy",
        "stable_legacy": "stable_legacy",
        "lazer": "lazer_default",
        "lazer_default": "lazer_default",
        "lazerclassic": "lazer_classic",
        "lazer_classic": "lazer_classic",
        "classic": "lazer_classic",
    }
    return aliases.get(token, "unverified")


def _trace_semantics(trace: Mapping[str, Any]) -> str:
    explicit = trace.get("judgement_semantics")
    if explicit is None:
        explicit = trace.get("semantic_mode")
    if explicit is None:
        explicit = trace.get("rule_semantics")
    semantics = _normalise_semantics(explicit)
    if semantics != "unverified":
        return semantics
    return _INDEPENDENT_TRACE_SOURCES.get(str(trace.get("source_kind", "")), "unverified")


def _trace_integrity(trace: Mapping[str, Any]) -> tuple[str, bool | None, str]:
    """Read old string and new object-shaped integrity fields uniformly."""

    raw = trace.get("integrity")
    if isinstance(raw, Mapping):
        status = str(raw.get("status", "unverified")).lower()
        identity = raw.get("per_event_identity")
        identity_value = identity if isinstance(identity, bool) else None
        parity = str(raw.get("aggregate_parity", "unverified")).lower()
        return status, identity_value, parity
    return str(raw or "unverified").lower(), None, "unverified"


def _event_value(event: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in event:
            return event[key]
    return None


def _normalise_result(value: Any) -> str:
    token = str(value or "").strip().lower().replace("_", "")
    return _RESULT_ALIASES.get(token, token)


def evaluate_slider_judgement_contract(trace: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate an independent per-event trace without inventing missing events."""

    if trace is None:
        phases = {phase: _unverified_phase("no_independent_ppy_judgement_trace") for phase in SLIDER_PHASES}
        return {
            "contract_version": SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION,
            "status": "UNVERIFIED",
            "source_kind": "none",
            "integrity": "unavailable",
            "judgement_semantics": "unverified",
            "aggregate_parity": "unverified",
            "formal_axis_admission": "NOT_ADMITTED",
            "phases": phases,
            "admission_reason": "osr_replay_or_map_geometry_does_not_identify_nested_judgements",
        }

    if not isinstance(trace, Mapping):
        return {
            "contract_version": SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION,
            "status": "UNVERIFIED",
            "source_kind": "invalid",
            "integrity": "invalid",
            "judgement_semantics": "unverified",
            "aggregate_parity": "unverified",
            "formal_axis_admission": "NOT_ADMITTED",
            "phases": {phase: _unverified_phase("trace_is_not_an_object") for phase in SLIDER_PHASES},
            "admission_reason": "trace_shape_invalid",
        }

    source_kind = str(trace.get("source_kind", "unverified"))
    semantics = _trace_semantics(trace)
    integrity_status, identity_flag, aggregate_parity = _trace_integrity(trace)
    if trace.get("schema_version") != SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION:
        reason = "unsupported_judgement_trace_schema"
    elif source_kind not in _INDEPENDENT_TRACE_SOURCES:
        reason = "trace_source_is_not_independent_ppy_judgement_trace"
    elif semantics == "unverified":
        reason = "judgement_semantics_unverified"
    elif integrity_status != "verified":
        reason = "judgement_trace_integrity_not_verified"
    elif identity_flag is False:
        reason = "judgement_trace_per_event_identity_not_verified"
    elif trace.get("reconstructed_from_replay") is True:
        reason = "replay_reconstruction_cannot_prove_nested_judgement"
    else:
        reason = None

    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    if reason is None and not events:
        reason = "judgement_trace_has_no_events"

    phase_events: dict[str, list[dict[str, Any]]] = {phase: [] for phase in SLIDER_PHASES}
    invalid = False
    seen_ids: set[str] = set()
    if reason is None:
        for event in events:
            if not isinstance(event, Mapping):
                invalid = True
                continue
            event_id_value = _event_value(event, "event_id", "EventIndex", "event_index")
            event_id = "" if event_id_value is None else str(event_id_value)
            object_id = _event_value(event, "object_id", "ObjectId")
            phase_value = _event_value(event, "phase", "Phase")
            phase = "" if phase_value is None else str(phase_value).lower()
            result = _normalise_result(_event_value(event, "result", "Result"))
            offset = _finite(_event_value(event, "offset_ms", "OffsetMs"))
            if (
                not event_id
                or event_id in seen_ids
                or object_id is None
                or phase not in SLIDER_PHASES
                or result not in _RESULTS
                or offset is None
            ):
                invalid = True
                continue
            seen_ids.add(event_id)
            phase_events[phase].append(dict(event))
    if reason is None and invalid:
        reason = "judgement_trace_event_contract_invalid"

    if reason is not None:
        phases = {phase: _unverified_phase(reason) for phase in SLIDER_PHASES}
        return {
            "contract_version": SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION,
            "status": "UNVERIFIED",
            "source_kind": source_kind,
            "integrity": integrity_status,
            "judgement_semantics": semantics,
            "aggregate_parity": aggregate_parity,
            "formal_axis_admission": "NOT_ADMITTED",
            "phases": phases,
            "admission_reason": reason,
        }

    # Presence proves that the trace identified an event.  It does not claim
    # that an absent event was a successful hit; absence remains unverified.
    phases = {
        phase: {
            "status": "PROVEN" if phase_events[phase] else "UNVERIFIED",
            "reason": "independent_ppy_event_trace" if phase_events[phase] else "phase_not_present_in_trace",
            "event_count": len(phase_events[phase]),
            "events": phase_events[phase],
        }
        for phase in SLIDER_PHASES
    }
    status = "PROVEN" if all(item["status"] == "PROVEN" for item in phases.values()) else "PARTIAL"
    return {
        "contract_version": SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION,
        "status": status,
        "source_kind": source_kind,
        "integrity": integrity_status,
        "judgement_semantics": semantics,
        "aggregate_parity": aggregate_parity,
        # A valid event trace identifies judgements, but it is not enough to
        # admit a player axis. That still requires aggregate parity and the
        # independent cross-map holdout described by the deployment contract.
        "formal_axis_admission": "NOT_ADMITTED",
        "phases": phases,
        "admission_reason": None if status == "PROVEN" else "one_or_more_slider_phases_absent",
    }


def _phase_routes(
    *,
    has_pressure_vector: bool,
    judgement_status: str,
    map_axis_admission: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    routes = {
        "flow": {
            "status": "diagnostic_candidate" if has_pressure_vector else "geometry_only",
            "owner": "slider_body_sustained_follow",
            "evidence_fields": [
                "slider.duration_ms",
                "slider.velocity_px_per_s",
                "slider.length_px",
                "pressure.active_follow_fraction",
                "pressure.longest_active_episode_ball_path_norm_px",
            ],
            "formal_axis_admission": "NOT_ADMITTED",
            "double_count_policy": "does_not_include_head_tail_transition_or_tick_judgement",
        },
        "aim_control": {
            "status": "diagnostic_candidate" if has_pressure_vector else "UNVERIFIED",
            "owner": "independent_body_steering_and_repeat_reversal",
            "evidence_fields": [
                "pressure.residual_steering_25px_rad",
                "pressure.residual_steering_50px_rad",
                "pressure.repeat_count",
            ],
            "formal_axis_admission": "NOT_ADMITTED",
            "double_count_policy": "never reuses total slider travel already owned by Flow or ppy Aim",
        },
        "precision": {
            "status": "proven_only_with_judgement_trace" if judgement_status == "PROVEN" else "UNVERIFIED",
            "owner": "head_tick_tail_break_judgement",
            "evidence_fields": [
                "judgement.head",
                "judgement.tick",
                "judgement.tail",
                "judgement.break",
            ],
            "formal_axis_admission": "NOT_ADMITTED",
            "double_count_policy": "no cursor proximity proxy is promoted to precision without event identity",
        },
        "transition_aim": {
            "status": "delegated_to_existing_ppy_aim",
            "owner": "existing_ppy_aim_branch",
            "evidence_fields": ["slider head/exit transition geometry"],
            "formal_axis_admission": "existing_ppy_aim_contract_only",
            "double_count_policy": "excluded from the Slider body/control lane",
        },
    }
    # Map-demand admission is a separate lane from player judgement.  A
    # ppy-derived map axis may be numeric even when no replay trace is present;
    # this never upgrades the player-side judgement contract.
    map_axis_admission = map_axis_admission if isinstance(map_axis_admission, Mapping) else {}
    for route_name, axis_name in {
        "flow": "flow_aim",
        "aim_control": "aim_control",
        "precision": "spatial_precision",
    }.items():
        axis = map_axis_admission.get(axis_name)
        if isinstance(axis, Mapping) and axis.get("status") == "ADMITTED_MAP_DEMAND":
            routes[route_name]["formal_axis_admission"] = "ADMITTED_MAP_DEMAND"
            routes[route_name]["status"] = "admitted_map_demand"
    return routes


def build_slider_evidence(
    features: Mapping[str, Any],
    *,
    pressure_vector: Mapping[str, Any] | None = None,
    judgement_trace: Mapping[str, Any] | None = None,
    replay_observation: Mapping[str, Any] | None = None,
    score_observation: Mapping[str, Any] | None = None,
    formal_release: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the default safe Slider evidence object for a map profile."""

    slider_ratio = _first_finite(features, "slider.slider_ratio_mean", "slider.slider_ratio")
    repeat_total = _first_finite(features, "slider.repeat_count_total_mean", "slider.repeats_total")
    span_total = _first_finite(features, "slider.span_count_total_mean", "slider.spans_total")
    transition_count = _first_finite(features, "slider.to_circle_transition_count_mean")
    geometry_available = any(value is not None for value in (slider_ratio, repeat_total, span_total, transition_count))
    vector = {str(key): _finite(value) for key, value in (pressure_vector or {}).items()}
    vector = {key: value for key, value in vector.items() if value is not None}
    judgement = evaluate_slider_judgement_contract(judgement_trace)

    replay_status = "absent"
    if replay_observation is not None:
        replay_status = str(replay_observation.get("status", "UNVERIFIED"))

    score_status = "absent"
    if score_observation is not None:
        score_status = str(score_observation.get("status", "UNVERIFIED"))

    release = formal_release if isinstance(formal_release, Mapping) else {}
    release_axes = release.get("axes") if isinstance(release.get("axes"), Mapping) else {}
    pressure = release.get("slider_pressure") if isinstance(release.get("slider_pressure"), Mapping) else {}
    pressure_admitted = bool(pressure.get("scalar_admitted"))
    release_admission = str(release.get("formal_axis_admission", "NOT_ADMITTED"))

    return {
        "schema_version": SLIDER_RUNTIME_SCHEMA_VERSION,
        "status": "geometry_available" if geometry_available else "UNVERIFIED",
        "geometry": {
            "available": geometry_available,
            "slider_ratio": slider_ratio,
            "repeat_count_total": repeat_total,
            "span_count_total": span_total,
            "to_circle_transition_count": transition_count,
            "source": "FeatureExtractor + canonical slider semantics",
        },
        "pressure_vector": vector or None,
        "replay_observation": {
            "status": replay_status,
            "formal_axis_admission": "NOT_ADMITTED",
            "source": "bounded replay matcher" if replay_observation is not None else "none",
        },
        "score_observation": {
            "status": score_status,
            "formal_axis_admission": "NOT_ADMITTED",
            "source": "verified ppy score statistics" if score_observation is not None else "none",
            "payload": dict(score_observation) if score_observation is not None else None,
        },
        "judgement_contract": judgement,
        "semantic_routes": _phase_routes(
            has_pressure_vector=bool(vector),
            judgement_status=str(judgement.get("status")),
            map_axis_admission=release_axes,
        ),
        "formal_axis_admission": release_admission,
        "slider_pressure_scalar_admitted": pressure_admitted,
        "player_skill_score_admitted": False,
        "formal_release": dict(release) if release else None,
        "provenance": [
            "ppy_first_geometry_fields",
            "matched_evidence_required_for_execution_claims",
            "not_admitted_when_unproven",
            "no_arbitrary_weighted_slider_pressure",
            "formal_map_demand_release_is_separate_from_player_skill",
        ],
    }


__all__ = [
    "SLIDER_JUDGEMENT_CONTRACT",
    "SLIDER_JUDGEMENT_SEMANTICS",
    "SLIDER_JUDGEMENT_TRACE_SCHEMA_VERSION",
    "SLIDER_PHASES",
    "SLIDER_RUNTIME_SCHEMA_VERSION",
    "SLIDER_SCORE_OBSERVATION_SCHEMA_VERSION",
    "build_slider_score_observation",
    "build_slider_evidence",
    "evaluate_slider_judgement_contract",
]
