"""Beta.9 Raw Speed scale and burst-support correction.

Beta.8 correctly separated instantaneous physical peak from the public Raw
Speed value, but two calibrations remained too generous: 200 BPM 1/4 streams
landed at 7.68, and partial burst support was interpolated linearly.  Beta.9
lowers the physical rate conversion and makes incomplete support sub-linear.
Fully established legal extremes remain unbounded.  Stamina, Finger Control,
and Endurance are inherited unchanged from beta.8.
"""

from __future__ import annotations

from typing import Any, Iterable

from . import tapping_axes_v03 as previous


SCHEMA_VERSION = "tapping_axes_v0.6.0"
VERSION = SCHEMA_VERSION
EVENT_BUNDLE_BASIS_SCHEMA_VERSION = previous.EVENT_BUNDLE_BASIS_SCHEMA_VERSION

RAW_SPEED_SCALE = "INDEPENDENT_PHYSICAL_RATE_ESTABLISHED_FRONTIER_V05"
RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID = (
    previous.RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID
)

# 200 BPM 1/4 = 13.333 taps/s.  Beta.8 mapped that to 7.68; beta.9 maps a
# fully established passage to 6.41.  This is still a demanding speed pattern
# while leaving room between ordinary 200 BPM play and genuinely extreme rate.
RAW_RATE_BASELINE_PER_S = 5.0
RAW_RATE_PER_STAR = 1.30

# A short burst is real evidence, but its very high threshold must not cancel
# the fact that it lasted only a handful of pairs.  Full support is unchanged.
RAW_PARTIAL_SUPPORT_EXPONENT = 1.50

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


def extract_tapping_measures(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return beta.9 Raw plus the frozen beta.8 auxiliary tapping axes."""

    bundle = build_event_bundle(rows)
    measures = {
        "raw_speed": previous._raw_speed_measure(  # noqa: SLF001
            bundle,
            rate_baseline_per_s=RAW_RATE_BASELINE_PER_S,
            rate_per_star=RAW_RATE_PER_STAR,
            partial_support_exponent=RAW_PARTIAL_SUPPORT_EXPONENT,
            scale=RAW_SPEED_SCALE,
        ),
        "stamina": previous._stamina_measure(bundle),  # noqa: SLF001
        "finger_control": previous._finger_measure(bundle),  # noqa: SLF001
        "endurance": previous.previous._endurance_measure(bundle),  # noqa: SLF001
    }
    for axis, measure in measures.items():
        measure["schema_version"] = SCHEMA_VERSION
        if axis == "raw_speed":
            measure["implementation_basis_schema_version"] = SCHEMA_VERSION
        else:
            measure["implementation_basis_schema_version"] = previous.SCHEMA_VERSION
    return measures


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
