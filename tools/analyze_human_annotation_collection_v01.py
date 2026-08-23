"""Capture and analyse a stable snapshot of the live multi-annotator pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.active_learning.collection_analysis_v01 import (  # noqa: E402
    capture_collection,
    write_snapshot,
)


DEFAULT_PILOT = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"
DEFAULT_COLLECTION = DEFAULT_PILOT / "collections/collection_001"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--collection-dir", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--max-capture-attempts", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root or (args.collection_dir / "analysis")
    capture = capture_collection(
        pilot_dir=args.pilot_dir,
        collection_dir=args.collection_dir,
        max_attempts=args.max_capture_attempts,
    )
    snapshot_dir, analysis = write_snapshot(capture, output_root=output_root)
    state = analysis["collection_state"]
    print(json.dumps({
        "status": "COLLECTION_SNAPSHOT_ANALYSED",
        "snapshot_id": analysis["snapshot_id"],
        "snapshot_dir": str(snapshot_dir.resolve()),
        "response_count": state["response_count"],
        "responded_participant_count": state["responded_participant_count"],
        "complete_five_response_sessions": state["complete_five_response_sessions"],
        "covered_task_count": state["covered_task_count"],
        "training_eligible": False,
        "taxonomy_frozen": False,
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
