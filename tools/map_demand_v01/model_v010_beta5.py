"""Publish the reviewed local-order Reading measure on the beta.4 basis."""
from __future__ import annotations

from typing import Any, Iterable

from . import contract as C
from . import local_pattern_geometry as geometry
from . import model_v010_beta4 as previous
from . import model_v092 as summaries
from . import model_v095 as archetypes
from . import reading_order_v01 as reading
from .public_beta import promote

ALGORITHM_ID = "MAP_DEMAND_READING_ORDER_V010_BETA5"
MAP_DEMAND_VERSION = "0.10.0-beta.5"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.5"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
extract_from_path = previous.extract_from_path
sha256_file_bytes = previous.sha256_file_bytes
RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.5 · Reading 顺序与遮挡试用版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Reading uses local order, retention, rapid decoding, and approximate HD memory rather than full visual simulation",
        "Medium-speed aim relief and HD disappearance timing remain heuristic",
        "Very short or unusual slider-internal reading patterns may be underestimated",
    ],
}


def extract_components(local_rows: Iterable[dict], features=None, difficulty=None,
                       clock_rate=1.0, effective_mods=()):
    rows = list(local_rows)
    components, warnings = previous.extract_components(
        rows, features, difficulty, clock_rate, effective_mods)
    objects = geometry.objects(rows, components.get("reading_preempt_median_ms"))
    components["beta5_reading"] = reading.reading_measure(
        objects, geometry.predictability(objects), effective_mods)
    return components, warnings


def calibration_id(base_calibration_id: str) -> str:
    return "md010beta5:reading_order_1:" + previous.calibration_id(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict:
    output = previous.analyze_components(**kwargs)
    promote(
        output,
        algorithm_id=ALGORITHM_ID,
        map_demand_version=MAP_DEMAND_VERSION,
        calibration_id=calibration_id(str(kwargs["calibration"].get("calibration_id", ""))),
        schema_version=SCHEMA_VERSION,
        release=RELEASE,
    )
    if output.get("status") == "OK":
        measure = kwargs["components"].get("beta5_reading")
        if not isinstance(measure, dict) or "value" not in measure:
            raise ValueError("beta.5 requires its own local Reading extraction")
        value = measure["value"]
        output["axes"]["reading"].update({
            "status": "EMITTED",
            "demand_star_equivalent": value,
            "score": value / 10.0,
            "percentile_rank": None,
            "method": "LOCAL_ORDER_MEMORY_READING_V1",
            "scale_method": "INDEPENDENT_LOCAL_SCALE_NO_TOTAL_SR",
            "evidence": [{"component": "beta5_reading", "signals": measure,
                          "evidence_tag": "PUBLIC_BETA5"}],
        })
        output["diagnostics"]["beta5_reading"] = measure
        output["summaries"] = summaries.derive_summaries(output["axes"])
        anchor = geometry.finite(
            output["diagnostics"].get("v091_star_anchor", {}).get("stars"), 5.0)
        output["archetype"] = archetypes._classify_axes_with_low_demand_abstention(
            output["axes"], anchor)
    C.scan_finite(output, "model_v010_beta5.output")
    return output
