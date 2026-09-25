"""Deployable ppy-derived map-demand release.

The public baseline profiler historically stopped at geometry and returned no
numeric skill-shaped values.  This module is the bounded release bridge for
map demand.  It uses the already versioned ``MAP_DEMAND_V100`` implementation
and its packaged calibration artifact, then adds the v0.36 Slider pressure
vector.  No new weighted Slider scalar is invented here: the optional scalar
is the maximum required cursor velocity among support-gated candidates and is
reported with its physical unit.

This release is deliberately map-side.  It does not turn a replay into a
player ability score.  Player Slider judgement remains governed by
``slider_runtime`` and its independent-trace contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping


FORMAL_RELEASE_SCHEMA_VERSION = "osu_skill_profiler_formal_map_demand_v040"
FORMAL_RELEASE_ID = "formal-map-demand-v0.40.0"
FORMAL_RELEASE_VERSION = "0.40.0"
MAP_DEMAND_ALGORITHM = "MAP_DEMAND_V100"
PRESSURE_SCHEMA_VERSION = "ppy_slider_pressure_corpus_v036"

AXES = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "finger_control",
    "reading",
    "stamina",
    "endurance",
)

_AXIS_UNITS = {
    "stamina": "bounded_0_10",
    "endurance": "bounded_0_10",
}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path() -> Path:
    return _package_root() / "training" / "formal_slider_release_v040" / "manifest.json"


def load_formal_release_manifest() -> dict[str, Any]:
    """Load and minimally validate the packaged release gate."""

    path = _manifest_path()
    if not path.is_file():
        raise FileNotFoundError(f"formal release manifest is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("release_id") != FORMAL_RELEASE_ID:
        raise ValueError("formal release manifest has an unsupported release_id")
    if payload.get("schema_version") != FORMAL_RELEASE_SCHEMA_VERSION:
        raise ValueError("formal release manifest schema_version mismatch")
    return payload


def _ensure_tool_path() -> Path:
    tools_root = _package_root() / "tools"
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
    return tools_root


def _axis_payload(axis: str, raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, Mapping) else {}
    status = str(raw.get("status", "NOT_ADMITTED"))
    value = None
    for key in ("demand_star_equivalent", "stars", "value", "score"):
        value = _finite(raw.get(key))
        if value is not None:
            break
    admitted = status == "EMITTED" and value is not None
    return {
        "status": "ADMITTED_MAP_DEMAND" if admitted else "NOT_ADMITTED",
        "value": value if admitted else None,
        "unit": _AXIS_UNITS.get(axis, "star_equivalent"),
        "source_status": status,
        "method": raw.get("method"),
        "scale_method": raw.get("scale_method"),
        "score_semantics": raw.get("score_semantics"),
        "evidence_quality": raw.get("evidence_quality"),
        "warnings": list(raw.get("warnings", [])) if isinstance(raw.get("warnings"), list) else [],
    }


def _candidate_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "slider_index",
        "start_time_ms",
        "end_time_ms",
        "start_time",
        "end_time",
        "span_count",
        "repeat_count",
        "curve_type",
        "duration_ms",
        "slider_ball_velocity_norm_px_per_ms",
        "mandatory_cursor_travel_norm_px",
        "mandatory_travel_fraction",
        "active_follow_fraction",
        "longest_active_episode_ball_path_norm_px",
        "mean_tracking_slack_fraction",
        "required_cursor_velocity_norm_px_per_ms",
        "residual_steering_25px_rad",
        "residual_steering_50px_rad",
        "support",
        "status",
    )
    return {key: row[key] for key in fields if key in row}


def _build_pressure_summary(beatmap: Any, source_name: str) -> dict[str, Any]:
    """Run one bounded v0.36 map scan and publish only auditable summaries."""

    _ensure_tool_path()
    from ppy_v01.slider_pressure_v036 import scan_beatmap

    report = scan_beatmap(beatmap, source_name=source_name, top_n=10)
    scan = report.get("scan") if isinstance(report.get("scan"), Mapping) else {}
    candidates = report.get("candidates", {})
    sustained = candidates.get("sustained_high_pressure_by_required_cursor_velocity", [])
    lazy = candidates.get("lazy_motion_negative_controls_by_ball_velocity", [])
    sustained = [row for row in sustained if isinstance(row, Mapping)]
    lazy = [row for row in lazy if isinstance(row, Mapping)]
    known = _finite(scan.get("known_slider_event_count"))
    total = _finite(scan.get("slider_event_count"))
    complete = known is not None and total is not None and known == total
    peak = _finite(sustained[0].get("required_cursor_velocity_norm_px_per_ms")) if sustained else None
    if total is None or total <= 0:
        status = "NOT_ADMITTED"
        reason = "map_has_no_sliders"
    elif not complete:
        status = "NOT_ADMITTED"
        reason = "one_or_more_slider_geometries_unavailable"
    elif peak is None:
        status = "NO_SUSTAINED_CANDIDATE"
        reason = "support_gates_found_no_sustained_candidate"
    else:
        status = "ADMITTED"
        reason = "bounded_ppy_geometry_scan_and_support_gates"

    vector = {
        "slider_event_count": int(total) if total is not None else None,
        "known_slider_event_count": int(known) if known is not None else None,
        "sustained_high_pressure_count": int(scan.get("sustained_high_pressure_count", 0) or 0),
        "lazy_motion_negative_control_count": int(scan.get("lazy_motion_negative_control_count", 0) or 0),
        "mandatory_cursor_travel_gate_norm_px": 50.0,
        "longest_active_ball_path_gate_norm_px": 100.0,
        "slider_pressure_peak_required_cursor_velocity_norm_px_per_ms": peak,
    }
    return {
        "schema_version": PRESSURE_SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "scalar_definition": (
            "max(required_cursor_velocity_norm_px_per_ms) over support-gated "
            "sustained_high_pressure candidates; no weighted sum"
        ),
        "scalar": peak,
        "scalar_unit": "normalized_px_per_ms",
        "scalar_admitted": status == "ADMITTED" and peak is not None,
        "vector": vector,
        "top_sustained_candidates": [_candidate_summary(row) for row in sustained[:5]],
        "lazy_negative_controls": [_candidate_summary(row) for row in lazy[:5]],
        "scan": {
            "sample_step_norm_px": scan.get("sample_step_norm_px"),
            "max_sample_intervals_per_span": scan.get("max_sample_intervals_per_span"),
        },
        "provenance": [
            "ppy_slider_pressure_corpus_v036",
            "canonical_slider_geometry_and_timing",
            "support_gates_are_physical_thresholds",
            "max_peak_is_not_a_star_rating_or_player_skill_score",
        ],
    }


def build_formal_map_demand(
    source: str | Path,
    beatmap: Any,
    *,
    requested_mods: list[str] | tuple[str, ...] = (),
    include_pressure_candidates: bool = True,
) -> dict[str, Any]:
    """Produce the formal map-demand payload for one local .osu file.

    Any missing calibration, unsupported map path, or non-emitted axis fails
    closed to ``NOT_ADMITTED`` at that axis.  The caller can still publish the
    ordinary deterministic feature output.
    """

    path = Path(source)
    base: dict[str, Any] = {
        "schema_version": FORMAL_RELEASE_SCHEMA_VERSION,
        "release_id": FORMAL_RELEASE_ID,
        "release_version": FORMAL_RELEASE_VERSION,
        "status": "NOT_ADMITTED",
        "formal_axis_admission": "NOT_ADMITTED",
        "map_checksum": None,
        "axis_values": {axis: None for axis in AXES},
        "axis_units": {axis: _AXIS_UNITS.get(axis, "star_equivalent") for axis in AXES},
        "axes": {axis: {"status": "NOT_ADMITTED", "value": None, "unit": _AXIS_UNITS.get(axis, "star_equivalent")} for axis in AXES},
        "slider_pressure": None,
        "player_skill_score_admitted": False,
        "provenance": [],
    }
    if not path.is_file() or path.suffix.lower() != ".osu":
        base["provenance"] = ["formal_map_demand_requires_a_local_osu_file"]
        return base

    try:
        manifest = load_formal_release_manifest()
        calibration_relative = manifest["artifacts"]["calibration_relative_path"]
        calibration_path = _package_root() / calibration_relative
        if not calibration_path.is_dir():
            raise FileNotFoundError(f"packaged calibration is missing: {calibration_path}")
        _ensure_tool_path()
        from map_demand_v01 import model_v100
        from map_demand_v01.calibration import load_calibration

        calibration = load_calibration(calibration_path)
        requested_mods = [str(mod) for mod in requested_mods]
        local_rows, features, metadata = model_v100.extract_from_path(
            str(path), requested_mods=requested_mods
        )
        kwargs: dict[str, Any] = {
            "difficulty": metadata.get("difficulty"),
            "clock_rate": metadata.get("mod_transform_context", {}).get("clock_rate", 1.0),
            "effective_mods": metadata.get("mod_context", {}).get("effective_mods", []),
        }
        if hasattr(model_v100, "EXPECTED_LOCAL_SIGNAL_VERSION"):
            kwargs["source_local_signal_version"] = metadata.get("local_signal_version")
        components, component_warnings = model_v100.extract_components(local_rows, features, **kwargs)
        demand = model_v100.analyze_components(
            checksum=model_v100.sha256_file_bytes(path.read_bytes()),
            requested_mods=requested_mods,
            components=components,
            calibration=calibration,
            applied_mod_context=metadata.get("mod_transform_context"),
        )
        axes = {axis: _axis_payload(axis, demand.get("axes", {}).get(axis)) for axis in AXES}
        base["map_checksum"] = _sha256(path)
        base["axes"] = axes
        base["axis_values"] = {axis: payload["value"] for axis, payload in axes.items()}
        base["axis_units"] = {axis: payload["unit"] for axis, payload in axes.items()}
        base["map_demand"] = {
            "schema_version": demand.get("schema_version"),
            "status": demand.get("status"),
            "identity": demand.get("identity"),
            "summaries": demand.get("summaries"),
            "calibration_id": (demand.get("identity") or {}).get("calibration_id"),
            "component_warnings": list(component_warnings),
        }
        if include_pressure_candidates:
            base["slider_pressure"] = _build_pressure_summary(beatmap, str(path))
        admitted_axes = [payload["status"] == "ADMITTED_MAP_DEMAND" for payload in axes.values()]
        pressure_admitted = bool(base["slider_pressure"] and base["slider_pressure"].get("scalar_admitted"))
        if all(admitted_axes):
            base["status"] = "ADMITTED" if pressure_admitted else "PARTIAL"
            base["formal_axis_admission"] = "ADMITTED_MAP_DEMAND"
        else:
            base["status"] = "PARTIAL"
            base["formal_axis_admission"] = "PARTIAL_MAP_DEMAND"
        base["provenance"] = [
            "packaged_formal_slider_release_manifest_v040",
            "MAP_DEMAND_V100_frozen_release",
            "ppy_slider_pressure_corpus_v036",
            "not_admitted_when_axis_evidence_is_not_emitted",
            "map_demand_is_not_player_skill",
        ]
    except (OSError, ValueError, KeyError, ImportError, TypeError) as error:
        base["status"] = "NOT_ADMITTED"
        base["formal_axis_admission"] = "NOT_ADMITTED"
        base["provenance"] = ["formal_release_failed_closed_to_not_admitted", str(error)]
    return base


__all__ = [
    "AXES",
    "FORMAL_RELEASE_ID",
    "FORMAL_RELEASE_SCHEMA_VERSION",
    "FORMAL_RELEASE_VERSION",
    "build_formal_map_demand",
    "load_formal_release_manifest",
]
