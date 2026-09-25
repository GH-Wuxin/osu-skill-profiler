"""Independent post-v0.40 measurement layer.

This is the narrow public entry point for the two new measurements.  It wraps
the frozen map-demand output, adds the common-star representation, and exposes
the player evidence estimator.  Selecting this module never changes the v0.40
algorithm or its historical fields.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .player_skill_rating_v01 import estimate_player_skill_profile
from .player_score_evidence_v01 import (
    ingest_score_records,
    skill_evidence_records,
)
from .unified_star_scale_v01 import (
    SCALE_ID,
    apply_unified_star_scale,
    load_calibration,
)


RELEASE_ID = "post-v040-measurements-v0.1"
SCHEMA_VERSION = "osu_skill_profiler_measurements_v0.1"


def apply_map_measurements(
    frozen_v040_output: Mapping[str, Any],
    calibration: Mapping[str, Any],
    *,
    mod_context: str | None = None,
) -> dict[str, Any]:
    """Add unified-star fields without rewriting the frozen map output."""

    result = apply_unified_star_scale(frozen_v040_output, calibration)
    result["measurement_context"] = {
        "mod_context": str(mod_context or calibration.get("mod_context") or "NM"),
        "scale_context": str(calibration.get("mod_context") or "NM"),
    }
    result["measurement_release"] = {
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "map_demand_basis": "FORMAL_MAP_DEMAND_V040_FROZEN",
        "player_skill_rating": "SEPARATE_PLAYER_EVIDENCE_LAYER",
    }
    return result


def apply_map_measurements_from_path(
    frozen_v040_output: Mapping[str, Any],
    calibration_path: str,
    *,
    mod_context: str | None = None,
) -> dict[str, Any]:
    """Load a packaged calibration and attach the independent map layer."""

    return apply_map_measurements(
        frozen_v040_output,
        load_calibration(calibration_path),
        mod_context=mod_context,
    )


def estimate_player_measurements(
    records: Iterable[Mapping[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Estimate the player axis vector from normalized evidence records."""

    result = estimate_player_skill_profile(records, **kwargs)
    result["measurement_release"] = {
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "map_demand_basis": "UNIFIED_STAR_DEMAND_EQUIVALENCE",
        "overall_scalar": "NOT_CONTRACTED",
    }
    return result


def ingest_player_scores(
    records: Iterable[Mapping[str, Any]],
    *,
    map_index: Mapping[str, Mapping[str, Any]] | None = None,
    source: str = "score_export",
    default_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Ingest every score/pp row and retain the subset ready for Skill Rating."""

    return ingest_score_records(
        records,
        map_index=map_index,
        source=source,
        default_timestamp=default_timestamp,
    )


def estimate_player_from_scores(
    records: Iterable[Mapping[str, Any]],
    *,
    player_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Estimate Skill Rating from already ingested score rows.

    Performance-only rows are preserved by ``ingest_player_scores`` but do not
    silently become skill evidence.
    """

    ingested = list(records)
    ready_records = skill_evidence_records(ingested)
    resolved_player_id = player_id
    if resolved_player_id is None and ingested:
        resolved_player_id = str(ingested[0].get("player_id"))
    requested_context = kwargs.get("mod_context")
    if requested_context is not None:
        result = estimate_player_measurements(
            ready_records,
            player_id=resolved_player_id,
            **kwargs,
        )
    else:
        contexts = sorted(
            {
                str(record.get("mod_context") or "NM").upper()
                for record in ready_records
            }
        )
        if len(contexts) <= 1:
            result = estimate_player_measurements(
                ready_records,
                player_id=resolved_player_id,
                **kwargs,
            )
        else:
            # Each context has its own ppy ruler.  Partitioning here keeps a
            # caller with mixed-mod score history useful without averaging
            # incompatible stars into one profile.
            estimator_kwargs = dict(kwargs)
            estimator_kwargs.pop("mod_context", None)
            profiles = {
                context: estimate_player_measurements(
                    [
                        record
                        for record in ready_records
                        if str(record.get("mod_context") or "NM").upper() == context
                    ],
                    player_id=resolved_player_id,
                    mod_context=context,
                    **estimator_kwargs,
                )
                for context in contexts
            }
            statuses = {profile.get("status") for profile in profiles.values()}
            profile_status = (
                "ADMITTED"
                if statuses == {"ADMITTED"}
                else "CANDIDATE"
                if statuses - {"UNKNOWN"}
                else "UNKNOWN"
            )
            timestamps = sorted(
                str(record.get("timestamp"))
                for record in ready_records
                if record.get("timestamp")
            )
            result = {
                "schema_version": "player_skill_rating_v0.1",
                "rating_id": "player-skill-rating-v0.1",
                "player_id": str(resolved_player_id),
                "status": profile_status,
                "scale_id": SCALE_ID,
                "mod_context": None,
                "profiles_by_mod_context": profiles,
                "overall": {
                    "status": "NOT_EMITTED",
                    "rating": None,
                    "reason": "cross_context_and_cross_axis_aggregation_not_defined",
                },
                "source_window": {
                    "from": timestamps[0] if timestamps else None,
                    "to": timestamps[-1] if timestamps else None,
                },
                "evidence_count": len(ready_records),
                "coverage": {
                    context: profile.get("coverage")
                    for context, profile in profiles.items()
                },
                "provenance": [
                    "context_partitioned_multi_map_player_evidence",
                    "one_ppy_ruler_per_non_flashlight_mod_context",
                    "no_cross_context_aggregation",
                ],
            }
    ready = sum(
        isinstance(item.get("skill_evidence"), Mapping)
        and item["skill_evidence"].get("status") == "READY_FOR_SKILL_RATING"
        for item in ingested
    )
    result["score_ingestion"] = {
        "input_count": len(ingested),
        "pp_observed_count": sum(
            (item.get("pp_measurement") or {}).get("status") == "OBSERVED"
            for item in ingested
        ),
        "skill_ready_count": ready,
        "performance_only_count": len(ingested) - ready,
        "flashlight_excluded_count": sum(
            (item.get("skill_evidence") or {}).get("reason")
            == "flashlight_excluded_from_current_axis_contract"
            for item in ingested
        ),
    }
    return result


__all__ = [
    "RELEASE_ID",
    "SCHEMA_VERSION",
    "apply_map_measurements",
    "apply_map_measurements_from_path",
    "estimate_player_measurements",
    "estimate_player_from_scores",
    "ingest_player_scores",
]
