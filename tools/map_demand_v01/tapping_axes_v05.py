"""Beta.9.1 Raw Speed with exponent-aware threshold selection.

The rate scale and 1.5 partial-support exponent remain beta.9 calibrations.
Unlike beta.9, the powered objective is evaluated for every observed threshold
before establishment, sustain, recurrence, and combined winners are selected.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import axis_support_frontier_v02 as powered_frontier
from . import raw_speed_frontier_v01 as raw_core
from . import tapping_axes_v04 as previous


SCHEMA_VERSION = "tapping_axes_v0.7.0"
VERSION = SCHEMA_VERSION
EVENT_BUNDLE_BASIS_SCHEMA_VERSION = previous.EVENT_BUNDLE_BASIS_SCHEMA_VERSION

RAW_SPEED_SCALE = "INDEPENDENT_PHYSICAL_RATE_POWERED_FRONTIER_V06"
RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID = (
    "RAW_MAX_ESTABLISHMENT_SUSTAIN_POWERED_SCAN_V02"
)
RAW_RATE_BASELINE_PER_S = previous.RAW_RATE_BASELINE_PER_S
RAW_RATE_PER_STAR = previous.RAW_RATE_PER_STAR
RAW_PARTIAL_SUPPORT_EXPONENT = previous.RAW_PARTIAL_SUPPORT_EXPONENT

FINGER_CONTROL_SCALE = previous.FINGER_CONTROL_SCALE
FINGER_DOUBLE_TAP_WEIGHT_POLICY = previous.FINGER_DOUBLE_TAP_WEIGHT_POLICY
STAMINA_DOUBLE_TAP_WEIGHT_POLICY = previous.STAMINA_DOUBLE_TAP_WEIGHT_POLICY
FULL_COVERAGE = previous.FULL_COVERAGE
DEGRADED_COVERAGE = previous.DEGRADED_COVERAGE
PHRASE_GAP_MS = previous.PHRASE_GAP_MS


def build_event_bundle(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    bundle = previous.build_event_bundle(rows)
    bundle["schema_version"] = SCHEMA_VERSION
    bundle["version"] = VERSION
    bundle["basis_schema_version"] = EVENT_BUNDLE_BASIS_SCHEMA_VERSION
    return bundle


def _powered_frontier(
    samples: Iterable[Mapping[str, Any]],
    evidence_confidence: float,
) -> dict[str, Any]:
    return powered_frontier.evaluate_support_frontier(
        samples,
        policy=powered_frontier.RAW_SPEED_SUPPORT_POLICY,
        evidence_confidence=evidence_confidence,
    )


def extract_tapping_measures(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return corrected beta.9.1 Raw and beta.9's other tapping axes."""

    materialised = list(rows)
    inherited = previous.extract_tapping_measures(materialised)
    bundle = build_event_bundle(materialised)
    raw = raw_core.raw_speed_measure(
        bundle,
        rate_baseline_per_s=RAW_RATE_BASELINE_PER_S,
        rate_per_star=RAW_RATE_PER_STAR,
        partial_support_exponent=RAW_PARTIAL_SUPPORT_EXPONENT,
        scale=RAW_SPEED_SCALE,
        output_schema_version=SCHEMA_VERSION,
        event_bundle_basis_schema_version=EVENT_BUNDLE_BASIS_SCHEMA_VERSION,
        frontier_engine_schema_version=powered_frontier.SCHEMA_VERSION,
        frontier_evaluator=_powered_frontier,
        frontier_selector=powered_frontier.select_public_frontier,
        public_frontier_policy_id=RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID,
    )
    raw["implementation_basis_schema_version"] = SCHEMA_VERSION
    inherited["raw_speed"] = raw
    for axis, measure in inherited.items():
        measure["schema_version"] = SCHEMA_VERSION
    return inherited


__all__ = [
    "SCHEMA_VERSION",
    "VERSION",
    "EVENT_BUNDLE_BASIS_SCHEMA_VERSION",
    "RAW_SPEED_SCALE",
    "RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID",
    "RAW_RATE_BASELINE_PER_S",
    "RAW_RATE_PER_STAR",
    "RAW_PARTIAL_SUPPORT_EXPONENT",
    "FINGER_CONTROL_SCALE",
    "FINGER_DOUBLE_TAP_WEIGHT_POLICY",
    "STAMINA_DOUBLE_TAP_WEIGHT_POLICY",
    "FULL_COVERAGE",
    "DEGRADED_COVERAGE",
    "PHRASE_GAP_MS",
    "build_event_bundle",
    "extract_tapping_measures",
]
