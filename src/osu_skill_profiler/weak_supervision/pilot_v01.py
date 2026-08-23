"""Small, provisional pilot registry and deterministic weak rules.

Thresholds are sparse QA discriminators, not learned boundaries.  Every
middle region abstains so the pilot does not manufacture coverage.
"""

from __future__ import annotations

import math
from typing import Protocol

from .contracts_v01 import (
    AbstentionReason,
    ConfidenceBand,
    EntityScope,
    EvidenceDirection,
    EvidenceStatus,
    EvidenceValue,
    PropositionStatus,
    RuleContext,
    RuleOutcome,
    SourceFamily,
)
from .registry_v01 import (
    PropositionDefinition,
    PropositionRegistry,
    RuleDefinition,
    RuleRegistry,
    SourceDefinition,
    SourceRegistry,
)

PILOT_PROPOSITION_VERSION = "0.1.0"
PILOT_RULE_VERSION = "0.1.0"


class ExecutableWeakRule(Protocol):
    definition: RuleDefinition

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        ...


def _numeric(context: RuleContext, names: tuple[str, ...]) -> tuple[tuple[float, ...] | None, RuleOutcome | None]:
    values: list[float] = []
    for name in names:
        value = context.values.get(name)
        if value is None:
            return None, RuleOutcome(
                status=EvidenceStatus.UNAVAILABLE,
                reason=AbstentionReason.MISSING_REQUIRED_SIGNAL,
                diagnostics=(f"missing:{name}",),
            )
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return None, RuleOutcome(
                status=EvidenceStatus.INVALID,
                reason=AbstentionReason.UNSUPPORTED_SEMANTICS,
                diagnostics=(f"invalid_nonfinite_or_nonnumeric:{name}",),
            )
        values.append(float(value))
    return tuple(values), None


def _strength(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        raise ValueError("invalid strength calibration range")
    return round(max(0.0, min(1.0, (value - lower) / (upper - lower))), 6)


class ObservableMovementTailRule:
    definition = RuleDefinition(
        rule_id="ws01.observable.movement_tail",
        version=PILOT_RULE_VERSION,
        source_id="ws01.source.observable.movement_tail",
        source_version="0.1.0",
        proposition_key="ws01.provisional.movement_demand_high",
        proposition_version=PILOT_PROPOSITION_VERSION,
        applicable_scopes=(EntityScope.MAP,),
        input_dependencies=("spatial.distance_norm_p95", "spatial.velocity_norm_per_s_p95"),
        confidence_semantics="HIGH means both observable tail discriminators clear sparse fixed bounds; it is not a probability.",
        confidence_band=ConfidenceBand.HIGH,
        abstention_conditions=("missing/nonfinite input", "mixed or middle-band evidence"),
        rationale="Large spacing and high movement-rate tails jointly provide observable evidence of high movement demand.",
        discriminator="positive at distance>=0.45 and velocity>=3.0; negative at distance<=0.18 and velocity<=0.8; otherwise abstain",
        failure_modes=("coordinate normalisation is not CS-normalised", "map-level p95 hides local structure"),
    )

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        values, unavailable = _numeric(context, self.definition.input_dependencies)
        if unavailable:
            return unavailable
        distance, velocity = values or (0.0, 0.0)
        diagnostics = (f"distance_norm_p95={distance:.6g}", f"velocity_norm_per_s_p95={velocity:.6g}")
        if distance >= 0.45 and velocity >= 3.0:
            joint = min(_strength(distance, 0.45, 0.9), _strength(velocity, 3.0, 9.0))
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.POSITIVE), joint, ConfidenceBand.HIGH, diagnostics=diagnostics)
        if distance <= 0.18 and velocity <= 0.8:
            joint = min(_strength(0.18 - distance, 0.0, 0.18), _strength(0.8 - velocity, 0.0, 0.8))
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), joint, ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        return RuleOutcome(EvidenceStatus.ABSTAINED, reason=AbstentionReason.AMBIGUOUS_EVIDENCE, diagnostics=diagnostics)


class ReferenceSnapTailRule:
    definition = RuleDefinition(
        rule_id="ws01.reference.ppy_snap_tail",
        version=PILOT_RULE_VERSION,
        source_id="ws01.source.reference.ppy_snap_tail",
        source_version="0.1.0",
        proposition_key="ws01.provisional.movement_demand_high",
        proposition_version=PILOT_PROPOSITION_VERSION,
        applicable_scopes=(EntityScope.MAP,),
        input_dependencies=("ref.ppy.snap_include_sliders",),
        confidence_semantics="MEDIUM is a fixed policy-tail discriminator over reference-only p90; it is not truth or probability.",
        confidence_band=ConfidenceBand.MEDIUM,
        abstention_conditions=("Reference unavailable", "geometry blocked", "middle-band policy value"),
        rationale="Pinned ppy snap policy supplies an intentionally reference-only second view of movement demand.",
        discriminator="positive at object p90>=1.8; negative at p90<=0.55; otherwise abstain",
        failure_modes=("ppy policy is tuned reference, not observable truth", "unmodded-only semantics", "p90 discards sequence order"),
    )

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        blocked = context.provenance.get("geometry_blocked", False)
        if blocked:
            return RuleOutcome(EvidenceStatus.UNAVAILABLE, reason=AbstentionReason.GEOMETRY_BLOCKED, diagnostics=("reference_geometry_blocked",))
        values, unavailable = _numeric(context, self.definition.input_dependencies)
        if unavailable:
            reason = AbstentionReason.REFERENCE_UNAVAILABLE
            return RuleOutcome(EvidenceStatus.UNAVAILABLE, reason=reason, diagnostics=unavailable.diagnostics)
        (snap_p90,) = values or (0.0,)
        diagnostics = (f"ref_ppy_snap_include_sliders_p90={snap_p90:.6g}",)
        if snap_p90 >= 1.8:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.POSITIVE), _strength(snap_p90, 1.8, 4.0), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        if snap_p90 <= 0.55:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), _strength(0.55 - snap_p90, 0.0, 0.55), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        return RuleOutcome(EvidenceStatus.ABSTAINED, reason=AbstentionReason.AMBIGUOUS_EVIDENCE, diagnostics=diagnostics)


class DenseTimingPressureRule:
    definition = RuleDefinition(
        rule_id="ws01.observable.dense_timing",
        version=PILOT_RULE_VERSION,
        source_id="ws01.source.observable.dense_timing",
        source_version="0.1.0",
        proposition_key="ws01.provisional.dense_timing_pressure_high",
        proposition_version=PILOT_PROPOSITION_VERSION,
        applicable_scopes=(EntityScope.MAP,),
        input_dependencies=("temporal.object_rate_max_1s", "temporal.burst_longest_duration_ms_125ms"),
        confidence_semantics="HIGH requires both peak rate and sustained 125ms-density bounds; deterministic strength is bounded margin only.",
        confidence_band=ConfidenceBand.HIGH,
        abstention_conditions=("missing/nonfinite input", "one discriminator without the other", "middle band"),
        rationale="Peak one-second rate plus sustained <=125ms gaps is a mechanically observable timing-pressure conjunction.",
        discriminator="positive at rate>=9 and duration>=750ms; negative at rate<=4 and duration=0; otherwise abstain",
        failure_modes=("does not distinguish alternating from single-tap patterns", "breaks and map length are not interpreted"),
    )

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        values, unavailable = _numeric(context, self.definition.input_dependencies)
        if unavailable:
            return unavailable
        rate, duration = values or (0.0, 0.0)
        diagnostics = (f"object_rate_max_1s={rate:.6g}", f"burst_longest_125ms={duration:.6g}")
        if rate >= 9.0 and duration >= 750.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.POSITIVE), min(_strength(rate, 9, 16), _strength(duration, 750, 3000)), ConfidenceBand.HIGH, diagnostics=diagnostics)
        if rate <= 4.0 and duration == 0.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), _strength(4.0 - rate, 0, 4), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        return RuleOutcome(EvidenceStatus.ABSTAINED, reason=AbstentionReason.INSUFFICIENT_SUPPORT, diagnostics=diagnostics)


class SliderControlLoadRule:
    definition = RuleDefinition(
        rule_id="ws01.observable.slider_control_load",
        version=PILOT_RULE_VERSION,
        source_id="ws01.source.observable.slider_control",
        source_version="0.1.0",
        proposition_key="ws01.provisional.slider_control_load_high",
        proposition_version=PILOT_PROPOSITION_VERSION,
        applicable_scopes=(EntityScope.MAP,),
        input_dependencies=("slider.slider_ratio", "slider.duration_ms_p90", "slider.repeat_count_total"),
        confidence_semantics="MEDIUM is a deterministic conjunction over corrected Feature 0.2 slider composition/duration/repeats.",
        confidence_band=ConfidenceBand.MEDIUM,
        abstention_conditions=("no sliders or missing duration", "mixed or middle-band evidence"),
        rationale="A slider-heavy map with long-tail duration or repeat burden supplies observable control-load evidence.",
        discriminator="positive at ratio>=0.55, p90>=700ms, repeats>=1; negative at ratio<=0.1 and repeats=0; otherwise abstain",
        failure_modes=("does not simulate cursor path difficulty", "slider count can reflect mapping style rather than demand"),
    )

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        ratio = context.values.get("slider.slider_ratio")
        duration = context.values.get("slider.duration_ms_p90")
        repeats = context.values.get("slider.repeat_count_total")
        if ratio == 0 and duration is None and repeats == 0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), 1.0, ConfidenceBand.HIGH, diagnostics=("no_sliders",))
        values, unavailable = _numeric(context, self.definition.input_dependencies)
        if unavailable:
            return unavailable
        ratio_f, duration_f, repeats_f = values or (0.0, 0.0, 0.0)
        diagnostics = (f"slider_ratio={ratio_f:.6g}", f"slider_duration_p90={duration_f:.6g}", f"repeat_count_total={repeats_f:.6g}")
        if ratio_f >= 0.55 and duration_f >= 700.0 and repeats_f >= 1.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.POSITIVE), min(_strength(ratio_f, .55, .9), _strength(duration_f, 700, 2500)), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        if ratio_f <= 0.1 and repeats_f == 0.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), _strength(0.1 - ratio_f, 0, .1), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        return RuleOutcome(EvidenceStatus.ABSTAINED, reason=AbstentionReason.AMBIGUOUS_EVIDENCE, diagnostics=diagnostics)


class LocalSliderTravelSegmentRule:
    definition = RuleDefinition(
        rule_id="ws01.local.slider_travel_segment",
        version=PILOT_RULE_VERSION,
        source_id="ws01.source.local.slider_travel_segment",
        source_version="0.1.0",
        proposition_key="ws01.provisional.slider_tracking_travel_high",
        proposition_version=PILOT_PROPOSITION_VERSION,
        applicable_scopes=(EntityScope.SEGMENT,),
        input_dependencies=("ls.lazy_travel_distance_cs_normalised",),
        confidence_semantics="MEDIUM is a fixed p90 discriminator inside the canonical Local 5s segment; it is not probability.",
        confidence_band=ConfidenceBand.MEDIUM,
        abstention_conditions=("Local signal unavailable", "geometry blocked", "middle-band segment"),
        rationale="Corrected Local lazy-travel distance supplies a slider-path-aware observable within canonical segments.",
        discriminator="positive at segment p90>=100; negative when segment max=0; otherwise abstain",
        failure_modes=("lazy cursor policy is an approximation", "segment p90 can hide one extreme slider"),
    )

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        if context.provenance.get("geometry_blocked", False):
            return RuleOutcome(EvidenceStatus.UNAVAILABLE, reason=AbstentionReason.GEOMETRY_BLOCKED, diagnostics=("local_geometry_blocked",))
        values, unavailable = _numeric(context, self.definition.input_dependencies)
        if unavailable:
            return unavailable
        (p90,) = values or (0.0,)
        maximum = context.provenance.get("source_segment_max")
        diagnostics = (f"lazy_travel_distance_segment_p90={p90:.6g}", f"segment_max={maximum}")
        if p90 >= 100.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.POSITIVE), _strength(p90, 100, 350), ConfidenceBand.MEDIUM, diagnostics=diagnostics)
        if isinstance(maximum, (int, float)) and math.isfinite(float(maximum)) and float(maximum) == 0.0:
            return RuleOutcome(EvidenceStatus.EMITTED, EvidenceValue(EvidenceDirection.NEGATIVE), 1.0, ConfidenceBand.HIGH, diagnostics=diagnostics)
        return RuleOutcome(EvidenceStatus.ABSTAINED, reason=AbstentionReason.AMBIGUOUS_EVIDENCE, diagnostics=diagnostics)


PILOT_PROPOSITIONS = PropositionRegistry("0.1.0", (
    PropositionDefinition(
        "ws01.provisional.movement_demand_high", PILOT_PROPOSITION_VERSION, PropositionStatus.PROVISIONAL,
        "The entity exhibits high movement-demand evidence under a declared source; not a canonical skill.",
        (EntityScope.MAP, EntityScope.SEGMENT), ("POSITIVE", "NEGATIVE", "PAIRWISE"),
    ),
    PropositionDefinition(
        "ws01.provisional.dense_timing_pressure_high", PILOT_PROPOSITION_VERSION, PropositionStatus.PROVISIONAL,
        "The entity exhibits high dense-timing pressure under fixed observable discriminators.",
        (EntityScope.MAP, EntityScope.SEGMENT), ("POSITIVE", "NEGATIVE", "PAIRWISE"),
    ),
    PropositionDefinition(
        "ws01.provisional.slider_control_load_high", PILOT_PROPOSITION_VERSION, PropositionStatus.PROVISIONAL,
        "The entity exhibits high slider-control load under fixed observable discriminators.",
        (EntityScope.MAP, EntityScope.SEGMENT), ("POSITIVE", "NEGATIVE", "PAIRWISE"),
    ),
    PropositionDefinition(
        "ws01.provisional.slider_tracking_travel_high", PILOT_PROPOSITION_VERSION, PropositionStatus.PROVISIONAL,
        "The canonical segment exhibits high corrected Local lazy-travel distance evidence.",
        (EntityScope.SEGMENT,), ("POSITIVE", "NEGATIVE", "PAIRWISE"),
    ),
))


PILOT_SOURCES = SourceRegistry("0.1.0", (
    SourceDefinition(
        "ws01.source.observable.movement_tail", "0.1.0", SourceFamily.OBSERVABLE,
        ("spatial.distance_norm_p95", "spatial.velocity_norm_per_s_p95"), (), True, True, False,
        "observable.feature.movement_tail", True, "Corrected Feature 0.2 map-level movement tails.",
        "docs/FEATURE_MIGRATION_V01_TO_V02.md",
    ),
    SourceDefinition(
        "ws01.source.reference.ppy_snap_tail", "0.1.0", SourceFamily.REFERENCE_PPY,
        ("ref.ppy.snap_include_sliders",), (), False, True, True,
        "reference.ppy.snap_policy", True, "Deterministic p90 transform of pinned ppy snap reference rows.",
        "docs/PPY_REFERENCE_SIGNAL_CONTRACT_V02.md",
    ),
    SourceDefinition(
        "ws01.source.observable.dense_timing", "0.1.0", SourceFamily.OBSERVABLE,
        ("temporal.object_rate_max_1s", "temporal.burst_longest_duration_ms_125ms"), (), True, True, False,
        "observable.feature.dense_timing", True, "Corrected Feature 0.2 map-level timing density measurements.",
        "docs/FEATURE_MIGRATION_V01_TO_V02.md",
    ),
    SourceDefinition(
        "ws01.source.observable.slider_control", "0.1.0", SourceFamily.OBSERVABLE,
        ("slider.slider_ratio", "slider.duration_ms_p90", "slider.repeat_count_total"), (), True, True, False,
        "observable.feature.slider_control", True, "Corrected Feature 0.2 slider composition and duration measurements.",
        "docs/FEATURE_MIGRATION_V01_TO_V02.md",
    ),
    SourceDefinition(
        "ws01.source.local.slider_travel_segment", "0.1.0", SourceFamily.LOCAL_SIGNAL,
        ("ls.lazy_travel_distance_cs_normalised",), (), True, True, False,
        "local.slider_lazy_travel", True, "Canonical Local 0.3 segment p90 over corrected lazy-travel distance.",
        "docs/LOCAL_SIGNAL_CONTRACT_V03.md",
    ),
))

PILOT_RULES: tuple[ExecutableWeakRule, ...] = (
    ObservableMovementTailRule(), ReferenceSnapTailRule(), DenseTimingPressureRule(), SliderControlLoadRule(),
    LocalSliderTravelSegmentRule(),
)
PILOT_RULE_REGISTRY = RuleRegistry((rule.definition for rule in PILOT_RULES), PILOT_PROPOSITIONS, PILOT_SOURCES)
