"""Runtime release selection shared by CLI and HTTP workbench.

The ignored runtime override is also read by the existing no-argument startup
task, so a rollback survives a subsequent machine restart.
"""

import json
import os
from pathlib import Path

from . import model_v010_beta1, model_v010_beta2, model_v010_beta3, model_v010_beta4, model_v096

DEFAULT_ALGORITHM = "v010-beta4"
RUNTIME_ALGORITHMS = {
    "v010-beta4": model_v010_beta4,
    "v010-beta3": model_v010_beta3,
    "v010-beta2": model_v010_beta2,
    "v010-beta1": model_v010_beta1,
    "v096": model_v096,
}
RUNTIME_SELECTION_PATH = Path(__file__).resolve().parents[2] / "tmp" / "runtime-release.json"


def default_algorithm() -> str:
    selected = os.environ.get("SKILL_PROFILER_ALGORITHM", "").strip()
    if not selected and RUNTIME_SELECTION_PATH.is_file():
        selected = json.loads(RUNTIME_SELECTION_PATH.read_text(encoding="utf-8-sig"))["algorithm"]
    selected = selected or DEFAULT_ALGORITHM
    if selected not in RUNTIME_ALGORITHMS:
        raise ValueError(f"Unsupported runtime algorithm: {selected}")
    return selected


def runtime_model(algorithm: str | None = None):
    return RUNTIME_ALGORITHMS[algorithm or default_algorithm()]
