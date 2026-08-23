"""P2C V02 10x6 retest package builder.

10 complete participants x 6 slider-core judgments (3 pairs x PATH/TIME),
plus 5 dropout-replacement reserve slots (P11-P15, never extra samples).
Stress / diagnostic / dense / repeat / inversion assets stay in the docs but
never enter the FORMAL assignments. Deterministic seeded schedules with
same-pair non-adjacency and per-item random A/B orientation. Tool code only;
no analyzer modification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402

PACKAGE_ID = "retest-10x6-core-package-001"
PACKAGE_VERSION = "0.1.0"
QUESTION_DEFINITIONS_VERSION = "0.2.0"   # wording 0.2.1 (see retest doc 0.2.1)
ASSIGNMENT_SEED_NONCE = "osu-skill-profiler-targeted-retest-10x6-v01"
CORE_PROBE_IDS = ("S-T1-CORE-A", "S-T2-CORE-A", "S-T2-CORE-B")
QUESTIONS = ("Q-V02-SLIDER-PATH", "Q-V02-SLIDER-TIME")
PLANNED_SLOTS = [{"participant_id": f"retest_p6_{i:02d}", "role": "planned"} for i in range(1, 11)]
RESERVE_SLOTS = [{"participant_id": f"retest_p6_{i:02d}", "role": "reserve"} for i in range(11, 16)]
PARTICIPANT_SLOTS = PLANNED_SLOTS + RESERVE_SLOTS
WINDOW_LENGTH_MS = 8500.0
WINDOW_END_PADDING_MS = 100.0
DEFAULT_CONTEXT = {"before_ms": 2000.0, "after_ms": 1500.0}


class SeededRandom:
    def __init__(self, seed: str):
        self._rng = random.Random(seed)

    def shuffle(self, items: list) -> list:
        result = list(items)
        self._rng.shuffle(result)
        return result

    def choice(self, items: list):
        return items[self._rng.randrange(len(items))]


def compute_pair_windows(package: dict) -> dict[str, dict]:
    """Equal-length, clip-safe window per slider pair (identical both sides)."""
    feature_index = Path(package["feature_index_path"])
    paths: dict[str, Path] = {}
    with feature_index.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if isinstance(row.get("checksum"), str):
                paths[row["checksum"]] = Path(row["path_abs"])
    windows: dict[str, dict] = {}
    for probe in package["probes"]:
        if probe["question_family"] != "slider":
            continue
        seg_start = min(float(probe["side_a"]["segment_start_ms"]), float(probe["side_b"]["segment_start_ms"]))
        seg_end = max(float(probe["side_a"]["segment_end_ms"]), float(probe["side_b"]["segment_end_ms"]))
        default_start = max(0.0, seg_start - DEFAULT_CONTEXT["before_ms"])
        default_end = seg_end + DEFAULT_CONTEXT["after_ms"]
        latest_end = default_end
        for side in ("side_a", "side_b"):
            checksum = probe[side]["map_checksum"]
            beatmap = parse_osu_file(paths[checksum])
            normalized = normalize(beatmap)
            seg_e = probe[side]["segment_end_ms"]
            for obj in normalized.objects:
                if obj.raw.object_type != "slider":
                    continue
                if obj.time_ms <= float(seg_e) + DEFAULT_CONTEXT["after_ms"]:
                    latest_end = max(latest_end, obj.canonical_end_time_ms())
        window_end = latest_end + WINDOW_END_PADDING_MS
        window_start = window_end - WINDOW_LENGTH_MS
        windows[probe["probe_id"]] = {
            "start_ms": round(window_start, 3),
            "end_ms": round(window_end, 3),
            "length_ms": WINDOW_LENGTH_MS,
            "clip_safe": True,
            "note": "default 8.5s window" if window_end <= default_end + 1e-6 else "equal length both sides; extended end",
        }
    return windows


def build_schedule_10x6(package: dict, seed: str) -> list[dict]:
    """Six slider-core judgments per participant, same-pair non-adjacent."""
    rng = SeededRandom(seed)
    base = [{"kind": "slider", "probe_id": pid, "question_id": qid}
            for pid in CORE_PROBE_IDS for qid in QUESTIONS]
    items = None
    for _attempt in range(500):
        candidate = rng.shuffle(base)
        if all(candidate[i]["probe_id"] != candidate[i + 1]["probe_id"] for i in range(len(candidate) - 1)):
            items = candidate
            break
    if items is None:
        raise ValueError("could not schedule six slider items without adjacent same-pair questions")
    final: list[dict] = []
    for index, item in enumerate(items):
        item_id = "item-" + hashlib.sha256(
            f"{seed}\n{index}\n{item['kind']}\n{item['probe_id']}\n{item['question_id']}".encode("utf-8")
        ).hexdigest()[:16]
        final.append({
            "item_id": item_id,
            "item_index": index,
            "item_kind": item["kind"],
            "probe_id": item["probe_id"],
            "question_id": item["question_id"],
            "question_definitions_version": QUESTION_DEFINITIONS_VERSION,
            "orientation": rng.choice(["AB", "BA"]),
        })
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-json", type=Path,
                        default=ROOT / "docs/HUMAN_TARGETED_RETEST_V02.json")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "training/datasets/retest_v01/package")
    parser.add_argument("--feature-index", type=Path,
                        default=ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl")
    args = parser.parse_args()

    doc = json.loads(args.package_json.read_text(encoding="utf-8"))
    core_probes = [p for p in doc["probes"] if p["probe_id"] in CORE_PROBE_IDS]
    if len(core_probes) != 3:
        raise ValueError("expected exactly 3 core probes")
    package = {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "question_definitions_version": QUESTION_DEFINITIONS_VERSION,
        "wording_version": "0.2.1",
        "feature_index_path": str(args.feature_index),
        "probes": core_probes,
        "question_definitions": doc["question_definitions"],
        "excluded_from_formal_assignments": {
            "preserved_assets": ["S-T1-STRESS", "S-T1-DIAGNOSTIC", "D-D1-CORE", "D-D3-CORE",
                                 "S-RES-1", "S-RES-2", "D-D1-RES", "D-D2-RES",
                                 "CONTROL-R1", "CONTROL-I1"],
            "note": "assets remain in docs; this package carries only the three slider core pairs",
        },
    }
    windows = compute_pair_windows(package)
    package["pair_windows"] = windows

    assignments = {}
    for slot in PARTICIPANT_SLOTS:
        participant_id = slot["participant_id"]
        seed = hashlib.sha256(f"{ASSIGNMENT_SEED_NONCE}\n{PACKAGE_ID}\n{participant_id}".encode("utf-8")).hexdigest()
        assignments[participant_id] = {
            "participant_id": participant_id,
            "role": slot["role"],
            "assignment_id": f"{PACKAGE_ID}-{participant_id}",
            "assignment_version": "0.1.0",
            "seed": seed,
            "items": build_schedule_10x6(package, seed),
        }
    package["assignments"] = assignments

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "retest_package_10x6_v01.json"
    payload = json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True)
    out_path.write_text(payload, encoding="utf-8")
    manifest_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    manifest = {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "question_definitions_version": QUESTION_DEFINITIONS_VERSION,
        "wording_version": "0.2.1",
        "file": out_path.name,
        "sha256": manifest_sha,
        "participant_slots": [dict(s) for s in PARTICIPANT_SLOTS],
        "items_per_participant": 6,
        "status": "PREPARED_NOT_LAUNCHED",
        "windows": windows,
    }
    (args.output_dir / "retest_package_manifest_10x6_v01.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "package_id": PACKAGE_ID,
        "planned_slots": [s["participant_id"] for s in PLANNED_SLOTS],
        "reserve_slots": [s["participant_id"] for s in RESERVE_SLOTS],
        "items_per_participant": {pid: len(a["items"]) for pid, a in assignments.items()},
        "manifest_sha256": manifest_sha,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
