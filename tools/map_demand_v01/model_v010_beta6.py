"""Opt-in Jump/Flow routing correction on the beta.5 release basis.

Beta.5 remains byte-replayable on Local Signal 0.3.  This release explicitly
opts into Local 0.4 compound-Bezier geometry, adds coherent Jump/Flow evidence,
and replaces only those two axes.  No existing release or runtime default is
mutated by importing this module.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from . import aim_routing_v01 as routing
from . import contract as C
from . import local_pattern_geometry as geometry
from . import model as base
from . import model_decoupled_v01 as decoupled
from . import model_v010_beta5 as previous
from . import model_v092 as summaries
from . import model_v095 as archetypes
from .mod_context_v01 import normalize_mods
from .mod_transform_v01 import transform_beatmap
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_AIM_ROUTING_V010_BETA6"
MAP_DEMAND_VERSION = "0.10.0-beta.6"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.6"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
sha256_file_bytes = previous.sha256_file_bytes
EXPECTED_LOCAL_SIGNAL_VERSION = routing.LOCAL_SIGNAL_VERSION
_LOCAL_ROWS_PROVENANCE_TOKEN = object()


def _rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(
        list(rows),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _Beta6LocalRows(list[dict[str, Any]]):
    """List-compatible rows bound to this release's extraction boundary."""

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        super().__init__(rows)
        self.local_signal_version = EXPECTED_LOCAL_SIGNAL_VERSION
        self._provenance_token = _LOCAL_ROWS_PROVENANCE_TOKEN
        self._content_digest = _rows_digest(self)


RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.6 · Jump/Flow 路径口径修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Local 0.4 corrects compound Bezier geometry but stacking is not implemented",
        "Jump/Flow gates are mechanism-audited heuristics, not a learned calibration",
        "Official Reference Signal 0.2 remains frozen on Local 0.3",
        "Star-equivalent scaling still uses the total osu!.db star anchor",
        "Existing Jump/Flow human reviews are assisted and not an independent calibration set",
    ],
}


def extract_from_path(
    path: str,
    requested_mods: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Extract beta6 rows without changing any historical release wrapper."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from osu_skill_profiler.features.extractor import FeatureExtractor
    from osu_skill_profiler.parser.normalized import normalize
    from osu_skill_profiler.parser.osu_parser import parse_osu_file
    from osu_skill_profiler.signals.extractor import LocalSignalExtractor

    source_beatmap = parse_osu_file(path)
    mod_context = normalize_mods(requested_mods)
    beatmap, transform_context = transform_beatmap(source_beatmap, mod_context)
    rows = LocalSignalExtractor(EXPECTED_LOCAL_SIGNAL_VERSION).extract(beatmap)[
        "objects"
    ]
    rows = base.scale_local_difficulty_windows(
        rows,
        transform_context.get("clock_rate", 1.0),
    )
    features = FeatureExtractor(C.FEATURE_VERSION).extract(normalize(beatmap))
    if len(rows) != len(beatmap.hit_objects):
        raise ValueError("beta6 position alignment failed")
    private_rows: list[dict[str, Any]] = []
    for row, obj in zip(rows, beatmap.hit_objects):
        enriched = dict(row)
        enriched["v091.start_x_px"] = float(obj.x)
        enriched["v091.start_y_px"] = float(obj.y)
        private_rows.append(enriched)
    metadata = {
        "path": path,
        "object_count": len(private_rows),
        "feature_count": len(features),
        "local_signal_version": EXPECTED_LOCAL_SIGNAL_VERSION,
        "difficulty": dict(beatmap.difficulty),
        "effective_difficulty": dict(
            transform_context.get("effective_difficulty", beatmap.difficulty)
        ),
        "source_difficulty": dict(source_beatmap.difficulty),
        "mod_context": mod_context,
        "mod_transform_context": transform_context,
    }
    return _Beta6LocalRows(private_rows), features, metadata


def extract_components(
    local_rows: Iterable[dict],
    features=None,
    difficulty=None,
    clock_rate=1.0,
    effective_mods=(),
    *,
    source_local_signal_version: str,
):
    if source_local_signal_version != EXPECTED_LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "beta6 components require Local Signal "
            f"{EXPECTED_LOCAL_SIGNAL_VERSION}, got {source_local_signal_version!r}"
        )
    if (
        not isinstance(local_rows, _Beta6LocalRows)
        or getattr(local_rows, "_provenance_token", None)
        is not _LOCAL_ROWS_PROVENANCE_TOKEN
        or getattr(local_rows, "local_signal_version", None)
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError(
            "beta6 components require rows returned by beta6.extract_from_path"
        )
    if getattr(local_rows, "_content_digest", None) != _rows_digest(local_rows):
        raise ValueError("beta6 Local Signal rows changed after extraction")
    rows = list(local_rows)
    components, warnings = previous.extract_components(
        rows,
        features,
        difficulty,
        clock_rate,
        effective_mods,
    )
    measure = routing.aim_routing_measure(
        rows,
        source_local_signal_version=source_local_signal_version,
    )
    components["beta6_aim_routing"] = measure
    components["beta6_source_local_signal_version"] = source_local_signal_version
    warnings = list(warnings)
    for mechanic in ("jump", "flow"):
        if measure[mechanic]["status"] == "INSUFFICIENT":
            warnings.append(f"beta6 {mechanic} evidence is insufficient; beta5 axis retained")
    return components, warnings


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta6:aim_routing_1:local04:"
        + previous.calibration_id(base_calibration_id)
    )


def _replace_axis(
    output: dict[str, Any],
    axis: str,
    value: float,
    evidence: tuple[float, float, dict[str, Any]],
) -> None:
    support, counterevidence, signals = evidence
    item = output["axes"][axis]
    item.update(
        {
            "status": "EMITTED",
            "demand_star_equivalent": value,
            "score": value / 10.0,
            "percentile_rank": None,
            "confidence": "LOW",
            "method": "COHERENT_SLIDER_AWARE_AIM_ROUTING_V1",
            "scale_method": "DECOUPLED_CONCAVE_CONTEXT_SCALE_V02",
            "combination_policy": "MAX_OF_COHERENT_MECHANISM_CHANNELS",
            "signals": dict(signals),
            "warnings": [],
            "evidence": [
                {
                    "component": "beta6_aim_routing",
                    "support_gate": support,
                    "counterevidence_gate": counterevidence,
                    "signals": dict(signals),
                    "evidence_tag": "PUBLIC_BETA6",
                }
            ],
        }
    )


def analyze_components(**kwargs: Any) -> dict:
    source_version = kwargs["components"].get("beta6_source_local_signal_version")
    if source_version != EXPECTED_LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "beta6 component provenance mismatch: "
            f"expected {EXPECTED_LOCAL_SIGNAL_VERSION}, got {source_version!r}"
        )
    measure = routing.validate_measure(
        kwargs["components"].get("beta6_aim_routing")
    )
    output = previous.analyze_components(**kwargs)
    # The formula basis is beta5, but the actual source geometry is Local 0.4.
    # Set this before promotion so release_basis_identity records the truthful
    # hybrid basis instead of claiming replayable beta5/Local0.3 provenance.
    output["identity"]["local_signal_version"] = EXPECTED_LOCAL_SIGNAL_VERSION
    promote(
        output,
        algorithm_id=ALGORITHM_ID,
        map_demand_version=MAP_DEMAND_VERSION,
        calibration_id=calibration_id(
            str(kwargs["calibration"].get("calibration_id", ""))
        ),
        schema_version=SCHEMA_VERSION,
        release=RELEASE,
    )

    if output.get("status") == "OK":
        evidence = routing.axis_evidence(measure)
        anchor = geometry.finite(
            output["diagnostics"].get("v091_star_anchor", {}).get("stars"),
            5.0,
        )
        replaced: list[str] = []
        activations: dict[str, float] = {}
        incoming_values: dict[str, float] = {}
        routed_candidates: dict[str, float] = {}
        for axis, mechanic in (("jump_aim", "jump"), ("flow_aim", "flow")):
            incoming = geometry.finite(
                output["axes"][axis].get("demand_star_equivalent"),
                0.0,
            )
            incoming_values[axis] = incoming
            if measure[mechanic]["status"] != "OK":
                activations[axis] = 0.0
                output["warnings"].append(
                    {
                        "code": "BETA6_AIM_EVIDENCE_INSUFFICIENT",
                        "message": f"{axis} retained from beta5",
                    }
                )
                continue
            activation = float(measure[mechanic]["routing_activation"])
            activations[axis] = activation
            if activation == 0.0:
                output["warnings"].append(
                    {
                        "code": "BETA6_AIM_ROUTING_NOT_ACTIVATED",
                        "message": f"{axis} retained from beta5: no qualified evidence",
                    }
                )
                continue
            support, counterevidence, _signals = evidence[axis]
            candidate = decoupled._axis_value(  # noqa: SLF001 - release integration
                axis,
                anchor,
                support,
                counterevidence,
            )
            routed_candidates[axis] = candidate
            value = (1.0 - activation) * incoming + activation * candidate
            if activation < 1.0:
                output["warnings"].append(
                    {
                        "code": "BETA6_AIM_ROUTING_PARTIAL_COVERAGE",
                        "message": (
                            f"{axis} blended with beta5 at evidence "
                            f"activation {activation:.6f}"
                        ),
                    }
                )
            _replace_axis(output, axis, value, evidence[axis])
            output["axes"][axis][
                "combination_policy"
            ] = "EVIDENCE_AVAILABILITY_WEIGHTED_ROUTE_FROM_BETA5"
            replaced.append(axis)

        output["diagnostics"]["beta6_aim_routing"] = measure
        output["diagnostics"]["beta6_aim_routing_activation"] = activations
        output["diagnostics"]["beta6_aim_routing_incoming"] = incoming_values
        output["diagnostics"]["beta6_aim_routing_candidate"] = routed_candidates
        output["diagnostics"]["beta6_flow_routing_activation"] = activations[
            "flow_aim"
        ]
        output["diagnostics"]["beta6_replaced_axes"] = replaced
        output["summaries"] = summaries.derive_summaries(output["axes"])
        output["archetype"] = archetypes._classify_axes_with_low_demand_abstention(
            output["axes"],
            anchor,
        )

    C.scan_finite(output, "model_v010_beta6.output")
    return output


__all__ = [
    "ALGORITHM_ID",
    "MAP_DEMAND_VERSION",
    "SCHEMA_VERSION",
    "AXIS_SCHEMA_VERSION",
    "AXIS_ORDER",
    "RELEASE",
    "EXPECTED_LOCAL_SIGNAL_VERSION",
    "extract_from_path",
    "extract_components",
    "analyze_components",
    "calibration_id",
    "sha256_file_bytes",
]
