"""Generate blinded human-label manifests from internal pair audit JSON.

Reads an internal high-information pair file (the audit JSON, not a
participant-facing file), selects pairs deterministically, and writes two
artifacts:

  participant_manifest.json  -- anonymous trial ids, construct, neutral
                                stimulus refs, orientation, answer schema.
                                Contains NO metric values and NO answers.
  unblinding_manifest.json   -- pair ids, map checksums, segment bounds,
                                class, all metric values, expected sign
                                (nullable), and the frozen SHA-256 identity.

This tool never fabricates labels and never fills in an answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


def _find_pairs(obj: Any) -> list[dict]:
    """Tolerantly find pair-like records in an audit JSON document."""
    if isinstance(obj, dict):
        side_a = obj.get("side_a")
        side_b = obj.get("side_b")
        if isinstance(side_a, dict) and isinstance(side_b, dict):
            return [{"a": side_a, "b": side_b, **{k: v for k, v in obj.items() if k not in ("side_a", "side_b")}}]
        if isinstance(obj.get("a"), dict) and isinstance(obj.get("b"), dict):
            return [obj]
        out: list[dict] = []
        for value in obj.values():
            out.extend(_find_pairs(value))
        return out
    if isinstance(obj, list):
        out = []
        for value in obj:
            out.extend(_find_pairs(value))
        return out
    return []


def _stable_identity(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _side_ref(side: dict) -> dict[str, str]:
    checksum = str(side.get("map_checksum") or side.get("checksum") or "unknown")
    segment = side.get("segment_index")
    return {
        "map_checksum": checksum,
        "segment_index": segment if segment is not None else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", default="osu-skill-profiler-label-manifest-v01")
    parser.add_argument("--sessions", type=int, default=4)
    args = parser.parse_args()

    doc = json.loads(args.pairs.read_text(encoding="utf-8"))
    pairs = _find_pairs(doc)
    pairs = pairs[: args.limit]
    if not pairs:
        raise SystemExit("no pair-like records found")

    rng = random.Random(args.seed)
    trials: list[dict] = []
    unblind: list[dict] = []
    session_size = max(1, (len(pairs) * 2 + args.sessions - 1) // args.sessions)
    for pair_index, pair in enumerate(pairs):
        a_checksum = str(
            pair.get("a", {}).get("map_checksum")
            or pair.get("a", {}).get("checksum")
            or "unknown-a"
        )
        b_checksum = str(
            pair.get("b", {}).get("map_checksum")
            or pair.get("b", {}).get("checksum")
            or "unknown-b"
        )
        base_key = f"{a_checksum}\n{b_checksum}\n{pair_index}"
        for question_index, construct in enumerate(("PATH", "TIME")):
            orientation = rng.choice(("AB", "BA"))
            trial_id = "trial-" + hashlib.sha256(
                f"{args.seed}\n{base_key}\n{construct}\n{orientation}".encode("utf-8")
            ).hexdigest()[:16]
            participant_trial = {
                "trial_id": trial_id,
                "session_id": f"session-{pair_index * 2 // session_size + 1:03d}",
                "construct": construct,
                "orientation": orientation,
                "stimulus_refs": {
                    "left": trial_id + "-left",
                    "right": trial_id + "-right",
                },
                "answer_schema": ["LEFT", "RIGHT", "NO_CLEAR_DIFFERENCE"],
                "confidence_schema": [1, 2, 3],
                "hidden_repeat_id": None,
                "control_flag": False,
            }
            trials.append(participant_trial)
            unblind.append({
                "trial_id": trial_id,
                "pair_index": pair_index,
                "pair_id": pair.get("pair_id", f"pair-{pair_index:04d}"),
                "class_id": pair.get("class_id", "UNKNOWN"),
                "construct": construct,
                "orientation": orientation,
                "stimulus_a": _side_ref(pair.get("a", {})),
                "stimulus_b": _side_ref(pair.get("b", {})),
                "metrics_a": pair.get("a", {}),
                "metrics_b": pair.get("b", {}),
                "expected_sign": None,
                "unblinding_earliest_utc": None,
            })

    participant = {
        "schema_version": "0.1.0",
        "kind": "participant_manifest",
        "trials": trials,
        "count": len(trials),
        "answer_schema": ["LEFT", "RIGHT", "NO_CLEAR_DIFFERENCE"],
        "confidence_schema": [1, 2, 3],
        "contains_answers": False,
        "contains_metrics": False,
        "manifest_sha256": None,
    }
    participant_bytes = json.dumps(participant, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
    participant["manifest_sha256"] = hashlib.sha256(participant_bytes).hexdigest()
    participant_bytes = json.dumps(participant, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")

    unblinding = {
        "schema_version": "0.1.0",
        "kind": "unblinding_manifest",
        "trials": unblind,
        "count": len(unblind),
        "contains_answers": False,
        "contains_metrics": True,
        "participant_manifest_sha256": participant["manifest_sha256"],
    }
    unblinding_bytes = json.dumps(unblinding, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "participant_manifest.json").write_bytes(participant_bytes)
    (args.out_dir / "unblinding_manifest.json").write_bytes(unblinding_bytes)
    print(json.dumps({
        "status": "PASS",
        "trials": len(trials),
        "participant_manifest_sha256": participant["manifest_sha256"],
        "out_dir": str(args.out_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
