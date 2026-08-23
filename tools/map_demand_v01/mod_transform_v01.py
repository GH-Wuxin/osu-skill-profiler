"""Pure beatmap transforms for MOD_CONTEXT_V01.

Transforms are applied to a copied parsed Beatmap before Local Signal 0.3 and
Feature 0.2 extraction.  This preserves the frozen upstream layers while
ensuring their fixed real-time windows observe the modded timeline.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from .mod_context_v01 import MOD_CONTEXT_SCHEMA_VERSION

MOD_TRANSFORM_VERSION = "0.1.0"
MOD_TRANSFORM_SCHEMA_VERSION = "mod_transform_v0.1.0"

SUPPORTED_EFFECTIVE_MODS = frozenset({"EZ", "HD", "HR", "HT", "DT"})
PLAYFIELD_HEIGHT = 384.0


def _finite_rate(value: Any) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid clock rate: {value!r}") from exc
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError(f"invalid clock rate: {value!r}")
    return rate


def _difficulty_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in sorted(set(before).union(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return changes


def build_transform_context(mod_context: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic execution plan from a normalized mod context."""
    if mod_context.get("schema_version") != MOD_CONTEXT_SCHEMA_VERSION:
        return {
            "schema_version": MOD_TRANSFORM_SCHEMA_VERSION,
            "status": "INVALID",
            "analysis_ready": False,
            "applied_mods": [],
            "blocked_mods": [],
            "clock_rate": 1.0,
            "difficulty_changes": {},
            "legacy_ar_fallback_applied": False,
            "geometry_reflected": False,
            "errors": [{"code": "MOD_CONTEXT_VERSION_MISMATCH"}],
        }
    if mod_context.get("status") != "NORMALIZED":
        return {
            "schema_version": MOD_TRANSFORM_SCHEMA_VERSION,
            "status": "INVALID",
            "analysis_ready": False,
            "applied_mods": [],
            "blocked_mods": [],
            "clock_rate": 1.0,
            "difficulty_changes": {},
            "legacy_ar_fallback_applied": False,
            "geometry_reflected": False,
            "errors": [{"code": "INVALID_MOD_CONTEXT"}],
        }

    effective = set(mod_context.get("effective_mods", []))
    applied = sorted(effective.intersection(SUPPORTED_EFFECTIVE_MODS))
    blocked = sorted(effective - SUPPORTED_EFFECTIVE_MODS)
    return {
        "schema_version": MOD_TRANSFORM_SCHEMA_VERSION,
        "status": "PLANNED" if not blocked else ("PARTIAL" if applied else "BLOCKED"),
        "analysis_ready": not blocked,
        "requested_mods": list(mod_context.get("requested_mods", [])),
        "effective_mods": list(mod_context.get("effective_mods", [])),
        "applied_mods": applied,
        "blocked_mods": blocked,
        "clock_rate": _finite_rate(mod_context.get("clock_rate", 1.0)),
        "difficulty_changes": {},
        "legacy_ar_fallback_applied": False,
        "geometry_reflected": False,
        "errors": [],
    }


def transform_beatmap(beatmap: Any, mod_context: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Return a transformed copy of ``beatmap`` and its execution context."""
    context = build_transform_context(mod_context)
    if context["status"] == "INVALID":
        return beatmap, context

    rate = context["clock_rate"]
    effective = set(context["applied_mods"])
    before = dict(beatmap.difficulty)
    difficulty = dict(before)
    legacy_ar_fallback = False

    # Legacy decoder semantics make missing AR inherit OD.  Materialise that
    # value only when a difficulty mod needs to transform AR.
    if effective.intersection({"EZ", "HR"}) and "ApproachRate" not in difficulty:
        if "OverallDifficulty" in difficulty:
            difficulty["ApproachRate"] = difficulty["OverallDifficulty"]
            legacy_ar_fallback = True

    if "EZ" in effective:
        for key in ("CircleSize", "ApproachRate", "HPDrainRate"):
            if key in difficulty:
                difficulty[key] = float(difficulty[key]) * 0.5
        if "OverallDifficulty" in difficulty:
            difficulty["OverallDifficulty"] = float(difficulty["OverallDifficulty"]) * 0.5

    if "HR" in effective:
        if "HPDrainRate" in difficulty:
            difficulty["HPDrainRate"] = min(float(difficulty["HPDrainRate"]) * 1.4, 10.0)
        if "OverallDifficulty" in difficulty:
            difficulty["OverallDifficulty"] = min(
                float(difficulty["OverallDifficulty"]) * 1.4, 10.0
            )
        if "ApproachRate" in difficulty:
            difficulty["ApproachRate"] = min(float(difficulty["ApproachRate"]) * 1.4, 10.0)
        if "CircleSize" in difficulty:
            difficulty["CircleSize"] = min(float(difficulty["CircleSize"]) * 1.3, 10.0)

    timing_points = beatmap.timing_points
    hit_objects = beatmap.hit_objects
    if rate != 1.0:
        transformed_points = []
        for point in timing_points:
            beat_length = point.beat_length_ms
            bpm = point.bpm
            if point.uninherited:
                beat_length = beat_length / rate
                bpm = bpm * rate if bpm is not None else None
            transformed_points.append(
                replace(
                    point,
                    time_ms=point.time_ms / rate,
                    beat_length_ms=beat_length,
                    bpm=bpm,
                )
            )
        timing_points = tuple(transformed_points)

        hit_objects = tuple(
            replace(
                obj,
                time_ms=obj.time_ms / rate,
                spinner_end_ms=(
                    obj.spinner_end_ms / rate if obj.spinner_end_ms is not None else None
                ),
            )
            for obj in hit_objects
        )

    reflected = "HR" in effective
    if reflected:
        hit_objects = tuple(
            replace(
                obj,
                y=PLAYFIELD_HEIGHT - obj.y,
                slider_points=tuple(
                    (x, PLAYFIELD_HEIGHT - y) for x, y in obj.slider_points
                ),
            )
            for obj in hit_objects
        )

    transformed = replace(
        beatmap,
        metadata=dict(beatmap.metadata),
        difficulty=difficulty,
        timing_points=timing_points,
        hit_objects=hit_objects,
    )
    context["status"] = "APPLIED" if context["analysis_ready"] else context["status"]
    context["difficulty_changes"] = _difficulty_changes(before, difficulty)
    context["legacy_ar_fallback_applied"] = legacy_ar_fallback
    context["geometry_reflected"] = reflected
    return transformed, context


def scale_local_difficulty_windows(
    rows: list[dict[str, Any]], clock_rate: float
) -> list[dict[str, Any]]:
    """Scale AR/OD-derived real-time windows after Local Signal extraction."""
    rate = _finite_rate(clock_rate)
    if rate == 1.0:
        return rows
    result: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        for key in ("ls.preempt_ms", "ls.fade_in_ms", "ls.hit_window_great_ms"):
            value = row.get(key)
            if value is not None:
                row[key] = float(value) / rate
        result.append(row)
    return result


def transform_context_matches(
    transform_context: Any, mod_context: dict[str, Any]
) -> bool:
    """Validate that supplied components were prepared for this exact context."""
    if not isinstance(transform_context, dict):
        return False
    if transform_context.get("schema_version") != MOD_TRANSFORM_SCHEMA_VERSION:
        return False
    if transform_context.get("status") != "APPLIED":
        return False
    if transform_context.get("analysis_ready") is not True:
        return False
    return (
        transform_context.get("requested_mods") == mod_context.get("requested_mods")
        and transform_context.get("effective_mods") == mod_context.get("effective_mods")
        and transform_context.get("clock_rate") == mod_context.get("clock_rate")
    )
