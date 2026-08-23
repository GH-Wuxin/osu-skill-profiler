"""Generate the deterministic remediated second single-annotator pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.active_learning.human_pilot_v02 import prepare_pilot_v02  # noqa: E402


DEFAULT_OUTPUT = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_pilot_v02(
        source_batch_path=ROOT / "training/datasets/active_learning_v01/dry_run/batch.jsonl",
        feature_path=ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl",
        session001_response_path=(
            ROOT / "training/datasets/active_learning_v01/human_pilot_v01/responses/annotator_001/pilot_session_001.jsonl"
        ),
        session001_disposition_path=ROOT / "docs/archive/HUMAN_ANNOTATION_PILOT_SESSION_001_DISPOSITION.json",
        output_dir=args.output,
    )
    print(json.dumps({
        "status": "PASS",
        "pilot_id": result["manifest"]["pilot_id"],
        "task_count": result["manifest"]["composition"]["task_count"],
        "formal_response_count": result["manifest"]["formal_response_count"],
        "manifest_sha256": result["manifest_file"]["sha256"],
        "waiting_for_second_human_annotation": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
