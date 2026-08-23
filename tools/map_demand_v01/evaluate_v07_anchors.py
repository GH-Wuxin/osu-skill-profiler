"""Recompute active BID review groups with V0.7 and print human-anchor errors."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .bid_review_ui_v01 import BidReviewWorkbench


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    responses_path = root / "training/datasets/map_demand_bid_review_v01/human_responses.jsonl"
    records = [
        json.loads(line)
        for line in responses_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    superseded = {
        record["supersedes_response_id"]
        for record in records
        if record.get("supersedes_response_id")
    }
    active = [record for record in records if record["response_id"] not in superseded]
    groups: dict[tuple[int, tuple[str, ...]], list[dict]] = defaultdict(list)
    for record in active:
        key = (
            int(record["beatmap"]["beatmap_id"]),
            tuple(record.get("mod_context", {}).get("requested_mods", [])),
        )
        groups[key].append(record)

    workbench = BidReviewWorkbench(
        manifest_path=root / "training/datasets/std_manifest.json",
        songs_root=Path("G:/osu! 20210821/Songs"),
        calibration_path=root
        / "training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k",
        responses_path=responses_path,
        reviewer_id="v07-anchor-eval",
    )
    errors: dict[str, list[float]] = defaultdict(list)
    for (bid, mods), responses in sorted(groups.items()):
        analysis = workbench.analyze_bid(bid, list(mods))
        latest = responses[-1]
        title = latest["beatmap"]["title"]
        comparisons: list[str] = []
        for axis, rating in latest["ratings"].items():
            if rating["qualifier"] == "SKIP":
                continue
            human = float(rating["value"])
            predicted = float(analysis["axes"][axis]["stars"])
            gap = predicted - human
            # AT_LEAST is a one-sided bound: values above it are not errors.
            error = min(0.0, gap) if rating["qualifier"] == "AT_LEAST" else gap
            errors[axis].append(error)
            comparisons.append(f"{axis}={predicted:.2f}/{rating['qualifier']}:{human:g}({gap:+.2f})")
        endurance = analysis["axes"].get("endurance", {}).get("stars")
        if endurance is not None:
            comparisons.append(f"endurance={float(endurance):.2f}/UNRATED")
        if comparisons:
            print(f"{bid} {''.join(mods) or 'NM'} {title}: " + "; ".join(comparisons))
    print("\nAGGREGATE predicted-human (AT_LEAST one-sided):")
    for axis, values in errors.items():
        mae = sum(abs(value) for value in values) / len(values)
        mean = sum(values) / len(values)
        print(f"{axis}: n={len(values)} mean={mean:+.2f} mae={mae:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
