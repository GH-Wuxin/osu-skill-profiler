"""Stable 1.0.0 release: frozen beta.9.2 computation, new identity only.

Do not tune the delegated modules in place. Future behavioral changes need
a new version; all nine axis payloads, summaries, and archetypes are frozen.
"""

from __future__ import annotations

from typing import Any

from . import contract as C
from . import model_v010_beta92 as previous
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_V100"
MAP_DEMAND_VERSION = "1.0.0"
SCHEMA_VERSION = "map_demand_v1.0.0"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = previous.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
SUPPORT_AWARE_AXES = previous.SUPPORT_AWARE_AXES
REBUILT_LOCAL_AXES = previous.REBUILT_LOCAL_AXES
INHERITED_AXIS_CONTRACTS = previous.INHERITED_AXIS_CONTRACTS
REBUILT_LOCAL_AXIS_CONTRACTS = previous.REBUILT_LOCAL_AXIS_CONTRACTS
CHANGED_FROM_PREVIOUS = frozenset()
ORDINARY_INPUT_ROLE = previous.ORDINARY_INPUT_ROLE
AUXILIARY_HITSOUND_INPUT_ROLE = previous.AUXILIARY_HITSOUND_INPUT_ROLE
sha256_file_bytes = previous.sha256_file_bytes
extract_from_path = previous.extract_from_path
extract_components = previous.extract_components

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "STABLE",
    "label": "1.0.0 · 正式版（冻结 Beta 9.2）",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        *previous.RELEASE["known_limitations"],
        "Stable release freezes behavior; heuristic star-equivalent scales are not official osu! difficulty or ground truth",
        "Flow CS adjustment is a map-level latent-load rebase, not a new local target-tolerance model",
    ],
}


def calibration_id(base_calibration_id: str) -> str:
    return "md100:frozen_beta92:" + previous.calibration_id(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    output = previous.analyze_components(**kwargs)
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
    C.scan_finite(output, "model_v100.output")
    return output
