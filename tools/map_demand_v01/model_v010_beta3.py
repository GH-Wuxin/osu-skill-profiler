"""Pre scale repair: additive log target cost, not a bounded base times r^-1.65.

Only spatial_precision changes. Beta.2 remains replayable, including its other
eight axes. Constants define an experimental demand scale, not human truth.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable

from . import contract as C
from . import model_v010_beta2 as previous

ALGORITHM_ID = "MAP_DEMAND_PRECISION_BALANCE_V010_BETA3"
MAP_DEMAND_VERSION = "0.10.0-beta.3"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.3"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
extract_from_path = previous.extract_from_path
sha256_file_bytes = previous.sha256_file_bytes
CHANGED_AXES = ("spatial_precision",)
RELEASE = {
    "version": MAP_DEMAND_VERSION, "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.3 · Precision 平衡修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Precision uses an experimental logarithmic demand scale, not physiological measurements",
        "Target tolerance is primary; bounded relocation/micro evidence is not full aim difficulty",
        "All other eight axes, including Stamina, retain beta.2 rules",
    ],
}


def target_cost(radius: float) -> float:
    """Continuous size cost; larger targets give relief, not a score ceiling.

    Each halving of a small target adds 4.2 units instead of multiplying the
    whole score. The gentler large-target branch avoids erasing real precision.
    """
    octaves = math.log2(previous.REF_RADIUS / radius)
    return (4.2 if octaves >= 0 else 1.6) * octaves


def precision_measure(events: list[dict]) -> dict:
    values, radii = [], []
    previous_distance = 0.0
    micro_peak = 0.0
    for event in events:
        radius, dt = event["radius"], event["dt"]
        if radius <= 0 or dt <= 0:
            previous_distance = 0.0
            continue
        if event["break"]:
            previous_distance = 0.0
        distance = event["distance"]
        acquisition = -math.expm1(-distance / 32.0)
        # A continuous deadline cost, without beta.2's ~2.7 normal-CS ceiling.
        # Raw distance saturates after relocation: this is not Jump Aim speed.
        deadline = 2.2 * math.log2(1.0 + (1000.0 / dt) / 2.0)
        micro = (previous.clamp((previous_distance - 128.0) / 128.0)
                 / (1.0 + (distance / 40.0) ** 2)
                 * previous.clamp((math.pi / 2.0 - event["angle"]) / (math.pi / 2.0))
                 * (-math.expm1(-150.0 / dt)) * acquisition)
        value = acquisition * max(0.0, deadline + target_cost(radius)) + .65 * micro
        values.append((event["time"], value))
        radii.append(radius)
        micro_peak = max(micro_peak, micro)
        previous_distance = distance
    result = previous._local_peak(values)
    radius = statistics.median(radii) if radii else None
    result.update(radius_median=radius, micro_peak=micro_peak,
                  target_cost=target_cost(radius) if radius else 0.0,
                  total_sr_used=False, scale="ADDITIVE_LOG_TOLERANCE")
    return result


def extract_components(local_rows: Iterable[dict], features=None, difficulty=None,
                       clock_rate=1.0, effective_mods=()):
    rows = list(local_rows)
    components, warnings = previous.extract_components(rows, features, difficulty, clock_rate, effective_mods)
    components["beta3_precision"] = precision_measure(previous._events(rows))
    return components, warnings


def calibration_id(base_calibration_id: str) -> str:
    return "md010beta3:additive_log_tolerance_1:" + previous.calibration_id(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict:
    output = previous.analyze_components(**kwargs)
    original_identity = dict(output["identity"])
    output["identity"] = {**original_identity, "algorithm_id": ALGORITHM_ID,
                          "map_demand_version": MAP_DEMAND_VERSION,
                          "calibration_id": calibration_id(str(kwargs["calibration"].get("calibration_id", "")))}
    output["schema_version"] = SCHEMA_VERSION
    output["release"] = {**RELEASE, "known_limitations": list(RELEASE["known_limitations"])}
    output["diagnostics"]["release_basis_identity"] = original_identity
    if output.get("status") == "OK":
        measure = kwargs["components"].get("beta3_precision")
        if not isinstance(measure, dict) or "value" not in measure:
            raise ValueError("beta.3 requires its own local component extraction")
        value = measure["value"]
        output["axes"]["spatial_precision"].update({
            "status": "EMITTED", "demand_star_equivalent": value, "score": value / 10.0,
            "percentile_rank": None, "method": "ADDITIVE_LOG_TOLERANCE_V1",
            "scale_method": "INDEPENDENT_PHYSICAL_SCALE_NO_TOTAL_SR",
            "evidence": [{"component": "beta3_precision", "signals": measure,
                          "evidence_tag": "PUBLIC_BETA3"}],
        })
        output["diagnostics"]["beta3_precision"] = measure
        base = previous.base
        output["summaries"] = base.v092.derive_summaries(output["axes"])
        anchor = previous.finite(output["diagnostics"].get("v091_star_anchor", {}).get("stars"), 5.0)
        output["archetype"] = base.v095._classify_axes_with_low_demand_abstention(output["axes"], anchor)
    C.scan_finite(output, "model_v010_beta3.output")
    return output
