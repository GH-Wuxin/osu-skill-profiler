"""Versioned contracts and finite-value / reference-leakage gates.

All constants in this file that are not quoted from inspected upstream code
are tagged HEURISTIC_V01 or HEURISTIC_SAFETY_CAP in the machine-readable
design JSONs. This module is experimental tooling only.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from typing import Any, Iterable

from .mod_context_v01 import canonicalize_effective_mods

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V04"
MAP_DEMAND_VERSION = "0.6.0"
SCHEMA_VERSION = "map_demand_v0.6.0"
RULESET = "osu"

FEATURE_VERSION = "0.2.0"
LOCAL_SIGNAL_VERSION = "0.3.0"
REFERENCE_SIGNAL_VERSION = "0.2.0"

# Effective mod behaviours with a complete MOD_TRANSFORM_V01 extraction path.
SUPPORTED_EFFECTIVE_MODS: tuple[str, ...] = ("EZ", "HD", "HR", "DT", "HT")

MIN_TIME_MS = 25.0

# HEURISTIC_SAFETY_CAP. Versioned, deterministic, and never Infinity/NaN.
AIM_STRAIN_CAP = 200.0
PRECISION_PRESSURE_CAP = 1_000_000.0

REFERENCE_SIGNAL_PREFIX = "ref.ppy."

AXIS_ORDER: tuple[str, ...] = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "stamina",
    "finger_control",
    "reading",
)

# Objective map settings are reported outside the human skill taxonomy.  A
# strict hit window matters, but OD by itself is not a learned map archetype.
CONTEXT_ORDER: tuple[str, ...] = ("accuracy_window",)

SUMMARY_ORDER: tuple[str, ...] = (
    "aim_summary",
    "tapping_summary",
    "overall_demand",
)

# Per-axis method and confidence. Confidence is a documented heuristic based
# on signal-family count and prior-art strength; it is not calibrated.
AXIS_META: dict[str, dict[str, Any]] = {
    "jump_aim": {
        "method": "HEURISTIC_ATOMIC_JUMP_AIM_V02",
        "combination_policy": "HEURISTIC_ATOMIC_V02_SINGLE_SIGNAL",
        "confidence": "MEDIUM",
        "signals": {
            "jump_aim_strain_p90": {
                "weight": 1.0,
                "source": "ls.lazy_jump_distance_cs_normalised, ls.minimum_jump_time_ms",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
        },
    },
    "flow_aim": {
        "method": "HEURISTIC_ATOMIC_CONTINUOUS_FLOW_V03",
        "combination_policy": "HEURISTIC_ATOMIC_V03_STRAIN_GATED",
        "confidence": "LOW",
        "signals": {
            "flow_aim_continuity_share": {
                "weight": 0.4,
                "source": "share of movement transitions in a stable forward-continuity chain",
                "evidence_tag": "HEURISTIC_ATOMIC_V02_REQUIRES_HUMAN_VALIDATION",
            },
            "flow_aim_chain_length_p90": {
                "weight": 0.35,
                "source": "p90 consecutive stable forward-continuity chain length",
                "evidence_tag": "HEURISTIC_ATOMIC_V02_REQUIRES_HUMAN_VALIDATION",
            },
            "flow_aim_chain_velocity_p90": {
                "weight": 0.25,
                "source": "p90 capped velocity within stable forward-continuity chains",
                "evidence_tag": "HEURISTIC_ATOMIC_V02_REQUIRES_HUMAN_VALIDATION",
            },
        },
    },
    "aim_control": {
        "method": "HEURISTIC_ATOMIC_SPATIAL_CHANGE_CONTROL_V02",
        "combination_policy": "HEURISTIC_ATOMIC_V02",
        "confidence": "LOW",
        "signals": {
            "aim_control_angle_change_p90": {
                "weight": 0.6,
                "source": "successive ls.slider_aware_angle_rad deltas / ls.adjusted_delta_time_ms",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
            "aim_control_velocity_change_p90": {
                "weight": 0.4,
                "source": "successive log movement-velocity ratios / ls.adjusted_delta_time_ms",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
        },
    },
    "spatial_precision": {
        "method": "HEURISTIC_PROXY_INSPIRED_BY_OSUSKILLS_HUMAN_TIME",
        "combination_policy": "HEURISTIC_ATOMIC_V02_SINGLE_SIGNAL",
        "confidence": "LOW",
        "signals": {
            "spatial_precision_pressure_p90": {
                "weight": 1.0,
                "source": "ls.minimum_jump_distance_cs_normalised, ls.minimum_jump_time_ms",
                "evidence_tag": "HEURISTIC_PROXY_INSPIRED_BY_OSUSKILLS_HUMAN_TIME",
            },
        },
    },
    "raw_speed": {
        "method": "HEURISTIC_PROXY_INSPIRED_BY_PPY_SPEED",
        "combination_policy": "HEURISTIC_ATOMIC_V02_SINGLE_SIGNAL",
        "confidence": "MEDIUM",
        "signals": {
            "raw_speed_strain_p90": {
                "weight": 1.0,
                "source": "ls.adjusted_delta_time_ms, ls.hit_window_great_ms, ls.double_tap_feasibility",
                "evidence_tag": "HEURISTIC_PROXY_INSPIRED_BY_PPY_SPEED",
            },
        },
    },
    "stamina": {
        "method": "HEURISTIC_MAP_DEMAND_PROXY",
        "combination_policy": "HEURISTIC_V01",
        "confidence": "LOW",
        "signals": {
            "stamina_sustained_ms": {
                "weight": 0.6,
                "source": "temporal.longest_dense_section_ms",
                "evidence_tag": "HEURISTIC_V01",
            },
            "stamina_duration_share": {
                "weight": 0.2,
                "source": "temporal.longest_dense_section_ms / temporal.map_duration_ms",
                "evidence_tag": "HEURISTIC_V01",
            },
            "stamina_density": {
                "weight": 0.2,
                "source": "section.duration_weighted_density_per_s",
                "evidence_tag": "HEURISTIC_V01",
            },
        },
    },
    "finger_control": {
        "method": "HEURISTIC_ATOMIC_TEMPORAL_PATTERN_CONTROL_V02",
        "combination_policy": "HEURISTIC_ATOMIC_V02",
        "confidence": "MEDIUM",
        "signals": {
            "finger_control_interval_entropy": {
                "weight": 0.5,
                "source": "temporal.rhythm_entropy_bits",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
            "finger_control_interval_diversity": {
                "weight": 0.3,
                "source": "temporal.interval_diversity",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
            "finger_control_interval_ratio": {
                "weight": 0.2,
                "source": "temporal.interval_ratio_mean",
                "evidence_tag": "HEURISTIC_ATOMIC_V02",
            },
        },
    },
    "reading": {
        "method": "HEURISTIC_PROXY_INSPIRED_BY_PPY_READING_V03",
        "combination_policy": "HEURISTIC_V03_VISUAL_PRIMARY_DENSITY_GATED",
        "confidence": "LOW",
        "signals": {
            "reading_high_ar_pressure": {
                "weight": 0.2,
                "source": "median ls.preempt_ms -> ((500-preempt+|preempt-500|)/2)^2.5/140000",
                "evidence_tag": "CODE_CONFIRMED_TERM + HEURISTIC_PROXY_USE",
            },
            "reading_density": {
                "weight": 0.5,
                "source": "section.density_per_s_p95",
                "evidence_tag": "HEURISTIC_V01",
            },
            "reading_visual_change": {
                "weight": 0.3,
                "source": "spatial.direction_change_ratio_ge_90",
                "evidence_tag": "HEURISTIC_V01",
            },
        },
    },
}

# Finite pathological values are kept but get a warning above this density
# threshold (objects/second). HEURISTIC_V01.
DENSITY_PATHOLOGICAL_THRESHOLD = 1_000_000.0


class ReferenceSignalLeakageError(ValueError):
    """Raised when a ref.ppy.* value tries to enter an axis computation path."""


class NonFiniteValueError(ValueError):
    """Raised when a non-finite float would enter an output boundary."""


def finite_float(value: Any, label: str) -> float:
    """Convert to float and reject None/non-finite values."""
    if value is None:
        raise NonFiniteValueError(f"{label} is None")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NonFiniteValueError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise NonFiniteValueError(f"{label} is non-finite: {number!r}")
    return number


def assert_no_reference_signals(mapping: dict[str, Any], context: str) -> None:
    """Field-role gate: ref.ppy.* may never enter axis computation or calibration."""
    if not isinstance(mapping, dict):
        raise TypeError(f"{context}: expected dict")
    for key in mapping:
        if isinstance(key, str) and key.startswith(REFERENCE_SIGNAL_PREFIX):
            raise ReferenceSignalLeakageError(
                f"{context}: reference signal {key!r} is DIAGNOSTIC_ONLY "
                "and must not enter axis computation or calibration"
            )


def strict_json_dumps(obj: Any, *, indent: int | None = None) -> str:
    text = json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=indent, sort_keys=True)
    scan_finite(obj, "strict_json_input")
    return text


def scan_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise NonFiniteValueError(f"non-finite float at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            scan_finite(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            scan_finite(value, f"{path}[{index}]")
    elif isinstance(obj, tuple):
        for index, value in enumerate(obj):
            scan_finite(value, f"{path}[{index}]")


def percentile_linear(sorted_values: list[float], q: float) -> float:
    """Production-style linear percentile q*(n-1) over sorted finite values."""
    if not sorted_values:
        raise ValueError("percentile_linear: empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def quantile_rank(sorted_values: list[float], value: float) -> float:
    """Tie-safe empirical midrank, with a true zero floor.

    The previous ``P(X <= value)`` policy assigned the *top* of a large tie to
    every tied item.  For example, a zero Reading pressure received rank .963
    because 4,814/5,000 calibration maps were also zero.  Midrank is used for
    ordinary ties, while a meaningful non-negative floor remains exactly 0.
    """
    if not sorted_values:
        raise ValueError("quantile_rank: empty calibration distribution")
    number = finite_float(value, "quantile_rank.value")
    if number < sorted_values[0]:
        return 0.0
    if number > sorted_values[-1]:
        return 1.0
    left = bisect.bisect_left(sorted_values, number)
    right = bisect.bisect_right(sorted_values, number)
    if number == 0.0 and sorted_values[0] == 0.0:
        return 0.0
    return float(left + right) / (2.0 * float(len(sorted_values)))


def make_identity(
    *,
    beatmap_checksum: str,
    effective_mods: Iterable[str] = (),
    clock_rate: float = 1.0,
    calibration_id: str,
    algorithm_id: str = ALGORITHM_ID,
    feature_version: str = FEATURE_VERSION,
    local_signal_version: str = LOCAL_SIGNAL_VERSION,
    map_demand_version: str = MAP_DEMAND_VERSION,
    ruleset: str = RULESET,
) -> dict[str, Any]:
    mods = canonicalize_effective_mods(effective_mods)
    return {
        "algorithm_id": algorithm_id,
        "beatmap_checksum": beatmap_checksum,
        "ruleset": ruleset,
        "effective_mods": mods,
        "clock_rate": finite_float(clock_rate, "identity.clock_rate"),
        "feature_version": feature_version,
        "local_signal_version": local_signal_version,
        "calibration_id": calibration_id,
        "map_demand_version": map_demand_version,
    }


def identity_cache_key(identity: dict[str, Any]) -> str:
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def component_labels() -> dict[str, str]:
    """Flattened axis -> (component -> evidence_tag) table for cross-checks."""
    labels: dict[str, str] = {}
    for axis in AXIS_ORDER:
        for name, meta in AXIS_META[axis]["signals"].items():
            labels[name] = str(meta["evidence_tag"])
    return labels
