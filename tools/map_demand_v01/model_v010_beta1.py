"""Public beta identity for the reviewed decoupled R2; numerical rules unchanged."""

from typing import Any

from . import model_decoupled_v01 as experiment

ALGORITHM_ID = "MAP_DEMAND_DECOUPLED_V010_BETA1"
MAP_DEMAND_VERSION = "0.10.0-beta.1"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.1"
AXIS_SCHEMA_VERSION = experiment.AXIS_SCHEMA_VERSION
AXIS_ORDER = experiment.AXIS_ORDER
extract_from_path = experiment.extract_from_path
extract_components = experiment.extract_components
sha256_file_bytes = experiment.sha256_file_bytes
RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.1 · 试用",
    "basis": experiment.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Finger Control can emit zero when switching evidence is absent",
        "Jump/Flow retain the reviewed 1.08-times-anchor guard",
        "Mod scale uses an estimated anchor; unavailable NM SR uses structural fallback",
    ],
}


def calibration_id(base_calibration_id: str) -> str:
    return f"md010beta1:{experiment.calibration_id(base_calibration_id)}"


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    # Do not copy or retune the reviewed formulas while promoting the release.
    output = experiment.analyze_components(**kwargs)
    original_identity = dict(output["identity"])
    output["identity"] = {
        **original_identity,
        "algorithm_id": ALGORITHM_ID,
        "map_demand_version": MAP_DEMAND_VERSION,
        "calibration_id": calibration_id(str(kwargs["calibration"].get("calibration_id", ""))),
    }
    output["schema_version"] = SCHEMA_VERSION
    output["release"] = {**RELEASE, "known_limitations": list(RELEASE["known_limitations"])}
    output["diagnostics"]["release_basis_identity"] = original_identity
    return output
