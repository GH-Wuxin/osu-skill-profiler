"""Versioned common demand-equivalence scale for the post-v0.40 layers.

This module deliberately does not modify the frozen v0.40 output.  It builds
an additional, auditable representation by mapping each axis' empirical rank
to the same ppy osu!standard mod-context star reference distribution.  The ppy
distribution is a ruler, not an axis label or a target for a weighted fit.

The calibration artifact contains only sorted observations and provenance.  No
cross-axis weights are fitted here, and no single map can create a calibration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import contract as C
from .mod_context_v01 import normalize_mods
from osu_skill_profiler.formal_release import AXES


SCHEMA_VERSION = "unified_star_calibration_v0.2"
SCALE_ID = "ppy-standard-mod-demand-equivalence-v0.2"
MAPPING_METHOD = "AXIS_EMPIRICAL_CDF_TO_SHARED_PPY_MOD_CONTEXT_REFERENCE_V02"
AXIS_ORDER = tuple(AXES)

# These are explicit admission gates, not fitted constants.  A caller may use
# lower values for a local candidate artifact, but it must remain CANDIDATE.
DEFAULT_MIN_FORMAL_MAPS = 256
DEFAULT_MIN_FORMAL_AXIS_SAMPLES = 128
DEFAULT_MIN_FORMAL_STRATA = 4
DEFAULT_MOD_CONTEXT = "NM"


class CalibrationError(ValueError):
    """Raised when a common-scale artifact violates its data contract."""


def canonical_mod_context(value: Any) -> str:
    """Return the effective non-FL map-demand context label.

    The same folds used by the map index are applied at calibration time so
    an NC request joins the DT ruler and a DC request joins the HT ruler.
    Unsupported mechanics remain explicit labels instead of being silently
    treated as NM.
    """

    text = "" if value is None else str(value).strip().upper()
    if not text or text in {"NM", "NOMOD", "NONE"}:
        return DEFAULT_MOD_CONTEXT
    normalized = normalize_mods(text)
    effective = normalized.get("effective_mods") if isinstance(normalized, Mapping) else None
    if normalized.get("status") == "NORMALIZED" and isinstance(effective, list):
        return "".join(str(item) for item in effective) or DEFAULT_MOD_CONTEXT
    return "".join(ch for ch in text if ch.isalnum()) or DEFAULT_MOD_CONTEXT


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise CalibrationError(f"{label} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalibrationError(f"{label} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0.0:
        raise CalibrationError(f"{label} must be a finite non-negative number")
    return number


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sorted_finite(values: Iterable[Any], label: str) -> list[float]:
    result = [_finite_nonnegative(value, f"{label}[{index}]") for index, value in enumerate(values)]
    if not result:
        raise CalibrationError(f"{label} must not be empty")
    return sorted(result)


def _record_map_id(record: Mapping[str, Any], index: int) -> str:
    value = record.get("map_id", record.get("beatmap_id", record.get("checksum")))
    if value is None or str(value).strip() == "":
        raise CalibrationError(f"records[{index}].map_id is required")
    return str(value)


def _record_ppy_star(record: Mapping[str, Any], index: int) -> float:
    for key in (
        "ppy_star",
        "ppy_mod_star",
        "ppy_nm_star",
        "ppy_nm_stars",
        "nm_stars",
        "star_rating",
    ):
        if key in record:
            return _finite_nonnegative(record[key], f"records[{index}].{key}")
    raise CalibrationError(f"records[{index}] requires a ppy star value for its mod_context")


def _axis_raw(record: Mapping[str, Any], axis: str, index: int) -> float | None:
    axes = record.get("axes")
    if not isinstance(axes, Mapping):
        raise CalibrationError(f"records[{index}].axes must be an object")
    raw = axes.get(axis)
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        for key in ("raw_value", "value", "demand_star_equivalent", "stars"):
            if key in raw:
                raw = raw[key]
                break
    return _finite_nonnegative(raw, f"records[{index}].axes.{axis}")


def _reference_summary(stars: list[float]) -> dict[str, Any]:
    quantiles = {
        str(q): C.percentile_linear(stars, q)
        for q in (0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0)
    }
    return {
        "count": len(stars),
        "min": stars[0],
        "max": stars[-1],
        "quantiles": quantiles,
    }


def fit_calibration(
    records: Iterable[Mapping[str, Any]],
    reference_nm_stars: Iterable[Any],
    *,
    source_scope: str,
    corpus_id: str | None = None,
    mod_context: str = DEFAULT_MOD_CONTEXT,
    min_formal_maps: int = DEFAULT_MIN_FORMAL_MAPS,
    min_formal_axis_samples: int = DEFAULT_MIN_FORMAL_AXIS_SAMPLES,
    min_formal_strata: int = DEFAULT_MIN_FORMAL_STRATA,
) -> dict[str, Any]:
    """Fit a rank-preserving common ruler from an external map corpus.

    The ppy star value is retained for corpus coverage diagnostics.  It is not
    used as a per-axis regression target.  The mapping itself uses each axis'
    raw empirical CDF and the shared reference CDF.
    """

    if not isinstance(source_scope, str) or not source_scope.strip():
        raise CalibrationError("source_scope is required")
    mod_context = canonical_mod_context(mod_context)
    if not mod_context or "FL" in mod_context:
        raise CalibrationError("mod_context must be a non-FL standard context")
    if min_formal_maps <= 0 or min_formal_axis_samples <= 0 or min_formal_strata <= 0:
        raise CalibrationError("formal admission gates must be positive")

    stars = _sorted_finite(reference_nm_stars, "reference_stars")
    parsed: list[dict[str, Any]] = []
    seen_map_ids: set[str] = set()
    axis_values: dict[str, list[float]] = {axis: [] for axis in AXIS_ORDER}
    axis_map_ids: dict[str, list[str]] = {axis: [] for axis in AXIS_ORDER}
    strata: set[str] = set()
    contexts: set[str] = set()

    for index, incoming in enumerate(records):
        if not isinstance(incoming, Mapping):
            raise CalibrationError(f"records[{index}] must be an object")
        map_id = _record_map_id(incoming, index)
        if map_id in seen_map_ids:
            raise CalibrationError(f"duplicate map_id: {map_id}")
        seen_map_ids.add(map_id)
        ppy_star = _record_ppy_star(incoming, index)
        record_context = canonical_mod_context(
            incoming.get("mod_context") or mod_context or DEFAULT_MOD_CONTEXT
        )
        contexts.add(record_context)
        stratum = incoming.get("stratum", incoming.get("map_family"))
        if stratum is not None and str(stratum).strip():
            strata.add(str(stratum))
        parsed_axes: dict[str, float] = {}
        for axis in AXIS_ORDER:
            raw = _axis_raw(incoming, axis, index)
            if raw is None:
                continue
            parsed_axes[axis] = raw
            axis_values[axis].append(raw)
            axis_map_ids[axis].append(map_id)
        parsed.append(
            {
                "map_id": map_id,
                "ppy_nm_star": ppy_star if record_context == "NM" else None,
                "ppy_star": ppy_star,
                "mod_context": record_context,
                "stratum": None if stratum is None else str(stratum),
                "axes_present": sorted(parsed_axes),
            }
        )

    if not parsed:
        raise CalibrationError("records must not be empty")
    if len(contexts) != 1 or contexts != {mod_context}:
        raise CalibrationError(
            "all corpus rows must match the requested non-FL mod_context"
        )
    resolved_mod_context = next(iter(contexts))
    for axis in AXIS_ORDER:
        if not axis_values[axis]:
            raise CalibrationError(f"no raw observations for axis: {axis}")
        axis_values[axis].sort()

    map_count = len(parsed)
    axis_counts = {axis: len(axis_values[axis]) for axis in AXIS_ORDER}
    # Callers may raise gates for a stricter local review, but lowering them
    # can only make a smaller candidate artifact; it must never manufacture a
    # formal admission from a fixture-sized corpus.
    formal_ready = (
        map_count >= max(DEFAULT_MIN_FORMAL_MAPS, min_formal_maps)
        and min(axis_counts.values()) >= max(DEFAULT_MIN_FORMAL_AXIS_SAMPLES, min_formal_axis_samples)
        and len(strata) >= max(DEFAULT_MIN_FORMAL_STRATA, min_formal_strata)
    )
    calibration_id = _canonical_hash(
        {
            "schema_version": SCHEMA_VERSION,
            "scale_id": SCALE_ID,
            "mapping_method": MAPPING_METHOD,
            "source_scope": source_scope,
            "corpus_id": corpus_id,
            "mod_context": resolved_mod_context,
            "reference_stars": stars,
            "axis_values": axis_values,
            "map_ids": [item["map_id"] for item in parsed],
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "scale_id": SCALE_ID,
        "calibration_id": f"unified-star-v02:{calibration_id[7:27]}",
        # Breadth is necessary but cannot itself prove axis semantics or
        # population validity.  Formal admission needs separate held-out
        # matched evidence and a versioned review artifact.
        "status": "CANDIDATE",
        "breadth_ready": formal_ready,
        "formal_admission_status": "PENDING_HELD_OUT_MATCHED_EVIDENCE",
        "mapping_method": MAPPING_METHOD,
        "source_scope": source_scope,
        "corpus_id": corpus_id,
        "mod_context": resolved_mod_context,
        "map_count": map_count,
        "strata": sorted(strata),
        "formal_admission_gates": {
            "min_formal_maps": min_formal_maps,
            "min_formal_axis_samples": min_formal_axis_samples,
            "min_formal_strata": min_formal_strata,
        },
        "axis_counts": axis_counts,
        "axis_distributions": axis_values,
        "reference_distribution": {
            "source": "ppy_osu_standard_mod_context_reference_population",
            "sha256": _canonical_hash(stars),
            "stars": stars,
            "nm_stars": stars if resolved_mod_context == "NM" else None,
            "summary": _reference_summary(stars),
        },
        "corpus_rows": parsed,
        "provenance": [
            "axis_specific_empirical_cdf",
            "shared_ppy_mod_context_reference_distribution",
            "no_cross_axis_weights",
            "ppy_total_sr_not_used_as_axis_ground_truth",
        ],
    }


def _validate_calibration(calibration: Mapping[str, Any]) -> None:
    if calibration.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationError("unsupported unified-star calibration schema")
    if calibration.get("mapping_method") != MAPPING_METHOD:
        raise CalibrationError("unsupported unified-star mapping method")
    if calibration.get("status") != "CANDIDATE":
        raise CalibrationError(
            "v0.2 calibration cannot claim formal admission without a held-out evidence contract"
        )
    mod_context = calibration.get("mod_context", DEFAULT_MOD_CONTEXT)
    if not isinstance(mod_context, str) or not mod_context.strip():
        raise CalibrationError("mod_context is required")
    resolved_context = canonical_mod_context(mod_context)
    if "FL" in resolved_context:
        raise CalibrationError("unified-star calibration cannot include FL")
    reference = calibration.get("reference_distribution")
    if not isinstance(reference, Mapping):
        raise CalibrationError("reference_distribution is required")
    stars = reference.get("stars", reference.get("nm_stars"))
    if not isinstance(stars, list) or not stars:
        raise CalibrationError("reference_distribution.stars is required")
    _sorted_finite(stars, "reference_distribution.stars")
    distributions = calibration.get("axis_distributions")
    if not isinstance(distributions, Mapping):
        raise CalibrationError("axis_distributions is required")
    for axis in AXIS_ORDER:
        values = distributions.get(axis)
        if not isinstance(values, list) or not values:
            raise CalibrationError(f"axis_distributions.{axis} is required")
        _sorted_finite(values, f"axis_distributions.{axis}")


def load_calibration(path: str | Path) -> dict[str, Any]:
    """Load and validate a JSON common-scale artifact."""

    artifact = Path(path)
    if artifact.is_dir():
        artifact = artifact / "calibration.json"
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"cannot load unified-star calibration: {artifact}") from exc
    if not isinstance(payload, Mapping):
        raise CalibrationError("unified-star calibration must be an object")
    _validate_calibration(payload)
    C.scan_finite(payload, "unified_star_calibration")
    return dict(payload)


def save_calibration(calibration: Mapping[str, Any], path: str | Path) -> Path:
    """Write a validated common-scale artifact without hidden runtime state."""

    _validate_calibration(calibration)
    C.scan_finite(calibration, "unified_star_calibration")
    target = Path(path)
    if target.suffix.lower() != ".json":
        target = target / "calibration.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(calibration, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def _reject_constant(value: str) -> Any:
    raise CalibrationError(f"non-finite JSON constant: {value}")


def map_axis_value(
    calibration: Mapping[str, Any],
    axis: str,
    raw_value: Any,
) -> dict[str, Any]:
    """Map one raw axis value without extrapolating outside observed support."""

    _validate_calibration(calibration)
    if axis not in AXIS_ORDER:
        raise CalibrationError(f"unsupported axis: {axis}")
    if raw_value is None:
        return {
            "status": "UNKNOWN",
            "value": None,
            "percentile": None,
            "coverage": 0.0,
            "reason": "raw_axis_value_missing",
        }
    raw = _finite_nonnegative(raw_value, f"{axis}.raw_value")
    distribution = calibration["axis_distributions"][axis]
    reference = calibration["reference_distribution"].get(
        "stars", calibration["reference_distribution"].get("nm_stars")
    )
    if not isinstance(reference, list) or not reference:
        raise CalibrationError("reference_distribution.stars is required")
    low = float(distribution[0])
    high = float(distribution[-1])
    if raw < low or raw > high:
        return {
            "status": "UNKNOWN",
            "value": None,
            "percentile": None,
            "coverage": 0.0,
            "raw_range": {"lower": low, "upper": high},
            "reason": "raw_value_outside_calibration_support",
        }
    percentile = C.quantile_rank(distribution, raw)
    value = C.percentile_linear(reference, percentile)
    artifact_status = str(calibration.get("status") or "CANDIDATE")
    status = "ADMITTED" if artifact_status == "FORMAL_READY" else "CANDIDATE"
    return {
        "status": status,
        "value": C.finite_float(value, f"{axis}.unified_star_equivalent"),
        "percentile": C.finite_float(percentile, f"{axis}.percentile"),
        "coverage": 1.0,
        "raw_range": {"lower": low, "upper": high},
        "reference_range": {
            "lower": float(reference[0]),
            "upper": float(reference[-1]),
        },
        "reason": "rank_preserving_common_reference_mapping",
    }


def apply_unified_star_scale(
    output: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach the new scale while leaving every v0.40 field untouched."""

    _validate_calibration(calibration)
    result = copy.deepcopy(dict(output))
    source_axes = result.get("axes")
    if not isinstance(source_axes, Mapping):
        raise CalibrationError("output.axes must be an object")
    axes: dict[str, Any] = dict(source_axes)
    axis_status: dict[str, str] = {}
    for axis in AXIS_ORDER:
        item = copy.deepcopy(dict(axes.get(axis) or {}))
        raw = item.get("demand_star_equivalent")
        mapped = map_axis_value(calibration, axis, raw)
        item["raw_value"] = raw
        item["raw_unit"] = item.get("unit", "legacy_local_value")
        item["unified_star_equivalent"] = mapped["value"]
        item["unified_star_status"] = mapped["status"]
        item["unified_star_percentile"] = mapped["percentile"]
        item["unified_star_coverage"] = mapped["coverage"]
        item["unified_star_scale_id"] = SCALE_ID
        item["unified_star_diagnostics"] = mapped
        axes[axis] = item
        axis_status[axis] = mapped["status"]

    result["axes"] = axes
    result["unified_star_scale"] = {
        "schema_version": SCHEMA_VERSION,
        "scale_id": SCALE_ID,
        "calibration_id": calibration.get("calibration_id"),
        "status": (
            "ADMITTED"
            if all(value == "ADMITTED" for value in axis_status.values())
            else "CANDIDATE"
            if any(value in {"ADMITTED", "CANDIDATE"} for value in axis_status.values())
            else "UNKNOWN"
        ),
        "axis_status": axis_status,
        "reference": {
            "source": calibration["reference_distribution"].get("source"),
            "sha256": calibration["reference_distribution"].get("sha256"),
            "count": calibration["reference_distribution"]["summary"]["count"],
        },
        "mapping_method": MAPPING_METHOD,
        "mod_context": calibration.get("mod_context", DEFAULT_MOD_CONTEXT),
    }
    identity = dict(result.get("identity") or {})
    identity["unified_star_calibration_id"] = calibration.get("calibration_id")
    result["identity"] = identity
    return result


__all__ = [
    "AXIS_ORDER",
    "CalibrationError",
    "canonical_mod_context",
    "DEFAULT_MOD_CONTEXT",
    "DEFAULT_MIN_FORMAL_AXIS_SAMPLES",
    "DEFAULT_MIN_FORMAL_MAPS",
    "DEFAULT_MIN_FORMAL_STRATA",
    "MAPPING_METHOD",
    "SCALE_ID",
    "SCHEMA_VERSION",
    "apply_unified_star_scale",
    "fit_calibration",
    "load_calibration",
    "map_axis_value",
    "save_calibration",
]
