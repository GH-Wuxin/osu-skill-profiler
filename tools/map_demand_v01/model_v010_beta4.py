"""Publish ONLY the reviewed V03 Aim Control on the live beta.3 foundation.

The offline experiment also carries an older Reading experiment. Deliberately
do not call its extract_components/analyze_components: the other eight live
axes, including Reading, must remain byte-for-byte beta.3 output.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import contract as C
from . import model_v010_beta3 as previous
from . import model_v092 as summaries
from . import model_v095 as archetypes
from . import control_execution_v03 as control
from . import local_pattern_geometry as geometry
from .public_beta import promote

ALGORITHM_ID = "MAP_DEMAND_CONTROL_EXECUTION_V010_BETA4"
MAP_DEMAND_VERSION = "0.10.0-beta.4"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.4"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
extract_from_path = previous.extract_from_path
sha256_file_bytes = previous.sha256_file_bytes
RELEASE = {
    "version": MAP_DEMAND_VERSION, "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.4 · Aim Control 执行时间试用版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Only Aim Control adopts offline execution experiment V03; Reading and the other seven axes retain beta.3",
        "Execution-time response is heuristic and requires player review, especially at very high speed",
        "Eight-consecutive-transition support may underestimate very short control passages",
        "Cursor trajectory and slider-internal control are not fully simulated",
    ],
}


def extract_components(local_rows: Iterable[dict], features=None, difficulty=None,
                       clock_rate=1.0, effective_mods=()):
    rows = list(local_rows)
    components, warnings = previous.extract_components(rows, features, difficulty, clock_rate, effective_mods)
    objects = geometry.objects(rows, components.get("reading_preempt_median_ms"))
    components["beta4_control"] = control.control_measure(objects, geometry.predictability(objects))
    return components, warnings


def calibration_id(base_calibration_id: str) -> str:
    return "md010beta4:control_execution_3:" + previous.calibration_id(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict:
    output = previous.analyze_current_basis(**kwargs)
    promote(
        output,
        algorithm_id=ALGORITHM_ID,
        map_demand_version=MAP_DEMAND_VERSION,
        calibration_id=calibration_id(str(kwargs["calibration"].get("calibration_id", ""))),
        schema_version=SCHEMA_VERSION,
        release=RELEASE,
    )
    if output.get("status") == "OK":
        measure = kwargs["components"].get("beta4_control")
        if not isinstance(measure, dict) or "value" not in measure:
            raise ValueError("beta.4 requires its own local component extraction")
        value = measure["value"]
        output["axes"]["aim_control"].update({
            "status": "EMITTED", "demand_star_equivalent": value, "score": value / 10.0,
            "percentile_rank": None, "method": "LOCAL_CONTROL_EXECUTION_V3",
            "scale_method": "INDEPENDENT_PHYSICAL_SCALE_NO_TOTAL_SR",
            "evidence": [{"component": "beta4_control", "signals": measure,
                          "evidence_tag": "PUBLIC_BETA4"}],
        })
        output["diagnostics"]["beta4_control"] = measure
        output["summaries"] = summaries.derive_summaries(output["axes"])
        anchor = geometry.finite(output["diagnostics"].get("v091_star_anchor", {}).get("stars"), 5.0)
        output["archetype"] = archetypes._classify_axes_with_low_demand_abstention(output["axes"], anchor)
    C.scan_finite(output, "model_v010_beta4.output")
    return output
