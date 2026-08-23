"""Prepare the bounded real-human annotation pilot from the validated dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.active_learning.human_pilot_v01 import prepare_pilot  # noqa: E402


DRY_RUN = ROOT / "training/datasets/active_learning_v01/dry_run"
DEFAULT_OUTPUT = ROOT / "training/datasets/active_learning_v01/human_pilot_v01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_pilot(
        batch_path=DRY_RUN / "batch.jsonl",
        blind_batch_path=DRY_RUN / "blind_batch.jsonl",
        source_manifest_path=DRY_RUN / "manifest.json",
        presentation_contract_path=DRY_RUN / "presentation_contract.json",
        feature_path=ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl",
        output_dir=args.output,
    )
    manifest = result["manifest"]
    print(json.dumps({
        "status": "PASS",
        "pilot_id": manifest["pilot_id"],
        "task_count": len(manifest["task_order"]),
        "manifest_sha256": result["manifest_file"]["sha256"],
        "waiting_for_human_annotation": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
